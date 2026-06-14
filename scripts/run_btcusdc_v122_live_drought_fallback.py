from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v122_btcusdc_live_drought_fallback"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V122_BTCUSDC_LIVE_DROUGHT_FALLBACK.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V121_PREDICTIONS = (
    ROOT
    / "runs"
    / "research_v121_btcusdc_live_native_entry_model"
    / "v121_live_native_entry_model_predictions.csv"
)

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24


PRIMARY_CONFIGS = [
    {"prob_col": "prob_good_10", "edge": 20.0, "prob": 0.55, "prior_max": 300.0},
    {"prob_col": "prob_good_20", "edge": 20.0, "prob": 0.50, "prior_max": 100.0},
]


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _timestamp_ns(timestamps: pd.Series | np.ndarray) -> np.ndarray:
    if isinstance(timestamps, np.ndarray) and np.issubdtype(timestamps.dtype, np.integer):
        return timestamps.astype("int64", copy=False)
    return pd.to_datetime(timestamps, utc=True).to_numpy(dtype="datetime64[ns]").astype("int64")


def _bool_mask(values: pd.Series | np.ndarray) -> np.ndarray:
    return values.fillna(False).to_numpy(bool) if isinstance(values, pd.Series) else np.asarray(values, dtype=bool)


def _live_drought_fallback_indices(
    timestamps: pd.Series | np.ndarray,
    primary_eligible: pd.Series | np.ndarray,
    fallback_eligible: pd.Series | np.ndarray,
    *,
    cooldown_minutes: int,
    drought_days: int,
) -> list[int]:
    ts_ns = _timestamp_ns(timestamps)
    primary = _bool_mask(primary_eligible)
    fallback = _bool_mask(fallback_eligible)
    event = primary | fallback
    cooldown_ns = pd.Timedelta(minutes=int(cooldown_minutes)).value
    drought_ns = pd.Timedelta(days=int(drought_days)).value
    out: list[int] = []
    next_allowed: int | None = None
    last_trade: int | None = None
    for idx in np.flatnonzero(event):
        current = int(ts_ns[idx])
        if next_allowed is not None and current < next_allowed:
            continue
        should_enter = bool(primary[idx])
        if not should_enter and bool(fallback[idx]):
            should_enter = last_trade is None or current - last_trade >= drought_ns
        if should_enter:
            out.append(int(idx))
            last_trade = current
            next_allowed = current + cooldown_ns
    return out


def _max_drawdown_bps(pnl: pd.Series) -> float:
    equity = pd.to_numeric(pnl, errors="coerce").fillna(0.0).cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max()) if len(drawdown) else 0.0


def _load_predictions() -> pd.DataFrame:
    frame = pd.read_csv(V121_PREDICTIONS)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
    numeric_cols = [
        "net_pnl_bps",
        "aligned_prior_ret_720_bps",
        "pred_edge_bps",
        "prob_good_0",
        "prob_good_10",
        "prob_good_20",
    ]
    for col in numeric_cols:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["pred_edge_bps", "prob_good_0", "prob_good_10", "prob_good_20"]).reset_index(drop=True)


def _condition(
    frame: pd.DataFrame,
    *,
    prob_col: str,
    edge_threshold: float,
    probability_threshold: float,
    prior_max: float | None,
) -> np.ndarray:
    edge_ok = frame["pred_edge_bps"].to_numpy(float) >= float(edge_threshold)
    prob_ok = frame[prob_col].to_numpy(float) >= float(probability_threshold)
    if prior_max is None:
        prior_ok = np.ones(len(frame), dtype=bool)
    else:
        prior_ok = frame["aligned_prior_ret_720_bps"].to_numpy(float) <= float(prior_max)
    return edge_ok & prob_ok & prior_ok


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


def _scan_drought_fallback(frame: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    ts_ns = _timestamp_ns(frame["timestamp"])
    fallback_prob_cols = ("prob_good_20", "prob_good_10")
    edge_thresholds = (-10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0)
    probability_thresholds = (0.40, 0.45, 0.50)
    prior_maxes: tuple[float | None, ...] = (None, 300.0, 100.0, -300.0)
    drought_days_grid = (7, 14, 30, 60)
    cooldowns = (30, 60, 120)
    for primary_cfg in PRIMARY_CONFIGS:
        primary = _condition(
            frame,
            prob_col=str(primary_cfg["prob_col"]),
            edge_threshold=float(primary_cfg["edge"]),
            probability_threshold=float(primary_cfg["prob"]),
            prior_max=float(primary_cfg["prior_max"]) if primary_cfg["prior_max"] is not None else None,
        )
        primary_label = (
            f"main_{primary_cfg['prob_col']}_edge{primary_cfg['edge']:g}"
            f"_prob{primary_cfg['prob']:g}_amax{primary_cfg['prior_max']:g}"
        )
        for fallback_prob_col in fallback_prob_cols:
            for edge_threshold in edge_thresholds:
                for probability_threshold in probability_thresholds:
                    for prior_max in prior_maxes:
                        fallback = _condition(
                            frame,
                            prob_col=fallback_prob_col,
                            edge_threshold=edge_threshold,
                            probability_threshold=probability_threshold,
                            prior_max=prior_max,
                        )
                        if int((primary | fallback).sum()) == 0:
                            continue
                        for drought_days in drought_days_grid:
                            for cooldown in cooldowns:
                                keep = _live_drought_fallback_indices(
                                    ts_ns,
                                    primary,
                                    fallback,
                                    cooldown_minutes=cooldown,
                                    drought_days=drought_days,
                                )
                                if not keep:
                                    continue
                                trades = frame.iloc[keep][["timestamp", "month", "net_pnl_bps"]].copy()
                                prior_label = "none" if prior_max is None else f"{prior_max:g}"
                                policy = (
                                    f"{primary_label}__fallback_{fallback_prob_col}"
                                    f"_edge{edge_threshold:g}_prob{probability_threshold:g}"
                                    f"_amax{prior_label}_drought{drought_days}_cool{cooldown}"
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
        "month_count",
        "worst_month_bps",
        "worst_month",
    ]
    passed = results.loc[results["live_similarity_passed"], cols] if not results.empty else pd.DataFrame(columns=cols)
    top = results[cols].head(30) if not results.empty else pd.DataFrame(columns=cols)
    lines = [
        "# Research V122 BTCUSDC Live Drought Fallback",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Prediction rows: `{payload['data']['prediction_rows']}`",
        f"- Explored policy count: `{payload['decision']['explored_policy_count']}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Best policy: `{payload['decision']['best_policy']}`",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V122 policy met the live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V122 policies were available.",
        "",
        "## Interpretation",
        "",
        "V122 keeps V121's live-native model predictions fixed and tests a real-time drought fallback. The primary rule can enter whenever it is eligible. The fallback rule can enter only after a configurable number of days without any trade, and all entries still obey a position cooldown. It does not use day-end ranking or a daily trade cap.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    frame = _load_predictions()
    results = _scan_drought_fallback(frame, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    payload = {
        "version": "v122_btcusdc_live_drought_fallback",
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
            "predictions": str(V121_PREDICTIONS),
            "prediction_rows": int(len(frame)),
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v122_live_drought_fallback_summary.json"),
            "results": str(OUT_DIR / "v122_live_drought_fallback_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    if not results.empty:
        results.to_csv(OUT_DIR / "v122_live_drought_fallback_results.csv", index=False)
    (OUT_DIR / "v122_live_drought_fallback_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
