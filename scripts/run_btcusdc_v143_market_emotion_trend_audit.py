from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v143_market_emotion_trend_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V143_BTCUSDC_MARKET_EMOTION_TREND_AUDIT.md"
V142_ACCOUNT_PATH = ROOT / "runs" / "research_v142_high_confidence_rescue_5x" / "v142_selected_account_path.csv"
V119_FEATURE_FRAME = ROOT / "runs" / "research_v119_btcusdc_live_entry_model" / "v119_live_feature_frame.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_SELECTOR_TRADES = 80

TREND_WINDOWS = (30, 60, 120, 240, 720, 1440)
AUDIT_FEATURES = (
    "trend_follow_30_bps",
    "trend_follow_120_bps",
    "trend_follow_720_bps",
    "trend_follow_1440_bps",
    "range_align_30",
    "range_align_240",
    "range_align_720",
    "emotion_prob_z_7d",
    "emotion_prob_z_30d",
    "emotion_prob_z_120d",
    "emotion_day_peak",
)


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    policy_type: str
    feature: str
    operator: str
    threshold: float


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True)


def _side_from_signal(signal: object) -> str:
    if pd.isna(signal):
        return "n/a"
    value = int(signal)
    if value > 0:
        return "long"
    if value < 0:
        return "short"
    return "n/a"


def _join_v142_with_v119_features(v142: pd.DataFrame, feature_frame: pd.DataFrame) -> pd.DataFrame:
    left = v142.copy()
    right = feature_frame.copy()
    left["timestamp"] = _to_utc(left["timestamp"])
    right["timestamp"] = _to_utc(right["timestamp"])
    right = right.drop_duplicates("timestamp", keep="last")

    feature_cols = ["timestamp", "signal"]
    for window in TREND_WINDOWS:
        for name in (f"prior_ret_{window}_bps", f"prior_range_pos_{window}"):
            if name in right.columns:
                feature_cols.append(name)
    for name in (
        "prob_z_7d",
        "prob_z_30d",
        "prob_z_120d",
        "prob_vs_day_sofar_max",
        "day_sofar_count",
        "day_sofar_max_prob",
    ):
        if name in right.columns:
            feature_cols.append(name)

    merged = left.merge(
        right[feature_cols].rename(columns={"signal": "signal_reference"}),
        on="timestamp",
        how="left",
        validate="many_to_one",
    )
    if "signal" not in merged.columns:
        merged["signal"] = pd.NA
    merged["signal"] = pd.to_numeric(merged["signal"], errors="coerce")
    merged["signal_reference"] = pd.to_numeric(merged["signal_reference"], errors="coerce")
    merged["signal"] = merged["signal"].fillna(merged["signal_reference"])
    merged["side"] = merged["signal"].map(_side_from_signal)
    if "month" not in merged.columns:
        merged["month"] = merged["timestamp"].dt.strftime("%Y-%m")
    return merged.sort_values(["timestamp"], kind="mergesort").reset_index(drop=True)


def _add_market_emotion_trend_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    signal = pd.to_numeric(out["signal"], errors="coerce")
    for window in TREND_WINDOWS:
        ret_col = f"prior_ret_{window}_bps"
        pos_col = f"prior_range_pos_{window}"
        if ret_col in out.columns:
            out[ret_col] = pd.to_numeric(out[ret_col], errors="coerce")
            out[f"trend_follow_{window}_bps"] = signal * out[ret_col]
            out[f"trend_abs_{window}_bps"] = out[ret_col].abs()
        if pos_col in out.columns:
            out[pos_col] = pd.to_numeric(out[pos_col], errors="coerce")
            centered = (out[pos_col] - 0.5) * 2.0
            out[f"range_align_{window}"] = signal * centered
            out[f"range_extreme_{window}"] = centered.abs()
    for src, dst in (
        ("prob_z_7d", "emotion_prob_z_7d"),
        ("prob_z_30d", "emotion_prob_z_30d"),
        ("prob_z_120d", "emotion_prob_z_120d"),
        ("prob_vs_day_sofar_max", "emotion_day_peak"),
    ):
        if src in out.columns:
            out[dst] = pd.to_numeric(out[src], errors="coerce")
    return out


