from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v135_btcusdc_live_drawdown_guard"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V135_BTCUSDC_LIVE_DRAWDOWN_GUARD.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V134_SUMMARY = ROOT / "runs" / "research_v134_btcusdc_live_weight_hour_step" / "v134_live_weight_hour_step_summary.json"

MIN_TOTAL_NET_PNL_BPS = 40000.0
REQUIRED_POSITIVE_MONTHS = 24
REQUIRED_DRAWDOWN_REDUCTION_RATE = 0.50
RESCUE_WEIGHT = 2.9
VETO_HOURS = (1, 5, 6, 9, 14)
DRAWDOWN_STOP_BPS = 1600.0
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


def _strategy_config() -> dict[str, object]:
    return {
        "base": "v130_best_consensus_confidence_trades",
        "rescue_floor": _V132.RESCUE_FLOOR,
        "rescue_cooldown_minutes": _V132.RESCUE_COOLDOWN_MINUTES,
        "rescue_weight": RESCUE_WEIGHT,
        "veto_hours_utc": list(VETO_HOURS),
        "drawdown_stop_bps": DRAWDOWN_STOP_BPS,
        "drawdown_stop_resume": "next_utc_day",
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "uses_realized_drawdown_guard": True,
        "allows_same_timestamp_additive_rescue": True,
    }


