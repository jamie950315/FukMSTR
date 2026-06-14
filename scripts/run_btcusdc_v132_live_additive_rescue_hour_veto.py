from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v132_btcusdc_live_additive_rescue_hour_veto"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V132_BTCUSDC_LIVE_ADDITIVE_RESCUE_HOUR_VETO.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V130_BEST_TRADES = (
    ROOT
    / "runs"
    / "research_v130_btcusdc_live_consensus_confidence_sizing"
    / "v130_best_consensus_confidence_trades.csv"
)

MIN_SIMILAR_PERFORMANCE_RATE = 0.80
REQUIRED_POSITIVE_MONTHS = 24
RESCUE_FLOOR = 0.60
RESCUE_COOLDOWN_MINUTES = 5
RESCUE_WEIGHT = 2.0
VETO_HOURS = (1, 14)


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V127 = _load_script_module("run_btcusdc_v127_live_source_adaptive_sizing", ROOT / "scripts" / "run_btcusdc_v127_live_source_adaptive_sizing.py")
_V131 = _load_script_module("run_btcusdc_v131_live_probability_floor_rescue", ROOT / "scripts" / "run_btcusdc_v131_live_probability_floor_rescue.py")


def _passes_live_similarity_gate(row: dict[str, object]) -> bool:
    return (
        float(row.get("vs_v115_rate", 0.0)) >= MIN_SIMILAR_PERFORMANCE_RATE
        and int(row.get("positive_months", 0)) >= REQUIRED_POSITIVE_MONTHS
        and float(row.get("total_net_pnl_bps", 0.0)) > 0.0
    )


def _load_v130_base_trades() -> pd.DataFrame:
    trades = pd.read_csv(V130_BEST_TRADES)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    if "month" not in trades.columns:
        trades["month"] = trades["timestamp"].dt.strftime("%Y-%m")
    return trades.sort_values("timestamp").reset_index(drop=True)


def _combine_base_with_additive_rescue(base_trades: pd.DataFrame, rescue_events: pd.DataFrame, *, rescue_weight: float) -> pd.DataFrame:
    base = base_trades.copy()
    base["timestamp"] = pd.to_datetime(base["timestamp"], utc=True)
    if "month" not in base.columns:
        base["month"] = base["timestamp"].dt.strftime("%Y-%m")
    if "source" not in base.columns:
        base["source"] = "base"
    base_position_weight = (
        pd.to_numeric(base["position_weight"], errors="coerce").fillna(1.0)
        if "position_weight" in base.columns
        else pd.Series(1.0, index=base.index)
    )
    base_out = pd.DataFrame(
        {
            "timestamp": base["timestamp"],
            "month": base["month"].astype(str),
            "source": base["source"].astype(str),
            "leg": "base",
            "net_pnl_bps": pd.to_numeric(base.get("net_pnl_bps", base["weighted_net_pnl_bps"]), errors="coerce").fillna(0.0),
            "position_weight": base_position_weight,
            "weighted_net_pnl_bps": pd.to_numeric(base["weighted_net_pnl_bps"], errors="coerce").fillna(0.0),
        }
    )

    rescue = rescue_events.copy()
    rescue["timestamp"] = pd.to_datetime(rescue["timestamp"], utc=True)
    if "month" not in rescue.columns:
        rescue["month"] = rescue["timestamp"].dt.strftime("%Y-%m")
    rescue_out = pd.DataFrame(
        {
            "timestamp": rescue["timestamp"],
            "month": rescue["month"].astype(str),
            "source": rescue["source"].astype(str),
            "leg": "rescue",
            "net_pnl_bps": pd.to_numeric(rescue["net_pnl_bps"], errors="coerce").fillna(0.0),
            "position_weight": float(rescue_weight),
            "weighted_net_pnl_bps": pd.to_numeric(rescue["net_pnl_bps"], errors="coerce").fillna(0.0) * float(rescue_weight),
        }
    )
    combined = pd.concat([base_out, rescue_out], ignore_index=True)
    combined = combined.sort_values(["timestamp", "leg", "source"], kind="mergesort").reset_index(drop=True)
    combined["weighted_equity_bps"] = combined["weighted_net_pnl_bps"].cumsum()
    return combined


def _apply_fixed_hour_veto(trades: pd.DataFrame, *, veto_hours: tuple[int, ...]) -> pd.DataFrame:
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    hours = frame["timestamp"].dt.hour
    kept = frame.loc[~hours.isin(tuple(int(hour) for hour in veto_hours))].copy().reset_index(drop=True)
    kept["weighted_equity_bps"] = kept["weighted_net_pnl_bps"].cumsum()
    return kept


def _max_drawdown_bps(pnl: pd.Series) -> float:
    equity = pd.to_numeric(pnl, errors="coerce").fillna(0.0).cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max()) if len(drawdown) else 0.0