def _month_index(frame: pd.DataFrame) -> pd.Index:
    if frame.empty:
        return pd.Index([], name="month")
    return pd.Index(frame["timestamp"].dt.strftime("%Y-%m").unique(), name="month").sort_values()


def _account_metrics(
    policy: str,
    path: pd.DataFrame,
    *,
    return_col: str,
    pnl_col: str,
    baseline_months: pd.Index,
) -> dict[str, object]:
    if path.empty:
        monthly = pd.Series(0.0, index=baseline_months)
        return {
            "policy": policy,
            "trade_count": 0,
            "total_account_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "positive_months": int((monthly > 0.0).sum()),
            "month_count": int(len(monthly)),
            "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
            "win_rate": 0.0,
        }

    ordered = path.sort_values("timestamp", kind="mergesort").copy()
    ordered["month"] = ordered["timestamp"].dt.strftime("%Y-%m")
    returns = pd.to_numeric(ordered[return_col], errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(ordered[pnl_col], errors="coerce").fillna(0.0)
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    monthly = returns.groupby(ordered["month"], sort=True).sum().reindex(baseline_months, fill_value=0.0)
    return {
        "policy": policy,
        "trade_count": int(len(ordered)),
        "total_account_return_pct": float(returns.sum()),
        "max_drawdown_pct": float(drawdown.min()) if len(drawdown) else 0.0,
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
        "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
    }


def _condition(frame: pd.DataFrame, feature: str, operator: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(frame[feature], errors="coerce")
    if operator == "<=":
        return values <= threshold
    if operator == ">=":
        return values >= threshold
    raise ValueError(f"unsupported operator: {operator}")


def _candidate_specs(frame: pd.DataFrame, *, selector_mask: pd.Series) -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []
    for feature in AUDIT_FEATURES:
        if feature not in frame.columns:
            continue
        selector_values = pd.to_numeric(frame.loc[selector_mask, feature], errors="coerce").dropna()
        if selector_values.nunique() < 4:
            continue
        thresholds = selector_values.quantile([0.2, 0.33, 0.5, 0.67, 0.8]).drop_duplicates()
        for quantile, threshold in thresholds.items():
            for operator, direction in (("<=", "low"), (">=", "high")):
                safe_threshold = float(threshold)
                qname = str(quantile).replace(".", "p")
                specs.append(
                    CandidateSpec(
                        name=f"skip_{feature}_{direction}_q{qname}",
                        policy_type="filter",
                        feature=feature,
                        operator=operator,
                        threshold=safe_threshold,
                    )
                )
                specs.append(
                    CandidateSpec(
                        name=f"halfsize_{feature}_{direction}_q{qname}",
                        policy_type="sizing",
                        feature=feature,
                        operator=operator,
                        threshold=safe_threshold,
                    )
                )
                specs.append(
                    CandidateSpec(
                        name=f"boost125_{feature}_{direction}_q{qname}",
                        policy_type="boost",
                        feature=feature,
                        operator=operator,
                        threshold=safe_threshold,
                    )
                )
    return specs


def _apply_candidate(frame: pd.DataFrame, spec: CandidateSpec) -> pd.DataFrame:
    danger = _condition(frame, spec.feature, spec.operator, spec.threshold).fillna(False)
    out = frame.copy()
    if spec.policy_type == "filter":
        out = out.loc[~danger].copy()
        out["candidate_account_return_pct"] = out["account_return_pct"]
        out["candidate_account_pnl_bps"] = out["account_pnl_bps"]
    elif spec.policy_type == "sizing":
        multiplier = pd.Series(1.0, index=out.index)
        multiplier.loc[danger] = 0.5
        out["candidate_account_return_pct"] = out["account_return_pct"] * multiplier
        out["candidate_account_pnl_bps"] = out["account_pnl_bps"] * multiplier
    elif spec.policy_type == "boost":
        multiplier = pd.Series(1.0, index=out.index)
        multiplier.loc[danger] = 1.25
        out["candidate_account_return_pct"] = out["account_return_pct"] * multiplier
        out["candidate_account_pnl_bps"] = out["account_pnl_bps"] * multiplier
    else:
        raise ValueError(f"unsupported policy type: {spec.policy_type}")
    return out


def _evaluate_candidate(
    frame: pd.DataFrame,
    spec: CandidateSpec,
    *,
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    candidate_path = _apply_candidate(frame, spec)
    row: dict[str, object] = {
        "candidate": spec.name,
        "policy_type": spec.policy_type,
        "feature": spec.feature,
        "operator": spec.operator,
        "threshold": spec.threshold,
    }
    for period, mask in masks.items():
        period_path = candidate_path.loc[candidate_path.index.intersection(frame.index[mask])]
        metrics = _account_metrics(
            f"{spec.name}_{period}",
            period_path,
            return_col="candidate_account_return_pct",
            pnl_col="candidate_account_pnl_bps",
            baseline_months=baseline_months[period],
        )
        base = baseline_metrics[period]
        prefix = period
        row[f"{prefix}_trade_count"] = metrics["trade_count"]
        row[f"{prefix}_return_pct"] = metrics["total_account_return_pct"]
        row[f"{prefix}_delta_return_pct"] = (
            float(metrics["total_account_return_pct"]) - float(base["total_account_return_pct"])
        )
        row[f"{prefix}_max_drawdown_pct"] = metrics["max_drawdown_pct"]
        row[f"{prefix}_delta_drawdown_pct"] = (
            float(metrics["max_drawdown_pct"]) - float(base["max_drawdown_pct"])
        )
        row[f"{prefix}_positive_months"] = metrics["positive_months"]
        row[f"{prefix}_month_count"] = metrics["month_count"]
        row[f"{prefix}_worst_month_pct"] = metrics["worst_month_pct"]
        row[f"{prefix}_win_rate"] = metrics["win_rate"]
    return row


def _select_best_candidate(candidates: pd.DataFrame) -> dict[str, object]:
    if candidates.empty:
        return {}
    eligible = candidates.copy()
    if "selector_trade_count" in eligible.columns:
        eligible = eligible.loc[eligible["selector_trade_count"] >= MIN_SELECTOR_TRADES]
    eligible = eligible.loc[
        (eligible["selector_delta_return_pct"] > 0.0)
        & (eligible["selector_delta_drawdown_pct"] >= 0.0)
        & (eligible["selector_positive_months"] == eligible["selector_month_count"])
    ]
    if eligible.empty:
        return {}
    eligible = eligible.sort_values(
        ["selector_delta_return_pct", "selector_delta_drawdown_pct", "holdout_delta_return_pct"],
        ascending=[False, False, False],
        kind="mergesort",
    )
    return eligible.iloc[0].to_dict()


def _feature_bucket_summary(frame: pd.DataFrame, *, baseline_months: pd.Index) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for feature in AUDIT_FEATURES:
        if feature not in frame.columns:
            continue
        values = pd.to_numeric(frame[feature], errors="coerce")
        valid = frame.loc[values.notna()].copy()
        if valid.empty or values.nunique() < 4:
            continue
        try:
            valid["_bucket"] = pd.qcut(values.loc[valid.index], q=5, duplicates="drop")
        except ValueError:
            continue
        for bucket, bucket_path in valid.groupby("_bucket", observed=False, sort=True):
            metrics = _account_metrics(
                f"{feature}_{bucket}",
                bucket_path,
                return_col="account_return_pct",
                pnl_col="account_pnl_bps",
                baseline_months=baseline_months,
            )
            rows.append(
                {
                    "feature": feature,
                    "bucket": str(bucket),
                    "trade_count": metrics["trade_count"],
                    "return_pct": metrics["total_account_return_pct"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "win_rate": metrics["win_rate"],
                    "worst_month_pct": metrics["worst_month_pct"],
                }
            )
    return pd.DataFrame(rows)


def _baseline_metrics(frame: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[dict[str, dict[str, object]], dict[str, pd.Index]]:
    metrics: dict[str, dict[str, object]] = {}
    months: dict[str, pd.Index] = {}
    for period, mask in masks.items():
        period_path = frame.loc[mask].copy()
        months[period] = _month_index(period_path)
        metrics[period] = _account_metrics(
            f"v142_{period}",
            period_path,
            return_col="account_return_pct",
            pnl_col="account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _decision(selected: dict[str, object]) -> dict[str, object]:
    if not selected:
        return {
            "status": "no_selector_candidate_found",
            "message": "No selector-period trend/emotion overlay improved return without worsening drawdown.",
            "promote_to_v144": False,
        }
    robust = (
        float(selected["holdout_delta_return_pct"]) > 0.0
        and float(selected["holdout_delta_drawdown_pct"]) >= 0.0
        and float(selected["full_delta_return_pct"]) > 0.0
        and float(selected["full_delta_drawdown_pct"]) >= 0.0
        and int(selected["full_positive_months"]) == int(selected["full_month_count"])
    )
    return {
        "status": "robust_candidate_found" if robust else "selector_candidate_not_holdout_robust",
        "message": (
            "The selector-period winner also improved holdout and full-period risk/return."
            if robust
            else "The selector-period winner did not stay clearly better on the later holdout."
        ),
        "promote_to_v144": bool(robust),
    }


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    top_candidates: pd.DataFrame,
    bucket_summary: pd.DataFrame,
) -> None:
    selected = payload["selected_candidate"]
    decision = payload["decision"]
    lines = [
        "# Research V143 BTCUSDC Market Emotion Trend Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v144']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## Selected Candidate",
        "",
    ]
    if selected:
        lines.extend(pd.DataFrame([selected]).to_csv(index=False).strip().splitlines())
    else:
        lines.append("No eligible selector candidate.")
    lines.extend(
        [
            "",
            "## Top Selector Candidates",
            "",
            top_candidates.to_csv(index=False).strip() if not top_candidates.empty else "No eligible candidates.",
            "",
            "## Feature Bucket Summary",
            "",
            bucket_summary.to_csv(index=False).strip() if not bucket_summary.empty else "No feature buckets.",
            "",
            "## Interpretation",
            "",
            "V143 is an overlay audit on top of V142. It does not change the V142 trade generator. Trend features measure whether the trade follows or fades the prior BTCUSDC move. Emotion features proxy how hot the model probability was versus recent history and the same trading day. Candidate selection uses only the selector period; the later holdout is reported after selection.",
            "",
            "This is a research candidate audit, not a live trading guarantee.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v142 = pd.read_csv(V142_ACCOUNT_PATH)
    feature_frame = pd.read_csv(V119_FEATURE_FRAME)
    frame = _add_market_emotion_trend_features(_join_v142_with_v119_features(v142, feature_frame))
    frame.to_csv(OUT_DIR / "v143_v142_with_market_emotion_trend_features.csv", index=False)

    masks = {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }
    baseline, months = _baseline_metrics(frame, masks)
    baseline_table = pd.DataFrame(baseline.values())

    specs = _candidate_specs(frame, selector_mask=masks["selector"])
    rows = [
        _evaluate_candidate(frame, spec, masks=masks, baseline_metrics=baseline, baseline_months=months)
        for spec in specs
    ]
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            ["selector_delta_return_pct", "selector_delta_drawdown_pct"],
            ascending=[False, False],
            kind="mergesort",
        )
    candidates.to_csv(OUT_DIR / "v143_market_emotion_trend_candidates.csv", index=False)

    selected = _select_best_candidate(candidates)
    bucket_summary = _feature_bucket_summary(frame, baseline_months=months["full"])
    bucket_summary.to_csv(OUT_DIR / "v143_market_emotion_trend_bucket_summary.csv", index=False)

    top_candidates = candidates.head(20).copy() if not candidates.empty else pd.DataFrame()
    payload = {
        "config": {
            "base": "v142_high_confidence_rescue_5x",
            "feature_source": "v119_live_feature_frame",
            "selector_end": SELECTOR_END.isoformat(),
            "min_selector_trades": MIN_SELECTOR_TRADES,
            "candidate_types": ["filter", "sizing", "boost"],
            "uses_holdout_for_selection": False,
        },
        "baseline": baseline,
        "selected_candidate": selected,
        "decision": _decision(selected),
    }
    (OUT_DIR / "v143_market_emotion_trend_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, baseline_table, top_candidates, bucket_summary)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
