from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144
import run_btcusdc_v154_rescue_funding_stabilizer as v154


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v155_base_long_premium_expansion"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V155_BTCUSDC_BASE_LONG_PREMIUM_EXPANSION.md"
V154_ACCOUNT_PATH = ROOT / "runs" / "research_v154_rescue_funding_stabilizer" / "v154_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_CHANGED_SELECTOR_TRADES = 80
MIN_CHANGED_HOLDOUT_TRADES = 20
MIN_FULL_IMPROVEMENT_RATE = 1.03
FEATURE = "premium_abs_bps"
SEGMENT = "base_long"
OPERATOR = "<="
QUANTILE = 0.60
MODIFIER = 1.075


@dataclass(frozen=True)
class BaseLongPremiumSpec:
    name: str
    feature: str
    segment: str
    operator: str
    quantile: float
    threshold: float
    modifier: float


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _compare(series: pd.Series, operator: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if operator == "<=":
        return values <= threshold
    if operator == ">=":
        return values >= threshold
    raise ValueError(f"unsupported operator: {operator}")


def _segment_mask(frame: pd.DataFrame, segment: str) -> pd.Series:
    if segment == "base_long":
        return frame["leg"].eq("base") & frame["side"].eq("long")
    raise ValueError(f"unsupported segment: {segment}")


def _overlay_spec(frame: pd.DataFrame, selector_mask: pd.Series, *, min_unique: int = 8) -> BaseLongPremiumSpec:
    mask = selector_mask & _segment_mask(frame, SEGMENT)
    values = pd.to_numeric(frame.loc[mask, FEATURE], errors="coerce").dropna()
    if values.nunique() < min_unique:
        raise ValueError(f"not enough selector values for {SEGMENT}:{FEATURE}")
    threshold = float(values.quantile(QUANTILE))
    return BaseLongPremiumSpec(
        name=f"{SEGMENT}_{FEATURE}_{OPERATOR}_q{str(QUANTILE).replace('.', 'p')}_expansion",
        feature=FEATURE,
        segment=SEGMENT,
        operator=OPERATOR,
        quantile=QUANTILE,
        threshold=threshold,
        modifier=MODIFIER,
    )


def _condition(frame: pd.DataFrame, spec: BaseLongPremiumSpec) -> pd.Series:
    return _segment_mask(frame, spec.segment) & _compare(frame[spec.feature], spec.operator, spec.threshold)


def _apply_overlay(frame: pd.DataFrame, spec: BaseLongPremiumSpec) -> pd.DataFrame:
    out = frame.copy()
    flag = _condition(out, spec).fillna(False)
    modifier = pd.Series(1.0, index=out.index)
    modifier.loc[flag] = spec.modifier
    out["v155_base_long_premium_flag"] = flag
    out["v155_modifier"] = modifier
    out["v155_account_return_pct"] = out["v154_account_return_pct"] * modifier
    out["v155_account_pnl_bps"] = out["v154_account_pnl_bps"] * modifier
    return out


def _period_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }


def _baseline_metrics(frame: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[dict[str, dict[str, object]], dict[str, pd.Index]]:
    metrics: dict[str, dict[str, object]] = {}
    months: dict[str, pd.Index] = {}
    for period, mask in masks.items():
        period_path = frame.loc[mask].copy()
        months[period] = v144.v143._month_index(period_path)
        metrics[period] = v144.v143._account_metrics(
            f"v154_{period}",
            period_path,
            return_col="v154_account_return_pct",
            pnl_col="v154_account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _candidate_metrics(
    baseline_path: pd.DataFrame,
    candidate_path: pd.DataFrame,
    *,
    spec: BaseLongPremiumSpec,
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    changed = candidate_path["v155_modifier"] != 1.0
    flag = candidate_path["v155_base_long_premium_flag"]
    row: dict[str, object] = {
        "candidate": "v155_base_long_premium_expansion",
        "feature": spec.feature,
        "segment": spec.segment,
        "operator": spec.operator,
        "quantile": spec.quantile,
        "threshold": spec.threshold,
        "modifier": spec.modifier,
        "changed_trade_count": int(changed.sum()),
        "changed_selector_count": int((changed & masks["selector"]).sum()),
        "changed_holdout_count": int((changed & masks["holdout"]).sum()),
        "flag_trade_count": int(flag.sum()),
        "flag_selector_count": int((flag & masks["selector"]).sum()),
        "flag_holdout_count": int((flag & masks["holdout"]).sum()),
        "baseline_trade_count": int(len(baseline_path)),
    }
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            f"v155_{period}",
            candidate_path.loc[mask].copy(),
            return_col="v155_account_return_pct",
            pnl_col="v155_account_pnl_bps",
            baseline_months=baseline_months[period],
        )
        base = baseline_metrics[period]
        row[f"{period}_trade_count"] = metrics["trade_count"]
        row[f"{period}_return_pct"] = metrics["total_account_return_pct"]
        row[f"{period}_delta_return_pct"] = (
            float(metrics["total_account_return_pct"]) - float(base["total_account_return_pct"])
        )
        row[f"{period}_max_drawdown_pct"] = metrics["max_drawdown_pct"]
        row[f"{period}_delta_drawdown_pct"] = (
            float(metrics["max_drawdown_pct"]) - float(base["max_drawdown_pct"])
        )
        row[f"{period}_positive_months"] = metrics["positive_months"]
        row[f"{period}_month_count"] = metrics["month_count"]
        row[f"{period}_worst_month_pct"] = metrics["worst_month_pct"]
        row[f"{period}_win_rate"] = metrics["win_rate"]
    return row


def _passes_v155_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
    if not candidate:
        return False
    return (
        int(candidate["changed_selector_count"]) >= MIN_CHANGED_SELECTOR_TRADES
        and int(candidate["changed_holdout_count"]) >= MIN_CHANGED_HOLDOUT_TRADES
        and float(candidate["full_return_pct"])
        >= float(baseline["full"]["total_account_return_pct"]) * MIN_FULL_IMPROVEMENT_RATE
        and float(candidate["full_max_drawdown_pct"]) >= float(baseline["full"]["max_drawdown_pct"])
        and int(candidate["full_positive_months"]) == int(candidate["full_month_count"])
        and float(candidate["selector_return_pct"]) > float(baseline["selector"]["total_account_return_pct"])
        and float(candidate["selector_max_drawdown_pct"]) >= float(baseline["selector"]["max_drawdown_pct"])
        and int(candidate["selector_positive_months"]) == int(candidate["selector_month_count"])
        and float(candidate["holdout_return_pct"]) > float(baseline["holdout"]["total_account_return_pct"])
        and float(candidate["holdout_max_drawdown_pct"]) >= float(baseline["holdout"]["max_drawdown_pct"])
        and int(candidate["holdout_positive_months"]) == int(candidate["holdout_month_count"])
    )


def _context_metrics(frame: pd.DataFrame, candidate_path: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["v155_bucket"] = "unchanged"
    out.loc[candidate_path["v155_base_long_premium_flag"], "v155_bucket"] = "base_long_premium_expansion"
    out["win"] = pd.to_numeric(out["v154_account_return_pct"], errors="coerce") > 0.0
    grouped = (
        out.groupby("v155_bucket", observed=False)
        .agg(
            trade_count=("v154_account_return_pct", "size"),
            v154_account_return_pct=("v154_account_return_pct", "sum"),
            win_rate=("win", "mean"),
            avg_premium_abs_bps=("premium_abs_bps", "mean"),
            avg_premium_crowd_follow_120d=("premium_crowd_follow_120d", "mean"),
            avg_trend_abs_60_bps=("trend_abs_60_bps", "mean"),
        )
        .reset_index()
    )
    grouped["win_rate"] = grouped["win_rate"] * 100.0
    return grouped


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    context_table: pd.DataFrame,
    selected_monthly: pd.DataFrame,
) -> None:
    candidate = payload["selected_candidate"]
    decision = payload["decision"]
    lines = [
        "# Research V155 BTCUSDC Base Long Premium Expansion",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v156']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Research Input",
        "",
        "- V155 tests whether the calm-premium base-long zone can be modestly expanded on top of V154.",
        f"- Expansion: `{SEGMENT}` trades where `{FEATURE} {OPERATOR} selector q{QUANTILE}` use `{MODIFIER}x` sizing.",
        "- The overlay does not add new trades. It only changes sizing on existing V154 trades.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## V155 Context Metrics",
        "",
        context_table.to_csv(index=False).strip(),
        "",
        "## Selected Candidate",
        "",
    ]
    lines.extend(pd.DataFrame([candidate]).to_csv(index=False).strip().splitlines())
    lines.extend(
        [
            "",
            "## Selected Monthly Account Return",
            "",
            selected_monthly.to_csv(index=False).strip(),
            "",
            "## Interpretation",
            "",
            "V155 suggests that V154 still under-sizes a broad base-long calm-premium zone. This is a sizing expansion only: it does not add entries, change sides, or use holdout data to set the threshold.",
            "",
            "This is a research audit, not a live trading guarantee.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V154_ACCOUNT_PATH.exists():
        v154.run()
    frame = pd.read_csv(V154_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    for column in ("v154_account_return_pct", "v154_account_pnl_bps"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    masks = _period_masks(frame)
    baseline, months = _baseline_metrics(frame, masks)
    spec = _overlay_spec(frame, masks["selector"])
    selected_path = _apply_overlay(frame, spec)
    selected = _candidate_metrics(
        frame,
        selected_path,
        spec=spec,
        masks=masks,
        baseline_metrics=baseline,
        baseline_months=months,
    )
    passed = _passes_v155_gate(selected, baseline)
    decision = {
        "status": "base_long_premium_expansion_passed" if passed else "base_long_premium_expansion_not_promoted",
        "promote_to_v156": bool(passed),
        "message": (
            "Base-long premium expansion improved V154 by at least 3% without worsening selector/full/holdout risk gates."
            if passed
            else "Base-long premium expansion did not clear the promotion gate."
        ),
    }
    payload = {
        "config": {
            "base": "v154_rescue_funding_stabilizer",
            "selector_end": SELECTOR_END.isoformat(),
            "min_full_improvement_rate": MIN_FULL_IMPROVEMENT_RATE,
            "min_changed_selector_trades": MIN_CHANGED_SELECTOR_TRADES,
            "min_changed_holdout_trades": MIN_CHANGED_HOLDOUT_TRADES,
            "uses_holdout_for_thresholds": False,
            "adds_new_trades": False,
        },
        "baseline": baseline,
        "spec": spec.__dict__,
        "selected_candidate": selected,
        "decision": decision,
    }
    selected_path.to_csv(OUT_DIR / "v155_selected_account_path.csv", index=False)
    pd.DataFrame([selected]).to_csv(OUT_DIR / "v155_base_long_premium_expansion_candidate.csv", index=False)
    selected_monthly = (
        selected_path.assign(month=selected_path["timestamp"].dt.strftime("%Y-%m"))
        .groupby("month", sort=True)["v155_account_return_pct"]
        .sum()
        .reset_index()
        .rename(columns={"v155_account_return_pct": "account_return_pct"})
    )
    selected_monthly.to_csv(OUT_DIR / "v155_monthly_account_return.csv", index=False)
    context_table = _context_metrics(frame, selected_path)
    context_table.to_csv(OUT_DIR / "v155_base_long_premium_context_metrics.csv", index=False)
    (OUT_DIR / "v155_base_long_premium_expansion_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, pd.DataFrame(baseline.values()), context_table, selected_monthly)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
