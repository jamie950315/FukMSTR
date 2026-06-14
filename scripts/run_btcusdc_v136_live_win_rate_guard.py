from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v136_btcusdc_live_win_rate_guard"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V136_BTCUSDC_LIVE_WIN_RATE_GUARD.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V135_SUMMARY = ROOT / "runs" / "research_v135_btcusdc_live_drawdown_guard" / "v135_live_drawdown_guard_summary.json"

MIN_WIN_RATE = 0.62
REQUIRED_POSITIVE_MONTHS = 24
RESCUE_WEIGHT = 3.0
VETO_HOURS = (1, 3, 5, 6, 9, 14)
DRAWDOWN_STOP_BPS = 1550.0
HOUR17_V1257_PRIOR_MEAN_FLOOR_BPS = 12.0
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
_V135 = _load_script_module(
    "run_btcusdc_v135_live_drawdown_guard",
    ROOT / "scripts" / "run_btcusdc_v135_live_drawdown_guard.py",
)


def _strategy_config() -> dict[str, object]:
    return {
        "base": "v130_best_consensus_confidence_trades",
        "rescue_floor": _V132.RESCUE_FLOOR,
        "rescue_cooldown_minutes": _V132.RESCUE_COOLDOWN_MINUTES,
        "rescue_weight": RESCUE_WEIGHT,
        "veto_hours_utc": list(VETO_HOURS),
        "hour17_base_keep_consensus_count": 2,
        "hour17_base_keep_source": "v125_top7_lb14_coverage",
        "hour17_base_keep_prior_source_mean_floor_bps": HOUR17_V1257_PRIOR_MEAN_FLOOR_BPS,
        "drawdown_stop_bps": DRAWDOWN_STOP_BPS,
        "drawdown_stop_resume": "next_utc_day",
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "uses_realized_drawdown_guard": True,
        "uses_hour17_confidence_guard": True,
        "allows_same_timestamp_additive_rescue": True,
    }


def _base_with_live_features(base_trades: pd.DataFrame) -> pd.DataFrame:
    base = base_trades.copy()
    base["timestamp"] = pd.to_datetime(base["timestamp"], utc=True)
    if "month" not in base.columns:
        base["month"] = base["timestamp"].dt.strftime("%Y-%m")
    for column, default in (("consensus_count", 1), ("prior_source_mean_bps", 0.0), ("prior_source_count", 0)):
        if column not in base.columns:
            base[column] = default
    return pd.DataFrame(
        {
            "timestamp": base["timestamp"],
            "month": base["month"].astype(str),
            "source": base["source"].astype(str),
            "leg": "base",
            "net_pnl_bps": pd.to_numeric(base["net_pnl_bps"], errors="coerce").fillna(0.0),
            "position_weight": pd.to_numeric(base["position_weight"], errors="coerce").fillna(1.0),
            "weighted_net_pnl_bps": pd.to_numeric(base["weighted_net_pnl_bps"], errors="coerce").fillna(0.0),
            "consensus_count": pd.to_numeric(base["consensus_count"], errors="coerce").fillna(1).astype(int),
            "prior_source_mean_bps": pd.to_numeric(base["prior_source_mean_bps"], errors="coerce").fillna(0.0),
            "prior_source_count": pd.to_numeric(base["prior_source_count"], errors="coerce").fillna(0).astype(int),
        }
    )


def _rescue_with_live_features(rescue_events: pd.DataFrame, *, rescue_weight: float) -> pd.DataFrame:
    rescue = rescue_events.copy()
    rescue["timestamp"] = pd.to_datetime(rescue["timestamp"], utc=True)
    if "month" not in rescue.columns:
        rescue["month"] = rescue["timestamp"].dt.strftime("%Y-%m")
    net = pd.to_numeric(rescue["net_pnl_bps"], errors="coerce").fillna(0.0)
    return pd.DataFrame(
        {
            "timestamp": rescue["timestamp"],
            "month": rescue["month"].astype(str),
            "source": rescue["source"].astype(str),
            "leg": "rescue",
            "net_pnl_bps": net,
            "position_weight": float(rescue_weight),
            "weighted_net_pnl_bps": net * float(rescue_weight),
            "consensus_count": 0,
            "prior_source_mean_bps": 0.0,
            "prior_source_count": 0,
        }
    )