def _apply_drawdown_rest_of_day_guard(trades: pd.DataFrame, *, drawdown_stop_bps: float) -> pd.DataFrame:
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values(["timestamp", "leg", "source"], kind="mergesort").reset_index(drop=True)
    pause_until = pd.Timestamp.min.tz_localize("UTC")
    equity = 0.0
    peak = 0.0
    kept_rows = []
    for _, row in frame.iterrows():
        ts = row["timestamp"]
        if ts < pause_until:
            continue
        kept_rows.append(row)
        equity += float(row["weighted_net_pnl_bps"])
        peak = max(peak, equity)
        drawdown = peak - equity
        if drawdown + FLOAT_TOLERANCE_BPS >= float(drawdown_stop_bps):
            pause_until = ts.normalize() + pd.Timedelta(days=1)
    if not kept_rows:
        out = frame.iloc[[]].copy()
    else:
        out = pd.DataFrame(kept_rows).reset_index(drop=True)
    out["weighted_equity_bps"] = pd.to_numeric(out["weighted_net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return out


def _passes_v135_gate(row: dict[str, object], *, baseline_drawdown_bps: float) -> bool:
    drawdown_target = float(baseline_drawdown_bps) * (1.0 - REQUIRED_DRAWDOWN_REDUCTION_RATE)
    return (
        float(row.get("total_net_pnl_bps", 0.0)) > MIN_TOTAL_NET_PNL_BPS
        and float(row.get("max_drawdown_bps", 0.0)) <= drawdown_target + FLOAT_TOLERANCE_BPS
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
    )


def _write_report(payload: dict[str, object], trades: pd.DataFrame, pre_guard_trades: pd.DataFrame) -> None:
    monthly = trades.groupby("month", sort=True)["weighted_net_pnl_bps"].sum().reset_index(name="weighted_net_pnl_bps")
    source_summary = (
        trades.groupby(["leg", "source"], sort=True)["weighted_net_pnl_bps"]
        .agg(trade_count="size", total_net_pnl_bps="sum", mean_net_pnl_bps="mean")
        .reset_index()
        .sort_values("total_net_pnl_bps", ascending=False)
    )
    skipped_count = int(len(pre_guard_trades) - len(trades))
    selected = payload["selected"]
    comparison = payload["comparison"]
    lines = [
        "# Research V135 BTCUSDC Live Drawdown Guard",
        "",
        "## Decision",
        "",
        f"- V134 total PnL: `{comparison['v134_total_net_pnl_bps']:.6f}` bps",
        f"- V134 max drawdown: `{comparison['v134_max_drawdown_bps']:.6f}` bps",
        f"- Required max drawdown: `<= {comparison['max_drawdown_target_bps']:.6f}` bps",
        f"- Required total PnL: `> {comparison['min_total_net_pnl_bps']:.6f}` bps",
        f"- V135 total PnL: `{selected['total_net_pnl_bps']:.6f}` bps",
        f"- V135 max drawdown: `{selected['max_drawdown_bps']:.6f}` bps",
        f"- Drawdown reduction: `{selected['drawdown_reduction_rate']:.6f}`",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Skipped by guard: `{skipped_count}`",
        f"- Win rate: `{selected['win_rate']:.6f}`",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month']}` `{selected['worst_month_bps']:.6f}` bps",
        f"- V135 drawdown/profit gate passed: `{selected['v135_drawdown_profit_passed']}`",
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
        "## Interpretation",
        "",
        "V135 lowers the V134 rescue weight, adds fixed UTC hour vetoes for 5 and 9, and applies a realized drawdown guard. The guard uses only already-booked strategy PnL: once drawdown reaches 1600 bps, it skips the rest of that UTC day and resumes the next day. This reaches the requested drawdown reduction while keeping total PnL above 40000 bps, but remains a research candidate rather than a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v134_payload = json.loads(V134_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    v134_selected = v134_payload["selected"]
    v134_total = float(v134_selected["total_net_pnl_bps"])
    v134_drawdown = float(v134_selected["max_drawdown_bps"])

    base = _V132._load_v130_base_trades()
    rescue = _V132._rescue_events()
    raw_combined = _V132._combine_base_with_additive_rescue(base, rescue, rescue_weight=RESCUE_WEIGHT)
    pre_guard_trades = _V132._apply_fixed_hour_veto(raw_combined, veto_hours=VETO_HOURS)
    selected_trades = _apply_drawdown_rest_of_day_guard(pre_guard_trades, drawdown_stop_bps=DRAWDOWN_STOP_BPS)
    selected = _V132._summarize_policy(
        "v135_v134_weight_2p9_veto_1_5_6_9_14_drawdown_stop_1600",
        selected_trades,
        v115_total=v115_total,
    )
    selected["vs_v134_rate"] = float(selected["total_net_pnl_bps"] / v134_total) if v134_total > 0.0 else 0.0
    selected["drawdown_reduction_rate"] = 1.0 - (
        float(selected["max_drawdown_bps"]) / v134_drawdown if v134_drawdown > 0.0 else 0.0
    )
    selected["v135_drawdown_profit_passed"] = _passes_v135_gate(selected, baseline_drawdown_bps=v134_drawdown)
    status = "drawdown_halved_profit_floor_candidate_found" if bool(selected["v135_drawdown_profit_passed"]) else "drawdown_profit_goal_not_found"
    payload = {
        "version": "v135_btcusdc_live_drawdown_guard",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "comparison": {
            "v134_total_net_pnl_bps": v134_total,
            "v134_max_drawdown_bps": v134_drawdown,
            "max_drawdown_target_bps": v134_drawdown * (1.0 - REQUIRED_DRAWDOWN_REDUCTION_RATE),
            "required_drawdown_reduction_rate": REQUIRED_DRAWDOWN_REDUCTION_RATE,
            "min_total_net_pnl_bps": MIN_TOTAL_NET_PNL_BPS,
        },
        "decision": {
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "status": status,
        },
        "config": _strategy_config(),
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v135_live_drawdown_guard_summary.json"),
            "raw_combined_trades": str(OUT_DIR / "v135_raw_combined_trades.csv"),
            "pre_guard_trades": str(OUT_DIR / "v135_pre_guard_trades.csv"),
            "selected_trades": str(OUT_DIR / "v135_selected_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    raw_combined.to_csv(OUT_DIR / "v135_raw_combined_trades.csv", index=False)
    pre_guard_trades.to_csv(OUT_DIR / "v135_pre_guard_trades.csv", index=False)
    selected_trades.to_csv(OUT_DIR / "v135_selected_trades.csv", index=False)
    (OUT_DIR / "v135_live_drawdown_guard_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_trades, pre_guard_trades)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
