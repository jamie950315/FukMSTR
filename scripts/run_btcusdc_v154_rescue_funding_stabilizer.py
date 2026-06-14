from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144
import run_btcusdc_v153_premium_balance_overlay as v153


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v154_rescue_funding_stabilizer"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V154_BTCUSDC_RESCUE_FUNDING_STABILIZER.md"
V153_ACCOUNT_PATH = ROOT / "runs" / "research_v153_premium_balance_overlay" / "v153_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_CHANGED_SELECTOR_TRADES = 60
MIN_CHANGED_HOLDOUT_TRADES = 20
MIN_FULL_IMPROVEMENT_RATE = 1.03
BOOST_FEATURE = "funding_abs_z_30d"
BOOST_SEGMENT = "rescue_long"
BOOST_OPERATOR = "<="
BOOST_QUANTILE = 0.60
BOOST_MODIFIER = 1.10
STABILIZER_FEATURE = "premium_crowd_follow_120d"
STABILIZER_SEGMENT = "base_long"
STABILIZER_OPERATOR = "<="
STABILIZER_QUANTILE = 0.10
STABILIZER_MODIFIER = 0.90


@dataclass(frozen=True)
class RescueFundingSpec:
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
    if segment == "rescue_long":
        return frame["leg"].eq("rescue") & frame["side"].eq("long")
    if segment == "base_long":
        return frame["leg"].eq("base") & frame["side"].eq("long")
    raise ValueError(f"unsupported segment: {segment}")


def _spec_threshold(
    frame: pd.DataFrame,
    selector_mask: pd.Series,
    *,
    feature: str,
    segment: str,
    quantile: float,
    min_unique: int = 8,
) -> float:
    mask = selector_mask & _segment_mask(frame, segment)
    values = pd.to_numeric(frame.loc[mask, feature], errors="coerce").dropna()
    if values.nunique() < min_unique:
        raise ValueError(f"not enough selector values for {segment}:{feature}")
    return float(values.quantile(quantile))


def _overlay_specs(
    frame: pd.DataFrame,
    selector_mask: pd.Series,
    *,
    min_unique: int = 8,
) -> dict[str, RescueFundingSpec]:
    boost_threshold = _spec_threshold(
        frame,
        selector_mask,
        feature=BOOST_FEATURE,
        segment=BOOST_SEGMENT,
        quantile=BOOST_QUANTILE,
        min_unique=min_unique,
    )
    stabilizer_threshold = _spec_threshold(
        frame,
        selector_mask,
        feature=STABILIZER_FEATURE,
        segment=STABILIZER_SEGMENT,
        quantile=STABILIZER_QUANTILE,
        min_unique=min_unique,
    )
    return {
        "boost": RescueFundingSpec(
            name=f"{BOOST_SEGMENT}_{BOOST_FEATURE}_{BOOST_OPERATOR}_q{str(BOOST_QUANTILE).replace('.', 'p')}_boost",
            feature=BOOST_FEATURE,
            segment=BOOST_SEGMENT,
            operator=BOOST_OPERATOR,
            quantile=BOOST_QUANTILE,
            threshold=boost_threshold,
            modifier=BOOST_MODIFIER,
        ),
        "stabilizer": RescueFundingSpec(
            name=(
                f"{STABILIZER_SEGMENT}_{STABILIZER_FEATURE}_{STABILIZER_OPERATOR}_"
                f"q{str(STABILIZER_QUANTILE).replace('.', 'p')}_stabilizer"
            ),
            feature=STABILIZER_FEATURE,
            segment=STABILIZER_SEGMENT,
            operator=STABILIZER_OPERATOR,
            quantile=STABILIZER_QUANTILE,
            threshold=stabilizer_threshold,
            modifier=STABILIZER_MODIFIER,
        ),
    }


def _condition(frame: pd.DataFrame, spec: RescueFundingSpec) -> pd.Series:
    return _segment_mask(frame, spec.segment) & _compare(frame[spec.feature], spec.operator, spec.threshold)


def _apply_overlay(frame: pd.DataFrame, specs: dict[str, RescueFundingSpec]) -> pd.DataFrame:
    out = frame.copy()
    boost_flag = _condition(out, specs["boost"]).fillna(False)
    stabilizer_flag = _condition(out, specs["stabilizer"]).fillna(False)
    modifier = pd.Series(1.0, index=out.index)
    modifier.loc[boost_flag] = modifier.loc[boost_flag] * specs["boost"].modifier
    modifier.loc[stabilizer_flag] = modifier.loc[stabilizer_flag] * specs["stabilizer"].modifier
    out["v154_boost_flag"] = boost_flag
    out["v154_stabilizer_flag"] = stabilizer_flag
    out["v154_modifier"] = modifier
    out["v154_account_return_pct"] = out["v153_account_return_pct"] * modifier
    out["v154_account_pnl_bps"] = out["v153_account_pnl_bps"] * modifier
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
            f"v153_{period}",
            period_path,
            return_col="v153_account_return_pct",
            pnl_col="v153_account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _candidate_metrics(
    baseline_path: pd.DataFrame,
    candidate_path: pd.DataFrame,
    *,
    specs: dict[str, RescueFundingSpec],
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    changed = candidate_path["v154_modifier"] != 1.0
    boost = candidate_path["v154_boost_flag"]
    stabilizer = candidate_path["v154_stabilizer_flag"]
    row: dict[str, object] = {
        "candidate": "v154_rescue_funding_stabilizer",
        "boost_feature": specs["boost"].feature,
        "boost_segment": specs["boost"].segment,
        "boost_operator": specs["boost"].operator,
        "boost_quantile": specs["boost"].quantile,
        "boost_threshold": specs["boost"].threshold,
        "boost_modifier": specs["boost"].modifier,
        "stabilizer_feature": specs["stabilizer"].feature,
        "stabilizer_segment": specs["stabilizer"].segment,
        "stabilizer_operator": specs["stabilizer"].operator,
        "stabilizer_quantile": specs["stabilizer"].quantile,
        "stabilizer_threshold": specs["stabilizer"].threshold,
        "stabilizer_modifier": specs["stabilizer"].modifier,
        "changed_trade_count": int(changed.sum()),
        "changed_selector_count": int((changed & masks["selector"]).sum()),
        "changed_holdout_count": int((changed & masks["holdout"]).sum()),
        "boost_trade_count": int(boost.sum()),
        "boost_selector_count": int((boost & masks["selector"]).sum()),
        "boost_holdout_count": int((boost & masks["holdout"]).sum()),
        "stabilizer_trade_count": int(stabilizer.sum()),
        "stabilizer_selector_count": int((stabilizer & masks["selector"]).sum()),
        "stabilizer_holdout_count": int((stabilizer & masks["holdout"]).sum()),
        "overlap_trade_count": int((boost & stabilizer).sum()),
        "baseline_trade_count": int(len(baseline_path)),
    }
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            f"v154_{period}",
            candidate_path.loc[mask].copy(),
            return_col="v154_account_return_pct",
            pnl_col="v154_account_pnl_bps",
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


