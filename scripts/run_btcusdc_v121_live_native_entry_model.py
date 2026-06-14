from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v121_btcusdc_live_native_entry_model"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V121_BTCUSDC_LIVE_NATIVE_ENTRY_MODEL.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V119_FEATURES = ROOT / "runs" / "research_v119_btcusdc_live_entry_model" / "v119_live_feature_frame.csv"

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24
MIN_TRAIN_FOLDS = 2

META_COLUMNS = {
    "timestamp",
    "fold",
    "test_start",
    "test_end_exclusive",
    "month",
}
TARGET_COLUMNS = {
    "future_return_bps",
    "base_net_pnl_bps",
    "raw_weighted_net_pnl_bps",
    "net_pnl_bps",
}


def _make_live_native_target(pnl: pd.Series, *, min_net_pnl_bps: float) -> pd.Series:
    return pd.to_numeric(pnl, errors="coerce").fillna(-np.inf).ge(float(min_net_pnl_bps)).astype(int)


def _prior_fold_train_indices(folds: pd.Series, *, test_fold: int, min_train_folds: int = MIN_TRAIN_FOLDS) -> list[int]:
    fold_values = pd.to_numeric(folds, errors="coerce")
    prior = fold_values < int(test_fold)
    if int(fold_values.loc[prior].nunique()) < int(min_train_folds):
        return []
    return [int(idx) for idx in folds.index[prior].tolist()]


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


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


def _feature_columns(frame: pd.DataFrame) -> list[str]:
    return [
        col
        for col in frame.columns
        if col not in META_COLUMNS
        and col not in TARGET_COLUMNS
        and pd.api.types.is_numeric_dtype(frame[col])
    ]


