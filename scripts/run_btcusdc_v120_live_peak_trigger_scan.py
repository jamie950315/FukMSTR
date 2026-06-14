from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v120_btcusdc_live_peak_trigger_scan"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V120_BTCUSDC_LIVE_PEAK_TRIGGER_SCAN.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V119_FEATURES = ROOT / "runs" / "research_v119_btcusdc_live_entry_model" / "v119_live_feature_frame.csv"

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24
BASE_HORIZON_MINUTES = 30


def _max_drawdown_bps(pnl: pd.Series) -> float:
    equity = pd.to_numeric(pnl, errors="coerce").fillna(0.0).cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max()) if len(drawdown) else 0.0


def _live_non_overlapping_indices(
    timestamps: pd.Series | np.ndarray,
    eligible: pd.Series | np.ndarray,
    *,
    horizon_minutes: int,
) -> list[int]:
    spacing_ns = pd.Timedelta(minutes=int(horizon_minutes)).value
    out: list[int] = []
    next_allowed: int | None = None
    if isinstance(timestamps, np.ndarray) and np.issubdtype(timestamps.dtype, np.integer):
        ts_ns = timestamps.astype("int64", copy=False)
    else:
        ts_ns = pd.to_datetime(timestamps, utc=True).to_numpy(dtype="datetime64[ns]").astype("int64")
    eligible_mask = eligible.fillna(False).to_numpy(bool) if isinstance(eligible, pd.Series) else np.asarray(eligible, dtype=bool)
    for idx in np.flatnonzero(eligible_mask):
        current = int(ts_ns[idx])
        if next_allowed is None or current >= next_allowed:
            out.append(int(idx))
            next_allowed = current + spacing_ns
    return out


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _summarize_policy(policy: str, trades: pd.DataFrame, *, v115_total: float) -> dict[str, object]:
    if trades.empty:
        return {
            "policy": policy,
            "trade_count": 0,
            "avg_trades_per_day": 0.0,
            "total_net_pnl_bps": 0.0,
            "vs_v115_rate": 0.0,
            "mean_net_pnl_bps": 0.0,
            "win_rate": 0.0,
            "max_drawdown_bps": 0.0,
            "positive_months": 0,
            "month_count": 0,
            "worst_month_bps": 0.0,
            "worst_month": "",
        }
    monthly = trades.groupby("month", sort=True)["net_pnl_bps"].sum()
    days = max(1.0, (trades["timestamp"].max() - trades["timestamp"].min()).total_seconds() / 86400.0)
    total = float(trades["net_pnl_bps"].sum())
    return {
        "policy": policy,
        "trade_count": int(len(trades)),
        "avg_trades_per_day": float(len(trades) / days),
        "total_net_pnl_bps": total,
        "vs_v115_rate": float(total / v115_total) if v115_total > 0.0 else np.nan,
        "mean_net_pnl_bps": float(trades["net_pnl_bps"].mean()),
        "win_rate": float((trades["net_pnl_bps"] > 0.0).mean()),
        "max_drawdown_bps": _max_drawdown_bps(trades["net_pnl_bps"]),
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_bps": float(monthly.min()),
        "worst_month": str(monthly.idxmin()),
    }


def _prepare_live_frame() -> pd.DataFrame:
    cols = [
        "timestamp",
        "direction_probability",
        "prob_margin",
        "signal",
        "aligned_prior_ret_720_bps",
        "raw_weighted_net_pnl_bps",
    ]
    frame = pd.read_csv(V119_FEATURES, usecols=cols)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame["net_pnl_bps"] = pd.to_numeric(frame["raw_weighted_net_pnl_bps"], errors="coerce").fillna(0.0)
    frame["score"] = pd.to_numeric(frame["direction_probability"], errors="coerce")
    frame["margin"] = pd.to_numeric(frame["prob_margin"], errors="coerce")
    frame["aligned_prior_ret_720_bps"] = pd.to_numeric(frame["aligned_prior_ret_720_bps"], errors="coerce")
    return frame


