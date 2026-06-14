from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v124_btcusdc_live_family_ensemble"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V124_BTCUSDC_LIVE_FAMILY_ENSEMBLE.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V119_FEATURES = ROOT / "runs" / "research_v119_btcusdc_live_entry_model" / "v119_live_feature_frame.csv"
V121_PREDICTIONS = (
    ROOT
    / "runs"
    / "research_v121_btcusdc_live_native_entry_model"
    / "v121_live_native_entry_model_predictions.csv"
)

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24


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


def _live_non_overlapping_indices(
    timestamps: pd.Series | np.ndarray,
    eligible: pd.Series | np.ndarray,
    *,
    horizon_minutes: int,
) -> list[int]:
    spacing_ns = pd.Timedelta(minutes=int(horizon_minutes)).value
    out: list[int] = []
    next_allowed: int | None = None
    ts_ns = _timestamp_ns(timestamps)
    eligible_mask = eligible.fillna(False).to_numpy(bool) if isinstance(eligible, pd.Series) else np.asarray(eligible, dtype=bool)
    for idx in np.flatnonzero(eligible_mask):
        current = int(ts_ns[idx])
        if next_allowed is None or current >= next_allowed:
            out.append(int(idx))
            next_allowed = current + spacing_ns
    return out


def _priority_non_overlapping_events(events: pd.DataFrame, *, cooldown_minutes: int) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    frame = events.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values(["timestamp", "priority", "source"], kind="mergesort").reset_index(drop=True)
    spacing = pd.Timedelta(minutes=int(cooldown_minutes))
    selected: list[int] = []
    next_allowed: pd.Timestamp | None = None
    for idx, row in frame.iterrows():
        ts = row["timestamp"]
        if next_allowed is None or ts >= next_allowed:
            selected.append(int(idx))
            next_allowed = ts + spacing
    return frame.loc[selected].reset_index(drop=True)


def _live_drought_fallback_indices(
    timestamps: pd.Series | np.ndarray,
    primary_eligible: pd.Series | np.ndarray,
    fallback_eligible: pd.Series | np.ndarray,
    *,
    cooldown_minutes: int,
    drought_days: int,
) -> list[int]:
    ts_ns = _timestamp_ns(timestamps)
    primary = primary_eligible.fillna(False).to_numpy(bool) if isinstance(primary_eligible, pd.Series) else np.asarray(primary_eligible, dtype=bool)
    fallback = fallback_eligible.fillna(False).to_numpy(bool) if isinstance(fallback_eligible, pd.Series) else np.asarray(fallback_eligible, dtype=bool)
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


def _feature_frame() -> pd.DataFrame:
    cols = [
        "timestamp",
        "fold",
        "direction_probability",
        "prob_margin",
        "aligned_prior_ret_720_bps",
        "raw_weighted_net_pnl_bps",
    ]
    frame = pd.read_csv(V119_FEATURES, usecols=cols)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame["score"] = pd.to_numeric(frame["direction_probability"], errors="coerce")
    frame["margin"] = pd.to_numeric(frame["prob_margin"], errors="coerce")
    frame["net_pnl_bps"] = pd.to_numeric(frame["raw_weighted_net_pnl_bps"], errors="coerce").fillna(0.0)
    frame["aligned_prior_ret_720_bps"] = pd.to_numeric(frame["aligned_prior_ret_720_bps"], errors="coerce")
    frame["fold"] = pd.to_numeric(frame["fold"], errors="coerce").astype(int)
    return frame


def _prediction_frame() -> pd.DataFrame:
    frame = pd.read_csv(V121_PREDICTIONS)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
    for col in ("net_pnl_bps", "aligned_prior_ret_720_bps", "pred_edge_bps", "prob_good_10", "prob_good_20"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["pred_edge_bps", "prob_good_10", "prob_good_20"]).reset_index(drop=True)


def _events_from_indices(frame: pd.DataFrame, keep: list[int], *, source: str, priority: int) -> pd.DataFrame:
    events = frame.iloc[keep][["timestamp", "month", "net_pnl_bps"]].copy()
    events["source"] = source
    events["priority"] = int(priority)
    return events


def _v120_peak_events(features: pd.DataFrame) -> pd.DataFrame:
    prior_score = features["score"].shift(1)
    q = prior_score.rolling(60 * 24 * 12, min_periods=20 * 24 * 12).quantile(0.99)
    prior_peak = prior_score.rolling(3, min_periods=1).max()
    eligible = (
        features["score"].ge(q)
        & features["score"].gt(prior_peak)
        & features["aligned_prior_ret_720_bps"].le(-300.0)
    )
    keep = _live_non_overlapping_indices(features["timestamp"], eligible, horizon_minutes=120)
    return _events_from_indices(features, keep, source="v120_peak", priority=4)


