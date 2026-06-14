from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144
import run_btcusdc_v156_base_long_premium_stepup as v156


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v157_market_condition_post_stepup_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V157_BTCUSDC_MARKET_CONDITION_POST_STEPUP_AUDIT.md"
V156_ACCOUNT_PATH = ROOT / "runs" / "research_v156_base_long_premium_stepup" / "v156_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_CHANGED_SELECTOR_TRADES = 60
MIN_CHANGED_HOLDOUT_TRADES = 20
QUANTILES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
MODIFIERS = (0.70, 0.80, 0.85, 0.90, 0.925, 0.95, 1.025, 1.05, 1.075, 1.10)
SEGMENTS = (
    "all",
    "long",
    "short",
    "base",
    "rescue",
    "base_long",
    "base_short",
    "rescue_long",
    "rescue_short",
)
FEATURE_PREFIXES = (
    "trend_",
    "range_",
    "emotion_",
    "funding_",
    "premium_",
    "prior_ret_",
    "prior_range_",
    "prob_",
    "day_sofar_",
)
EXCLUDE_FEATURE_TOKENS = (
    "account_return",
    "account_pnl",
    "multiplier",
    "modifier",
    "flag",
    "return_pct",
    "pnl_bps",
    "drawdown_pct",
    "timestamp",
    "month",
)


@dataclass(frozen=True)
class AuditSpec:
    feature: str
    segment: str
    operator: str
    quantile: float
    threshold: float
    modifier: float


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _candidate_features(frame: pd.DataFrame, *, min_non_null: int = 100, min_unique: int = 8) -> list[str]:
    features: list[str] = []
    for column in frame.columns:
        allowed_name = column in ("direction_probability", "position_weight", "account_leverage") or column.startswith(
            FEATURE_PREFIXES
        )
        if not allowed_name or any(token in column for token in EXCLUDE_FEATURE_TOKENS):
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.notna().sum() >= min_non_null and values.nunique(dropna=True) >= min_unique:
            features.append(column)
    return features


def _segment_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "all": pd.Series(True, index=frame.index),
        "long": frame["side"].eq("long"),
        "short": frame["side"].eq("short"),
        "base": frame["leg"].eq("base"),
        "rescue": frame["leg"].eq("rescue"),
        "base_long": frame["leg"].eq("base") & frame["side"].eq("long"),
        "base_short": frame["leg"].eq("base") & frame["side"].eq("short"),
        "rescue_long": frame["leg"].eq("rescue") & frame["side"].eq("long"),
        "rescue_short": frame["leg"].eq("rescue") & frame["side"].eq("short"),
    }


def _period_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }


def _condition(frame: pd.DataFrame, spec: AuditSpec, segment_masks: dict[str, pd.Series]) -> pd.Series:
    values = pd.to_numeric(frame[spec.feature], errors="coerce")
    if spec.operator == "<=":
        return segment_masks[spec.segment] & values.notna() & (values <= spec.threshold)
    if spec.operator == ">=":
        return segment_masks[spec.segment] & values.notna() & (values >= spec.threshold)
    raise ValueError(f"unsupported operator: {spec.operator}")


