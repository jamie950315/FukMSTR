from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v128_btcusdc_live_source_health_sizing"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V128_BTCUSDC_LIVE_SOURCE_HEALTH_SIZING.md"
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


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _apply_source_health_gate(
    trades: pd.DataFrame,
    *,
    min_source_count: int,
    prior_mean_floor_bps: float,
    last_n: int,
    last_sum_floor_bps: float,
) -> pd.DataFrame:
    frame = trades.sort_values("timestamp").reset_index(drop=True).copy()
    kept_rows: list[pd.Series] = []
    source_history: dict[str, list[float]] = {}
    for _, row in frame.iterrows():
        source = str(row["source"])
        history = source_history.get(source, [])
        prior_count = len(history)
        prior_mean = float(np.mean(history)) if history else 0.0
        prior_last_sum = float(np.sum(history[-int(last_n) :])) if history and int(last_n) > 0 else 0.0
        passes_mean = prior_count < int(min_source_count) or prior_mean >= float(prior_mean_floor_bps)
        passes_last = int(last_n) <= 0 or prior_count < int(last_n) or prior_last_sum >= float(last_sum_floor_bps)
        if passes_mean and passes_last:
            kept = row.copy()
            kept["prior_source_count"] = int(prior_count)
            kept["prior_source_mean_bps"] = float(prior_mean)
            kept["prior_source_last_sum_bps"] = float(prior_last_sum)
            kept_rows.append(kept)
        history.append(float(row["net_pnl_bps"]))
        source_history[source] = history
    if not kept_rows:
        return frame.iloc[:0].copy()
    return pd.DataFrame(kept_rows).reset_index(drop=True)


def _scan_health_sizing(base_trades: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    health_configs = [
        {"min_source_count": 0, "prior_mean_floor_bps": -200.0, "last_n": 0, "last_sum_floor_bps": -500.0},
        {"min_source_count": 1, "prior_mean_floor_bps": -200.0, "last_n": 20, "last_sum_floor_bps": -500.0},
        {"min_source_count": 1, "prior_mean_floor_bps": -100.0, "last_n": 20, "last_sum_floor_bps": -500.0},
        {"min_source_count": 1, "prior_mean_floor_bps": -50.0, "last_n": 20, "last_sum_floor_bps": -500.0},
        {"min_source_count": 5, "prior_mean_floor_bps": -100.0, "last_n": 20, "last_sum_floor_bps": -500.0},
        {"min_source_count": 10, "prior_mean_floor_bps": -100.0, "last_n": 20, "last_sum_floor_bps": -500.0},
        {"min_source_count": 20, "prior_mean_floor_bps": -100.0, "last_n": 20, "last_sum_floor_bps": -500.0},
    ]
    sizing_configs = [
        {"amp": 2.0, "scale_bps": 30.0, "min_weight": 1.0, "max_weight": 3.0},
        {"amp": 8.0, "scale_bps": 50.0, "min_weight": 1.0, "max_weight": 8.0},
        {"amp": 10.0, "scale_bps": 80.0, "min_weight": 1.0, "max_weight": 8.0},
        {"amp": 12.0, "scale_bps": 80.0, "min_weight": 1.0, "max_weight": 8.0},
        {"amp": 15.0, "scale_bps": 80.0, "min_weight": 1.0, "max_weight": 8.0},
    ]
    for health in health_configs:
        gated = _apply_source_health_gate(base_trades, **health)
        if gated.empty:
            continue
        for sizing in sizing_configs:
            sized = _V127._apply_source_adaptive_sizing(gated, **sizing)
            policy = (
                f"health_minc{health['min_source_count']}_mean{health['prior_mean_floor_bps']:g}"
                f"_last{health['last_n']}_lastsum{health['last_sum_floor_bps']:g}"
                f"__size_amp{sizing['amp']:g}_scale{sizing['scale_bps']:g}"
                f"_min{sizing['min_weight']:g}_max{sizing['max_weight']:g}"
            )
            row = _V127._summarize_policy(policy, sized, v115_total=v115_total)
            row["base_trade_count_after_health_gate"] = int(len(gated))
            row.update({f"health_{key}": value for key, value in health.items()})
            row.update({f"sizing_{key}": value for key, value in sizing.items()})
            rows.append(row)
    results = pd.DataFrame(rows)
    results["live_similarity_passed"] = results.apply(lambda row: _passes_live_similarity_gate(row.to_dict()), axis=1)
    return results.sort_values(
        ["live_similarity_passed", "total_net_pnl_bps", "positive_months", "win_rate"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def _write_report(payload: dict[str, object], results: pd.DataFrame) -> None:
    cols = [
        "policy",
        "live_similarity_passed",
        "trade_count",
        "base_trade_count_after_health_gate",
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
    lines = [
        "# Research V128 BTCUSDC Live Source Health Sizing",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- V127 baseline PnL: `{payload['data']['v127_best_total_net_pnl_bps']:.6f}` bps",
        f"- Explored policy count: `{payload['decision']['explored_policy_count']}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Best policy: `{payload['decision']['best_policy']}`",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V128 policy met the live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V128 policies were available.",
        "",
        "## Interpretation",
        "",
        "V128 keeps the same real-time source family as V126/V127, adds a causal source health gate, and then applies causal source-adaptive sizing. The health gate and sizing overlay only use prior settled outcomes from the same source. The result improves exposure allocation, but it remains far below V115's day-end top-k performance target.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    base_trades = _V127._v126_best_live_trades()
    results = _scan_health_sizing(base_trades, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    best_health = {key.replace("health_", ""): best[key] for key in best if key.startswith("health_")}
    best_sizing = {key.replace("sizing_", ""): best[key] for key in best if key.startswith("sizing_")}
    best_gated = _apply_source_health_gate(base_trades, **best_health) if best else base_trades.iloc[:0].copy()
    best_sized = _V127._apply_source_adaptive_sizing(best_gated, **best_sizing) if best else best_gated
    v127_summary_path = ROOT / "runs" / "research_v127_btcusdc_live_source_adaptive_sizing" / "v127_live_source_adaptive_sizing_summary.json"
    v127_best_total = 0.0
    if v127_summary_path.exists():
        v127_best_total = float(json.loads(v127_summary_path.read_text(encoding="utf-8"))["decision"]["best_total_net_pnl_bps"])
    payload = {
        "version": "v128_btcusdc_live_source_health_sizing",
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
            "base_trade_count": int(len(base_trades)),
            "v127_best_total_net_pnl_bps": v127_best_total,
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
            "uses_prior_source_outcomes_only": True,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v128_live_source_health_sizing_summary.json"),
            "best_gated_trades": str(OUT_DIR / "v128_best_gated_trades.csv"),
            "best_sized_trades": str(OUT_DIR / "v128_best_sized_trades.csv"),
            "results": str(OUT_DIR / "v128_live_source_health_sizing_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    best_gated.to_csv(OUT_DIR / "v128_best_gated_trades.csv", index=False)
    best_sized.to_csv(OUT_DIR / "v128_best_sized_trades.csv", index=False)
    results.to_csv(OUT_DIR / "v128_live_source_health_sizing_results.csv", index=False)
    (OUT_DIR / "v128_live_source_health_sizing_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
