from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v127_btcusdc_live_source_adaptive_sizing"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V127_BTCUSDC_LIVE_SOURCE_ADAPTIVE_SIZING.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24
BASE_SOURCES = ("v122_drought", "v123_threshold", "v125_top3_lb14_quality", "v125_top5_lb14_strict")
BASE_COOLDOWN_MINUTES = 30


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V126 = _load_script_module(
    "run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff",
    ROOT / "scripts" / "run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff.py",
)
_V124 = _V126._V124


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _max_drawdown_bps(pnl: pd.Series) -> float:
    equity = pd.to_numeric(pnl, errors="coerce").fillna(0.0).cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max()) if len(drawdown) else 0.0


def _v126_best_live_trades() -> pd.DataFrame:
    events = _V126._build_source_events()
    subset = events.loc[events["source"].isin(BASE_SOURCES)].copy()
    selected = _V124._priority_non_overlapping_events(subset, cooldown_minutes=BASE_COOLDOWN_MINUTES)
    return selected.sort_values("timestamp").reset_index(drop=True)


def _apply_source_adaptive_sizing(
    trades: pd.DataFrame,
    *,
    amp: float,
    scale_bps: float,
    min_weight: float,
    max_weight: float,
) -> pd.DataFrame:
    sized = trades.sort_values("timestamp").reset_index(drop=True).copy()
    prior_means: list[float] = []
    prior_counts: list[int] = []
    source_sums: dict[str, float] = {}
    source_counts: dict[str, int] = {}
    for row in sized.itertuples(index=False):
        source = str(row.source)
        count = int(source_counts.get(source, 0))
        total = float(source_sums.get(source, 0.0))
        prior_counts.append(count)
        prior_means.append(total / count if count else 0.0)
        source_sums[source] = total + float(row.net_pnl_bps)
        source_counts[source] = count + 1

    raw = 1.0 + float(amp) * np.tanh(np.asarray(prior_means, dtype=float) / float(scale_bps))
    raw = pd.Series(raw, index=sized.index).clip(float(min_weight), float(max_weight))
    prior_normalizer = raw.expanding(min_periods=1).mean().shift(1).fillna(1.0)
    weights = (raw / prior_normalizer).clip(float(min_weight), float(max_weight))
    weights.iloc[0] = 1.0

    sized["prior_source_count"] = prior_counts
    sized["prior_source_mean_bps"] = prior_means
    sized["raw_position_weight"] = raw.astype(float)
    sized["position_weight"] = weights.astype(float)
    sized["weighted_net_pnl_bps"] = sized["net_pnl_bps"] * sized["position_weight"]
    sized["weighted_equity_bps"] = sized["weighted_net_pnl_bps"].cumsum()
    return sized


def _summarize_policy(policy: str, trades: pd.DataFrame, *, v115_total: float) -> dict[str, object]:
    if trades.empty:
        return {
            "policy": policy,
            "trade_count": 0,
            "avg_trades_per_day": 0.0,
            "total_net_pnl_bps": 0.0,
            "vs_v115_rate": 0.0,
            "mean_net_pnl_bps": 0.0,
            "win_rate": 0.0,
            "max_drawdown_bps": 0.0,
            "positive_months": 0,
            "month_count": 0,
            "worst_month_bps": 0.0,
            "worst_month": "",
            "position_weight_mean": 0.0,
            "position_weight_min": 0.0,
            "position_weight_max": 0.0,
        }
    pnl_col = "weighted_net_pnl_bps" if "weighted_net_pnl_bps" in trades else "net_pnl_bps"
    monthly = trades.groupby("month", sort=True)[pnl_col].sum()
    days = max(1.0, (trades["timestamp"].max() - trades["timestamp"].min()).total_seconds() / 86400.0)
    total = float(trades[pnl_col].sum())
    weights = trades["position_weight"] if "position_weight" in trades else pd.Series(1.0, index=trades.index)
    return {
        "policy": policy,
        "trade_count": int(len(trades)),
        "avg_trades_per_day": float(len(trades) / days),
        "total_net_pnl_bps": total,
        "vs_v115_rate": float(total / v115_total) if v115_total > 0.0 else np.nan,
        "mean_net_pnl_bps": float(trades[pnl_col].mean()),
        "win_rate": float((trades[pnl_col] > 0.0).mean()),
        "max_drawdown_bps": _max_drawdown_bps(trades[pnl_col]),
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_bps": float(monthly.min()),
        "worst_month": str(monthly.idxmin()),
        "position_weight_mean": float(weights.mean()),
        "position_weight_min": float(weights.min()),
        "position_weight_max": float(weights.max()),
    }