def _baseline_metrics(frame: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[dict[str, dict[str, object]], dict[str, pd.Index]]:
    metrics: dict[str, dict[str, object]] = {}
    months: dict[str, pd.Index] = {}
    for period, mask in masks.items():
        period_path = frame.loc[mask].copy()
        months[period] = v144.v143._month_index(period_path)
        metrics[period] = v144.v143._account_metrics(
            f"v156_{period}",
            period_path,
            return_col="v156_account_return_pct",
            pnl_col="v156_account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _passes_strict_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
    return _rejection_reason(candidate, baseline) == "passed"


def _rejection_reason(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> str:
    if int(candidate.get("changed_selector_count", MIN_CHANGED_SELECTOR_TRADES)) < MIN_CHANGED_SELECTOR_TRADES:
        return "too_few_selector_trades"
    if int(candidate.get("changed_holdout_count", MIN_CHANGED_HOLDOUT_TRADES)) < MIN_CHANGED_HOLDOUT_TRADES:
        return "too_few_holdout_trades"
    for period in ("full", "selector", "holdout"):
        if float(candidate[f"{period}_max_drawdown_pct"]) < float(baseline[period]["max_drawdown_pct"]):
            return f"{period}_drawdown_worse"
        if float(candidate[f"{period}_worst_month_pct"]) < float(baseline[period]["worst_month_pct"]):
            return f"{period}_worst_month_worse"
        if int(candidate.get(f"{period}_positive_months", 0)) != int(candidate.get(f"{period}_month_count", -1)):
            return f"{period}_non_positive_month"
    if float(candidate["full_return_pct"]) < float(baseline["full"]["total_account_return_pct"]):
        return "full_return_not_improved"
    if float(candidate["selector_return_pct"]) <= float(baseline["selector"]["total_account_return_pct"]):
        return "selector_return_not_improved"
    if float(candidate["holdout_return_pct"]) <= float(baseline["holdout"]["total_account_return_pct"]):
        return "holdout_return_not_improved"
    return "passed"


def _candidate_metrics(
    frame: pd.DataFrame,
    condition: pd.Series,
    spec: AuditSpec,
    *,
    masks: dict[str, pd.Series],
    baseline: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    candidate = frame.copy()
    candidate["candidate_return_pct"] = pd.to_numeric(candidate["v156_account_return_pct"], errors="coerce").fillna(0.0)
    candidate["candidate_pnl_bps"] = pd.to_numeric(candidate["v156_account_pnl_bps"], errors="coerce").fillna(0.0)
    candidate.loc[condition, "candidate_return_pct"] *= spec.modifier
    candidate.loc[condition, "candidate_pnl_bps"] *= spec.modifier
    row: dict[str, object] = {
        "feature": spec.feature,
        "segment": spec.segment,
        "operator": spec.operator,
        "quantile": spec.quantile,
        "threshold": spec.threshold,
        "modifier": spec.modifier,
        "changed_trade_count": int(condition.sum()),
        "changed_selector_count": int((condition & masks["selector"]).sum()),
        "changed_holdout_count": int((condition & masks["holdout"]).sum()),
    }
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            f"candidate_{period}",
            candidate.loc[mask].copy(),
            return_col="candidate_return_pct",
            pnl_col="candidate_pnl_bps",
            baseline_months=baseline_months[period],
        )
        row[f"{period}_return_pct"] = metrics["total_account_return_pct"]
        row[f"{period}_delta_return_pct"] = (
            float(metrics["total_account_return_pct"]) - float(baseline[period]["total_account_return_pct"])
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
    row["rejection_reason"] = _rejection_reason(row, baseline)
    return row


def _return_possible(
    condition: pd.Series,
    modifier: float,
    *,
    returns: pd.Series,
    masks: dict[str, pd.Series],
) -> bool:
    for period in ("full", "selector", "holdout"):
        delta = float(returns[condition & masks[period]].sum()) * (modifier - 1.0)
        if period == "full" and delta < 0.0:
            return False
        if period != "full" and delta <= 0.0:
            return False
    return True


def _scan_candidates(
    frame: pd.DataFrame,
    *,
    masks: dict[str, pd.Series],
    baseline: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    features = _candidate_features(frame)
    segment_masks = _segment_masks(frame)
    returns = pd.to_numeric(frame["v156_account_return_pct"], errors="coerce").fillna(0.0)
    evaluated: list[dict[str, object]] = []
    fast_rows: list[dict[str, object]] = []
    for feature in features:
        values = pd.to_numeric(frame[feature], errors="coerce")
        for segment in SEGMENTS:
            selector_values = values[masks["selector"] & segment_masks[segment]].dropna()
            if len(selector_values) < 40 or selector_values.nunique() < 8:
                continue
            for quantile in QUANTILES:
                threshold = float(selector_values.quantile(quantile))
                for operator in ("<=", ">="):
                    probe = AuditSpec(
                        feature=feature,
                        segment=segment,
                        operator=operator,
                        quantile=quantile,
                        threshold=threshold,
                        modifier=1.0,
                    )
                    condition = _condition(frame, probe, segment_masks)
                    changed_selector = int((condition & masks["selector"]).sum())
                    changed_holdout = int((condition & masks["holdout"]).sum())
                    if changed_selector < MIN_CHANGED_SELECTOR_TRADES or changed_holdout < MIN_CHANGED_HOLDOUT_TRADES:
                        continue
                    for modifier in MODIFIERS:
                        full_delta = float(returns[condition & masks["full"]].sum()) * (modifier - 1.0)
                        selector_delta = float(returns[condition & masks["selector"]].sum()) * (modifier - 1.0)
                        holdout_delta = float(returns[condition & masks["holdout"]].sum()) * (modifier - 1.0)
                        fast_rows.append(
                            {
                                "feature": feature,
                                "segment": segment,
                                "operator": operator,
                                "quantile": quantile,
                                "threshold": threshold,
                                "modifier": modifier,
                                "changed_trade_count": int(condition.sum()),
                                "changed_selector_count": changed_selector,
                                "changed_holdout_count": changed_holdout,
                                "fast_full_delta_return_pct": full_delta,
                                "fast_selector_delta_return_pct": selector_delta,
                                "fast_holdout_delta_return_pct": holdout_delta,
                            }
                        )
                        if not _return_possible(condition, modifier, returns=returns, masks=masks):
                            continue
                        spec = AuditSpec(
                            feature=feature,
                            segment=segment,
                            operator=operator,
                            quantile=quantile,
                            threshold=threshold,
                            modifier=modifier,
                        )
                        evaluated.append(
                            _candidate_metrics(
                                frame,
                                condition,
                                spec,
                                masks=masks,
                                baseline=baseline,
                                baseline_months=baseline_months,
                            )
                        )
    return pd.DataFrame(evaluated), pd.DataFrame(fast_rows)


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    top_passed: pd.DataFrame,
    top_rejected: pd.DataFrame,
    rejection_summary: pd.DataFrame,
    fast_top: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V157 BTCUSDC Market Condition Post-Stepup Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v158']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Research Input",
        "",
        "- V157 audits whether a single market-condition overlay can safely improve V156.",
        "- Candidate features include trend, range, funding, premium, probability, and intraday activity fields.",
        "- Thresholds use selector-period quantiles only. Holdout is only used for validation.",
        "- This audit does not add trades, change sides, or promote a new live rule.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## Scan Summary",
        "",
        json.dumps(payload["scan_summary"], indent=2, sort_keys=True),
        "",
        "## Rejection Summary",
        "",
        rejection_summary.to_csv(index=False).strip() if not rejection_summary.empty else "No fully evaluated candidates.",
        "",
        "## Top Passed Candidates",
        "",
        top_passed.to_csv(index=False).strip() if not top_passed.empty else "No candidates passed the strict gate.",
        "",
        "## Top Rejected Return-Eligible Candidates",
        "",
        top_rejected.to_csv(index=False).strip() if not top_rejected.empty else "No return-eligible candidates.",
        "",
        "## Top Fast Return Candidates Before Risk Gate",
        "",
        fast_top.to_csv(index=False).strip() if not fast_top.empty else "No fast candidates.",
        "",
        "## Interpretation",
        "",
        (
            "V157 found a small set of market-condition overlays that clear the strict post-V156 return and risk gate. "
            "Most high-return raw candidates still fail through worse drawdown or thinner worst-month behavior, so only the passed candidates should be considered for promotion."
            if decision["promote_to_v158"]
            else "V157 found that market-condition fields can raise raw return estimates, but the return-eligible candidates fail the strict post-V156 risk gate, mainly through worse drawdown or thinner worst-month behavior. This supports using these fields as monitoring context rather than promoting them as a new sizing rule."
        ),
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V156_ACCOUNT_PATH.exists():
        v156.run()
    frame = pd.read_csv(V156_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    for column in ("v156_account_return_pct", "v156_account_pnl_bps"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    masks = _period_masks(frame)
    baseline, months = _baseline_metrics(frame, masks)
    evaluated, fast = _scan_candidates(frame, masks=masks, baseline=baseline, baseline_months=months)
    passed = evaluated[evaluated["rejection_reason"].eq("passed")].copy() if not evaluated.empty else pd.DataFrame()
    decision = {
        "status": "market_condition_overlay_not_promoted" if passed.empty else "market_condition_overlay_passed",
        "promote_to_v158": bool(not passed.empty),
        "message": (
            "No single market-condition overlay cleared the strict post-V156 return and risk gate."
            if passed.empty
            else "At least one single market-condition overlay cleared the strict post-V156 gate."
        ),
    }
    scan_summary = {
        "candidate_feature_count": len(_candidate_features(frame)),
        "fast_candidate_count": int(len(fast)),
        "return_eligible_candidate_count": int(len(evaluated)),
        "strict_pass_count": int(len(passed)),
        "min_changed_selector_trades": MIN_CHANGED_SELECTOR_TRADES,
        "min_changed_holdout_trades": MIN_CHANGED_HOLDOUT_TRADES,
        "uses_holdout_for_thresholds": False,
        "adds_new_trades": False,
    }
    payload = {
        "config": {
            "base": "v156_base_long_premium_stepup",
            "selector_end": SELECTOR_END.isoformat(),
            "quantiles": list(QUANTILES),
            "modifiers": list(MODIFIERS),
            "segments": list(SEGMENTS),
        },
        "baseline": baseline,
        "scan_summary": scan_summary,
        "decision": decision,
    }
    if not evaluated.empty:
        evaluated = evaluated.sort_values(["full_delta_return_pct", "holdout_delta_return_pct"], ascending=False)
    if not fast.empty:
        fast = fast.sort_values(["fast_full_delta_return_pct", "fast_holdout_delta_return_pct"], ascending=False)
    rejection_summary = (
        evaluated.groupby("rejection_reason", observed=False)
        .size()
        .reset_index(name="candidate_count")
        .sort_values(["candidate_count", "rejection_reason"], ascending=[False, True])
        if not evaluated.empty
        else pd.DataFrame(columns=["rejection_reason", "candidate_count"])
    )
    top_rejected_cols = [
        "feature",
        "segment",
        "operator",
        "quantile",
        "threshold",
        "modifier",
        "changed_trade_count",
        "changed_selector_count",
        "changed_holdout_count",
        "full_return_pct",
        "full_delta_return_pct",
        "full_max_drawdown_pct",
        "full_delta_drawdown_pct",
        "full_worst_month_pct",
        "full_delta_worst_month_pct",
        "selector_delta_return_pct",
        "selector_delta_drawdown_pct",
        "selector_delta_worst_month_pct",
        "holdout_delta_return_pct",
        "holdout_delta_drawdown_pct",
        "holdout_delta_worst_month_pct",
        "rejection_reason",
    ]
    top_passed = (
        evaluated[evaluated["rejection_reason"].eq("passed")]
        .sort_values(["full_delta_return_pct", "holdout_delta_return_pct"], ascending=False)
        if not evaluated.empty
        else pd.DataFrame()
    )
    top_rejected = (
        evaluated[~evaluated["rejection_reason"].eq("passed")]
        .sort_values(["full_delta_return_pct", "holdout_delta_return_pct"], ascending=False)
        if not evaluated.empty
        else pd.DataFrame()
    )
    fast_cols = [
        "feature",
        "segment",
        "operator",
        "quantile",
        "threshold",
        "modifier",
        "changed_trade_count",
        "changed_selector_count",
        "changed_holdout_count",
        "fast_full_delta_return_pct",
        "fast_selector_delta_return_pct",
        "fast_holdout_delta_return_pct",
    ]
    evaluated.to_csv(OUT_DIR / "v157_return_eligible_candidates.csv", index=False)
    fast.to_csv(OUT_DIR / "v157_fast_candidate_scan.csv", index=False)
    rejection_summary.to_csv(OUT_DIR / "v157_rejection_summary.csv", index=False)
    (OUT_DIR / "v157_market_condition_post_stepup_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(
        payload,
        pd.DataFrame(baseline.values()),
        top_passed.head(25)[top_rejected_cols] if not top_passed.empty else pd.DataFrame(columns=top_rejected_cols),
        top_rejected.head(25)[top_rejected_cols] if not top_rejected.empty else pd.DataFrame(columns=top_rejected_cols),
        rejection_summary,
        fast.head(25)[fast_cols] if not fast.empty else pd.DataFrame(columns=fast_cols),
    )
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
