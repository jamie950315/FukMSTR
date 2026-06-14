from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94


OUT_DIR = ROOT / "runs" / "research_v114_btcusdc_v112_guard_sweep"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V114_BTCUSDC_V112_GUARD_SWEEP_RESULTS.md"
V113_LEDGER = ROOT / "runs" / "research_v113_btcusdc_v112_earliest_walk_forward" / "v113_v112_earliest_walk_forward_trade_ledger.csv"

TARGET_MONTH = "2026-04"
MAX_OTHER_MONTH_DEGRADATION = 0.05
FEE_BPS = 8.5


def _pretrade_feature_frame(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.copy().sort_values("timestamp").reset_index(drop=True)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    open_px = pd.to_numeric(frame["open"], errors="coerce")
    prior_close = pd.to_numeric(frame["close"], errors="coerce").shift(1)
    prior_high = pd.to_numeric(frame["high"], errors="coerce").shift(1)
    prior_low = pd.to_numeric(frame["low"], errors="coerce").shift(1)

    out = frame[["timestamp"]].copy()
    for window in (30, 60, 120, 240, 720, 1440):
        window = int(window)
        rolling_high = prior_high.rolling(window, min_periods=window).max()
        rolling_low = prior_low.rolling(window, min_periods=window).min()
        out[f"prior_ret_{window}_bps"] = (open_px / prior_close.shift(window) - 1.0) * 10000.0
        out[f"prior_range_{window}_bps"] = (rolling_high / rolling_low - 1.0) * 10000.0
        out[f"prior_range_pos_{window}"] = (open_px - rolling_low) / (rolling_high - rolling_low).replace(0.0, pd.NA)
    return out


def _ledger_with_features() -> pd.DataFrame:
    ledger = pd.read_csv(V113_LEDGER)
    ledger["timestamp"] = pd.to_datetime(ledger["timestamp"], utc=True)
    ledger["month"] = ledger["timestamp"].dt.strftime("%Y-%m")
    ledger["hour"] = ledger["timestamp"].dt.hour
    bars = v94._full_bars()
    features = _pretrade_feature_frame(bars)
    return ledger.merge(features, on="timestamp", how="left")


def _monthly_pnl(frame: pd.DataFrame, months: pd.Index | None = None) -> pd.Series:
    monthly = frame.groupby("month", sort=True)["net_pnl_bps"].sum()
    if months is not None:
        monthly = monthly.reindex(months, fill_value=0.0)
    return monthly


def _candidate_summary(name: str, frame: pd.DataFrame, keep_mask: pd.Series, baseline_monthly: pd.Series) -> dict[str, object]:
    kept = frame.loc[keep_mask].copy()
    monthly = _monthly_pnl(kept, baseline_monthly.index)
    other_months = [month for month in baseline_monthly.index if month != TARGET_MONTH]
    floors = baseline_monthly.loc[other_months] * (1.0 - MAX_OTHER_MONTH_DEGRADATION)
    month_deltas = monthly.loc[other_months] - baseline_monthly.loc[other_months]
    passed_other_months = bool((monthly.loc[other_months] >= floors).all())
    target_improvement_bps = float(monthly.loc[TARGET_MONTH] - baseline_monthly.loc[TARGET_MONTH])
    target_improved = bool(monthly.loc[TARGET_MONTH] > baseline_monthly.loc[TARGET_MONTH])
    failed_months = monthly.loc[other_months][monthly.loc[other_months] < floors]
    return {
        "candidate": name,
        "trade_count": int(len(kept)),
        "skipped_trade_count": int((~keep_mask).sum()),
        "total_net_pnl_bps": float(monthly.sum()),
        "target_month_net_pnl_bps": float(monthly.loc[TARGET_MONTH]),
        "target_month_improvement_bps": target_improvement_bps,
        "target_month_improved": target_improved,
        "other_month_guard_passed": passed_other_months,
        "selected_gate_passed": bool(target_improved and passed_other_months),
        "worst_other_month_delta_bps": float(month_deltas.min()),
        "worst_other_month_degradation_rate": float((month_deltas / baseline_monthly.loc[other_months]).min()),
        "failed_other_months": ";".join(failed_months.index.astype(str).tolist()),
    }


def _candidate_masks(frame: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    candidates: list[tuple[str, pd.Series]] = []
    all_keep = pd.Series(True, index=frame.index)
    candidates.append(("baseline_no_guard", all_keep))

    for floor in (0.43, 0.45, 0.48, 0.50, 0.52, 0.55):
        candidates.append((f"global_confidence_floor_{floor:.2f}", frame["direction_probability"] >= floor))
        candidates.append(
            (
                f"short_confidence_floor_{floor:.2f}",
                ~((frame["signal"] == -1) & (frame["direction_probability"] < floor)),
            )
        )

    for window in (30, 60, 120, 240, 720, 1440):
        for threshold in (25, 50, 75, 100, 150, 200, 300, 400):
            candidates.append(
                (
                    f"short_uptrend_veto_ret{window}_gt_{threshold}",
                    ~((frame["signal"] == -1) & (frame[f"prior_ret_{window}_bps"] > float(threshold))),
                )
            )

    for window in (120, 240, 720, 1440):
        for threshold in (25, 50, 75, 100, 150, 200):
            for position in (0.60, 0.70, 0.80, 0.90):
                candidates.append(
                    (
                        f"short_uptrend_veto_ret{window}_gt_{threshold}_pos{position:.2f}",
                        ~(
                            (frame["signal"] == -1)
                            & (frame[f"prior_ret_{window}_bps"] > float(threshold))
                            & (frame[f"prior_range_pos_{window}"] > float(position))
                        ),
                    )
                )

    for window in (60, 120, 240, 720):
        for threshold in (200, 300, 400, 500, 700, 1000):
            candidates.append(
                (
                    f"tail_range_guard_range{window}_gt_{threshold}",
                    ~(frame[f"prior_range_{window}_bps"] > float(threshold)),
                )
            )
            candidates.append(
                (
                    f"short_tail_range_guard_range{window}_gt_{threshold}",
                    ~((frame["signal"] == -1) & (frame[f"prior_range_{window}_bps"] > float(threshold))),
                )
            )

    for hours in ((22,), (12,), (23,), (13,), (12, 13), (22, 23), (12, 13, 22, 23)):
        label = "_".join(str(hour) for hour in hours)
        candidates.append((f"short_hour_veto_{label}", ~((frame["signal"] == -1) & frame["hour"].isin(hours))))

    return candidates


def _month_table(candidate_frame: pd.DataFrame, baseline_monthly: pd.Series) -> pd.DataFrame:
    monthly = _monthly_pnl(candidate_frame, baseline_monthly.index)
    table = pd.DataFrame(
        {
            "month": baseline_monthly.index,
            "baseline_net_pnl_bps": baseline_monthly.to_numpy(float),
            "guarded_net_pnl_bps": monthly.to_numpy(float),
        }
    )
    table["delta_bps"] = table["guarded_net_pnl_bps"] - table["baseline_net_pnl_bps"]
    table["degradation_rate"] = table["delta_bps"] / table["baseline_net_pnl_bps"]
    table.loc[table["month"] == TARGET_MONTH, "degradation_rate"] = pd.NA
    return table


def _write_report(payload: dict[str, object], candidates: pd.DataFrame, month_table: pd.DataFrame) -> None:
    selected = payload["decision"]["selected_candidate"]
    top_cols = [
        "candidate",
        "selected_gate_passed",
        "trade_count",
        "skipped_trade_count",
        "total_net_pnl_bps",
        "target_month_net_pnl_bps",
        "target_month_improvement_bps",
        "worst_other_month_degradation_rate",
        "failed_other_months",
    ]
    passing = candidates.loc[candidates["selected_gate_passed"]].copy()
    lines = [
        "# Research V114 BTCUSDC V112 Guard Sweep Results",
        "",
        "## Decision",
        "",
        f"- Target month: `{TARGET_MONTH}`",
        f"- Other-month max allowed degradation: `{MAX_OTHER_MONTH_DEGRADATION:.2%}`",
        f"- Candidate count: `{len(candidates)}`",
        f"- Passing candidate count: `{int(candidates['selected_gate_passed'].sum())}`",
        f"- Selected candidate: `{selected}`",
        f"- Baseline target month PnL: `{payload['baseline']['target_month_net_pnl_bps']:.6f}` bps",
        f"- Selected target month PnL: `{payload['selected']['target_month_net_pnl_bps']:.6f}` bps",
        f"- Selected total PnL: `{payload['selected']['total_net_pnl_bps']:.6f}` bps",
        f"- Selected skipped trades: `{payload['selected']['skipped_trade_count']}`",
        f"- Worst other-month degradation: `{payload['selected']['worst_other_month_degradation_rate']:.6f}`",
        "",
        "## Selected Month Table",
        "",
        month_table.to_csv(index=False).strip(),
        "",
        "## Passing Candidates",
        "",
        passing[top_cols].to_csv(index=False).strip() if not passing.empty else "No guard passed the month degradation constraint.",
        "",
        "## Top Candidates By Target Month",
        "",
        candidates.sort_values("target_month_net_pnl_bps", ascending=False).head(24)[top_cols].to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V114 tests pretrade guards on the locked V112 walk-forward ledger. The selected guard is a short-only uptrend veto: skip short trades when the prior 30-minute return exceeds 150 bps. It improves 2026-04 while keeping every other month within the 5% degradation limit. This remains a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame = _ledger_with_features()
    baseline_monthly = _monthly_pnl(frame)
    rows = []
    masks = {}
    for name, keep in _candidate_masks(frame):
        keep = keep.fillna(True).astype(bool)
        masks[name] = keep
        rows.append(_candidate_summary(name, frame, keep, baseline_monthly))
    candidates = pd.DataFrame(rows).sort_values(
        ["selected_gate_passed", "target_month_net_pnl_bps", "total_net_pnl_bps"],
        ascending=[False, False, False],
    )
    passing = candidates.loc[candidates["selected_gate_passed"]].copy()
    selected_name = str(passing.iloc[0]["candidate"]) if not passing.empty else None
    selected_keep = masks[selected_name] if selected_name is not None else pd.Series(False, index=frame.index)
    selected_ledger = frame.loc[selected_keep].copy().sort_values("timestamp").reset_index(drop=True)
    selected_ledger["equity_bps"] = pd.to_numeric(selected_ledger["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    skipped = frame.loc[~selected_keep].copy().sort_values("timestamp").reset_index(drop=True)
    selected_summary = candidates.loc[candidates["candidate"] == selected_name].iloc[0].to_dict() if selected_name else {}
    month_table = _month_table(selected_ledger, baseline_monthly) if selected_name else pd.DataFrame()

    candidates_path = OUT_DIR / "v114_guard_candidates.csv"
    selected_path = OUT_DIR / "v114_selected_guard_trade_ledger.csv"
    skipped_path = OUT_DIR / "v114_selected_guard_skipped_trades.csv"
    month_path = OUT_DIR / "v114_selected_guard_months.csv"
    candidates.to_csv(candidates_path, index=False)
    selected_ledger.to_csv(selected_path, index=False)
    skipped.to_csv(skipped_path, index=False)
    month_table.to_csv(month_path, index=False)

    payload = {
        "version": "v114_btcusdc_v112_guard_sweep",
        "target_month": TARGET_MONTH,
        "max_other_month_degradation": MAX_OTHER_MONTH_DEGRADATION,
        "baseline": {
            "trade_count": int(len(frame)),
            "total_net_pnl_bps": float(baseline_monthly.sum()),
            "target_month_net_pnl_bps": float(baseline_monthly.loc[TARGET_MONTH]),
        },
        "decision": {
            "candidate_count": int(len(candidates)),
            "passing_candidate_count": int(len(passing)),
            "selected_candidate": selected_name,
            "goal_satisfied": bool(selected_name is not None),
        },
        "selected": selected_summary,
        "outputs": {
            "summary_json": str(OUT_DIR / "v114_summary.json"),
            "candidates": str(candidates_path),
            "selected_trade_ledger": str(selected_path),
            "selected_skipped_trades": str(skipped_path),
            "selected_months": str(month_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v114_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, candidates, month_table)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