def _v121_native_events(predictions: pd.DataFrame) -> pd.DataFrame:
    eligible = (
        predictions["pred_edge_bps"].ge(20.0)
        & predictions["prob_good_10"].ge(0.55)
        & predictions["aligned_prior_ret_720_bps"].le(300.0)
    )
    keep = _live_non_overlapping_indices(predictions["timestamp"], eligible, horizon_minutes=30)
    return _events_from_indices(predictions, keep, source="v121_native", priority=2)


def _v122_drought_events(predictions: pd.DataFrame) -> pd.DataFrame:
    primary = (
        predictions["pred_edge_bps"].ge(20.0)
        & predictions["prob_good_10"].ge(0.55)
        & predictions["aligned_prior_ret_720_bps"].le(300.0)
    )
    fallback = predictions["pred_edge_bps"].ge(5.0) & predictions["prob_good_10"].ge(0.40)
    keep = _live_drought_fallback_indices(
        predictions["timestamp"],
        primary,
        fallback,
        cooldown_minutes=30,
        drought_days=14,
    )
    return _events_from_indices(predictions, keep, source="v122_drought", priority=1)


def _prior_fold_global_thresholds(frame: pd.DataFrame, *, quantile: float) -> pd.Series:
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    for fold in sorted(frame["fold"].unique()):
        train = frame.loc[frame["fold"] < int(fold)]
        test_idx = frame.index[frame["fold"] == int(fold)]
        if train["fold"].nunique() < 2:
            continue
        out.loc[test_idx] = float(train["score"].quantile(float(quantile)))
    return out


def _v123_threshold_events(features: pd.DataFrame) -> pd.DataFrame:
    threshold = _prior_fold_global_thresholds(features, quantile=0.995)
    eligible = features["score"].ge(threshold) & features["aligned_prior_ret_720_bps"].le(-100.0)
    keep = _live_non_overlapping_indices(features["timestamp"], eligible, horizon_minutes=120)
    return _events_from_indices(features, keep, source="v123_threshold", priority=3)


def _build_source_events() -> pd.DataFrame:
    features = _feature_frame()
    predictions = _prediction_frame()
    frames = [
        _v120_peak_events(features),
        _v121_native_events(predictions),
        _v122_drought_events(predictions),
        _v123_threshold_events(features),
    ]
    return pd.concat(frames, ignore_index=True).sort_values(["timestamp", "priority"]).reset_index(drop=True)


def _summarize_policy(policy: str, trades: pd.DataFrame, *, v115_total: float) -> dict[str, object]:
    if trades.empty:
        return {
            "policy": policy,
            "sources": "",
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
    source_counts = trades["source"].value_counts().sort_index()
    days = max(1.0, (trades["timestamp"].max() - trades["timestamp"].min()).total_seconds() / 86400.0)
    total = float(trades["net_pnl_bps"].sum())
    return {
        "policy": policy,
        "sources": ";".join(f"{k}:{int(v)}" for k, v in source_counts.items()),
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


def _scan_ensembles(events: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    sources = sorted(events["source"].unique().tolist())
    for r in range(1, len(sources) + 1):
        for source_subset in itertools.combinations(sources, r):
            subset_events = events.loc[events["source"].isin(source_subset)].copy()
            for cooldown in (30, 60, 120):
                selected = _priority_non_overlapping_events(subset_events, cooldown_minutes=cooldown)
                policy = f"sources_{'+'.join(source_subset)}_cool{cooldown}"
                rows.append(_summarize_policy(policy, selected, v115_total=v115_total))
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
        "sources",
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
        "# Research V124 BTCUSDC Live Family Ensemble",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Source event count: `{payload['data']['source_event_count']}`",
        f"- Explored policy count: `{payload['decision']['explored_policy_count']}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Best policy: `{payload['decision']['best_policy']}`",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V124 policy met the live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V124 policies were available.",
        "",
        "## Interpretation",
        "",
        "V124 combines the best prior real-time families as a chronological priority event stream. It does not use day-end ranking and does not cap trades per day. When multiple sources fire close together, source priority and position cooldown decide the entry before the outcome is known.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    events = _build_source_events()
    results = _scan_ensembles(events, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    payload = {
        "version": "v124_btcusdc_live_family_ensemble",
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
            "source_event_count": int(len(events)),
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v124_live_family_ensemble_summary.json"),
            "source_events": str(OUT_DIR / "v124_live_family_source_events.csv"),
            "results": str(OUT_DIR / "v124_live_family_ensemble_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    events.to_csv(OUT_DIR / "v124_live_family_source_events.csv", index=False)
    if not results.empty:
        results.to_csv(OUT_DIR / "v124_live_family_ensemble_results.csv", index=False)
    (OUT_DIR / "v124_live_family_ensemble_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