def _passes_v154_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
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
    out["v154_bucket"] = "unchanged"
    out.loc[candidate_path["v154_boost_flag"], "v154_bucket"] = "boost"
    out.loc[candidate_path["v154_stabilizer_flag"], "v154_bucket"] = "stabilizer"
    out["win"] = pd.to_numeric(out["v153_account_return_pct"], errors="coerce") > 0.0
    grouped = (
        out.groupby("v154_bucket", observed=False)
        .agg(
            trade_count=("v153_account_return_pct", "size"),
            v153_account_return_pct=("v153_account_return_pct", "sum"),
            win_rate=("win", "mean"),
            avg_funding_abs_z_30d=("funding_abs_z_30d", "mean"),
            avg_premium_crowd_follow_120d=("premium_crowd_follow_120d", "mean"),
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
        "# Research V154 BTCUSDC Rescue Funding Stabilizer",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v155']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Research Input",
        "",
        "- V154 tests a fixed rescue funding boost plus premium stress stabilizer on top of V153.",
        f"- Boost: `{BOOST_SEGMENT}` trades where `{BOOST_FEATURE} {BOOST_OPERATOR} selector q{BOOST_QUANTILE}` use `{BOOST_MODIFIER}x` sizing.",
        f"- Stabilizer: `{STABILIZER_SEGMENT}` trades where `{STABILIZER_FEATURE} {STABILIZER_OPERATOR} selector q{STABILIZER_QUANTILE}` use `{STABILIZER_MODIFIER}x` sizing.",
        "- The overlay does not add new trades. It only changes sizing on existing V153 trades.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## V154 Context Metrics",
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
            "V154 suggests that V153 rescue-long trades remain strongest when funding pressure is not extreme. It adds a small rescue boost in calm funding states and a small extra stabilizer to the already identified weak base-long premium crowd-follow zone.",
            "",
            "This is a research audit, not a live trading guarantee.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V153_ACCOUNT_PATH.exists():
        v153.run()
    frame = pd.read_csv(V153_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    for column in ("v153_account_return_pct", "v153_account_pnl_bps"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    masks = _period_masks(frame)
    baseline, months = _baseline_metrics(frame, masks)
    specs = _overlay_specs(frame, masks["selector"])
    selected_path = _apply_overlay(frame, specs)
    selected = _candidate_metrics(
        frame,
        selected_path,
        specs=specs,
        masks=masks,
        baseline_metrics=baseline,
        baseline_months=months,
    )
    passed = _passes_v154_gate(selected, baseline)
    decision = {
        "status": "rescue_funding_stabilizer_passed" if passed else "rescue_funding_stabilizer_not_promoted",
        "promote_to_v155": bool(passed),
        "message": (
            "Rescue funding stabilizer improved V153 by at least 3% without worsening selector/full/holdout risk gates."
            if passed
            else "Rescue funding stabilizer did not clear the promotion gate."
        ),
    }
    payload = {
        "config": {
            "base": "v153_premium_balance_overlay",
            "selector_end": SELECTOR_END.isoformat(),
            "min_full_improvement_rate": MIN_FULL_IMPROVEMENT_RATE,
            "min_changed_selector_trades": MIN_CHANGED_SELECTOR_TRADES,
            "min_changed_holdout_trades": MIN_CHANGED_HOLDOUT_TRADES,
            "uses_holdout_for_thresholds": False,
            "adds_new_trades": False,
        },
        "baseline": baseline,
        "specs": {name: spec.__dict__ for name, spec in specs.items()},
        "selected_candidate": selected,
        "decision": decision,
    }
    selected_path.to_csv(OUT_DIR / "v154_selected_account_path.csv", index=False)
    pd.DataFrame([selected]).to_csv(OUT_DIR / "v154_rescue_funding_stabilizer_candidate.csv", index=False)
    selected_monthly = (
        selected_path.assign(month=selected_path["timestamp"].dt.strftime("%Y-%m"))
        .groupby("month", sort=True)["v154_account_return_pct"]
        .sum()
        .reset_index()
        .rename(columns={"v154_account_return_pct": "account_return_pct"})
    )
    selected_monthly.to_csv(OUT_DIR / "v154_monthly_account_return.csv", index=False)
    context_table = _context_metrics(frame, selected_path)
    context_table.to_csv(OUT_DIR / "v154_rescue_funding_context_metrics.csv", index=False)
    (OUT_DIR / "v154_rescue_funding_stabilizer_summary.json").write_text(
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
