from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144
import run_btcusdc_v162_long_trend_follow_boost as v162


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v163_post_v162_candidate_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V163_BTCUSDC_POST_V162_CANDIDATE_AUDIT.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_CHANGED_SELECTOR_TRADES = 60
MIN_CHANGED_HOLDOUT_TRADES = 20
MIN_INCREMENTAL_IMPROVEMENT_RATE = 1.005
QUANTILES = (0.20, 0.30, 0.40, 0.60, 0.70, 0.80)
MODIFIERS = (0.90, 0.95, 1.05, 1.10)
USED_OR_UNSUITABLE_FEATURES = {
    "day_sofar_count",
    "trend_follow_1440_bps",
    "prior_ret_1440_bps",
    "drawdown_pct",
}
EXCLUDED_SUBSTRINGS = (
    "pnl",
    "return",
    "equity",
    "net_pnl",
    "weighted",
    "candidate_account",
    "account_return",
    "account_pnl",
    "v148_",
    "v149_",
    "v150_",
    "v151_",
    "v152_",
    "v153_",
    "v154_",
    "v155_",
    "v156_",
    "v158_",
    "v159_",
    "v160_",
    "v161_",
    "v162_",
    "flag",
    "modifier",
    "timestamp",
    "month",
    "funding_time",
    "premium_time",
    "premium_open_time",
)
NON_FEATURE_COLUMNS = {
    "source",
    "leg",
    "signal",
    "indicator_source",
    "indicator_key",
    "signal_reference",
    "symbol",
    "side",
}


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _candidate_feature_columns(frame: pd.DataFrame, *, min_non_null: int = 100, min_unique: int = 8) -> list[str]:
    features: list[str] = []
    for column in frame.columns:
        if column in USED_OR_UNSUITABLE_FEATURES or column in NON_FEATURE_COLUMNS:
            continue
        if any(marker in column for marker in EXCLUDED_SUBSTRINGS):
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().sum() < min_non_null or values.nunique(dropna=True) < min_unique:
            continue
        features.append(column)
    return features


def _period_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }


def _segment_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "all": pd.Series(True, index=frame.index),
        "base": frame["leg"].eq("base"),
        "rescue": frame["leg"].eq("rescue"),
        "long": frame["side"].eq("long"),
        "short": frame["side"].eq("short"),
        "base_long": frame["leg"].eq("base") & frame["side"].eq("long"),
        "base_short": frame["leg"].eq("base") & frame["side"].eq("short"),
        "rescue_long": frame["leg"].eq("rescue") & frame["side"].eq("long"),
        "rescue_short": frame["leg"].eq("rescue") & frame["side"].eq("short"),
    }


