from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144
import run_btcusdc_v161_day_sofar_count_boost as v161
import run_btcusdc_v162_long_trend_follow_boost as v162


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v164_v162_robustness_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V164_BTCUSDC_V162_ROBUSTNESS_AUDIT.md"
V161_ACCOUNT_PATH = ROOT / "runs" / "research_v161_day_sofar_count_boost" / "v161_selected_account_path.csv"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
EXTRA_COST_BPS = (0.0, 2.0, 4.0, 8.0, 16.0)
REQUIRED_EXTRA_COST_BPS = 4.0
THRESHOLD_OFFSETS_BPS = (-100.0, -50.0, 0.0, 50.0, 100.0)
MODIFIERS = (1.05, 1.10, 1.15)
V162_THRESHOLD = -29.0642030867616
V162_MODIFIER = 1.10


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _period_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }


def _metric_row(
    frame: pd.DataFrame,
    *,
    scenario_type: str,
    scenario_value: float,
    return_col: str,
    pnl_col: str,
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    masks = _period_masks(frame)
    row: dict[str, object] = {
        "scenario_type": scenario_type,
        "scenario_value": float(scenario_value),
        "trade_count": int(len(frame)),
    }
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            f"v164_{scenario_type}_{period}",
            frame.loc[mask].copy(),
            return_col=return_col,
            pnl_col=pnl_col,
            baseline_months=baseline_months[period],
        )
        row[f"{period}_return_pct"] = metrics["total_account_return_pct"]
        row[f"{period}_max_drawdown_pct"] = metrics["max_drawdown_pct"]
        row[f"{period}_worst_month_pct"] = metrics["worst_month_pct"]
        row[f"{period}_positive_months"] = metrics["positive_months"]
        row[f"{period}_month_count"] = metrics["month_count"]
        row[f"{period}_win_rate"] = metrics["win_rate"]
    row["passed_scenario"] = _scenario_passed(row)
    return row


def _scenario_passed(row: dict[str, object]) -> bool:
    return (
        float(row["full_return_pct"]) > 0.0
        and int(row["full_positive_months"]) == int(row["full_month_count"])
        and float(row["holdout_return_pct"]) > 0.0
        and int(row["holdout_positive_months"]) == int(row["holdout_month_count"])
    )


def _baseline_months(frame: pd.DataFrame) -> dict[str, pd.Index]:
    masks = _period_masks(frame)
    return {period: v144.v143._month_index(frame.loc[mask].copy()) for period, mask in masks.items()}


def _apply_extra_execution_cost(frame: pd.DataFrame, *, extra_cost_bps: float) -> pd.DataFrame:
    out = frame.copy()
    leverage = pd.to_numeric(out.get("account_leverage", 1.0), errors="coerce").fillna(1.0)
    position_weight = pd.to_numeric(out.get("position_weight", 1.0), errors="coerce").fillna(1.0)
    extra_account_bps = float(extra_cost_bps) * leverage * position_weight
    out["v164_extra_cost_bps"] = float(extra_cost_bps)
    out["v164_extra_cost_account_bps"] = extra_account_bps
    out["v164_account_pnl_bps"] = pd.to_numeric(out["v162_account_pnl_bps"], errors="coerce").fillna(0.0) - extra_account_bps
    out["v164_account_return_pct"] = out["v164_account_pnl_bps"] / 100.0
    return out


def _apply_v162_overlay_from_v161(frame: pd.DataFrame, *, threshold: float, modifier: float) -> pd.DataFrame:
    out = frame.copy()
    values = pd.to_numeric(out["trend_follow_1440_bps"], errors="coerce")
    flag = out["side"].eq("long") & (values >= float(threshold))
    multiplier = pd.Series(1.0, index=out.index)
    multiplier.loc[flag] = float(modifier)
    out["v164_v162_replay_flag"] = flag
    out["v164_v162_replay_modifier"] = multiplier
    out["v164_account_return_pct"] = pd.to_numeric(out["v161_account_return_pct"], errors="coerce").fillna(0.0) * multiplier
    out["v164_account_pnl_bps"] = pd.to_numeric(out["v161_account_pnl_bps"], errors="coerce").fillna(0.0) * multiplier
    return out