def _prepare_frame() -> pd.DataFrame:
    frame = pd.read_csv(V119_FEATURES)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame["net_pnl_bps"] = pd.to_numeric(frame["raw_weighted_net_pnl_bps"], errors="coerce").fillna(0.0)
    for col in frame.columns:
        if col not in META_COLUMNS:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def _clean_features(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[columns].replace([np.inf, -np.inf], np.nan)


def _fit_walk_forward_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    feature_cols = _feature_columns(frame)
    out_cols = [
        "timestamp",
        "month",
        "fold",
        "net_pnl_bps",
        "aligned_prior_ret_720_bps",
        "pred_edge_bps",
        "prob_good_0",
        "prob_good_10",
        "prob_good_20",
    ]
    out = frame[["timestamp", "month", "fold", "net_pnl_bps", "aligned_prior_ret_720_bps"]].copy()
    out["pred_edge_bps"] = np.nan
    out["prob_good_0"] = np.nan
    out["prob_good_10"] = np.nan
    out["prob_good_20"] = np.nan
    folds = pd.to_numeric(frame["fold"], errors="coerce").astype(int)
    X_all = _clean_features(frame, feature_cols)
    y_reg_all = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    for test_fold in sorted(folds.dropna().unique()):
        train_idx = _prior_fold_train_indices(folds, test_fold=int(test_fold))
        if not train_idx:
            continue
        test_mask = folds.eq(int(test_fold))
        test_idx = frame.index[test_mask].tolist()
        if not test_idx:
            continue
        X_train = X_all.loc[train_idx]
        X_test = X_all.loc[test_idx]
        y_train = y_reg_all.loc[train_idx].clip(-250.0, 250.0)
        reg = HistGradientBoostingRegressor(
            max_iter=80,
            learning_rate=0.05,
            max_leaf_nodes=31,
            min_samples_leaf=120,
            l2_regularization=0.1,
            random_state=121,
        )
        reg.fit(X_train, y_train)
        out.loc[test_idx, "pred_edge_bps"] = reg.predict(X_test)
        for min_good, col in ((0.0, "prob_good_0"), (10.0, "prob_good_10"), (20.0, "prob_good_20")):
            y_cls = _make_live_native_target(y_reg_all.loc[train_idx], min_net_pnl_bps=min_good)
            if y_cls.nunique() < 2:
                out.loc[test_idx, col] = float(y_cls.mean())
                continue
            clf = HistGradientBoostingClassifier(
                max_iter=80,
                learning_rate=0.05,
                max_leaf_nodes=31,
                min_samples_leaf=120,
                l2_regularization=0.1,
                random_state=121 + int(min_good),
            )
            clf.fit(X_train, y_cls)
            out.loc[test_idx, col] = clf.predict_proba(X_test)[:, 1]
    return out[out_cols]


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


def _scan_live_native_policies(predictions: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    valid = predictions.dropna(subset=["pred_edge_bps", "prob_good_0", "prob_good_10", "prob_good_20"]).copy()
    if valid.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    timestamp_ns = valid["timestamp"].to_numpy(dtype="datetime64[ns]").astype("int64")
    prior = pd.to_numeric(valid["aligned_prior_ret_720_bps"], errors="coerce").to_numpy(float)
    edge = pd.to_numeric(valid["pred_edge_bps"], errors="coerce").to_numpy(float)
    prior_ret_maxes: tuple[float | None, ...] = (None, 500.0, 300.0, 100.0, 0.0, -100.0, -300.0)
    cooldowns = (30, 60, 120)
    edge_thresholds = (-20.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 30.0)
    probability_thresholds = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75)
    all_ok = np.ones(len(valid), dtype=bool)
    for prob_col in ("prob_good_0", "prob_good_10", "prob_good_20"):
        prob = pd.to_numeric(valid[prob_col], errors="coerce").to_numpy(float)
        for edge_th in edge_thresholds:
            edge_ok = edge >= edge_th
            for prob_th in probability_thresholds:
                prob_ok = prob >= prob_th
                for prior_ret_max in prior_ret_maxes:
                    prior_ok = all_ok if prior_ret_max is None else prior <= prior_ret_max
                    eligible = edge_ok & prob_ok & prior_ok
                    if int(eligible.sum()) == 0:
                        continue
                    for cooldown in cooldowns:
                        keep = _live_non_overlapping_indices(timestamp_ns, eligible, horizon_minutes=cooldown)
                        if not keep:
                            continue
                        trades = valid.iloc[keep][["timestamp", "month", "net_pnl_bps"]].copy()
                        prior_label = "none" if prior_ret_max is None else f"{prior_ret_max:g}"
                        policy = (
                            f"{prob_col}_edge{edge_th:g}_prob{prob_th:g}"
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
        "worst_month_bps",
        "worst_month",
    ]
    passed = results.loc[results["live_similarity_passed"], cols] if not results.empty else pd.DataFrame(columns=cols)
    top = results[cols].head(30) if not results.empty else pd.DataFrame(columns=cols)
    lines = [
        "# Research V121 BTCUSDC Live Native Entry Model",
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
        passed.to_csv(index=False).strip() if not passed.empty else "No V121 policy met the live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V121 policies were available.",
        "",
        "## Interpretation",
        "",
        "V121 trains live-native entry models directly on current-trade net PnL. Each test fold is predicted by models trained only on earlier folds. Entry rules use predicted edge, good-trade probability, an optional prior-trend guard, and a position cooldown. They do not use day-end ranking or a daily trade cap.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    frame = _prepare_frame()
    predictions = _fit_walk_forward_predictions(frame)
    results = _scan_live_native_policies(predictions, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    payload = {
        "version": "v121_btcusdc_live_native_entry_model",
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
            "prediction_rows": int(len(predictions)),
            "min_train_folds": MIN_TRAIN_FOLDS,
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v121_live_native_entry_model_summary.json"),
            "predictions": str(OUT_DIR / "v121_live_native_entry_model_predictions.csv"),
            "results": str(OUT_DIR / "v121_live_native_entry_model_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    predictions.to_csv(OUT_DIR / "v121_live_native_entry_model_predictions.csv", index=False)
    if not results.empty:
        results.to_csv(OUT_DIR / "v121_live_native_entry_model_results.csv", index=False)
    (OUT_DIR / "v121_live_native_entry_model_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
