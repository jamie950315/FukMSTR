from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v146_fear_greed_macro_overlay"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V146_BTCUSDC_FEAR_GREED_MACRO_OVERLAY.md"
V144_ACCOUNT_PATH = ROOT / "runs" / "research_v144_funding_sentiment_governor" / "v144_selected_account_path.csv"
FNG_CACHE = OUT_DIR / "fear_greed_index.csv"
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_SELECTOR_TRADES = 80
MIN_FULL_IMPROVEMENT_RATE = 1.03


@dataclass(frozen=True)
class MacroOverlaySpec:
    name: str
    policy_type: str
    crowd_operator: str
    crowd_threshold: float
    extreme_threshold: float
    multiplier: float


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _request_json(url: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "FukMSTR-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Fear & Greed response: {payload!r}")
    if payload.get("metadata", {}).get("error"):
        raise RuntimeError(f"Fear & Greed API error: {payload['metadata']['error']}")
    return payload


def _parse_fng_payload(payload: dict[str, object]) -> pd.DataFrame:
    rows = payload.get("data", [])
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("No Fear & Greed rows returned")
    frame = pd.DataFrame(rows)
    out = pd.DataFrame(
        {
            "fng_time": pd.to_datetime(pd.to_numeric(frame["timestamp"]), unit="s", utc=True).astype(
                "datetime64[ns, UTC]"
            ),
            "fng_value": pd.to_numeric(frame["value"], errors="coerce").astype("Int64"),
            "fng_classification": frame["value_classification"].astype(str),
        }
    )
    return out.dropna(subset=["fng_value"]).sort_values("fng_time", kind="mergesort").reset_index(drop=True)


def _download_fng_index() -> pd.DataFrame:
    return _parse_fng_payload(_request_json(FNG_URL))


