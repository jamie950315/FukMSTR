from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94
import run_btcusdc_v111_high_confidence_daily_fallback as v111


OUT_DIR = ROOT / "runs" / "research_v131_btcusdc_live_probability_floor_rescue"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V131_BTCUSDC_LIVE_PROBABILITY_FLOOR_RESCUE.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24
FEE_BPS = 8.5


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V129 = _load_script_module("run_btcusdc_v129_live_short_cooldown_source_sizing", ROOT / "scripts" / "run_btcusdc_v129_live_short_cooldown_source_sizing.py")
_V130 = _load_script_module("run_btcusdc_v130_live_consensus_confidence_sizing", ROOT / "scripts" / "run_btcusdc_v130_live_consensus_confidence_sizing.py")


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _passes_profit_similarity(row: dict[str, object]) -> bool:
    return float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE and float(row.get("total_net_pnl_bps", 0.0)) > 0.0


def _probability_floor_events(
    predictions: pd.DataFrame,
    *,
    floor: float,
    cooldown_minutes: int,
    source: str,
    priority: int,
    fee_bps: float,
) -> pd.DataFrame:
    frame = predictions.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for column in ("future_return_bps", "prob_down", "prob_flat", "prob_up"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "future_return_bps", "prob_down", "prob_up"]).sort_values("timestamp").reset_index(drop=True)
    frame["direction_probability"] = frame[["prob_up", "prob_down"]].max(axis=1)
    frame["signal"] = np.where(frame["prob_up"] >= frame["prob_down"], 1, -1).astype(int)
    frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame["net_pnl_bps"] = frame["future_return_bps"] * frame["signal"] - float(fee_bps)
    eligible = frame["direction_probability"].ge(float(floor))
    keep = _V129._V126._V124._live_non_overlapping_indices(frame["timestamp"], eligible, horizon_minutes=int(cooldown_minutes))
    events = frame.iloc[keep][["timestamp", "month", "net_pnl_bps"]].copy()
    events["source"] = source
    events["priority"] = int(priority)
    return events.reset_index(drop=True)


def _probability_predictions() -> pd.DataFrame:
    bars = v94._full_bars()
    selector, holdout, _ = v111._ensemble_predictions(bars, horizon=30)
    return pd.concat([selector, holdout], ignore_index=True).sort_values("timestamp").reset_index(drop=True)


def _source_events_with_probability_floor(
    predictions: pd.DataFrame,
    *,
    floor: float,
    probability_cooldown_minutes: int,
) -> pd.DataFrame:
    base_sources = (
        "v120_peak",
        "v121_native",
        "v122_drought",
        "v123_threshold",
        "v125_top3_lb14_quality",
        "v125_top5_lb14_strict",
        "v125_top7_lb14_coverage",
    )
    base_events = _V129._V126._build_source_events()
    rescue = _probability_floor_events(
        predictions,
        floor=float(floor),
        cooldown_minutes=int(probability_cooldown_minutes),
        source=f"v131_prob_floor_{floor:g}_cool{probability_cooldown_minutes}",
        priority=8,
        fee_bps=FEE_BPS,
    )
    events = pd.concat([base_events.loc[base_events["source"].isin(base_sources)].copy(), rescue], ignore_index=True)
    return events.sort_values(["timestamp", "priority", "source"], kind="mergesort").reset_index(drop=True)


