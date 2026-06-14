from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v123_btcusdc_live_hourly_threshold_scan"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V123_BTCUSDC_LIVE_HOURLY_THRESHOLD_SCAN.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V119_FEATURES = ROOT / "runs" / "research_v119_btcusdc_live_entry_model" / "v119_live_feature_frame.csv"

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24
MIN_TRAIN_FOLDS = 2


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _prior_fold_group_thresholds(
    frame: pd.DataFrame,
    *,
    test_fold: int,
    group_cols: list[str],
    quantile: float,
    min_train_folds: int = MIN_TRAIN_FOLDS,
) -> pd.Series:
    folds = pd.to_numeric(frame["fold"], errors="coerce").astype(int)
    train = frame.loc[folds < int(test_fold)]
    test = frame.loc[folds == int(test_fold)]
    if train["fold"].nunique() < int(min_train_folds) or test.empty:
        return pd.Series(np.nan, index=test.index, dtype=float)
    global_threshold = float(train["score"].quantile(float(quantile)))
    if not group_cols:
        return pd.Series(global_threshold, index=test.index, dtype=float)
    grouped = train.groupby(group_cols, sort=False)["score"].quantile(float(quantile))
    keys = test[group_cols].apply(lambda row: tuple(row.tolist()), axis=1)
    if len(group_cols) == 1:
        mapped = test[group_cols[0]].map(grouped)
    else:
        mapped = keys.map(grouped)
    return mapped.fillna(global_threshold).astype(float)


def _threshold_vector(frame: pd.DataFrame, *, group_cols: list[str], quantile: float) -> pd.Series:
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    folds = pd.to_numeric(frame["fold"], errors="coerce").astype(int)
    for test_fold in sorted(folds.dropna().unique()):
        thresholds = _prior_fold_group_thresholds(
            frame,
            test_fold=int(test_fold),
            group_cols=group_cols,
            quantile=quantile,
        )
        out.loc[thresholds.index] = thresholds
    return out


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


def _max_drawdown_bps(pnl: pd.Series) -> float:
    equity = pd.to_numeric(pnl, errors="coerce").fillna(0.0).cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max()) if len(drawdown) else 0.0


def _prepare_frame() -> pd.DataFrame:
    cols = [
        "timestamp",
        "fold",
        "direction_probability",
        "prob_margin",
        "hour",
        "dow",
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
    frame["hour"] = pd.to_numeric(frame["hour"], errors="coerce").astype(int)
    frame["dow"] = pd.to_numeric(frame["dow"], errors="coerce").astype(int)
    return frame


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


def _scan_hourly_thresholds(frame: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_modes: dict[str, list[str]] = {
        "global": [],
        "hour": ["hour"],
        "dow": ["dow"],
        "hour_dow": ["hour", "dow"],
    }
    quantiles = (0.90, 0.95, 0.975, 0.99, 0.995)
    margin_mins = (0.0, 0.02, 0.05, 0.08, 0.10, 0.12)
    prior_ret_maxes: tuple[float | None, ...] = (None, 500.0, 300.0, 100.0, 0.0, -100.0, -300.0)
    cooldowns = (30, 60, 120)
    score = frame["score"].to_numpy(float)
    margin = frame["margin"].to_numpy(float)
    prior = frame["aligned_prior_ret_720_bps"].to_numpy(float)
    ts_ns = _timestamp_ns(frame["timestamp"])
    all_ok = np.ones(len(frame), dtype=bool)
    for group_name, group_cols in group_modes.items():
        for quantile in quantiles:
            thresholds = _threshold_vector(frame, group_cols=group_cols, quantile=quantile).to_numpy(float)
            threshold_ok = score >= thresholds
            if int(np.isfinite(thresholds).sum()) == 0:
                continue
            for margin_min in margin_mins:
                margin_ok = margin >= margin_min
                for prior_ret_max in prior_ret_maxes:
                    prior_ok = all_ok if prior_ret_max is None else prior <= prior_ret_max
                    eligible = threshold_ok & margin_ok & prior_ok
                    if int(eligible.sum()) == 0:
                        continue
                    for cooldown in cooldowns:
                        keep = _live_non_overlapping_indices(ts_ns, eligible, horizon_minutes=cooldown)
                        if not keep:
                            continue
                        trades = frame.iloc[keep][["timestamp", "month", "net_pnl_bps"]].copy()
                        prior_label = "none" if prior_ret_max is None else f"{prior_ret_max:g}"
                        policy = (
                            f"{group_name}_q{quantile:g}_margin{margin_min:g}"
                            f"_amax{prior_label}_cool{cooldown}"
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
        "# Research V123 BTCUSDC Live Hourly Threshold Scan",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Feature rows: `{payload['data']['feature_rows']}`",
        f"- Explored policy count: `{payload['decision']['explored_policy_count']}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Best policy: `{payload['decision']['best_policy']}`",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V123 policy met the live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V123 policies were available.",
        "",
        "## Interpretation",
        "",
        "V123 tests whether V115's day-end top-9 effect can be approximated by live thresholds calibrated by prior-fold time buckets. Thresholds are computed from earlier folds only, grouped by global, hour, day-of-week, or hour plus day-of-week score distributions. Entry rules do not use day-end ranking and do not impose a daily trade cap.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    frame = _prepare_frame()
    results = _scan_hourly_thresholds(frame, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    payload = {
        "version": "v123_btcusdc_live_hourly_threshold_scan",
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
            "min_train_folds": MIN_TRAIN_FOLDS,
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v123_live_hourly_threshold_summary.json"),
            "results": str(OUT_DIR / "v123_live_hourly_threshold_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    if not results.empty:
        results.to_csv(OUT_DIR / "v123_live_hourly_threshold_results.csv", index=False)
    (OUT_DIR / "v123_live_hourly_threshold_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
