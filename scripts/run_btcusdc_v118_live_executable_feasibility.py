from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v118_btcusdc_v115_live_threshold_exploration"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V118_BTCUSDC_V115_LIVE_EXECUTABLE_FEASIBILITY.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
PREDICTION_CACHE = OUT_DIR / "v118_fold_predictions.csv"
EXPLORATION_FILES = {
    "fixed_threshold": OUT_DIR / "v118_live_threshold_fast_exploration.csv",
    "rolling_threshold": OUT_DIR / "v118_live_rolling_threshold_exploration.csv",
    "meta_threshold": OUT_DIR / "v118_live_meta_threshold_exploration.csv",
    "day_so_far": OUT_DIR / "v118_live_daysofar_exploration.csv",
}

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24


def _live_non_overlapping_indices(
    timestamps: pd.Series,
    eligible: pd.Series,
    *,
    horizon_minutes: int,
) -> list[int]:
    spacing = pd.Timedelta(minutes=int(horizon_minutes))
    out: list[int] = []
    next_allowed: pd.Timestamp | None = None
    ts = pd.to_datetime(timestamps, utc=True)
    for idx, ok in eligible.fillna(False).astype(bool).items():
        if not ok:
            continue
        current = pd.to_datetime(ts.loc[idx], utc=True)
        if next_allowed is None or current >= next_allowed:
            out.append(int(idx))
            next_allowed = current + spacing
    return out


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _load_family_results() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for family, path in EXPLORATION_FILES.items():
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        frame["family"] = family
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined["live_similarity_passed"] = combined.apply(lambda row: _passes_live_similarity_gate(row.to_dict()), axis=1)
    return combined.sort_values(
        ["live_similarity_passed", "total_net_pnl_bps", "positive_months", "win_rate"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def _write_report(payload: dict[str, object], results: pd.DataFrame) -> None:
    cols = [
        "family",
        "policy",
        "live_similarity_passed",
        "trade_count",
        "total_net_pnl_bps",
        "vs_v115_rate",
        "mean_net_pnl_bps",
        "win_rate",
        "max_drawdown_bps",
        "positive_months",
        "worst_month_bps",
        "worst_month",
    ]
    top = results[cols].head(30) if not results.empty else pd.DataFrame(columns=cols)
    passed = results.loc[results["live_similarity_passed"], cols] if not results.empty else pd.DataFrame(columns=cols)
    lines = [
        "# Research V118 BTCUSDC V115 Live Executable Feasibility",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- Prediction cache rows: `{payload['data']['prediction_cache_rows']}`",
        f"- Explored live policy count: `{payload['decision']['explored_policy_count']}`",
        f"- Passing live policy count: `{payload['decision']['passing_policy_count']}`",
        f"- Best live family: `{payload['decision']['best_family']}`",
        f"- Best live policy: `{payload['decision']['best_policy']}`",
        f"- Best live PnL: `{payload['decision']['best_total_net_pnl_bps']:.6f}` bps",
        f"- Best vs V115: `{payload['decision']['best_vs_v115_rate']:.6f}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Passing Live Policies",
        "",
        passed.to_csv(index=False).strip() if not passed.empty else "No live policy met the similarity gate.",
        "",
        "## Top Live Policies",
        "",
        top.to_csv(index=False).strip() if not top.empty else "No live policies were available.",
        "",
        "## Interpretation",
        "",
        "V118 tests live-executable replacements for V115's daily top-9 hindsight selection. The tested families do not use a daily trade cap and do not wait until the day finishes before deciding. None reached the similarity gate. The best explored live policy produced only a small fraction of V115's PnL, so the real-time conversion is not solved yet.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    results = _load_family_results()
    prediction_rows = int(len(pd.read_csv(PREDICTION_CACHE, usecols=["timestamp"]))) if PREDICTION_CACHE.exists() else 0
    passing_count = int(results["live_similarity_passed"].sum()) if not results.empty else 0
    best = results.iloc[0].to_dict() if not results.empty else {}
    status = "live_conversion_not_solved" if passing_count == 0 else "live_conversion_candidate_found"
    payload = {
        "version": "v118_btcusdc_v115_live_executable_feasibility",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "data": {
            "prediction_cache": str(PREDICTION_CACHE),
            "prediction_cache_rows": prediction_rows,
            "exploration_files": {key: str(value) for key, value in EXPLORATION_FILES.items()},
        },
        "decision": {
            "similar_performance_rate": MIN_SIMILAR_PERFORMANCE_RATE,
            "similar_performance_target_bps": v115_total * MIN_SIMILAR_PERFORMANCE_RATE,
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "explored_policy_count": int(len(results)),
            "passing_policy_count": passing_count,
            "best_family": str(best.get("family")) if best else None,
            "best_policy": str(best.get("policy")) if best else None,
            "best_total_net_pnl_bps": float(best.get("total_net_pnl_bps", 0.0)) if best else 0.0,
            "best_vs_v115_rate": float(best.get("vs_v115_rate", 0.0)) if best else 0.0,
            "status": status,
        },
        "outputs": {
            "summary_json": str(OUT_DIR / "v118_live_feasibility_summary.json"),
            "combined_results": str(OUT_DIR / "v118_live_feasibility_combined_results.csv"),
            "report": str(REPORT_PATH),
        },
    }
    if not results.empty:
        results.to_csv(OUT_DIR / "v118_live_feasibility_combined_results.csv", index=False)
    (OUT_DIR / "v118_live_feasibility_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, results)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
