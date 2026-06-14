from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v130_btcusdc_live_consensus_confidence_sizing"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V130_BTCUSDC_LIVE_CONSENSUS_CONFIDENCE_SIZING.md"
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


_V127 = _load_script_module("run_btcusdc_v127_live_source_adaptive_sizing", ROOT / "scripts" / "run_btcusdc_v127_live_source_adaptive_sizing.py")
_V129 = _load_script_module("run_btcusdc_v129_live_short_cooldown_source_sizing", ROOT / "scripts" / "run_btcusdc_v129_live_short_cooldown_source_sizing.py")


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _passes_profit_similarity(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _attach_same_timestamp_consensus(selected: pd.DataFrame, source_events: pd.DataFrame) -> pd.DataFrame:
    if selected.empty:
        out = selected.copy()
        out["consensus_count"] = pd.Series(dtype=int)
        out["consensus_sources"] = pd.Series(dtype=str)
        return out

    source_frame = source_events.copy()
    selected_frame = selected.copy()
    source_frame["timestamp"] = pd.to_datetime(source_frame["timestamp"], utc=True)
    selected_frame["timestamp"] = pd.to_datetime(selected_frame["timestamp"], utc=True)
    consensus = (
        source_frame.groupby("timestamp", sort=True)["source"]
        .agg(
            consensus_count=lambda values: int(len(set(map(str, values)))),
            consensus_sources=lambda values: "+".join(sorted(set(map(str, values)))),
        )
        .reset_index()
    )
    return selected_frame.merge(consensus, on="timestamp", how="left").assign(
        consensus_count=lambda frame: frame["consensus_count"].fillna(1).astype(int),
        consensus_sources=lambda frame: frame["consensus_sources"].fillna(frame["source"].astype(str)),
    )


def _apply_consensus_confidence_sizing(
    trades: pd.DataFrame,
    *,
    amp: float,
    scale_bps: float,
    min_weight: float,
    max_weight: float,
    consensus_multiplier: float,
    consensus_cap: float,
) -> pd.DataFrame:
    sized = _V127._apply_source_adaptive_sizing(
        trades,
        amp=float(amp),
        scale_bps=float(scale_bps),
        min_weight=float(min_weight),
        max_weight=float(max_weight),
    )
    consensus_raw = 1.0 + float(consensus_multiplier) * (sized["consensus_count"].astype(float) - 1.0)
    consensus_raw = consensus_raw.clip(1.0, float(consensus_cap))
    raw = sized["position_weight"].astype(float) * consensus_raw
    prior_normalizer = raw.expanding(min_periods=1).mean().shift(1).fillna(1.0)
    weights = (raw / prior_normalizer).clip(float(min_weight), float(max_weight))
    weights.iloc[0] = 1.0

    sized["source_adaptive_position_weight"] = sized["position_weight"].astype(float)
    sized["consensus_raw_multiplier"] = consensus_raw.astype(float)
    sized["position_weight"] = weights.astype(float)
    sized["weighted_net_pnl_bps"] = sized["net_pnl_bps"] * sized["position_weight"]
    sized["weighted_equity_bps"] = sized["weighted_net_pnl_bps"].cumsum()
    return sized


def _scan_consensus_policies(events: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    source_sets = (
        (
            "v120_peak",
            "v122_drought",
            "v123_threshold",
            "v125_top3_lb14_quality",
            "v125_top5_lb14_strict",
            "v125_top7_lb14_coverage",
        ),
        (
            "v121_native",
            "v122_drought",
            "v123_threshold",
            "v125_top3_lb14_quality",
            "v125_top5_lb14_strict",
            "v125_top7_lb14_coverage",
        ),
        (
            "v120_peak",
            "v121_native",
            "v122_drought",
            "v123_threshold",
            "v125_top3_lb14_quality",
            "v125_top5_lb14_strict",
            "v125_top7_lb14_coverage",
        ),
        (
            "v120_peak",
            "v122_drought",
            "v123_threshold",
            "v125_top3_lb14_quality",
            "v125_top5_lb14_strict",
        ),
    )
    sizing_pairs = (
        (8.0, 50.0),
        (8.0, 80.0),
        (8.0, 120.0),
        (10.0, 50.0),
        (10.0, 80.0),
        (10.0, 120.0),
        (10.0, 160.0),
        (12.0, 50.0),
        (12.0, 80.0),
        (12.0, 120.0),
        (12.0, 160.0),
        (12.0, 240.0),
        (15.0, 80.0),
        (15.0, 120.0),
        (15.0, 160.0),
        (15.0, 240.0),
        (20.0, 120.0),
        (20.0, 160.0),
        (20.0, 240.0),
    )
    sizing_configs = tuple(
        {"amp": amp, "scale_bps": scale, "min_weight": min_weight, "max_weight": 8.0}
        for amp, scale in sizing_pairs
        for min_weight in (0.75, 1.0)
    )
    consensus_configs = tuple(
        {"consensus_multiplier": multiplier, "consensus_cap": cap}
        for multiplier in (0.5, 1.0, 1.5, 2.0)
        for cap in (3.0, 4.0, 8.0)
    )
    for source_subset in source_sets:
        subset_events = events.loc[events["source"].isin(source_subset)].copy()
        for cooldown in (0, 5, 10, 20):
            selected = _V129._deduped_priority_non_overlapping_events(subset_events, cooldown_minutes=int(cooldown))
            selected = _attach_same_timestamp_consensus(selected, subset_events)
            for sizing in sizing_configs:
                for consensus in consensus_configs:
                    sized = _apply_consensus_confidence_sizing(selected, **sizing, **consensus)
                    policy = (
                        f"sources_{'+'.join(source_subset)}_cool{cooldown}"
                        f"__size_amp{sizing['amp']:g}_scale{sizing['scale_bps']:g}"
                        f"_min{sizing['min_weight']:g}_max{sizing['max_weight']:g}"
                        f"__cons_mult{consensus['consensus_multiplier']:g}_cap{consensus['consensus_cap']:g}"
                    )
                    row = _V127._summarize_policy(policy, sized, v115_total=v115_total)
                    row["live_similarity_passed"] = _passes_live_similarity_gate(row)
                    row["profit_similarity_passed"] = _passes_profit_similarity(row)
                    row["source_subset"] = "+".join(source_subset)
                    row["cooldown_minutes"] = int(cooldown)
                    row.update({f"sizing_{key}": value for key, value in sizing.items()})
                    row.update({f"consensus_{key}": value for key, value in consensus.items()})
                    rows.append(row)
    results = pd.DataFrame(rows)
    if results.empty:
        return results
    return results.sort_values(
        ["live_similarity_passed", "profit_similarity_passed", "positive_months", "total_net_pnl_bps", "win_rate"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)


def _best_trades(events: pd.DataFrame, best: dict[str, object]) -> pd.DataFrame:
    source_subset = str(best["source_subset"]).split("+")
    subset_events = events.loc[events["source"].isin(source_subset)].copy()
    selected = _V129._deduped_priority_non_overlapping_events(subset_events, cooldown_minutes=int(best["cooldown_minutes"]))
    selected = _attach_same_timestamp_consensus(selected, subset_events)
    sizing = {key.removeprefix("sizing_"): best[key] for key in best if key.startswith("sizing_")}
    consensus = {key.removeprefix("consensus_"): best[key] for key in best if key.startswith("consensus_")}
    return _apply_consensus_confidence_sizing(selected, **sizing, **consensus)


def _write_report(payload: dict[str, object], results: pd.DataFrame, best_trades: pd.DataFrame) -> None:
    cols = [
        "policy",
        "live_similarity_passed",
        "profit_similarity_passed",
        "trade_count",
        "total_net_pnl_bps",
        "vs_v115_rate",
        "mean_net_pnl_bps",
        "win_rate",
        "max_drawdown_bps",
        "positive_months",
        "month_count",
        "worst_month_bps",
        "worst_month",
        "position_weight_mean",
        "position_weight_min",
        "position_weight_max",
    ]
    passed = results.loc[results["live_similarity_passed"], cols] if not results.empty else pd.DataFrame(columns=cols)
    profit_passed = results.loc[results["profit_similarity_passed"], cols].head(30) if not results.empty else pd.DataFrame(columns=cols)
    top = results[cols].head(30) if not results.empty else pd.DataFrame(columns=cols)
    top_total = results.sort_values("total_net_pnl_bps", ascending=False)[cols].head(20) if not results.empty else pd.DataFrame(columns=cols)
    monthly = best_trades.groupby("month", sort=True)["weighted_net_pnl_bps"].sum().reset_index(name="weighted_net_pnl_bps") if not best_trades.empty else pd.DataFrame(columns=["month", "weighted_net_pnl_bps"])
    consensus_summary = (
        best_trades.groupby("consensus_count", sort=True)["net_pnl_bps"]
        .agg(trade_count="size", raw_total_net_pnl_bps="sum", raw_mean_net_pnl_bps="mean")
        .reset_index()
    ) if not best_trades.empty else pd.DataFrame(columns=["consensus_count", "trade_count", "raw_total_net_pnl_bps", "raw_mean_net_pnl_bps"])
    lines = [
        "# Research V130 BTCUSDC Live Consensus Confidence Sizing",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Highest live PnL: `{payload['decision']['highest_total_net_pnl_bps']:.6f}` bps",
        f"- Highest vs V115: `{payload['decision']['highest_vs_v115_rate']:.6f}`",
        f"- Profit-similar policy count: `{payload['decision']['profit_similarity_policy_count']}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V130 policy met the full live similarity gate.",
        "",
        "## Profit-Similar Policies",
        "",
        profit_passed.to_csv(index=False).strip() if not profit_passed.empty else "No V130 policy reached the profit-similarity threshold.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V130 policies were available.",
        "",
        "## Highest Total Policies",
        "",
        top_total.to_csv(index=False).strip() if not top_total.empty else "No V130 policies were available.",
        "",
        "## Best Policy Monthly PnL",
        "",
        monthly.to_csv(index=False).strip(),
        "",
        "## Best Policy Consensus Buckets",
        "",
        consensus_summary.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V130 treats same-timestamp multi-source agreement as a real-time confidence signal. It never uses a daily trade cap or day-end ranking. The best policy crosses the 80% profit-similarity threshold versus V115, but still fails the full gate because month stability remains below the required 24 positive months.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    events = _V129._V126._build_source_events()
    results = _scan_consensus_policies(events, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    profit_similarity_count = int(results["profit_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    highest = results.sort_values("total_net_pnl_bps", ascending=False).iloc[0].to_dict() if not results.empty else {}
    best_trades = _best_trades(events, best) if best else pd.DataFrame()
    if passing_count:
        status = "live_conversion_candidate_found"
    elif profit_similarity_count:
        status = "profit_similarity_met_but_month_stability_failed"
    else:
        status = "live_conversion_not_solved"
    payload = {
        "version": "v130_btcusdc_live_consensus_confidence_sizing",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "decision": {
            "similar_performance_rate": MIN_SIMILAR_PERFORMANCE_RATE,
            "similar_performance_target_bps": v115_total * MIN_SIMILAR_PERFORMANCE_RATE,
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "explored_policy_count": int(len(results)),
            "profit_similarity_policy_count": profit_similarity_count,
            "passing_policy_count": passing_count,
            "best_policy": str(best.get("policy")) if best else None,
            "best_total_net_pnl_bps": float(best.get("total_net_pnl_bps", 0.0)) if best else 0.0,
            "best_vs_v115_rate": float(best.get("vs_v115_rate", 0.0)) if best else 0.0,
            "best_positive_months": int(best.get("positive_months", 0)) if best else 0,
            "highest_policy": str(highest.get("policy")) if highest else None,
            "highest_total_net_pnl_bps": float(highest.get("total_net_pnl_bps", 0.0)) if highest else 0.0,
            "highest_vs_v115_rate": float(highest.get("vs_v115_rate", 0.0)) if highest else 0.0,
            "highest_positive_months": int(highest.get("positive_months", 0)) if highest else 0,
            "status": status,
        },
        "data": {
            "source_event_count": int(len(events)),
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
            "uses_same_timestamp_consensus": True,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v130_live_consensus_confidence_sizing_summary.json"),
            "results": str(OUT_DIR / "v130_live_consensus_confidence_sizing_results.csv"),
            "best_trades": str(OUT_DIR / "v130_best_consensus_confidence_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    results.to_csv(OUT_DIR / "v130_live_consensus_confidence_sizing_results.csv", index=False)
    best_trades.to_csv(OUT_DIR / "v130_best_consensus_confidence_trades.csv", index=False)
    (OUT_DIR / "v130_live_consensus_confidence_sizing_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, results, best_trades)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