def _baseline_metrics(frame: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[dict[str, dict[str, object]], dict[str, pd.Index]]:
    metrics: dict[str, dict[str, object]] = {}
    months: dict[str, pd.Index] = {}
    for period, mask in masks.items():
        period_path = frame.loc[mask].copy()
        months[period] = v144.v143._month_index(period_path)
        metrics[period] = v144.v143._account_metrics(
            f"v162_{period}",
            period_path,
            return_col="v162_account_return_pct",
            pnl_col="v162_account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _passes_promotion_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
    if not candidate:
        return False
    return (
        float(candidate["full_return_pct"])
        >= float(baseline["full"]["total_account_return_pct"]) * (1.0 + MIN_INCREMENTAL_IMPROVEMENT_RATE - 1.0)
        and float(candidate["full_max_drawdown_pct"]) >= float(baseline["full"]["max_drawdown_pct"])
        and float(candidate["full_worst_month_pct"]) >= float(baseline["full"]["worst_month_pct"])
        and int(candidate["full_positive_months"]) == int(candidate["full_month_count"])
        and float(candidate["selector_return_pct"]) > float(baseline["selector"]["total_account_return_pct"])
        and float(candidate["selector_max_drawdown_pct"]) >= float(baseline["selector"]["max_drawdown_pct"])
        and float(candidate["selector_worst_month_pct"]) >= float(baseline["selector"]["worst_month_pct"])
        and int(candidate["selector_positive_months"]) == int(candidate["selector_month_count"])
        and float(candidate["holdout_return_pct"]) > float(baseline["holdout"]["total_account_return_pct"])
        and float(candidate["holdout_max_drawdown_pct"]) >= float(baseline["holdout"]["max_drawdown_pct"])
        and float(candidate["holdout_worst_month_pct"]) >= float(baseline["holdout"]["worst_month_pct"])
        and int(candidate["holdout_positive_months"]) == int(candidate["holdout_month_count"])
    )


def _evaluate_candidate(
    frame: pd.DataFrame,
    condition: pd.Series,
    *,
    feature: str,
    segment: str,
    operator: str,
    quantile: float,
    threshold: float,
    modifier: float,
    masks: dict[str, pd.Series],
    baseline: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    tmp_return = frame["v162_account_return_pct"].copy()
    tmp_pnl = frame["v162_account_pnl_bps"].copy()
    tmp_return.loc[condition] = tmp_return.loc[condition] * modifier
    tmp_pnl.loc[condition] = tmp_pnl.loc[condition] * modifier
    row: dict[str, object] = {
        "feature": feature,
        "segment": segment,
        "operator": operator,
        "quantile": quantile,
        "threshold": threshold,
        "modifier": modifier,
        "changed_trade_count": int(condition.sum()),
        "changed_selector_count": int((condition & masks["selector"]).sum()),
        "changed_holdout_count": int((condition & masks["holdout"]).sum()),
    }
    for period, mask in masks.items():
        row[f"{period}_return_pct"] = float(tmp_return.loc[mask].sum())
        row[f"{period}_delta_return_pct"] = (
            float(row[f"{period}_return_pct"]) - float(baseline[period]["total_account_return_pct"])
        )
    audit_path = frame[["timestamp"]].copy()
    audit_path["tmp_return"] = tmp_return
    audit_path["tmp_pnl"] = tmp_pnl
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            "tmp",
            audit_path.loc[mask].copy(),
            return_col="tmp_return",
            pnl_col="tmp_pnl",
            baseline_months=baseline_months[period],
        )
        row[f"{period}_max_drawdown_pct"] = metrics["max_drawdown_pct"]
        row[f"{period}_delta_drawdown_pct"] = (
            float(metrics["max_drawdown_pct"]) - float(baseline[period]["max_drawdown_pct"])
        )
        row[f"{period}_worst_month_pct"] = metrics["worst_month_pct"]
        row[f"{period}_delta_worst_month_pct"] = (
            float(metrics["worst_month_pct"]) - float(baseline[period]["worst_month_pct"])
        )
        row[f"{period}_positive_months"] = metrics["positive_months"]
        row[f"{period}_month_count"] = metrics["month_count"]
        row[f"{period}_win_rate"] = metrics["win_rate"]
    return row


def _scan_candidates(
    frame: pd.DataFrame,
    *,
    masks: dict[str, pd.Series],
    baseline: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> tuple[pd.DataFrame, Counter[str], dict[str, int]]:
    features = _candidate_feature_columns(frame)
    segments = _segment_masks(frame)
    reasons: Counter[str] = Counter()
    passed: list[dict[str, object]] = []
    stats = {"feature_count": len(features), "eligible_conditions": 0, "evaluated_candidates": 0, "risk_checked_candidates": 0}
    for feature in features:
        values = pd.to_numeric(frame[feature], errors="coerce")
        for segment, segment_mask in segments.items():
            selector_values = values.loc[masks["selector"] & segment_mask].dropna()
            if selector_values.nunique() < 8:
                continue
            for quantile in QUANTILES:
                threshold = float(selector_values.quantile(quantile))
                for operator in ("<=", ">="):
                    condition = (values <= threshold) if operator == "<=" else (values >= threshold)
                    condition = (condition & segment_mask).fillna(False)
                    changed_selector = int((condition & masks["selector"]).sum())
                    changed_holdout = int((condition & masks["holdout"]).sum())
                    if changed_selector < MIN_CHANGED_SELECTOR_TRADES or changed_holdout < MIN_CHANGED_HOLDOUT_TRADES:
                        reasons["too_few_changed_trades"] += 1
                        continue
                    stats["eligible_conditions"] += 1
                    for modifier in MODIFIERS:
                        stats["evaluated_candidates"] += 1
                        candidate = _evaluate_candidate(
                            frame,
                            condition,
                            feature=feature,
                            segment=segment,
                            operator=operator,
                            quantile=quantile,
                            threshold=threshold,
                            modifier=modifier,
                            masks=masks,
                            baseline=baseline,
                            baseline_months=baseline_months,
                        )
                        if (
                            float(candidate["full_return_pct"])
                            < float(baseline["full"]["total_account_return_pct"]) * MIN_INCREMENTAL_IMPROVEMENT_RATE
                        ):
                            reasons["full_return_lt_minimum"] += 1
                            continue
                        if float(candidate["selector_return_pct"]) <= float(baseline["selector"]["total_account_return_pct"]):
                            reasons["selector_not_better"] += 1
                            continue
                        if float(candidate["holdout_return_pct"]) <= float(baseline["holdout"]["total_account_return_pct"]):
                            reasons["holdout_not_better"] += 1
                            continue
                        stats["risk_checked_candidates"] += 1
                        if float(candidate["full_max_drawdown_pct"]) < float(baseline["full"]["max_drawdown_pct"]):
                            reasons["full_drawdown_worse"] += 1
                            continue
                        if float(candidate["selector_max_drawdown_pct"]) < float(baseline["selector"]["max_drawdown_pct"]):
                            reasons["selector_drawdown_worse"] += 1
                            continue
                        if float(candidate["holdout_max_drawdown_pct"]) < float(baseline["holdout"]["max_drawdown_pct"]):
                            reasons["holdout_drawdown_worse"] += 1
                            continue
                        if float(candidate["full_worst_month_pct"]) < float(baseline["full"]["worst_month_pct"]):
                            reasons["full_worst_month_worse"] += 1
                            continue
                        if float(candidate["selector_worst_month_pct"]) < float(baseline["selector"]["worst_month_pct"]):
                            reasons["selector_worst_month_worse"] += 1
                            continue
                        if float(candidate["holdout_worst_month_pct"]) < float(baseline["holdout"]["worst_month_pct"]):
                            reasons["holdout_worst_month_worse"] += 1
                            continue
                        if not _passes_promotion_gate(candidate, baseline):
                            reasons["promotion_gate_failed"] += 1
                            continue
                        passed.append(candidate)
                        reasons["passed"] += 1
    return pd.DataFrame(passed), reasons, stats


def _write_report(payload: dict[str, object], baseline_table: pd.DataFrame, rejection_table: pd.DataFrame) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V163 BTCUSDC Post V162 Candidate Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v164']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Audit Rules",
        "",
        "- Base: V162 selected account path.",
        "- Excluded post-trade or account-path result fields, including `drawdown_pct`, returns, pnl, equity, flags, and modifiers.",
        "- Excluded already-promoted same-family fields: `day_sofar_count`, `trend_follow_1440_bps`, and duplicate `prior_ret_1440_bps`.",
        f"- Minimum changed trades: selector `{MIN_CHANGED_SELECTOR_TRADES}`, holdout `{MIN_CHANGED_HOLDOUT_TRADES}`.",
        f"- Minimum full-period improvement before promotion: `{MIN_INCREMENTAL_IMPROVEMENT_RATE}`.",
        "- Holdout is used only for validation.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## Scan Summary",
        "",
        json.dumps(payload["scan_stats"], indent=2, sort_keys=True),
        "",
        "## Rejection Summary",
        "",
        rejection_table.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "No clean, independent post-V162 candidate cleared the promotion gate. The large candidates found before this audit depended on `drawdown_pct`, which is treated as unsuitable for entry-time promotion. The correct action is to keep V162 fixed and avoid adding another weak historical overlay.",
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
    frame = pd.read_csv(V162_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    for column in ("v162_account_return_pct", "v162_account_pnl_bps"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    masks = _period_masks(frame)
    baseline, months = _baseline_metrics(frame, masks)
    passed, reasons, stats = _scan_candidates(frame, masks=masks, baseline=baseline, baseline_months=months)
    promoted = not passed.empty
    decision = {
        "status": "post_v162_no_clean_candidate" if not promoted else "post_v162_candidate_found",
        "promote_to_v164": bool(promoted),
        "message": (
            "No clean independent post-V162 candidate cleared the promotion gate."
            if not promoted
            else "At least one clean independent post-V162 candidate cleared the promotion gate."
        ),
    }
    rejection_table = pd.DataFrame(
        [{"reason": key, "count": value} for key, value in reasons.most_common()]
    )
    payload = {
        "config": {
            "base": "v162_long_trend_follow_boost",
            "selector_end": SELECTOR_END.isoformat(),
            "min_incremental_improvement_rate": MIN_INCREMENTAL_IMPROVEMENT_RATE,
            "min_changed_selector_trades": MIN_CHANGED_SELECTOR_TRADES,
            "min_changed_holdout_trades": MIN_CHANGED_HOLDOUT_TRADES,
            "uses_holdout_for_thresholds": False,
            "adds_new_trades": False,
            "excludes_post_trade_account_path_fields": True,
            "excluded_used_or_unsuitable_features": sorted(USED_OR_UNSUITABLE_FEATURES),
        },
        "baseline": baseline,
        "scan_stats": stats,
        "rejection_summary": rejection_table.to_dict(orient="records"),
        "passed_candidate_count": int(len(passed)),
        "decision": decision,
    }
    passed.to_csv(OUT_DIR / "v163_passed_candidates.csv", index=False)
    rejection_table.to_csv(OUT_DIR / "v163_candidate_rejection_summary.csv", index=False)
    (OUT_DIR / "v163_post_v162_candidate_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, pd.DataFrame(baseline.values()), rejection_table)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
