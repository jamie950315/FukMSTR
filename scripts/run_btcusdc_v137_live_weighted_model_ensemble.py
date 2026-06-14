from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v137_btcusdc_live_weighted_model_ensemble"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V137_BTCUSDC_LIVE_WEIGHTED_MODEL_ENSEMBLE.md"
V115_SUMMARY = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing" / "v115_summary.json"
V135_SUMMARY = ROOT / "runs" / "research_v135_btcusdc_live_drawdown_guard" / "v135_live_drawdown_guard_summary.json"

MODEL_FAMILY_WEIGHTS = {"ma": 11.0, "price_context": 8.0, "technical": 5.0}
HORIZON_MINUTES = 30
RESCUE_WEIGHT = 2.9
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


_V94 = _load_script_module(
    "run_btcusdc_v94_high_frequency_scan",
    ROOT / "scripts" / "run_btcusdc_v94_high_frequency_scan.py",
)
_V109 = _load_script_module(
    "run_btcusdc_v109_feature_family_ensemble_exact_daily",
    ROOT / "scripts" / "run_btcusdc_v109_feature_family_ensemble_exact_daily.py",
)
_V131 = _load_script_module(
    "run_btcusdc_v131_live_probability_floor_rescue",
    ROOT / "scripts" / "run_btcusdc_v131_live_probability_floor_rescue.py",
)
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
        "model_family_weights": dict(MODEL_FAMILY_WEIGHTS),
        "horizon_minutes": HORIZON_MINUTES,
        "rescue_floor": _V132.RESCUE_FLOOR,
        "rescue_cooldown_minutes": _V132.RESCUE_COOLDOWN_MINUTES,
        "rescue_weight": RESCUE_WEIGHT,
        "veto_hours_utc": list(VETO_HOURS),
        "drawdown_stop_bps": DRAWDOWN_STOP_BPS,
        "drawdown_stop_resume": "next_utc_day",
        "uses_weighted_model_ensemble": True,
        "uses_new_trade_limitations": False,
        "uses_daily_trade_cap": False,
        "uses_day_end_ranking": False,
        "uses_realized_drawdown_guard": True,
        "allows_same_timestamp_additive_rescue": True,
    }


def _weighted_average_probability_frames(
    frames_by_family: dict[str, pd.DataFrame],
    *,
    weights: dict[str, float],
) -> pd.DataFrame:
    if not frames_by_family:
        return pd.DataFrame(columns=["timestamp", "future_return_bps", "prob_down", "prob_flat", "prob_up"])
    merged: pd.DataFrame | None = None
    ordered_families = [family for family in weights if family in frames_by_family]
    total_weight = sum(float(weights[family]) for family in ordered_families)
    if total_weight <= 0.0:
        raise ValueError("total model family weight must be positive")

    for family in ordered_families:
        frame = frames_by_family[family][["timestamp", "future_return_bps", "prob_down", "prob_flat", "prob_up"]].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.rename(
            columns={
                "future_return_bps": f"future_return_bps_{family}",
                "prob_down": f"prob_down_{family}",
                "prob_flat": f"prob_flat_{family}",
                "prob_up": f"prob_up_{family}",
            }
        )
        merged = frame if merged is None else merged.merge(frame, on="timestamp", how="inner")
    if merged is None:
        return pd.DataFrame(columns=["timestamp", "future_return_bps", "prob_down", "prob_flat", "prob_up"])

    out = pd.DataFrame({"timestamp": pd.to_datetime(merged["timestamp"], utc=True)})
    first_family = ordered_families[0]
    out["future_return_bps"] = pd.to_numeric(merged[f"future_return_bps_{first_family}"], errors="coerce")
    for column in ("prob_down", "prob_flat", "prob_up"):
        weighted_sum = pd.Series(0.0, index=merged.index)
        for family in ordered_families:
            weighted_sum = weighted_sum + pd.to_numeric(merged[f"{column}_{family}"], errors="coerce") * float(weights[family])
        out[column] = weighted_sum / total_weight
    return out.sort_values("timestamp").reset_index(drop=True)