def _scan_source_sizing(base_trades: pd.DataFrame, *, v115_total: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for amp in (0.5, 1.0, 1.5, 2.0):
        for scale in (20.0, 30.0, 50.0, 80.0, 120.0):
            for min_weight, max_weight in ((0.1, 3.0), (0.1, 5.0), (1.0, 3.0), (1.0, 5.0)):
                sized = _apply_source_adaptive_sizing(
                    base_trades,
                    amp=float(amp),
                    scale_bps=float(scale),
                    min_weight=float(min_weight),
                    max_weight=float(max_weight),
                )
                policy = f"source_adaptive_amp{amp:g}_scale{scale:g}_min{min_weight:g}_max{max_weight:g}"
                row = _summarize_policy(policy, sized, v115_total=v115_total)
                row["amp"] = float(amp)
                row["scale_bps"] = float(scale)
                row["min_weight_config"] = float(min_weight)
                row["max_weight_config"] = float(max_weight)
                rows.append(row)
    results = pd.DataFrame(rows)
    results["live_similarity_passed"] = results.apply(lambda row: _passes_live_similarity_gate(row.to_dict()), axis=1)
    return results.sort_values(
        ["live_similarity_passed", "total_net_pnl_bps", "positive_months", "win_rate"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def _write_report(payload: dict[str, object], results: pd.DataFrame, base_summary: dict[str, object]) -> None:
    cols = [
        "policy",
        "live_similarity_passed",
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
        "position_weight_mean",
        "position_weight_min",
        "position_weight_max",
    ]
    passed = results.loc[results["live_similarity_passed"], cols] if not results.empty else pd.DataFrame(columns=cols)
    top = results[cols].head(30) if not results.empty else pd.DataFrame(columns=cols)
    lines = [
        "# Research V127 BTCUSDC Live Source-Adaptive Sizing",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Base policy: `V126 {payload['data']['base_sources']}`",
        f"- Base live PnL before sizing: `{base_summary['total_net_pnl_bps']:.6f}` bps",
        f"- Explored sizing policy count: `{payload['decision']['explored_policy_count']}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Best policy: `{payload['decision']['best_policy']}`",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V127 policy met the live similarity gate.",
        "",
        "## Top Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No V127 policies were available.",
        "",
        "## Interpretation",
        "",
        "V127 keeps the V126 real-time trade set unchanged and adds a causal source-adaptive sizing overlay. Each trade's size only uses the prior settled PnL history of the same source. It still has no daily trade-count cap and does not wait for day-end ranking. The improvement comes from exposure allocation, not from discovering enough new real-time entries to replicate V115.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    base_trades = _v126_best_live_trades()
    base_summary = _summarize_policy("v126_best_unsized", base_trades, v115_total=v115_total)
    results = _scan_source_sizing(base_trades, v115_total=v115_total)
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    best_sized = _apply_source_adaptive_sizing(
        base_trades,
        amp=float(best.get("amp", 0.0)),
        scale_bps=float(best.get("scale_bps", 1.0)),
        min_weight=float(best.get("min_weight_config", 1.0)),
        max_weight=float(best.get("max_weight_config", 1.0)),
    ) if best else base_trades.copy()
    payload = {
        "version": "v127_btcusdc_live_source_adaptive_sizing",
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
            "base_sources": "+".join(BASE_SOURCES),
            "base_cooldown_minutes": BASE_COOLDOWN_MINUTES,
            "base_trade_count": int(len(base_trades)),
            "base_total_net_pnl_bps": float(base_summary["total_net_pnl_bps"]),
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
            "changes_trade_set": False,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v127_live_source_adaptive_sizing_summary.json"),
            "base_trades": str(OUT_DIR / "v127_base_v126_live_trades.csv"),
            "best_sized_trades": str(OUT_DIR / "v127_best_sized_trades.csv"),
            "results": str(OUT_DIR / "v127_live_source_adaptive_sizing_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    base_trades.to_csv(OUT_DIR / "v127_base_v126_live_trades.csv", index=False)
    best_sized.to_csv(OUT_DIR / "v127_best_sized_trades.csv", index=False)
    results.to_csv(OUT_DIR / "v127_live_source_adaptive_sizing_results.csv", index=False)
    (OUT_DIR / "v127_live_source_adaptive_sizing_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, results, base_summary)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
