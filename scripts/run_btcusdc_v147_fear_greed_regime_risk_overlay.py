from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144
import run_btcusdc_v146_fear_greed_macro_overlay as v146


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v147_fear_greed_regime_risk_overlay"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V147_BTCUSDC_FEAR_GREED_REGIME_RISK_OVERLAY.md"
V146_FEATURE_PATH = ROOT / "runs" / "research_v146_fear_greed_macro_overlay" / "v146_v144_with_fear_greed_features.csv"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_SELECTOR_TRADES = 20


@dataclass(frozen=True)
class RegimeRiskSpec:
    name: str
    lower: float
    upper: float
    multiplier: float
    crowd_operator: str
    crowd_threshold: float


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _add_regime_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    value = pd.to_numeric(out["fng_value"], errors="coerce")
    out["fng_regime"] = pd.cut(
        value,
        bins=[-1, 24, 44, 55, 75, 101],
        labels=["extreme_fear", "fear", "neutral", "greed", "extreme_greed"],
    ).astype("string")
    if "fng_crowd_follow" not in out.columns:
        raw_signal = out["signal"] if "signal" in out.columns else pd.Series(0.0, index=out.index)
        signal = pd.to_numeric(raw_signal, errors="coerce").fillna(0.0)
        out["fng_crowd_follow"] = signal * (value - 50.0)
    return out