def _cost_sensitivity(frame: pd.DataFrame, baseline_months: dict[str, pd.Index]) -> pd.DataFrame:
    rows = []
    for extra_cost in EXTRA_COST_BPS:
        stressed = _apply_extra_execution_cost(frame, extra_cost_bps=float(extra_cost))
        rows.append(
            _metric_row(
                stressed,
                scenario_type="extra_cost_bps",
                scenario_value=float(extra_cost),
                return_col="v164_account_return_pct",
                pnl_col="v164_account_pnl_bps",
                baseline_months=baseline_months,
            )
        )
    return pd.DataFrame(rows)


def _threshold_sensitivity(frame: pd.DataFrame, baseline_months: dict[str, pd.Index]) -> pd.DataFrame:
    rows = []
    for offset in THRESHOLD_OFFSETS_BPS:
        threshold = V162_THRESHOLD + float(offset)
        replay = _apply_v162_overlay_from_v161(frame, threshold=threshold, modifier=V162_MODIFIER)
        row = _metric_row(
            replay,
            scenario_type="threshold_offset_bps",
            scenario_value=float(offset),
            return_col="v164_account_return_pct",
            pnl_col="v164_account_pnl_bps",
            baseline_months=baseline_months,
        )
        row["threshold"] = threshold
        row["flag_trade_count"] = int(replay["v164_v162_replay_flag"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def _modifier_sensitivity(frame: pd.DataFrame, baseline_months: dict[str, pd.Index]) -> pd.DataFrame:
    rows = []
    for modifier in MODIFIERS:
        replay = _apply_v162_overlay_from_v161(frame, threshold=V162_THRESHOLD, modifier=float(modifier))
        row = _metric_row(
            replay,
            scenario_type="modifier",
            scenario_value=float(modifier),
            return_col="v164_account_return_pct",
            pnl_col="v164_account_pnl_bps",
            baseline_months=baseline_months,
        )
        row["threshold"] = V162_THRESHOLD
        row["flag_trade_count"] = int(replay["v164_v162_replay_flag"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def _decision(cost_table: pd.DataFrame, threshold_table: pd.DataFrame, modifier_table: pd.DataFrame) -> dict[str, object]:
    required_cost = cost_table.loc[pd.to_numeric(cost_table["scenario_value"], errors="coerce") <= REQUIRED_EXTRA_COST_BPS]
    threshold_pass_count = int(threshold_table["passed_scenario"].astype(bool).sum()) if not threshold_table.empty else 0
    modifier_pass_count = int(modifier_table["passed_scenario"].astype(bool).sum()) if not modifier_table.empty else 0
    required_cost_passed = bool(not required_cost.empty and required_cost["passed_scenario"].astype(bool).all())
    base_threshold = threshold_table.loc[pd.to_numeric(threshold_table["scenario_value"], errors="coerce") == 0.0]
    base_modifier = modifier_table.loc[pd.to_numeric(modifier_table["scenario_value"], errors="coerce") == V162_MODIFIER]
    base_replay_passed = bool(
        not base_threshold.empty
        and bool(base_threshold.iloc[0]["passed_scenario"])
        and not base_modifier.empty
        and bool(base_modifier.iloc[0]["passed_scenario"])
    )
    passed = bool(required_cost_passed and base_replay_passed)
    return {
        "status": "v162_robustness_passed" if passed else "v162_robustness_warning",
        "promote_to_live": False,
        "message": (
            "V162 passed the required extra-cost robustness checks and replayed base overlay checks."
            if passed
            else "V162 did not pass every required robustness check; keep it as research-only."
        ),
        "required_extra_cost_bps": REQUIRED_EXTRA_COST_BPS,
        "required_extra_cost_passed": required_cost_passed,
        "base_replay_passed": base_replay_passed,
        "threshold_scenario_count": int(len(threshold_table)),
        "threshold_pass_count": threshold_pass_count,
        "modifier_scenario_count": int(len(modifier_table)),
        "modifier_pass_count": modifier_pass_count,
    }


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    cost_table: pd.DataFrame,
    threshold_table: pd.DataFrame,
    modifier_table: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V164 BTCUSDC V162 Robustness Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Message: {decision['message']}",
        f"- Required extra-cost max: `{REQUIRED_EXTRA_COST_BPS}` bps",
        f"- Required extra-cost passed: `{decision['required_extra_cost_passed']}`",
        f"- Base overlay replay passed: `{decision['base_replay_passed']}`",
        "",
        "## Audit Rules",
        "",
        "- Base robustness path: V162 selected account path.",
        "- Extra cost is added on top of V162 as `extra_cost_bps * account_leverage * position_weight` account bps per trade.",
        "- Threshold sensitivity replays the V162 long trend-follow overlay from V161 with threshold offsets.",
        "- Modifier sensitivity replays the V162 overlay from V161 with nearby sizing values.",
        "- This audit does not add trades, change sides, or promote a live-trading system.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## Extra Cost Sensitivity",
        "",
        cost_table.to_csv(index=False).strip(),
        "",
        "## Threshold Sensitivity",
        "",
        threshold_table.to_csv(index=False).strip(),
        "",
        "## Modifier Sensitivity",
        "",
        modifier_table.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V164 audits whether the promoted research candidate is fragile to realistic execution headwinds and small parameter movement. It is a robustness report, not a new return-improving strategy.",
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V162_ACCOUNT_PATH.exists():
        v162.run()
    if not V161_ACCOUNT_PATH.exists():
        v161.run()
    v162_frame = pd.read_csv(V162_ACCOUNT_PATH)
    v162_frame["timestamp"] = _to_utc(v162_frame["timestamp"])
    for column in ("v162_account_return_pct", "v162_account_pnl_bps"):
        v162_frame[column] = pd.to_numeric(v162_frame[column], errors="coerce").fillna(0.0)
    v161_frame = pd.read_csv(V161_ACCOUNT_PATH)
    v161_frame["timestamp"] = _to_utc(v161_frame["timestamp"])
    for column in ("v161_account_return_pct", "v161_account_pnl_bps"):
        v161_frame[column] = pd.to_numeric(v161_frame[column], errors="coerce").fillna(0.0)

    months = _baseline_months(v162_frame)
    baseline = _metric_row(
        v162_frame,
        scenario_type="baseline_v162",
        scenario_value=0.0,
        return_col="v162_account_return_pct",
        pnl_col="v162_account_pnl_bps",
        baseline_months=months,
    )
    cost_table = _cost_sensitivity(v162_frame, months)
    threshold_table = _threshold_sensitivity(v161_frame, months)
    modifier_table = _modifier_sensitivity(v161_frame, months)
    decision = _decision(cost_table, threshold_table, modifier_table)
    payload = {
        "config": {
            "base": "v162_long_trend_follow_boost",
            "selector_end": SELECTOR_END.isoformat(),
            "extra_cost_bps": list(EXTRA_COST_BPS),
            "required_extra_cost_bps": REQUIRED_EXTRA_COST_BPS,
            "threshold_offsets_bps": list(THRESHOLD_OFFSETS_BPS),
            "modifiers": list(MODIFIERS),
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "promotes_live_trading": False,
        },
        "baseline": baseline,
        "decision": decision,
    }
    cost_table.to_csv(OUT_DIR / "v164_extra_cost_sensitivity.csv", index=False)
    threshold_table.to_csv(OUT_DIR / "v164_threshold_sensitivity.csv", index=False)
    modifier_table.to_csv(OUT_DIR / "v164_modifier_sensitivity.csv", index=False)
    (OUT_DIR / "v164_v162_robustness_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, pd.DataFrame([baseline]), cost_table, threshold_table, modifier_table)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
