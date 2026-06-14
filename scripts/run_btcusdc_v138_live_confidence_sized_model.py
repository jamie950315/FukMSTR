from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v138_btcusdc_live_confidence_sized_model"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V138_BTCUSDC_LIVE_CONFIDENCE_SIZED_MODEL.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V137_SUMMARY = ROOT / "runs" / "research_v137_btcusdc_live_weighted_model_ensemble" / "v137_live_weighted_model_ensemble_summary.json"

MODEL_FAMILY_WEIGHTS = {"ma": 11.0, "price_context": 8.0, "technical": 5.0}
HORIZON_MINUTES = 30
BASE_RESCUE_WEIGHT = 2.9
HIGH_CONFIDENCE_RESCUE_WEIGHT = 4.5
HIGH_CONFIDENCE_PROBABILITY_FLOOR = 0.66
VETO_HOURS = (1, 5, 6, 9, 14)
DRAWDOWN_STOP_BPS = 1600.0
REQUIRED_POSITIVE_MONTHS = 24
FLOAT_TOLERANCE_BPS = 1e-9


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V137 = _load_script_module(
    "run_btcusdc_v137_live_weighted_model_ensemble",
    ROOT / "scripts" / "run_btcusdc_v137_live_weighted_model_ensemble.py",
)
_V132 = _V137._V132
_V131 = _V137._V131
_V135 = _V137._V135


def _strategy_config() -> dict[str, object]:
    return {
        "base": "v130_best_consensus_confidence_trades",
        "model_family_weights": dict(MODEL_FAMILY_WEIGHTS),
        "horizon_minutes": HORIZON_MINUTES,
        "rescue_floor": _V132.RESCUE_FLOOR,
        "rescue_cooldown_minutes": _V132.RESCUE_COOLDOWN_MINUTES,
        "base_rescue_weight": BASE_RESCUE_WEIGHT,
        "high_confidence_rescue_weight": HIGH_CONFIDENCE_RESCUE_WEIGHT,
        "high_confidence_probability_floor": HIGH_CONFIDENCE_PROBABILITY_FLOOR,
        "veto_hours_utc": list(VETO_HOURS),
        "drawdown_stop_bps": DRAWDOWN_STOP_BPS,
        "drawdown_stop_resume": "next_utc_day",
        "uses_weighted_model_ensemble": True,
        "uses_confidence_sized_model": True,
        "uses_new_trade_limitations": False,
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "uses_realized_drawdown_guard": True,
        "allows_same_timestamp_additive_rescue": True,
    }