def _load_or_download_fng(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if FNG_CACHE.exists():
        cached = pd.read_csv(FNG_CACHE)
        cached["fng_time"] = _to_utc(cached["fng_time"])
        if cached["fng_time"].min() <= start.floor("D") and cached["fng_time"].max() >= end.floor("D"):
            return cached.sort_values("fng_time", kind="mergesort").reset_index(drop=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fng = _download_fng_index()
    fng.to_csv(FNG_CACHE, index=False)
    return fng


def _join_prior_fng(trades: pd.DataFrame, fng: pd.DataFrame) -> pd.DataFrame:
    left = trades.copy()
    right = fng.copy()
    left["timestamp"] = _to_utc(left["timestamp"])
    right["fng_time"] = _to_utc(right["fng_time"])
    return pd.merge_asof(
        left.sort_values("timestamp", kind="mergesort"),
        right.sort_values("fng_time", kind="mergesort"),
        left_on="timestamp",
        right_on="fng_time",
        direction="backward",
        allow_exact_matches=True,
    ).reset_index(drop=True)


def _add_fng_macro_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    signal = pd.to_numeric(out["signal"], errors="coerce").fillna(0.0)
    out["fng_value"] = pd.to_numeric(out["fng_value"], errors="coerce")
    out["fng_centered"] = out["fng_value"] - 50.0
    out["fng_extreme_distance"] = out["fng_centered"].abs()
    out["fng_crowd_follow"] = signal * out["fng_centered"]
    out["fng_contrarian_alignment"] = -out["fng_crowd_follow"]
    out["fng_extreme_fear"] = out["fng_value"] <= 24.0
    out["fng_extreme_greed"] = out["fng_value"] >= 76.0
    out["fng_is_extreme"] = out["fng_extreme_fear"] | out["fng_extreme_greed"]
    out["fng_value_7d_change"] = out["fng_value"].diff(7).fillna(0.0)
    out["fng_value_30d_mean"] = out["fng_value"].rolling(window=30, min_periods=5).mean().fillna(out["fng_value"])
    return out


def _compare(series: pd.Series, operator: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if operator == ">=":
        return values >= threshold
    if operator == "<=":
        return values <= threshold
    raise ValueError(f"unsupported operator: {operator}")


def _candidate_specs(frame: pd.DataFrame, selector_mask: pd.Series) -> list[MacroOverlaySpec]:
    selector = frame.loc[selector_mask].copy()
    crowd = pd.to_numeric(selector["fng_crowd_follow"], errors="coerce").dropna()
    extreme = pd.to_numeric(selector["fng_extreme_distance"], errors="coerce").dropna()
    if crowd.nunique() < 4 or extreme.nunique() < 4:
        return []
    crowd_quantiles = crowd.quantile([0.2, 0.33, 0.67, 0.8]).drop_duplicates()
    extreme_quantiles = extreme.quantile([0.5, 0.67, 0.8]).drop_duplicates()
    specs: list[MacroOverlaySpec] = []
    for c_quantile, c_threshold in crowd_quantiles.items():
        c_name = str(c_quantile).replace(".", "p")
        for e_quantile, e_threshold in extreme_quantiles.items():
            e_name = str(e_quantile).replace(".", "p")
            specs.append(
                MacroOverlaySpec(
                    name=f"halfsize_macro_crowd_q{c_name}_e{e_name}",
                    policy_type="halfsize_macro_crowd",
                    crowd_operator=">=",
                    crowd_threshold=float(c_threshold),
                    extreme_threshold=float(e_threshold),
                    multiplier=0.5,
                )
            )
            specs.append(
                MacroOverlaySpec(
                    name=f"trim75_macro_crowd_q{c_name}_e{e_name}",
                    policy_type="trim_macro_crowd",
                    crowd_operator=">=",
                    crowd_threshold=float(c_threshold),
                    extreme_threshold=float(e_threshold),
                    multiplier=0.75,
                )
            )
            specs.append(
                MacroOverlaySpec(
                    name=f"boost110_macro_contrarian_q{c_name}_e{e_name}",
                    policy_type="boost_macro_contrarian",
                    crowd_operator="<=",
                    crowd_threshold=float(c_threshold),
                    extreme_threshold=float(e_threshold),
                    multiplier=1.10,
                )
            )
            specs.append(
                MacroOverlaySpec(
                    name=f"boost115_macro_contrarian_q{c_name}_e{e_name}",
                    policy_type="boost_macro_contrarian",
                    crowd_operator="<=",
                    crowd_threshold=float(c_threshold),
                    extreme_threshold=float(e_threshold),
                    multiplier=1.15,
                )
            )
    return specs


def _apply_overlay(frame: pd.DataFrame, spec: MacroOverlaySpec) -> pd.DataFrame:
    out = frame.copy()
    condition = _compare(out["fng_crowd_follow"], spec.crowd_operator, spec.crowd_threshold)
    condition &= pd.to_numeric(out["fng_extreme_distance"], errors="coerce") >= spec.extreme_threshold
    if "prior_drawdown_pct" in out.columns and spec.policy_type.startswith("boost"):
        condition &= pd.to_numeric(out["prior_drawdown_pct"], errors="coerce").fillna(-999.0) > -5.0
    multiplier = pd.Series(1.0, index=out.index)
    multiplier.loc[condition.fillna(False)] = spec.multiplier
    out["v146_multiplier"] = multiplier
    out["v146_account_return_pct"] = out["candidate_account_return_pct"] * multiplier
    out["v146_account_pnl_bps"] = out["candidate_account_pnl_bps"] * multiplier
    return out


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
    spec: MacroOverlaySpec,
    *,
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    candidate_path = _apply_overlay(frame, spec)
    row: dict[str, object] = {
        "candidate": spec.name,
        "policy_type": spec.policy_type,
        "crowd_operator": spec.crowd_operator,
        "crowd_threshold": spec.crowd_threshold,
        "extreme_threshold": spec.extreme_threshold,
        "multiplier": spec.multiplier,
        "changed_trade_count": int((candidate_path["v146_multiplier"] != 1.0).sum()),
    }
    for period, mask in masks.items():
        period_path = candidate_path.loc[mask].copy()
        metrics = v144.v143._account_metrics(
            f"{spec.name}_{period}",
            period_path,
            return_col="v146_account_return_pct",
            pnl_col="v146_account_pnl_bps",
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
    eligible = eligible.sort_values(
        ["selector_delta_return_pct", "selector_delta_drawdown_pct", "changed_trade_count"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    return eligible.iloc[0].to_dict()


def _passes_v146_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
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


def _fng_context_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["fng_bucket"] = pd.cut(
        pd.to_numeric(out["fng_value"], errors="coerce"),
        bins=[-1, 24, 44, 55, 75, 101],
        labels=["extreme_fear", "fear", "neutral", "greed", "extreme_greed"],
    )
    out["win"] = pd.to_numeric(out["candidate_account_return_pct"], errors="coerce") > 0.0
    grouped = (
        out.groupby("fng_bucket", observed=False)
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
    context_table: pd.DataFrame,
    top_candidates: pd.DataFrame,
    selected_monthly: pd.DataFrame,
) -> None:
    selected = payload["selected_candidate"]
    decision = payload["decision"]
    lines = [
        "# Research V146 BTCUSDC Fear & Greed Macro Overlay",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v147']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Fear & Greed Data",
        "",
        pd.DataFrame([payload["fng_summary"]]).to_csv(index=False).strip(),
        "",
        "## Research Inputs",
        "",
        "- Alternative.me publishes the Crypto Fear & Greed Index as a daily 0-100 market sentiment series, where low values indicate fear and high values indicate greed.",
        "- Recent research is mixed: some sentiment studies find short-horizon relationships, while a 2018-2025 daily FGI study reports that FGI changes add little next-day return forecasting value and are often moved by prior Bitcoin returns.",
        "- V146 therefore uses FGI as a macro sentiment overlay only. It does not replace the short-term V144 signal.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## Fear & Greed Context Metrics",
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
            "V146 tests whether a daily macro sentiment series can improve V144 by changing sizing only during extreme Fear & Greed states. Candidate selection uses only the pre-2026 selector period; the 2026 holdout is reported after selection.",
            "",
            "This is a research audit, not a live trading guarantee.",
            "",
            "## References",
            "",
            "- https://alternative.me/crypto/fear-and-greed-index/",
            "- https://api.alternative.me/fng/?limit=0&format=json",
            "- https://www.sciencedirect.com/science/article/pii/S305070062600006X",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V144_ACCOUNT_PATH.exists():
        v144.run()
    v144_frame = pd.read_csv(V144_ACCOUNT_PATH)
    v144_frame["timestamp"] = _to_utc(v144_frame["timestamp"])
    start = v144_frame["timestamp"].min()
    end = v144_frame["timestamp"].max()
    fng = _load_or_download_fng(start, end)
    frame = _add_fng_macro_features(_join_prior_fng(v144_frame, fng))
    frame.to_csv(OUT_DIR / "v146_v144_with_fear_greed_features.csv", index=False)

    masks = {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }
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
    candidates.to_csv(OUT_DIR / "v146_fear_greed_macro_candidates.csv", index=False)
    selected = _select_best_candidate(candidates)
    passed = _passes_v146_gate(selected, baseline)
    decision = {
        "status": "fear_greed_macro_overlay_passed" if passed else "fear_greed_macro_overlay_not_promoted",
        "promote_to_v147": bool(passed),
        "message": (
            "Fear & Greed macro overlay improved V144 without worsening holdout/full drawdown."
            if passed
            else "Fear & Greed is useful context, but the selected macro overlay did not clear the full promotion gate."
        ),
    }
    fng_summary = {
        "rows": int(len(fng)),
        "start": fng["fng_time"].min().isoformat(),
        "end": fng["fng_time"].max().isoformat(),
        "avg_value": float(pd.to_numeric(fng["fng_value"], errors="coerce").mean()),
        "min_value": int(pd.to_numeric(fng["fng_value"], errors="coerce").min()),
        "max_value": int(pd.to_numeric(fng["fng_value"], errors="coerce").max()),
    }
    payload = {
        "config": {
            "base": "v144_funding_sentiment_governor",
            "external_sentiment_source": "alternative_me_crypto_fear_greed_index",
            "selector_end": SELECTOR_END.isoformat(),
            "min_full_improvement_rate": MIN_FULL_IMPROVEMENT_RATE,
            "uses_holdout_for_selection": False,
        },
        "fng_summary": fng_summary,
        "baseline": baseline,
        "selected_candidate": selected,
        "decision": decision,
    }
    selected_monthly = pd.DataFrame()
    if selected:
        selected_spec = next((spec for spec in specs if spec.name == selected["candidate"]), None)
        if selected_spec is not None:
            selected_path = _apply_overlay(frame, selected_spec)
            selected_path.to_csv(OUT_DIR / "v146_selected_account_path.csv", index=False)
            selected_monthly = (
                selected_path.assign(month=selected_path["timestamp"].dt.strftime("%Y-%m"))
                .groupby("month", sort=True)["v146_account_return_pct"]
                .sum()
                .reset_index()
                .rename(columns={"v146_account_return_pct": "account_return_pct"})
            )
    context_table = _fng_context_metrics(frame)
    context_table.to_csv(OUT_DIR / "v146_fear_greed_context_metrics.csv", index=False)
    (OUT_DIR / "v146_fear_greed_macro_summary.json").write_text(
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
