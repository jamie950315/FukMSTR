from __future__ import annotations

import importlib.util
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v126_btcusdc_live_family_ensemble_with_prior_day_cutoff"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V126_BTCUSDC_LIVE_FAMILY_ENSEMBLE_WITH_PRIOR_DAY_CUTOFF.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V124 = _load_script_module("run_btcusdc_v124_live_family_ensemble", ROOT / "scripts" / "run_btcusdc_v124_live_family_ensemble.py")
_V125 = _load_script_module("run_btcusdc_v125_live_prior_day_topk_cutoff", ROOT / "scripts" / "run_btcusdc_v125_live_prior_day_topk_cutoff.py")


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _v125_prior_day_cutoff_events(
    frame: pd.DataFrame,
    *,
    source: str,
    priority: int,
    top_k: int,
    lookback_days: int,
    offset: float,
    margin_min: float,
    prior_ret_max: float | None,
    cooldown_minutes: int,
    min_history_days: int | None = None,
) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], utc=True)
    if "date" not in prepared.columns:
        prepared["date"] = prepared["timestamp"].dt.strftime("%Y-%m-%d")
    if "month" not in prepared.columns:
        prepared["month"] = prepared["timestamp"].dt.strftime("%Y-%m")
    if min_history_days is None:
        min_history_days = min(5, int(lookback_days))
    cutoffs = _V125._prior_day_topk_cutoffs(
        prepared,
        top_k=int(top_k),
        lookback_days=int(lookback_days),
        min_history_days=int(min_history_days),
    )
    eligible = (
        prepared["score"].ge(cutoffs + float(offset))
        & prepared["margin"].ge(float(margin_min))
    )
    if prior_ret_max is not None:
        eligible &= prepared["aligned_prior_ret_720_bps"].le(float(prior_ret_max))
    keep = _V124._live_non_overlapping_indices(
        prepared["timestamp"],
        eligible,
        horizon_minutes=int(cooldown_minutes),
    )
    events = prepared.iloc[keep][["timestamp", "month", "net_pnl_bps"]].copy()
    events["source"] = source
    events["priority"] = int(priority)
    return events


def _feature_frame() -> pd.DataFrame:
    frame = _V124._feature_frame()
    frame["date"] = frame["timestamp"].dt.strftime("%Y-%m-%d")
    return frame


def _build_source_events() -> pd.DataFrame:
    features = _feature_frame()
    predictions = _V124._prediction_frame()
    frames = [
        _V124._v120_peak_events(features),
        _V124._v121_native_events(predictions),
        _V124._v122_drought_events(predictions),
        _V124._v123_threshold_events(features),
        _v125_prior_day_cutoff_events(
            features,
            source="v125_top5_lb14_strict",
            priority=5,
            top_k=5,
            lookback_days=14,
            offset=-0.025,
            margin_min=0.10,
            prior_ret_max=-300.0,
            cooldown_minutes=120,
        ),
        _v125_prior_day_cutoff_events(
            features,
            source="v125_top7_lb14_coverage",
            priority=6,
            top_k=7,
            lookback_days=14,
            offset=0.0,
            margin_min=0.10,
            prior_ret_max=None,
            cooldown_minutes=120,
        ),
        _v125_prior_day_cutoff_events(
            features,
            source="v125_top3_lb14_quality",
            priority=7,
            top_k=3,
            lookback_days=14,
            offset=0.025,
            margin_min=0.10,
            prior_ret_max=None,
            cooldown_minutes=120,
        ),
    ]
    return pd.concat(frames, ignore_index=True).sort_values(["timestamp", "priority"]).reset_index(drop=True)


def _summarize_policy(policy: str, trades: pd.DataFrame, *, v115_total: float) -> dict[str, object]:
    summary = _V124._summarize_policy(policy, trades, v115_total=v115_total)
    summary["live_similarity_passed"] = _passes_live_similarity_gate(summary)
    return summary


def _scan_ensembles(events: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    sources = sorted(events["source"].unique().tolist())
    for r in range(1, len(sources) + 1):
        for source_subset in itertools.combinations(sources, r):
            subset_events = events.loc[events["source"].isin(source_subset)].copy()
            for cooldown in (30, 60, 120):
                selected = _V124._priority_non_overlapping_events(subset_events, cooldown_minutes=cooldown)
                policy = f"sources_{'+'.join(source_subset)}_cool{cooldown}"
                rows.append(_summarize_policy(policy, selected, v115_total=v115_total))
    results = pd.DataFrame(rows)
    if results.empty:
        return results
    return results.sort_values(
        ["live_similarity_passed", "total_net_pnl_bps", "positive_months", "win_rate"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def _write_report(payload: dict[str, object], results: pd.DataFrame) -> None:
    cols = [
        "policy",
        "live_similarity_passed",
        "sources",
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
        "# Research V126 BTCUSDC Live Family Ensemble With Prior-Day Cutoff",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Source event count: `{payload['data']['source_event_count']}`",
        f"- Explored policy count: `{payload['decision']['explored_policy_count']}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Best policy: `{payload['decision']['best_policy']}`",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V126 policy met the live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V126 policies were available.",
        "",
        "## Interpretation",
        "",
        "V126 adds prior-day top-k cutoff event sources to the V124 chronological live ensemble. The added cutoff is known before the current day starts, so each current signal can be accepted or rejected when it appears. The scan still has no daily trade-count cap and does not wait for day-end ranking.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    events = _build_source_events()
    results = _scan_ensembles(events, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    payload = {
        "version": "v126_btcusdc_live_family_ensemble_with_prior_day_cutoff",
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
            "source_event_count": int(len(events)),
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
            "added_prior_day_cutoff_sources": True,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v126_live_family_ensemble_with_prior_day_cutoff_summary.json"),
            "source_events": str(OUT_DIR / "v126_live_family_source_events.csv"),
            "results": str(OUT_DIR / "v126_live_family_ensemble_with_prior_day_cutoff_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    events.to_csv(OUT_DIR / "v126_live_family_source_events.csv", index=False)
    if not results.empty:
        results.to_csv(OUT_DIR / "v126_live_family_ensemble_with_prior_day_cutoff_results.csv", index=False)
    (OUT_DIR / "v126_live_family_ensemble_with_prior_day_cutoff_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