def _summarize_policy(policy: str, trades: pd.DataFrame, *, v115_total: float) -> dict[str, object]:
    if trades.empty:
        return {
            "policy": policy,
            "trade_count": 0,
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
    monthly = trades.groupby("month", sort=True)["weighted_net_pnl_bps"].sum()
    total = float(trades["weighted_net_pnl_bps"].sum())
    return {
        "policy": policy,
        "trade_count": int(len(trades)),
        "total_net_pnl_bps": total,
        "vs_v115_rate": float(total / v115_total) if v115_total > 0 else 0.0,
        "mean_net_pnl_bps": float(trades["weighted_net_pnl_bps"].mean()),
        "win_rate": float((trades["weighted_net_pnl_bps"] > 0.0).mean()),
        "max_drawdown_bps": _max_drawdown_bps(trades["weighted_net_pnl_bps"]),
        "positive_months": int((monthly > 0.0).sum()),
        "month_count": int(len(monthly)),
        "worst_month_bps": float(monthly.min()),
        "worst_month": str(monthly.idxmin()),
        "position_weight_mean": float(trades["position_weight"].mean()),
        "position_weight_min": float(trades["position_weight"].min()),
        "position_weight_max": float(trades["position_weight"].max()),
    }


def _rescue_events() -> pd.DataFrame:
    predictions = _V131._probability_predictions()
    return _V131._probability_floor_events(
        predictions,
        floor=RESCUE_FLOOR,
        cooldown_minutes=RESCUE_COOLDOWN_MINUTES,
        source=f"v132_prob_floor_{RESCUE_FLOOR:g}_cool{RESCUE_COOLDOWN_MINUTES}",
        priority=8,
        fee_bps=_V131.FEE_BPS,
    )


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
    lines = [
        "# Research V132 BTCUSDC Live Additive Rescue Hour Veto",
        "",
        "## Decision",
        "",
        f"- V115 total PnL: `{payload['v115']['total_net_pnl_bps']:.6f}` bps",
        f"- Similar-performance target: `{payload['decision']['similar_performance_target_bps']:.6f}` bps",
        f"- V132 total PnL: `{selected['total_net_pnl_bps']:.6f}` bps",
        f"- V132 vs V115: `{selected['vs_v115_rate']:.6f}`",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Win rate: `{selected['win_rate']:.6f}`",
        f"- Max drawdown: `{selected['max_drawdown_bps']:.6f}` bps",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month']}` `{selected['worst_month_bps']:.6f}` bps",
        f"- Full gate passed: `{selected['live_similarity_passed']}`",
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
        "V132 keeps the V130 main trade set and adds a separate real-time probability-floor rescue leg. The rescue leg uses a fixed probability floor, chronological cooldown, and fixed position weight. It does not rank a completed day and has no daily trade-count cap. A fixed UTC hour veto removes hours 1 and 14 using only the current signal timestamp. This meets the full research gate, but remains a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    base = _load_v130_base_trades()
    rescue = _rescue_events()
    raw_combined = _combine_base_with_additive_rescue(base, rescue, rescue_weight=RESCUE_WEIGHT)
    selected_trades = _apply_fixed_hour_veto(raw_combined, veto_hours=VETO_HOURS)
    selected = _summarize_policy(
        "v132_v130_base_plus_probability_floor_rescue_hour_veto_1_14",
        selected_trades,
        v115_total=v115_total,
    )
    selected["live_similarity_passed"] = _passes_live_similarity_gate(selected)
    status = "live_conversion_candidate_found" if bool(selected["live_similarity_passed"]) else "live_conversion_not_solved"
    payload = {
        "version": "v132_btcusdc_live_additive_rescue_hour_veto",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "decision": {
            "similar_performance_rate": MIN_SIMILAR_PERFORMANCE_RATE,
            "similar_performance_target_bps": v115_total * MIN_SIMILAR_PERFORMANCE_RATE,
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "status": status,
        },
        "config": {
            "base": "v130_best_consensus_confidence_trades",
            "rescue_floor": RESCUE_FLOOR,
            "rescue_cooldown_minutes": RESCUE_COOLDOWN_MINUTES,
            "rescue_weight": RESCUE_WEIGHT,
            "veto_hours_utc": list(VETO_HOURS),
            "uses_daily_trade_cap": False,
            "uses_day_end_ranking": False,
            "allows_same_timestamp_additive_rescue": True,
        },
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v132_live_additive_rescue_hour_veto_summary.json"),
            "raw_combined_trades": str(OUT_DIR / "v132_raw_combined_trades.csv"),
            "selected_trades": str(OUT_DIR / "v132_selected_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    raw_combined.to_csv(OUT_DIR / "v132_raw_combined_trades.csv", index=False)
    selected_trades.to_csv(OUT_DIR / "v132_selected_trades.csv", index=False)
    (OUT_DIR / "v132_live_additive_rescue_hour_veto_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_trades, raw_combined)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