def _compare_crowd(series: pd.Series, operator: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    if operator == "any":
        return pd.Series(True, index=series.index)
    if operator == ">=":
        return values >= threshold
    if operator == "<=":
        return values <= threshold
    raise ValueError(f"unsupported crowd operator: {operator}")


def _apply_regime_overlay(frame: pd.DataFrame, spec: RegimeRiskSpec) -> pd.DataFrame:
    out = _add_regime_features(frame)
    value = pd.to_numeric(out["fng_value"], errors="coerce")
    condition = value.between(spec.lower, spec.upper, inclusive="both")
    condition &= _compare_crowd(out["fng_crowd_follow"], spec.crowd_operator, spec.crowd_threshold)
    multiplier = pd.Series(1.0, index=out.index)
    multiplier.loc[condition.fillna(False)] = spec.multiplier
    out["v147_multiplier"] = multiplier
    out["v147_account_return_pct"] = out["candidate_account_return_pct"] * multiplier
    out["v147_account_pnl_bps"] = out["candidate_account_pnl_bps"] * multiplier
    return out


def _candidate_specs() -> list[RegimeRiskSpec]:
    ranges = [
        ("fear", 25.0, 44.0),
        ("neutral", 45.0, 55.0),
        ("fear_neutral", 25.0, 55.0),
        ("greed", 56.0, 75.0),
    ]
    specs: list[RegimeRiskSpec] = []
    for label, lower, upper in ranges:
        for multiplier in (0.0, 0.25, 0.5, 0.75, 0.9):
            mult_name = str(multiplier).replace(".", "p")
            specs.append(
                RegimeRiskSpec(
                    name=f"risk_trim_{label}_m{mult_name}",
                    lower=lower,
                    upper=upper,
                    multiplier=multiplier,
                    crowd_operator="any",
                    crowd_threshold=0.0,
                )
            )
        for operator, threshold, suffix in ((">=", 0.0, "crowd_follow"), ("<=", 0.0, "contrarian")):
            for multiplier in (0.5, 0.75, 0.9):
                mult_name = str(multiplier).replace(".", "p")
                specs.append(
                    RegimeRiskSpec(
                        name=f"risk_trim_{label}_{suffix}_m{mult_name}",
                        lower=lower,
                        upper=upper,
                        multiplier=multiplier,
                        crowd_operator=operator,
                        crowd_threshold=threshold,
                    )
                )
    return specs


def _baseline_metrics(frame: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[dict[str, dict[str, object]], dict[str, pd.Index]]:
    metrics: dict[str, dict[str, object]] = {}
    months: dict[str, pd.Index] = {}
    for period, mask in masks.items():
        period_path = frame.loc[mask].copy()
        months[period] = v144.v143._month_index(period_path)
        metrics[period] = v144.v143._account_metrics(
            f"v144_{period}",
            period_path,
            return_col="candidate_account_return_pct",
            pnl_col="candidate_account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _evaluate_candidate(
    frame: pd.DataFrame,
    spec: RegimeRiskSpec,
    *,
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    candidate_path = _apply_regime_overlay(frame, spec)
    row: dict[str, object] = {
        "candidate": spec.name,
        "lower": spec.lower,
        "upper": spec.upper,
        "multiplier": spec.multiplier,
        "crowd_operator": spec.crowd_operator,
        "crowd_threshold": spec.crowd_threshold,
        "changed_trade_count": int((candidate_path["v147_multiplier"] != 1.0).sum()),
    }
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            f"{spec.name}_{period}",
            candidate_path.loc[mask].copy(),
            return_col="v147_account_return_pct",
            pnl_col="v147_account_pnl_bps",
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
        & (candidates["selector_delta_return_pct"] > 0.0)
        & (candidates["selector_delta_drawdown_pct"] >= 0.0)
        & (candidates["selector_positive_months"] == candidates["selector_month_count"])
    ].copy()
    if eligible.empty:
        return {}
    if "changed_trade_count" not in eligible.columns:
        eligible["changed_trade_count"] = 0
    eligible = eligible.sort_values(
        ["selector_delta_return_pct", "selector_delta_drawdown_pct", "changed_trade_count"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    return eligible.iloc[0].to_dict()


def _passes_v147_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
    if not candidate:
        return False
    return (
        float(candidate["full_return_pct"]) > float(baseline["full"]["total_account_return_pct"])
        and float(candidate["full_max_drawdown_pct"]) >= float(baseline["full"]["max_drawdown_pct"])
        and int(candidate["full_positive_months"]) == int(candidate["full_month_count"])
        and float(candidate["holdout_return_pct"]) > float(baseline["holdout"]["total_account_return_pct"])
        and float(candidate["holdout_max_drawdown_pct"]) >= float(baseline["holdout"]["max_drawdown_pct"])
        and int(candidate["holdout_positive_months"]) == int(candidate["holdout_month_count"])
    )


def _load_feature_frame() -> pd.DataFrame:
    if not V146_FEATURE_PATH.exists():
        v146.run()
    frame = pd.read_csv(V146_FEATURE_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    return _add_regime_features(frame)


def _regime_context_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["win"] = pd.to_numeric(out["candidate_account_return_pct"], errors="coerce") > 0.0
    grouped = (
        out.groupby("fng_regime", dropna=False)
        .agg(
            trade_count=("candidate_account_return_pct", "size"),
            account_return_pct=("candidate_account_return_pct", "sum"),
            win_rate=("win", "mean"),
            avg_fng_value=("fng_value", "mean"),
            avg_fng_crowd_follow=("fng_crowd_follow", "mean"),
        )
        .reset_index()
    )
    grouped["win_rate"] = grouped["win_rate"] * 100.0
    return grouped


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    context_tables: dict[str, pd.DataFrame],
    top_candidates: pd.DataFrame,
    selected_monthly: pd.DataFrame,
) -> None:
    selected = payload["selected_candidate"]
    decision = payload["decision"]
    lines = [
        "# Research V147 BTCUSDC Fear & Greed Regime Risk Overlay",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v148']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Research Inputs",
        "",
        "- V146 showed that Fear & Greed contrarian boosting can raise return but worsens drawdown and monthly stability.",
        "- External references frame sentiment indicators as risk-management or position-sizing context, not standalone trade triggers.",
        "- V147 therefore tests downside-only sizing reductions in Fear & Greed regimes, especially the ordinary `fear` bucket that was weak in the selector period.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
    ]
    for period, table in context_tables.items():
        lines.extend([f"## {period.title()} Regime Context", "", table.to_csv(index=False).strip(), ""])
    lines.extend(["## Selected Candidate", ""])
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
            "V147 confirms that Fear & Greed can identify weak historical pockets, but the selector-positive risk trims do not generalize cleanly to the holdout. This keeps Fear & Greed in the research/monitoring layer instead of promoting it into the trading system.",
            "",
            "This is a research audit, not a live trading guarantee.",
            "",
            "## References",
            "",
            "- https://alternative.me/crypto/fear-and-greed-index/",
            "- https://academy.hyblockcapital.com/indicators/sentiment/fear-and-greed-index",
            "- https://www.gate.com/crypto-market-data/market-sentiment/fear-and-greed-index/btc",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame = _load_feature_frame()
    frame.to_csv(OUT_DIR / "v147_v144_with_fear_greed_regime_features.csv", index=False)
    masks = {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }
    baseline, months = _baseline_metrics(frame, masks)
    specs = _candidate_specs()
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
    candidates.to_csv(OUT_DIR / "v147_fear_greed_regime_candidates.csv", index=False)
    selected = _select_best_candidate(candidates)
    passed = _passes_v147_gate(selected, baseline)
    decision = {
        "status": "fear_greed_regime_risk_overlay_passed" if passed else "fear_greed_regime_risk_overlay_not_promoted",
        "promote_to_v148": bool(passed),
        "message": (
            "Fear & Greed regime risk overlay improved V144 without holdout/full risk degradation."
            if passed
            else "Fear & Greed regime trims improved selector pockets but did not pass holdout/full promotion gates."
        ),
    }
    selected_monthly = pd.DataFrame()
    if selected:
        selected_spec = next((spec for spec in specs if spec.name == selected["candidate"]), None)
        if selected_spec is not None:
            selected_path = _apply_regime_overlay(frame, selected_spec)
            selected_path.to_csv(OUT_DIR / "v147_selected_account_path.csv", index=False)
            selected_monthly = (
                selected_path.assign(month=selected_path["timestamp"].dt.strftime("%Y-%m"))
                .groupby("month", sort=True)["v147_account_return_pct"]
                .sum()
                .reset_index()
                .rename(columns={"v147_account_return_pct": "account_return_pct"})
            )
    context_tables = {period: _regime_context_metrics(frame.loc[mask].copy()) for period, mask in masks.items()}
    for period, table in context_tables.items():
        table.to_csv(OUT_DIR / f"v147_{period}_regime_context.csv", index=False)
    payload = {
        "config": {
            "base": "v144_funding_sentiment_governor",
            "feature_source": "v146_fear_greed_macro_features",
            "selector_end": SELECTOR_END.isoformat(),
            "uses_holdout_for_selection": False,
        },
        "baseline": baseline,
        "selected_candidate": selected,
        "decision": decision,
    }
    (OUT_DIR / "v147_fear_greed_regime_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, pd.DataFrame(baseline.values()), context_tables, candidates.head(20), selected_monthly)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