def _combine_base_with_rescue_features(
    base_trades: pd.DataFrame,
    rescue_events: pd.DataFrame,
    *,
    rescue_weight: float,
) -> pd.DataFrame:
    combined = pd.concat(
        [
            _base_with_live_features(base_trades),
            _rescue_with_live_features(rescue_events, rescue_weight=rescue_weight),
        ],
        ignore_index=True,
    )
    combined = combined.sort_values(["timestamp", "leg", "source"], kind="mergesort").reset_index(drop=True)
    combined["weighted_equity_bps"] = combined["weighted_net_pnl_bps"].cumsum()
    return combined


def _apply_v136_hour_confidence_guard(trades: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    hours = frame["timestamp"].dt.hour
    frame = frame.loc[~hours.isin(VETO_HOURS)].copy()
    frame_hours = frame["timestamp"].dt.hour
    consensus = pd.to_numeric(frame.get("consensus_count", 1), errors="coerce").fillna(1)
    prior_mean = pd.to_numeric(frame.get("prior_source_mean_bps", 0.0), errors="coerce").fillna(0.0)
    is_base_hour17 = frame["leg"].astype(str).eq("base") & frame_hours.eq(17)
    keep_base_hour17 = consensus.eq(2) | (
        frame["source"].astype(str).eq("v125_top7_lb14_coverage")
        & prior_mean.ge(HOUR17_V1257_PRIOR_MEAN_FLOOR_BPS)
    )
    kept = frame.loc[~is_base_hour17 | keep_base_hour17].copy().reset_index(drop=True)
    kept["weighted_equity_bps"] = pd.to_numeric(kept["weighted_net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    return kept


def _passes_v136_gate(row: dict[str, object], *, v135_selected: dict[str, object]) -> bool:
    return (
        float(row.get("win_rate", 0.0)) > MIN_WIN_RATE
        and float(row.get("total_net_pnl_bps", 0.0)) >= float(v135_selected["total_net_pnl_bps"]) - FLOAT_TOLERANCE_BPS
        and float(row.get("max_drawdown_bps", 0.0)) <= float(v135_selected["max_drawdown_bps"]) + FLOAT_TOLERANCE_BPS
        and int(row.get("positive_months", 0)) >= max(REQUIRED_POSITIVE_MONTHS, int(v135_selected["positive_months"]))
        and int(row.get("month_count", 0)) >= int(v135_selected["month_count"])
        and float(row.get("worst_month_bps", 0.0)) >= float(v135_selected["worst_month_bps"]) - FLOAT_TOLERANCE_BPS
    )


def _write_report(payload: dict[str, object], trades: pd.DataFrame, pre_guard_trades: pd.DataFrame) -> None:
    monthly = trades.groupby("month", sort=True)["weighted_net_pnl_bps"].sum().reset_index(name="weighted_net_pnl_bps")
    source_summary = (
        trades.groupby(["leg", "source"], sort=True)["weighted_net_pnl_bps"]
        .agg(trade_count="size", total_net_pnl_bps="sum", win_rate=lambda s: (s > 0.0).mean())
        .reset_index()
        .sort_values("total_net_pnl_bps", ascending=False)
    )
    skipped_count = int(len(pre_guard_trades) - len(trades))
    selected = payload["selected"]
    comparison = payload["comparison"]
    lines = [
        "# Research V136 BTCUSDC Live Win Rate Guard",
        "",
        "## Decision",
        "",
        f"- V135 total PnL: `{comparison['v135_total_net_pnl_bps']:.6f}` bps",
        f"- V135 win rate: `{comparison['v135_win_rate']:.6f}`",
        f"- V135 max drawdown: `{comparison['v135_max_drawdown_bps']:.6f}` bps",
        f"- V135 worst month: `{comparison['v135_worst_month']}` `{comparison['v135_worst_month_bps']:.6f}` bps",
        f"- Required win rate: `> {comparison['min_win_rate']:.6f}`",
        f"- V136 total PnL: `{selected['total_net_pnl_bps']:.6f}` bps",
        f"- V136 win rate: `{selected['win_rate']:.6f}`",
        f"- V136 max drawdown: `{selected['max_drawdown_bps']:.6f}` bps",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Skipped by drawdown guard: `{skipped_count}`",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month']}` `{selected['worst_month_bps']:.6f}` bps",
        f"- V136 no-degrade/win-rate gate passed: `{selected['v136_no_degrade_win_rate_passed']}`",
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
        "V136 keeps the V135 live structure and adds a fixed current-hour confidence guard. UTC hour 3 is fully vetoed. UTC hour 17 keeps base trades only when same-timestamp consensus_count is 2, or when the base source is v125_top7_lb14_coverage with prior_source_mean_bps at least 12. The probability-floor rescue leg remains additive, fixed-weight, chronological, and is not selected by day-end ranking or a daily trade cap. This is a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v135_payload = json.loads(V135_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    v135_selected = v135_payload["selected"]

    base = _V132._load_v130_base_trades()
    rescue = _V132._rescue_events()
    raw_combined = _combine_base_with_rescue_features(base, rescue, rescue_weight=RESCUE_WEIGHT)
    pre_guard_trades = _apply_v136_hour_confidence_guard(raw_combined)
    selected_trades = _V135._apply_drawdown_rest_of_day_guard(pre_guard_trades, drawdown_stop_bps=DRAWDOWN_STOP_BPS)
    selected = _V132._summarize_policy(
        "v136_v135_win_rate_guard_weight_3p0_veto_1_3_5_6_9_14_h17_cons2_or_v1257_prior12_drawdown_stop_1550",
        selected_trades,
        v115_total=v115_total,
    )
    selected["vs_v135_rate"] = (
        float(selected["total_net_pnl_bps"] / float(v135_selected["total_net_pnl_bps"]))
        if float(v135_selected["total_net_pnl_bps"]) > 0.0
        else 0.0
    )
    selected["drawdown_vs_v135_rate"] = (
        float(selected["max_drawdown_bps"] / float(v135_selected["max_drawdown_bps"]))
        if float(v135_selected["max_drawdown_bps"]) > 0.0
        else 0.0
    )
    selected["v136_no_degrade_win_rate_passed"] = _passes_v136_gate(selected, v135_selected=v135_selected)
    status = (
        "win_rate_gt_62_no_v135_degrade_candidate_found"
        if bool(selected["v136_no_degrade_win_rate_passed"])
        else "win_rate_no_degrade_goal_not_found"
    )
    payload = {
        "version": "v136_btcusdc_live_win_rate_guard",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "comparison": {
            "v135_total_net_pnl_bps": float(v135_selected["total_net_pnl_bps"]),
            "v135_win_rate": float(v135_selected["win_rate"]),
            "v135_max_drawdown_bps": float(v135_selected["max_drawdown_bps"]),
            "v135_positive_months": int(v135_selected["positive_months"]),
            "v135_month_count": int(v135_selected["month_count"]),
            "v135_worst_month_bps": float(v135_selected["worst_month_bps"]),
            "v135_worst_month": str(v135_selected["worst_month"]),
            "min_win_rate": MIN_WIN_RATE,
        },
        "decision": {
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "status": status,
        },
        "config": _strategy_config(),
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v136_live_win_rate_guard_summary.json"),
            "raw_combined_trades": str(OUT_DIR / "v136_raw_combined_trades.csv"),
            "pre_guard_trades": str(OUT_DIR / "v136_pre_guard_trades.csv"),
            "selected_trades": str(OUT_DIR / "v136_selected_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    raw_combined.to_csv(OUT_DIR / "v136_raw_combined_trades.csv", index=False)
    pre_guard_trades.to_csv(OUT_DIR / "v136_pre_guard_trades.csv", index=False)
    selected_trades.to_csv(OUT_DIR / "v136_selected_trades.csv", index=False)
    (OUT_DIR / "v136_live_win_rate_guard_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_trades, pre_guard_trades)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