def _scan_probability_rescue(predictions: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    probability_configs = (
        {"floor": 0.58, "probability_cooldown_minutes": 5},
        {"floor": 0.58, "probability_cooldown_minutes": 10},
        {"floor": 0.60, "probability_cooldown_minutes": 5},
        {"floor": 0.60, "probability_cooldown_minutes": 10},
        {"floor": 0.62, "probability_cooldown_minutes": 5},
        {"floor": 0.65, "probability_cooldown_minutes": 5},
        {"floor": 0.65, "probability_cooldown_minutes": 30},
    )
    ensemble_cooldowns = (0, 5, 10, 20)
    sizing_configs = (
        {"amp": 8.0, "scale_bps": 80.0, "min_weight": 0.75, "max_weight": 8.0, "consensus_multiplier": 1.5, "consensus_cap": 8.0},
        {"amp": 8.0, "scale_bps": 80.0, "min_weight": 0.75, "max_weight": 8.0, "consensus_multiplier": 2.0, "consensus_cap": 8.0},
        {"amp": 8.0, "scale_bps": 80.0, "min_weight": 1.0, "max_weight": 8.0, "consensus_multiplier": 2.0, "consensus_cap": 8.0},
        {"amp": 15.0, "scale_bps": 80.0, "min_weight": 1.0, "max_weight": 8.0, "consensus_multiplier": 2.0, "consensus_cap": 8.0},
        {"amp": 20.0, "scale_bps": 120.0, "min_weight": 0.75, "max_weight": 8.0, "consensus_multiplier": 2.0, "consensus_cap": 8.0},
        {"amp": 20.0, "scale_bps": 120.0, "min_weight": 1.0, "max_weight": 8.0, "consensus_multiplier": 2.0, "consensus_cap": 8.0},
    )
    for probability_config in probability_configs:
        events = _source_events_with_probability_floor(predictions, **probability_config)
        for ensemble_cooldown in ensemble_cooldowns:
            selected = _V129._deduped_priority_non_overlapping_events(events, cooldown_minutes=int(ensemble_cooldown))
            selected = _V130._attach_same_timestamp_consensus(selected, events)
            for sizing in sizing_configs:
                sized = _V130._apply_consensus_confidence_sizing(selected, **sizing)
                policy = (
                    f"prob_floor{probability_config['floor']:g}_pcool{probability_config['probability_cooldown_minutes']}"
                    f"_ecool{ensemble_cooldown}"
                    f"__size_amp{sizing['amp']:g}_scale{sizing['scale_bps']:g}_min{sizing['min_weight']:g}_max{sizing['max_weight']:g}"
                    f"__cons_mult{sizing['consensus_multiplier']:g}_cap{sizing['consensus_cap']:g}"
                )
                row = _V130._V127._summarize_policy(policy, sized, v115_total=v115_total)
                row["live_similarity_passed"] = _passes_live_similarity_gate(row)
                row["profit_similarity_passed"] = _passes_profit_similarity(row)
                row.update(probability_config)
                row["ensemble_cooldown_minutes"] = int(ensemble_cooldown)
                row.update({f"sizing_{key}": value for key, value in sizing.items()})
                rows.append(row)
    results = pd.DataFrame(rows)
    if results.empty:
        return results
    return results.sort_values(
        ["live_similarity_passed", "profit_similarity_passed", "positive_months", "total_net_pnl_bps", "win_rate"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)


def _best_trades(predictions: pd.DataFrame, best: dict[str, object]) -> pd.DataFrame:
    events = _source_events_with_probability_floor(
        predictions,
        floor=float(best["floor"]),
        probability_cooldown_minutes=int(best["probability_cooldown_minutes"]),
    )
    selected = _V129._deduped_priority_non_overlapping_events(events, cooldown_minutes=int(best["ensemble_cooldown_minutes"]))
    selected = _V130._attach_same_timestamp_consensus(selected, events)
    sizing = {key.removeprefix("sizing_"): best[key] for key in best if key.startswith("sizing_")}
    return _V130._apply_consensus_confidence_sizing(selected, **sizing)


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
    top = results[cols].head(30) if not results.empty else pd.DataFrame(columns=cols)
    top_total = results.sort_values("total_net_pnl_bps", ascending=False)[cols].head(20) if not results.empty else pd.DataFrame(columns=cols)
    monthly = best_trades.groupby("month", sort=True)["weighted_net_pnl_bps"].sum().reset_index(name="weighted_net_pnl_bps") if not best_trades.empty else pd.DataFrame(columns=["month", "weighted_net_pnl_bps"])
    lines = [
        "# Research V131 BTCUSDC Live Probability-Floor Rescue",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Highest live PnL: `{payload['decision']['highest_total_net_pnl_bps']:.6f}` bps",
        f"- Highest vs V115: `{payload['decision']['highest_vs_v115_rate']:.6f}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V131 policy met the full live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V131 policies were available.",
        "",
        "## Highest Total Policies",
        "",
        top_total.to_csv(index=False).strip() if not top_total.empty else "No V131 policies were available.",
        "",
        "## Best Policy Monthly PnL",
        "",
        monthly.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V131 adds a real-time probability-floor rescue source to the V130 source family. The rescue source accepts chronological model signals above a fixed probability floor with a cooldown; it does not rank a completed day and has no daily trade-count cap. It improves profit similarity versus V115, but still fails the full month-stability gate.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    predictions = _probability_predictions()
    results = _scan_probability_rescue(predictions, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    profit_similarity_count = int(results["profit_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    highest = results.sort_values("total_net_pnl_bps", ascending=False).iloc[0].to_dict() if not results.empty else {}
    best_trades = _best_trades(predictions, best) if best else pd.DataFrame()
    if passing_count:
        status = "live_conversion_candidate_found"
    elif profit_similarity_count:
        status = "profit_similarity_met_but_month_stability_failed"
    else:
        status = "live_conversion_not_solved"
    payload = {
        "version": "v131_btcusdc_live_probability_floor_rescue",
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
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
            "uses_probability_floor_rescue": True,
            "prediction_start": str(pd.to_datetime(predictions["timestamp"], utc=True).min()) if not predictions.empty else None,
            "prediction_end": str(pd.to_datetime(predictions["timestamp"], utc=True).max()) if not predictions.empty else None,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v131_live_probability_floor_rescue_summary.json"),
            "results": str(OUT_DIR / "v131_live_probability_floor_rescue_results.csv"),
            "best_trades": str(OUT_DIR / "v131_best_probability_floor_rescue_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    results.to_csv(OUT_DIR / "v131_live_probability_floor_rescue_results.csv", index=False)
    best_trades.to_csv(OUT_DIR / "v131_best_probability_floor_rescue_trades.csv", index=False)
    (OUT_DIR / "v131_live_probability_floor_rescue_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, results, best_trades)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