def _add_live_history_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    bars_per_day = 24 * 12
    for lookback_days in (7, 14, 30, 60, 120):
        window = lookback_days * bars_per_day
        min_periods = max(bars_per_day, window // 3)
        prior_score = out["score"].shift(1)
        for q in (0.90, 0.95, 0.975, 0.99, 0.995):
            out[f"score_q{int(q * 1000):03d}_{lookback_days}d"] = prior_score.rolling(
                window,
                min_periods=min_periods,
            ).quantile(q)
    for peak_bars in (3, 6, 12, 24, 36, 72, 144):
        out[f"prior_peak_{peak_bars}"] = out["score"].shift(1).rolling(peak_bars, min_periods=1).max()
    return out


def _scan_peak_triggers(frame: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    margin_mins = (0.0, 0.02, 0.05, 0.08, 0.10, 0.12)
    prior_ret_maxes: tuple[float | None, ...] = (None, 500.0, 300.0, 100.0, 0.0, -100.0, -300.0)
    cooldowns = (30, 60, 120)
    all_ok = np.ones(len(frame), dtype=bool)
    score = frame["score"].to_numpy(float)
    margin = frame["margin"].to_numpy(float)
    aligned_prior = frame["aligned_prior_ret_720_bps"].to_numpy(float)
    timestamp_ns = frame["timestamp"].to_numpy(dtype="datetime64[ns]").astype("int64")
    for lookback_days in (7, 14, 30, 60, 120):
        for q in (0.90, 0.95, 0.975, 0.99, 0.995):
            q_col = f"score_q{int(q * 1000):03d}_{lookback_days}d"
            base = score >= frame[q_col].to_numpy(float)
            for peak_bars in (3, 6, 12, 24, 36, 72, 144):
                peak_col = f"prior_peak_{peak_bars}"
                is_new_peak = score > frame[peak_col].to_numpy(float)
                for margin_min in margin_mins:
                    margin_ok = margin >= margin_min
                    for prior_ret_max in prior_ret_maxes:
                        prior_ok = all_ok if prior_ret_max is None else aligned_prior <= prior_ret_max
                        eligible = base & is_new_peak & margin_ok & prior_ok
                        if int(eligible.sum()) == 0:
                            continue
                        for cooldown in cooldowns:
                            keep = _live_non_overlapping_indices(
                                timestamp_ns,
                                eligible,
                                horizon_minutes=cooldown,
                            )
                            if not keep:
                                continue
                            trades = frame.loc[keep, ["timestamp", "month", "net_pnl_bps"]].copy()
                            prior_label = "none" if prior_ret_max is None else f"{prior_ret_max:g}"
                            policy = (
                                f"peak_lb{lookback_days}d_q{q:g}_past{peak_bars}"
                                f"_margin{margin_min:g}_amax{prior_label}_cool{cooldown}"
                            )
                            rows.append(_summarize_policy(policy, trades, v115_total=v115_total))
    results = pd.DataFrame(rows)
    if results.empty:
        return results
    results["live_similarity_passed"] = results.apply(lambda row: _passes_live_similarity_gate(row.to_dict()), axis=1)
    return results.sort_values(
        ["live_similarity_passed", "total_net_pnl_bps", "positive_months", "win_rate"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def _write_report(payload: dict[str, object], results: pd.DataFrame) -> None:
    cols = [
        "policy",
        "live_similarity_passed",
        "trade_count",
        "avg_trades_per_day",
        "total_net_pnl_bps",
        "vs_v115_rate",
        "mean_net_pnl_bps",
        "win_rate",
        "max_drawdown_bps",
        "positive_months",
        "worst_month_bps",
        "worst_month",
    ]
    passed = results.loc[results["live_similarity_passed"], cols] if not results.empty else pd.DataFrame(columns=cols)
    top = results[cols].head(30) if not results.empty else pd.DataFrame(columns=cols)
    lines = [
        "# Research V120 BTCUSDC Live Peak Trigger Scan",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Explored policy count: `{payload['decision']['explored_policy_count']}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Best policy: `{payload['decision']['best_policy']}`",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V120 policy met the live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V120 policies were available.",
        "",
        "## Interpretation",
        "",
        "V120 tests whether V115's daily top-9 effect can be approximated by live score peaks. Every rule uses only prior score history, a current margin check, an optional prior-trend guard, and a position cooldown. It does not use a daily trade cap and does not wait for the day to finish. Passing still requires V115-like PnL and all 24 months positive.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    frame = _add_live_history_columns(_prepare_live_frame())
    results = _scan_peak_triggers(frame, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    payload = {
        "version": "v120_btcusdc_live_peak_trigger_scan",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "decision": {
            "similar_performance_rate": MIN_SIMILAR_PERFORMANCE_RATE,
            "similar_performance_target_bps": v115_total * MIN_SIMILAR_PERFORMANCE_RATE,
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "explored_policy_count": int(len(results)),
            "passing_policy_count": passing_count,
            "best_policy": str(best.get("policy")) if best else None,
            "best_total_net_pnl_bps": float(best.get("total_net_pnl_bps", 0.0)) if best else 0.0,
            "best_vs_v115_rate": float(best.get("vs_v115_rate", 0.0)) if best else 0.0,
            "status": "live_conversion_candidate_found" if passing_count else "live_conversion_not_solved",
        },
        "data": {
            "feature_frame": str(V119_FEATURES),
            "feature_rows": int(len(frame)),
            "base_horizon_minutes": BASE_HORIZON_MINUTES,
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v120_live_peak_trigger_summary.json"),
            "results": str(OUT_DIR / "v120_live_peak_trigger_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    if not results.empty:
        results.to_csv(OUT_DIR / "v120_live_peak_trigger_results.csv", index=False)
    (OUT_DIR / "v120_live_peak_trigger_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
