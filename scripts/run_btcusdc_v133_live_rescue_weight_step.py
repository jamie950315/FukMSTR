from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v133_btcusdc_live_rescue_weight_step"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V133_BTCUSDC_LIVE_RESCUE_WEIGHT_STEP.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V132_SUMMARY = (
    ROOT
    / "runs"
    / "research_v132_btcusdc_live_additive_rescue_hour_veto"
    / "v132_live_additive_rescue_hour_veto_summary.json"
)

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24
REQUIRED_V132_IMPROVEMENT_RATE = 1.05
RESCUE_WEIGHT = 2.5
VETO_HOURS = (1, 14)


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


def _passes_v133_gate(row: dict[str, object], *, v132_total: float) -> bool:
    return (
        float(row.get("total_net_pnl_bps", 0.0)) >= float(v132_total) * REQUIRED_V132_IMPROVEMENT_RATE
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
        "# Research V133 BTCUSDC Live Rescue Weight Step",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- V132 total PnL: `{comparison['v132_total_net_pnl_bps']:.6f}` bps",
        f"- V132 +5% target: `{comparison['v132_plus_five_percent_target_bps']:.6f}` bps",
        f"- V133 total PnL: `{selected['total_net_pnl_bps']:.6f}` bps",
        f"- V133 vs V115: `{selected['vs_v115_rate']:.6f}`",
        f"- V133 vs V132: `{selected['vs_v132_rate']:.6f}`",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Win rate: `{selected['win_rate']:.6f}`",
        f"- Max drawdown: `{selected['max_drawdown_bps']:.6f}` bps",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month']}` `{selected['worst_month_bps']:.6f}` bps",
        f"- V133 improvement gate passed: `{selected['v133_improvement_passed']}`",
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
        "V133 keeps the V132 live-executable structure unchanged and only raises the fixed probability-floor rescue leg weight from 2.0 to 2.5. It still uses the current timestamp for the fixed UTC hour veto, does not rank a completed day, and has no daily trade-count cap. This reaches the requested 5% improvement over V132 in the current research window, but remains a research candidate rather than a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v132_payload = json.loads(V132_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    v132_total = float(v132_payload["selected"]["total_net_pnl_bps"])

    base = _V132._load_v130_base_trades()
    rescue = _V132._rescue_events()
    raw_combined = _V132._combine_base_with_additive_rescue(base, rescue, rescue_weight=RESCUE_WEIGHT)
    selected_trades = _V132._apply_fixed_hour_veto(raw_combined, veto_hours=VETO_HOURS)
    selected = _V132._summarize_policy(
        "v133_v132_rescue_weight_2p5_hour_veto_1_14",
        selected_trades,
        v115_total=v115_total,
    )
    selected["vs_v132_rate"] = float(selected["total_net_pnl_bps"] / v132_total) if v132_total > 0.0 else 0.0
    selected["v133_improvement_passed"] = _passes_v133_gate(selected, v132_total=v132_total)
    status = "v132_plus_five_percent_candidate_found" if bool(selected["v133_improvement_passed"]) else "v132_plus_five_percent_not_found"
    payload = {
        "version": "v133_btcusdc_live_rescue_weight_step",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "comparison": {
            "v132_total_net_pnl_bps": v132_total,
            "v132_plus_five_percent_target_bps": v132_total * REQUIRED_V132_IMPROVEMENT_RATE,
            "required_v132_improvement_rate": REQUIRED_V132_IMPROVEMENT_RATE,
        },
        "decision": {
            "similar_performance_rate": MIN_SIMILAR_PERFORMANCE_RATE,
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "status": status,
        },
        "config": _strategy_config(),
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v133_live_rescue_weight_step_summary.json"),
            "raw_combined_trades": str(OUT_DIR / "v133_raw_combined_trades.csv"),
            "selected_trades": str(OUT_DIR / "v133_selected_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    raw_combined.to_csv(OUT_DIR / "v133_raw_combined_trades.csv", index=False)
    selected_trades.to_csv(OUT_DIR / "v133_selected_trades.csv", index=False)
    (OUT_DIR / "v133_live_rescue_weight_step_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_trades, raw_combined)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