def _confidence_rescue_events(predictions: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for column in ("future_return_bps", "prob_down", "prob_flat", "prob_up"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = (
        frame.dropna(subset=["timestamp", "future_return_bps", "prob_down", "prob_up"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    frame["direction_probability"] = frame[["prob_up", "prob_down"]].max(axis=1)
    frame["signal"] = np.where(frame["prob_up"] >= frame["prob_down"], 1, -1).astype(int)
    frame["month"] = frame["timestamp"].dt.strftime("%Y-%m")
    frame["net_pnl_bps"] = frame["future_return_bps"] * frame["signal"] - float(_V131.FEE_BPS)
    eligible = frame["direction_probability"].ge(float(_V132.RESCUE_FLOOR))
    keep = _V131._V129._V126._V124._live_non_overlapping_indices(
        frame["timestamp"],
        eligible,
        horizon_minutes=int(_V132.RESCUE_COOLDOWN_MINUTES),
    )
    events = frame.iloc[keep][
        [
            "timestamp",
            "month",
            "net_pnl_bps",
            "direction_probability",
            "signal",
            "prob_up",
            "prob_down",
        ]
    ].copy()
    events["source"] = "v138_confidence_sized_weighted_family_rescue"
    events["priority"] = 8
    return events.reset_index(drop=True)


def _assign_confidence_rescue_weights(events: pd.DataFrame) -> pd.DataFrame:
    sized = events.copy()
    probability = pd.to_numeric(sized["direction_probability"], errors="coerce").fillna(0.0)
    net = pd.to_numeric(sized["net_pnl_bps"], errors="coerce").fillna(0.0)
    sized["position_weight"] = np.where(
        probability.ge(HIGH_CONFIDENCE_PROBABILITY_FLOOR),
        HIGH_CONFIDENCE_RESCUE_WEIGHT,
        BASE_RESCUE_WEIGHT,
    )
    sized["weighted_net_pnl_bps"] = net * pd.to_numeric(sized["position_weight"], errors="coerce").fillna(0.0)
    return sized


def _combine_base_with_confidence_rescue(base_trades: pd.DataFrame, rescue_events: pd.DataFrame) -> pd.DataFrame:
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
    rescue = _assign_confidence_rescue_weights(rescue_events)
    rescue["timestamp"] = pd.to_datetime(rescue["timestamp"], utc=True)
    rescue_out = pd.DataFrame(
        {
            "timestamp": rescue["timestamp"],
            "month": rescue["month"].astype(str),
            "source": rescue["source"].astype(str),
            "leg": "rescue",
            "net_pnl_bps": pd.to_numeric(rescue["net_pnl_bps"], errors="coerce").fillna(0.0),
            "position_weight": pd.to_numeric(rescue["position_weight"], errors="coerce").fillna(0.0),
            "weighted_net_pnl_bps": pd.to_numeric(rescue["weighted_net_pnl_bps"], errors="coerce").fillna(0.0),
        }
    )
    combined = pd.concat([base_out, rescue_out], ignore_index=True)
    combined = combined.sort_values(["timestamp", "leg", "source"], kind="mergesort").reset_index(drop=True)
    combined["weighted_equity_bps"] = combined["weighted_net_pnl_bps"].cumsum()
    return combined


def _passes_v138_gate(row: dict[str, object], *, v137_selected: dict[str, object]) -> bool:
    return (
        float(row.get("total_net_pnl_bps", 0.0)) > float(v137_selected["total_net_pnl_bps"]) + FLOAT_TOLERANCE_BPS
        and float(row.get("win_rate", 0.0)) >= float(v137_selected["win_rate"]) - FLOAT_TOLERANCE_BPS
        and float(row.get("max_drawdown_bps", 0.0)) <= float(v137_selected["max_drawdown_bps"]) + FLOAT_TOLERANCE_BPS
        and int(row.get("positive_months", 0)) >= max(REQUIRED_POSITIVE_MONTHS, int(v137_selected["positive_months"]))
        and int(row.get("month_count", 0)) >= int(v137_selected["month_count"])
        and float(row.get("worst_month_bps", 0.0)) >= float(v137_selected["worst_month_bps"]) - FLOAT_TOLERANCE_BPS
    )


def _write_report(payload: dict[str, object], trades: pd.DataFrame, pre_guard_trades: pd.DataFrame) -> None:
    monthly = trades.groupby("month", sort=True)["weighted_net_pnl_bps"].sum().reset_index(name="weighted_net_pnl_bps")
    source_summary = (
        trades.groupby(["leg", "source"], sort=True)["weighted_net_pnl_bps"]
        .agg(trade_count="size", total_net_pnl_bps="sum", win_rate=lambda s: (s > 0.0).mean())
        .reset_index()
        .sort_values("total_net_pnl_bps", ascending=False)
    )
    rescue_weight_summary = (
        pre_guard_trades.loc[pre_guard_trades["leg"].astype(str).eq("rescue")]
        .groupby("position_weight", sort=True)["weighted_net_pnl_bps"]
        .agg(trade_count="size", total_net_pnl_bps="sum", win_rate=lambda s: (s > 0.0).mean())
        .reset_index()
    )
    skipped_count = int(len(pre_guard_trades) - len(trades))
    selected = payload["selected"]
    comparison = payload["comparison"]
    lines = [
        "# Research V138 BTCUSDC Live Confidence Sized Model",
        "",
        "## Decision",
        "",
        f"- V137 total PnL: `{comparison['v137_total_net_pnl_bps']:.6f}` bps",
        f"- V137 win rate: `{comparison['v137_win_rate']:.6f}`",
        f"- V137 max drawdown: `{comparison['v137_max_drawdown_bps']:.6f}` bps",
        f"- V137 worst month: `{comparison['v137_worst_month']}` `{comparison['v137_worst_month_bps']:.6f}` bps",
        f"- V138 total PnL: `{selected['total_net_pnl_bps']:.6f}` bps",
        f"- V138 vs V137: `{selected['vs_v137_rate']:.6f}`",
        f"- V138 win rate: `{selected['win_rate']:.6f}`",
        f"- V138 max drawdown: `{selected['max_drawdown_bps']:.6f}` bps",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Skipped by drawdown guard: `{skipped_count}`",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month']}` `{selected['worst_month_bps']:.6f}` bps",
        f"- V138 model-improvement gate passed: `{selected['v138_model_improvement_passed']}`",
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
        "## Rescue Weight Summary",
        "",
        rescue_weight_summary.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V138 keeps the V137 weighted model ensemble and the V135 live structure: the same fixed UTC hour veto, the same realized drawdown guard, no daily trade cap, and no day-end ranking. It does not add or remove rescue events. The model-level change is confidence sizing: rescue events keep the base weight unless direction_probability is at least 0.66, in which case the rescue weight increases to 4.5. This is a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    v115_payload = json.loads(V115_SUMMARY.read_text(encoding="utf-8"))
    v137_payload = json.loads(V137_SUMMARY.read_text(encoding="utf-8"))
    v115_total = float(v115_payload["selected"]["weighted_total_net_pnl_bps"])
    v137_selected = v137_payload["selected"]

    bars = _V137._V94._full_bars()
    predictions, family_metas = _V137._weighted_family_predictions(bars)
    rescue = _confidence_rescue_events(predictions)
    sized_rescue = _assign_confidence_rescue_weights(rescue)
    base = _V132._load_v130_base_trades()
    raw_combined = _combine_base_with_confidence_rescue(base, rescue)
    pre_guard_trades = _V132._apply_fixed_hour_veto(raw_combined, veto_hours=VETO_HOURS)
    selected_trades = _V135._apply_drawdown_rest_of_day_guard(pre_guard_trades, drawdown_stop_bps=DRAWDOWN_STOP_BPS)
    selected = _V132._summarize_policy(
        "v138_v137_confidence_sized_rescue_prob066_weight4p5",
        selected_trades,
        v115_total=v115_total,
    )
    selected["vs_v137_rate"] = (
        float(selected["total_net_pnl_bps"] / float(v137_selected["total_net_pnl_bps"]))
        if float(v137_selected["total_net_pnl_bps"]) > 0.0
        else 0.0
    )
    selected["drawdown_vs_v137_rate"] = (
        float(selected["max_drawdown_bps"] / float(v137_selected["max_drawdown_bps"]))
        if float(v137_selected["max_drawdown_bps"]) > 0.0
        else 0.0
    )
    selected["v138_model_improvement_passed"] = _passes_v138_gate(selected, v137_selected=v137_selected)
    status = (
        "confidence_sized_model_improvement_candidate_found"
        if bool(selected["v138_model_improvement_passed"])
        else "confidence_sized_model_improvement_not_found"
    )
    payload = {
        "version": "v138_btcusdc_live_confidence_sized_model",
        "v115": {
            "total_net_pnl_bps": v115_total,
            "trade_count": int(v115_payload["selected"]["trade_count"]),
        },
        "comparison": {
            "v137_total_net_pnl_bps": float(v137_selected["total_net_pnl_bps"]),
            "v137_win_rate": float(v137_selected["win_rate"]),
            "v137_max_drawdown_bps": float(v137_selected["max_drawdown_bps"]),
            "v137_positive_months": int(v137_selected["positive_months"]),
            "v137_month_count": int(v137_selected["month_count"]),
            "v137_worst_month_bps": float(v137_selected["worst_month_bps"]),
            "v137_worst_month": str(v137_selected["worst_month"]),
        },
        "decision": {
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "status": status,
        },
        "config": _strategy_config(),
        "family_metas": family_metas,
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v138_live_confidence_sized_model_summary.json"),
            "weighted_predictions": str(OUT_DIR / "v138_weighted_predictions.csv"),
            "confidence_rescue_events": str(OUT_DIR / "v138_confidence_rescue_events.csv"),
            "sized_rescue_events": str(OUT_DIR / "v138_sized_rescue_events.csv"),
            "raw_combined_trades": str(OUT_DIR / "v138_raw_combined_trades.csv"),
            "pre_guard_trades": str(OUT_DIR / "v138_pre_guard_trades.csv"),
            "selected_trades": str(OUT_DIR / "v138_selected_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    predictions.to_csv(OUT_DIR / "v138_weighted_predictions.csv", index=False)
    rescue.to_csv(OUT_DIR / "v138_confidence_rescue_events.csv", index=False)
    sized_rescue.to_csv(OUT_DIR / "v138_sized_rescue_events.csv", index=False)
    raw_combined.to_csv(OUT_DIR / "v138_raw_combined_trades.csv", index=False)
    pre_guard_trades.to_csv(OUT_DIR / "v138_pre_guard_trades.csv", index=False)
    selected_trades.to_csv(OUT_DIR / "v138_selected_trades.csv", index=False)
    (OUT_DIR / "v138_live_confidence_sized_model_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_trades, pre_guard_trades)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
