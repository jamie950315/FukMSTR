from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144
import run_btcusdc_v149_confidence_persistence_overlay as v149


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v150_funding_persistence_overlay"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V150_BTCUSDC_FUNDING_PERSISTENCE_OVERLAY.md"
V149_ACCOUNT_PATH = ROOT / "runs" / "research_v149_confidence_persistence_overlay" / "v149_selected_account_path.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_SELECTOR_TRADES = 80
MIN_CHANGED_SELECTOR_TRADES = 40
MIN_FULL_IMPROVEMENT_RATE = 1.03
FUNDING_FEATURES = (
    "funding_crowd_follow_120d",
    "funding_z_120d",
    "funding_crowd_follow_30d",
    "funding_z_30d",
)


@dataclass(frozen=True)
class FundingPersistenceSpec:
    name: str
    feature: str
    operator: str
    quantile: float
    threshold: float
    multiplier: float


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _compare(series: pd.Series, operator: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if operator == ">=":
        return values >= threshold
    if operator == "<=":
        return values <= threshold
    raise ValueError(f"unsupported operator: {operator}")


def _candidate_specs(frame: pd.DataFrame, selector_mask: pd.Series) -> list[FundingPersistenceSpec]:
    specs: list[FundingPersistenceSpec] = []
    for feature in FUNDING_FEATURES:
        if feature not in frame.columns:
            continue
        values = pd.to_numeric(frame.loc[selector_mask, feature], errors="coerce").dropna()
        if values.nunique() < 8:
            continue
        for quantile, threshold in values.quantile([0.33, 0.5, 0.67, 0.75, 0.8, 0.85]).drop_duplicates().items():
            q_name = str(quantile).replace(".", "p")
            for multiplier in (1.05, 1.10, 1.15):
                mult_name = str(multiplier).replace(".", "p")
                specs.append(
                    FundingPersistenceSpec(
                        name=f"boost{mult_name}_{feature}_q{q_name}",
                        feature=feature,
                        operator=">=",
                        quantile=float(quantile),
                        threshold=float(threshold),
                        multiplier=float(multiplier),
                    )
                )
    return specs


def _apply_overlay(frame: pd.DataFrame, spec: FundingPersistenceSpec) -> pd.DataFrame:
    out = frame.copy()
    condition = _compare(out[spec.feature], spec.operator, spec.threshold)
    multiplier = pd.Series(1.0, index=out.index)
    multiplier.loc[condition.fillna(False)] = spec.multiplier
    out["v150_multiplier"] = multiplier
    out["v150_account_return_pct"] = out["v149_account_return_pct"] * multiplier
    out["v150_account_pnl_bps"] = out["v149_account_pnl_bps"] * multiplier
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
            f"v149_{period}",
            period_path,
            return_col="v149_account_return_pct",
            pnl_col="v149_account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _evaluate_candidate(
    frame: pd.DataFrame,
    spec: FundingPersistenceSpec,
    *,
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    candidate_path = _apply_overlay(frame, spec)
    changed = candidate_path["v150_multiplier"] != 1.0
    row: dict[str, object] = {
        "candidate": spec.name,
        "feature": spec.feature,
        "operator": spec.operator,
        "quantile": spec.quantile,
        "threshold": spec.threshold,
        "multiplier": spec.multiplier,
        "changed_trade_count": int(changed.sum()),
        "changed_selector_count": int((changed & masks["selector"]).sum()),
        "changed_holdout_count": int((changed & masks["holdout"]).sum()),
    }
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            f"{spec.name}_{period}",
            candidate_path.loc[mask].copy(),
            return_col="v150_account_return_pct",
            pnl_col="v150_account_pnl_bps",
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


def _select_best_candidate(candidates: pd.DataFrame) -> dict[str, object]:
    if candidates.empty:
        return {}
    eligible = candidates.loc[
        (candidates["selector_trade_count"] >= MIN_SELECTOR_TRADES)
        & (candidates["changed_selector_count"] >= MIN_CHANGED_SELECTOR_TRADES)
        & (candidates["selector_delta_return_pct"] > 0.0)
        & (candidates["selector_delta_drawdown_pct"] >= 0.0)
        & (candidates["selector_positive_months"] == candidates["selector_month_count"])
    ].copy()
    if eligible.empty:
        return {}
    eligible = eligible.sort_values(
        ["selector_delta_return_pct", "selector_delta_drawdown_pct", "changed_trade_count"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    return eligible.iloc[0].to_dict()


def _passes_v150_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
    if not candidate:
        return False
    return (
        float(candidate["full_return_pct"])
        >= float(baseline["full"]["total_account_return_pct"]) * MIN_FULL_IMPROVEMENT_RATE
        and float(candidate["full_max_drawdown_pct"]) >= float(baseline["full"]["max_drawdown_pct"])
        and int(candidate["full_positive_months"]) == int(candidate["full_month_count"])
        and float(candidate["holdout_return_pct"]) > float(baseline["holdout"]["total_account_return_pct"])
        and float(candidate["holdout_max_drawdown_pct"]) >= float(baseline["holdout"]["max_drawdown_pct"])
        and int(candidate["holdout_positive_months"]) == int(candidate["holdout_month_count"])
    )


def _funding_context_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["funding_bucket"] = pd.qcut(
        pd.to_numeric(out["funding_crowd_follow_120d"], errors="coerce"),
        q=5,
        duplicates="drop",
    )
    out["win"] = pd.to_numeric(out["v149_account_return_pct"], errors="coerce") > 0.0
    grouped = (
        out.groupby("funding_bucket", observed=False)
        .agg(
            trade_count=("v149_account_return_pct", "size"),
            account_return_pct=("v149_account_return_pct", "sum"),
            win_rate=("win", "mean"),
            avg_funding_crowd_follow_120d=("funding_crowd_follow_120d", "mean"),
            avg_funding_rate_bps=("funding_rate_bps", "mean"),
        )
        .reset_index()
    )
    grouped["funding_bucket"] = grouped["funding_bucket"].astype(str)
    grouped["win_rate"] = grouped["win_rate"] * 100.0
    return grouped


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    context_table: pd.DataFrame,
    top_candidates: pd.DataFrame,
    selected_monthly: pd.DataFrame,
) -> None:
    selected = payload["selected_candidate"]
    decision = payload["decision"]
    lines = [
        "# Research V150 BTCUSDC Funding Persistence Overlay",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v151']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Research Input",
        "",
        "- V150 tests whether longer-horizon funding context can improve V149 sizing.",
        "- Candidate selection uses only the pre-2026 selector period. The 2026 holdout is reported after selection.",
        "- The overlay does not add new trades. It only changes sizing on existing V149 trades.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## Funding Context Metrics",
        "",
        context_table.to_csv(index=False).strip(),
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
            "## Selected Monthly Account Return",
            "",
            selected_monthly.to_csv(index=False).strip() if not selected_monthly.empty else "No selected candidate.",
            "",
            "## Top Selector Candidates",
            "",
            top_candidates.to_csv(index=False).strip() if not top_candidates.empty else "No candidates.",
            "",
            "## Interpretation",
            "",
            "V150 suggests funding is still useful after V149, but only as a sizing overlay on existing trades. It does not create new entries and it keeps holdout selection separate from selector-period candidate choice.",
            "",
            "This is a research audit, not a live trading guarantee.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V149_ACCOUNT_PATH.exists():
        v149.run()
    frame = pd.read_csv(V149_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    for column in ("v149_account_return_pct", "v149_account_pnl_bps"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    masks = _period_masks(frame)
    baseline, months = _baseline_metrics(frame, masks)
    specs = _candidate_specs(frame, masks["selector"])
    candidates = pd.DataFrame(
        [
            _evaluate_candidate(frame, spec, masks=masks, baseline_metrics=baseline, baseline_months=months)
            for spec in specs
        ]
    )
    if not candidates.empty:
        candidates = candidates.sort_values(
            ["selector_delta_return_pct", "selector_delta_drawdown_pct", "changed_trade_count"],
            ascending=[False, False, True],
            kind="mergesort",
        )
    candidates.to_csv(OUT_DIR / "v150_funding_persistence_candidates.csv", index=False)
    selected = _select_best_candidate(candidates)
    passed = _passes_v150_gate(selected, baseline)
    decision = {
        "status": "funding_persistence_overlay_passed" if passed else "funding_persistence_overlay_not_promoted",
        "promote_to_v151": bool(passed),
        "message": (
            "Funding persistence improved V149 without worsening holdout/full risk gates."
            if passed
            else "Funding persistence did not clear the promotion gate."
        ),
    }
    payload = {
        "config": {
            "base": "v149_confidence_persistence_overlay",
            "selector_end": SELECTOR_END.isoformat(),
            "min_full_improvement_rate": MIN_FULL_IMPROVEMENT_RATE,
            "min_changed_selector_trades": MIN_CHANGED_SELECTOR_TRADES,
            "uses_holdout_for_selection": False,
            "adds_new_trades": False,
        },
        "baseline": baseline,
        "selected_candidate": selected,
        "decision": decision,
    }
    selected_monthly = pd.DataFrame()
    if selected:
        selected_spec = next((spec for spec in specs if spec.name == selected["candidate"]), None)
        if selected_spec is not None:
            selected_path = _apply_overlay(frame, selected_spec)
            selected_path.to_csv(OUT_DIR / "v150_selected_account_path.csv", index=False)
            selected_monthly = (
                selected_path.assign(month=selected_path["timestamp"].dt.strftime("%Y-%m"))
                .groupby("month", sort=True)["v150_account_return_pct"]
                .sum()
                .reset_index()
                .rename(columns={"v150_account_return_pct": "account_return_pct"})
            )
    context_table = _funding_context_metrics(frame)
    context_table.to_csv(OUT_DIR / "v150_funding_context_metrics.csv", index=False)
    (OUT_DIR / "v150_funding_persistence_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, pd.DataFrame(baseline.values()), context_table, candidates.head(20), selected_monthly)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