def _weighted_family_predictions(bars: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    frames_by_family: dict[str, pd.DataFrame] = {}
    metas: list[dict[str, object]] = []
    for family in _V109.FEATURE_FAMILIES:
        selector_pred, holdout_pred, meta = _V109._family_predictions(
            bars,
            horizon=HORIZON_MINUTES,
            family=str(family),
        )
        frames_by_family[str(family)] = (
            pd.concat([selector_pred, holdout_pred], ignore_index=True)
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        metas.append(meta)
    predictions = _weighted_average_probability_frames(frames_by_family, weights=MODEL_FAMILY_WEIGHTS)
    return predictions, metas


def _weighted_rescue_events(predictions: pd.DataFrame) -> pd.DataFrame:
    return _V131._probability_floor_events(
        predictions,
        floor=_V132.RESCUE_FLOOR,
        cooldown_minutes=_V132.RESCUE_COOLDOWN_MINUTES,
        source="v137_weighted_family_rescue_11_8_5",
        priority=8,
        fee_bps=_V131.FEE_BPS,
    )


def _passes_v137_gate(row: dict[str, object], *, v135_selected: dict[str, object]) -> bool:
    return (
        float(row.get("total_net_pnl_bps", 0.0)) > float(v135_selected["total_net_pnl_bps"]) + FLOAT_TOLERANCE_BPS
        and float(row.get("win_rate", 0.0)) > float(v135_selected["win_rate"]) + FLOAT_TOLERANCE_BPS
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
        "# Research V137 BTCUSDC Live Weighted Model Ensemble",
        "",
        "## Decision",
        "",
        f"- V135 total PnL: `{comparison['v135_total_net_pnl_bps']:.6f}` bps",
        f"- V135 win rate: `{comparison['v135_win_rate']:.6f}`",
        f"- V135 max drawdown: `{comparison['v135_max_drawdown_bps']:.6f}` bps",
        f"- V135 worst month: `{comparison['v135_worst_month']}` `{comparison['v135_worst_month_bps']:.6f}` bps",
        f"- V137 total PnL: `{selected['total_net_pnl_bps']:.6f}` bps",
        f"- V137 win rate: `{selected['win_rate']:.6f}`",
        f"- V137 max drawdown: `{selected['max_drawdown_bps']:.6f}` bps",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Skipped by drawdown guard: `{skipped_count}`",
        f"- Positive months: `{selected['positive_months']}/{selected['month_count']}`",
        f"- Worst month: `{selected['worst_month']}` `{selected['worst_month_bps']:.6f}` bps",
        f"- V137 model-improvement gate passed: `{selected['v137_model_improvement_passed']}`",
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
        "V137 keeps the V135 live structure: the same fixed UTC hour veto, the same realized drawdown guard, no daily trade cap, and no day-end ranking. The change is model-level only: the probability-floor rescue leg no longer uses equal family averaging; it weights the ma, price_context, and technical families as 11:8:5 before creating chronological rescue events. This is a research candidate, not a live trading guarantee.",
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

    bars = _V94._full_bars()
    predictions, family_metas = _weighted_family_predictions(bars)
    rescue = _weighted_rescue_events(predictions)
    base = _V132._load_v130_base_trades()
    raw_combined = _V132._combine_base_with_additive_rescue(base, rescue, rescue_weight=RESCUE_WEIGHT)
    pre_guard_trades = _V132._apply_fixed_hour_veto(raw_combined, veto_hours=VETO_HOURS)
    selected_trades = _V135._apply_drawdown_rest_of_day_guard(pre_guard_trades, drawdown_stop_bps=DRAWDOWN_STOP_BPS)
    selected = _V132._summarize_policy(
        "v137_v135_weighted_model_ensemble_11_8_5_rescue_weight_2p9_drawdown_stop_1600",
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
    selected["v137_model_improvement_passed"] = _passes_v137_gate(selected, v135_selected=v135_selected)
    status = (
        "weighted_model_ensemble_improvement_candidate_found"
        if bool(selected["v137_model_improvement_passed"])
        else "weighted_model_ensemble_improvement_not_found"
    )
    payload = {
        "version": "v137_btcusdc_live_weighted_model_ensemble",
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
        },
        "decision": {
            "required_positive_months": REQUIRED_POSITIVE_MONTHS,
            "status": status,
        },
        "config": _strategy_config(),
        "family_metas": family_metas,
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v137_live_weighted_model_ensemble_summary.json"),
            "weighted_predictions": str(OUT_DIR / "v137_weighted_predictions.csv"),
            "weighted_rescue_events": str(OUT_DIR / "v137_weighted_rescue_events.csv"),
            "raw_combined_trades": str(OUT_DIR / "v137_raw_combined_trades.csv"),
            "pre_guard_trades": str(OUT_DIR / "v137_pre_guard_trades.csv"),
            "selected_trades": str(OUT_DIR / "v137_selected_trades.csv"),
            "report": str(REPORT_PATH),
        },
    }
    predictions.to_csv(OUT_DIR / "v137_weighted_predictions.csv", index=False)
    rescue.to_csv(OUT_DIR / "v137_weighted_rescue_events.csv", index=False)
    raw_combined.to_csv(OUT_DIR / "v137_raw_combined_trades.csv", index=False)
    pre_guard_trades.to_csv(OUT_DIR / "v137_pre_guard_trades.csv", index=False)
    selected_trades.to_csv(OUT_DIR / "v137_selected_trades.csv", index=False)
    (OUT_DIR / "v137_live_weighted_model_ensemble_summary.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload, selected_trades, pre_guard_trades)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
