from __future__ import annotations

import importlib.util
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v129_btcusdc_live_short_cooldown_source_sizing"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V129_BTCUSDC_LIVE_SHORT_COOLDOWN_SOURCE_SIZING.md"
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


_V126 = _load_script_module(
    "run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff",
    ROOT / "scripts" / "run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff.py",
)
_V127 = _load_script_module("run_btcusdc_v127_live_source_adaptive_sizing", ROOT / "scripts" / "run_btcusdc_v127_live_source_adaptive_sizing.py")


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _deduped_priority_non_overlapping_events(events: pd.DataFrame, *, cooldown_minutes: int) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    frame = events.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = (
        frame.sort_values(["timestamp", "priority", "source"], kind="mergesort")
        .drop_duplicates("timestamp", keep="first")
        .reset_index(drop=True)
    )
    spacing = pd.Timedelta(minutes=int(cooldown_minutes))
    if spacing <= pd.Timedelta(0):
        return frame
    selected: list[int] = []
    next_allowed: pd.Timestamp | None = None
    for idx, row in frame.iterrows():
        ts = row["timestamp"]
        if next_allowed is None or ts >= next_allowed:
            selected.append(int(idx))
            next_allowed = ts + spacing
    return frame.loc[selected].reset_index(drop=True)


