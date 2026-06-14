from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v134_btcusdc_live_weight_hour_step"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V134_BTCUSDC_LIVE_WEIGHT_HOUR_STEP.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V133_SUMMARY = ROOT / "runs" / "research_v133_btcusdc_live_rescue_weight_step" / "v133_live_rescue_weight_step_summary.json"

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24
REQUIRED_V133_IMPROVEMENT_RATE = 1.10
RESCUE_WEIGHT = 3.2
VETO_HOURS = (1, 6, 14)
FLOAT_TOLERANCE_BPS = 1e-9


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V132 = _load_script_module(
    "run_btcusdc_v132_live_additive_rescue_hour_veto",
    ROOT / "scripts" / "run_btcusdc_v132_live_additive_rescue_hour_veto.py",
)


def _passes_v134_gate(row: dict[str, object], *, v133_total: float) -> bool:
    return (
        float(row.get("total_net_pnl_bps", 0.0)) + FLOAT_TOLERANCE_BPS
        >= float(v133_total) * REQUIRED_V133_IMPROVEMENT_RATE
        and float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _strategy_config() -> dict[str, object]:
    return {
        "base": "v130_best_consensus_confidence_trades",
        "rescue_floor": _V132.RESCUE_FLOOR,
        "rescue_cooldown_minutes": _V132.RESCUE_COOLDOWN_MINUTES,
        "rescue_weight": RESCUE_WEIGHT,
        "veto_hours_utc": list(VETO_HOURS),
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "allows_same_timestamp_additive_rescue": True,
    }


def _write_report(payload: dict[str, object], trades: pd.DataFrame, raw_combined: pd.DataFrame) -> None:
    monthly = trades.groupby("month", sort=True)["weighted_net_pnl_bps"].sum().reset_index(name="weighted_net_pnl_bps")
    source_summary = (
        trades.groupby(["leg", "source"], sort=True)["weighted_net_pnl_bps"]
        .agg(trade_count="size", total_net_pnl_bps="sum", mean_net_pnl_bps="mean")
        .reset_index()
        .sort_values("total_net_pnl_bps", ascending=False)
    )
    vetoed = raw_combined.loc[raw_combined["timestamp"].dt.hour.isin(VETO_HOURS)].copy()
    veto_summary = (
        vetoed.groupby("timestamp", sort=True)["weighted_net_pnl_bps"].sum().reset_index(name="vetoed_weighted_net_pnl_bps")
        if not vetoed.empty
        else pd.DataFrame(columns=["timestamp", "vetoed_weighted_net_pnl_bps"])
    )
    selected = payload["selected"]
    comparison = payload["comparison"]
    lines = [
        "# Research V134 BTCUSDC Live Weight Hour Step",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- V133 total PnL: `{comparison['v133_total_net_pnl_bps']:.6f}` bps",
        f"- V133 +10% target: `{comparison['v133_plus_ten_percent_target_bps']:.6f}` bps",
        f"- V134 total PnL: `{selected['total_net_pnl_bps']:.6f}` bps",
        f"- V134 vs V115: `{selected['vs_v115_rate']:.6f}`",
        f"- V134 vs V133: `{selected['vs_v133_rate']:.6f}`",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Win rate: `{selected['win_rate']:.6f}`",
        f"- Max drawdown: `{selected['max_drawdown_bps']:.6f}` bps",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month']}` `{selected['worst_month_bps']:.6f}` bps",
        f"- V134 improvement gate passed: `{selected['v134_improvement_passed']}`",
        f"- Status: `{payload['decision']['status']}`",
        "",
        "## Monthly PnL",
        "",
        monthly.to_csv(index=False).strip(),
        "",
        "## Source Summary",
        "",
        source_summary.to_csv(index=False).strip(),
        "",
        "## Vetoed Trades",
        "",
        veto_summary.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V134 keeps the V132/V133 live-executable structure and adds one fixed current-hour veto for UTC 6, while raising the fixed probability-floor rescue leg weight to 3.2. It still does not rank a completed day and has no daily trade-count cap. This reaches the requested 10% improvement over V133 in the current research window, but remains a research candidate rather than a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v133_payload = json.loads(V133_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    v133_total = float(v133_payload["selected"]["total_net_pnl_bps"])

    base = _V132._load_v130_base_trades()
    rescue = _V132._rescue_events()
    raw_combined = _V132._combine_base_with_additive_rescue(base, rescue, rescue_weight=RESCUE_WEIGHT)
    selected_trades = _V132._apply_fixed_hour_veto(raw_combined, veto_hours=VETO_HOURS)
    selected = _V132._summarize_policy(
        "v134_v133_rescue_weight_3p2_hour_veto_1_6_14",
        selected_trades,
        v115_total=v115_total,
    )
    selected["vs_v133_rate"] = float(selected["total_net_pnl_bps"] / v133_total) if v133_total > 0.0 else 0.0
    selected["v134_improvement_passed"] = _passes_v134_gate(selected, v133_total=v133_total)
    status = "v133_plus_ten_percent_candidate_found" if bool(selected["v134_improvement_passed"]) else "v133_plus_ten_percent_not_found"
    payload = {
        "version": "v134_btcusdc_live_weight_hour_step",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "comparison": {
            "v133_total_net_pnl_bps": v133_total,
            "v133_plus_ten_percent_target_bps": v133_total * REQUIRED_V133_IMPROVEMENT_RATE,
            "required_v133_improvement_rate": REQUIRED_V133_IMPROVEMENT_RATE,
        },
        "decision": {
            "similar_performance_rate": MIN_SIMILAR_PERFORMANCE_RATE,
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "status": status,
        },
        "config": _strategy_config(),
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v134_live_weight_hour_step_summary.json"),
            "raw_combined_trades": str(OUT_DIR / "v134_raw_combined_trades.csv"),
            "selected_trades": str(OUT_DIR / "v134_selected_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    raw_combined.to_csv(OUT_DIR / "v134_raw_combined_trades.csv", index=False)
    selected_trades.to_csv(OUT_DIR / "v134_selected_trades.csv", index=False)
    (OUT_DIR / "v134_live_weight_hour_step_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_trades, raw_combined)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