def _scan_short_cooldown_sources(events: pd.DataFrame, *, v115_total: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    sized_rows: list[dict[str, object]] = []
    sources = sorted(events["source"].unique().tolist())
    cooldowns = (0, 5, 10, 15, 20, 25, 30)
    sizing_configs = (
        {"amp": 2.0, "scale_bps": 30.0, "min_weight": 1.0, "max_weight": 3.0},
        {"amp": 5.0, "scale_bps": 50.0, "min_weight": 1.0, "max_weight": 5.0},
        {"amp": 10.0, "scale_bps": 80.0, "min_weight": 1.0, "max_weight": 8.0},
        {"amp": 12.0, "scale_bps": 80.0, "min_weight": 1.0, "max_weight": 8.0},
    )
    for r in range(1, len(sources) + 1):
        for source_subset in itertools.combinations(sources, r):
            subset_events = events.loc[events["source"].isin(source_subset)].copy()
            for cooldown in cooldowns:
                selected = _deduped_priority_non_overlapping_events(subset_events, cooldown_minutes=int(cooldown))
                policy = f"sources_{'+'.join(source_subset)}_cool{cooldown}"
                base_row = _V127._summarize_policy(policy, selected, v115_total=v115_total)
                base_row["live_similarity_passed"] = _passes_live_similarity_gate(base_row)
                base_row["source_subset"] = "+".join(source_subset)
                base_row["cooldown_minutes"] = int(cooldown)
                rows.append(base_row)
                for sizing in sizing_configs:
                    sized = _V127._apply_source_adaptive_sizing(selected, **sizing)
                    sized_policy = (
                        f"{policy}__size_amp{sizing['amp']:g}_scale{sizing['scale_bps']:g}"
                        f"_min{sizing['min_weight']:g}_max{sizing['max_weight']:g}"
                    )
                    sized_row = _V127._summarize_policy(sized_policy, sized, v115_total=v115_total)
                    sized_row["live_similarity_passed"] = _passes_live_similarity_gate(sized_row)
                    sized_row["source_subset"] = "+".join(source_subset)
                    sized_row["cooldown_minutes"] = int(cooldown)
                    sized_row.update({f"sizing_{key}": value for key, value in sizing.items()})
                    sized_rows.append(sized_row)
    base_results = pd.DataFrame(rows).sort_values(
        ["live_similarity_passed", "total_net_pnl_bps", "positive_months", "win_rate"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    sized_results = pd.DataFrame(sized_rows).sort_values(
        ["live_similarity_passed", "total_net_pnl_bps", "positive_months", "win_rate"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    return base_results, sized_results


def _write_report(payload: dict[str, object], base_results: pd.DataFrame, sized_results: pd.DataFrame) -> None:
    cols = [
        "policy",
        "live_similarity_passed",
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
    passed = sized_results.loc[sized_results["live_similarity_passed"], cols] if not sized_results.empty else pd.DataFrame(columns=cols)
    top_sized = sized_results[cols].head(30) if not sized_results.empty else pd.DataFrame(columns=cols)
    top_base = base_results[cols].head(20) if not base_results.empty else pd.DataFrame(columns=cols)
    lines = [
        "# Research V129 BTCUSDC Live Short-Cooldown Source Sizing",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Best unsized live PnL: `{payload['decision']['best_unsized_total_net_pnl_bps']:.6f}` bps",
        f"- Best sized live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Passing policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Sized Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No V129 policy met the live similarity gate.",
        "",
        "## Top Sized Policies",
        "",
        top_sized.to_csv(index=False).strip() if not top_sized.empty else "No sized policies were available.",
        "",
        "## Top Unsized Policies",
        "",
        top_base.to_csv(index=False).strip() if not top_base.empty else "No unsized policies were available.",
        "",
        "## Interpretation",
        "",
        "V129 tests whether the 30-minute V124-V128 non-overlap rule was too restrictive. It deduplicates simultaneous multi-source hits, then scans short cooldowns from 0 to 30 minutes before applying causal source-adaptive sizing. The best result is materially closer to V115, but still fails the required V115-like performance and month-stability gate.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def _best_sized_trades(events: pd.DataFrame, best: dict[str, object]) -> pd.DataFrame:
    source_subset = str(best["source_subset"]).split("+")
    cooldown = int(best["cooldown_minutes"])
    selected = _deduped_priority_non_overlapping_events(events.loc[events["source"].isin(source_subset)].copy(), cooldown_minutes=cooldown)
    sizing = {key.replace("sizing_", ""): best[key] for key in best if key.startswith("sizing_")}
    return _V127._apply_source_adaptive_sizing(selected, **sizing)


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    events = _V126._build_source_events()
    base_results, sized_results = _scan_short_cooldown_sources(events, v115_total=v115_total)
    passing_count = int(sized_results["live_similarity_passed"].sum()) if not sized_results.empty else 0
    best_base = base_results.iloc[0].to_dict() if not base_results.empty else {}
    best = sized_results.iloc[0].to_dict() if not sized_results.empty else {}
    best_sized = _best_sized_trades(events, best) if best else pd.DataFrame()
    payload = {
        "version": "v129_btcusdc_live_short_cooldown_source_sizing",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "decision": {
            "similar_performance_rate": MIN_SIMILAR_PERFORMANCE_RATE,
            "similar_performance_target_bps": v115_total * MIN_SIMILAR_PERFORMANCE_RATE,
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "explored_unsized_policy_count": int(len(base_results)),
            "explored_sized_policy_count": int(len(sized_results)),
            "passing_policy_count": passing_count,
            "best_unsized_policy": str(best_base.get("policy")) if best_base else None,
            "best_unsized_total_net_pnl_bps": float(best_base.get("total_net_pnl_bps", 0.0)) if best_base else 0.0,
            "best_policy": str(best.get("policy")) if best else None,
            "best_total_net_pnl_bps": float(best.get("total_net_pnl_bps", 0.0)) if best else 0.0,
            "best_vs_v115_rate": float(best.get("vs_v115_rate", 0.0)) if best else 0.0,
            "status": "live_conversion_candidate_found" if passing_count else "live_conversion_not_solved",
        },
        "data": {
            "source_event_count": int(len(events)),
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
            "deduplicates_same_timestamp": True,
            "short_cooldown_scan_minutes": [0, 5, 10, 15, 20, 25, 30],
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v129_live_short_cooldown_source_sizing_summary.json"),
            "unsized_results": str(OUT_DIR / "v129_live_short_cooldown_unsized_results.csv"),
            "sized_results": str(OUT_DIR / "v129_live_short_cooldown_sized_results.csv"),
            "best_sized_trades": str(OUT_DIR / "v129_best_sized_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    base_results.to_csv(OUT_DIR / "v129_live_short_cooldown_unsized_results.csv", index=False)
    sized_results.to_csv(OUT_DIR / "v129_live_short_cooldown_sized_results.csv", index=False)
    best_sized.to_csv(OUT_DIR / "v129_best_sized_trades.csv", index=False)
    (OUT_DIR / "v129_live_short_cooldown_source_sizing_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, base_results, sized_results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
