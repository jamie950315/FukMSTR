from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_contract_data import write_btc_contract_data_plan
from .btc_leverage_lock import BTCSideGuardSpec, _dedupe_float, _leverage_scenarios, _mask_for_btc_side_guard, _side_guard_candidates, default_btc_side_guard
from .btc_rescue_profit_lock import BTCRescueLaneSpec, _mask_for_rescue_lane, _selected_signal, default_v22_rescue_lane
from .exit_lock import ExitLockSpec, execution_path_arrays
from .profit_execution_lock import _accepted_shift_positions, _precompute_exit_pnl_by_row
from .profit_lock import _jsonable, _path_diagnostics
from .profit_success_fast import _stability
from .real_fee_lock import RealFeeLockGate, RealFeeSpec, _extra_cost_reserve, _fold_metrics, _mask_for_filters, _missed_trade_stress, _stress_summary, default_v19_fee_filters
from .slot_veto import _shift_values
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class BTCAdaptiveExitSpec:
    """Small slot-preserving BTC take-profit ladder.

    Entries are the frozen V22 entries.  This spec only decides the take-profit
    threshold assigned to an already selected row.  It never creates a new entry
    and, with reserve_horizon=True, an early exit never frees a slot for another
    overlapping trade.
    """

    long_default_tp_bps: float = 52.0
    short_default_tp_bps: float = 45.0
    short_opposing_signal_threshold: float = 0.45
    short_opposing_tp_bps: float = 25.0
    long_soft_prob_edge_max: float = 0.20
    long_soft_kline_signal_max: float = -0.40
    long_soft_tp_bps: float = 20.0
    stop_loss_bps: float = 0.0
    reserve_horizon: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BTCAdaptiveExitGate:
    min_trades: int = 11
    min_hit_rate: float = 1.0
    min_total_net_pnl_bps: float = 185.0
    min_mean_net_pnl_bps: float = 17.0
    min_fold_total_net_pnl_bps: float = 0.0
    min_fold_mean_net_pnl_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_entry_exit_family_addone_p: float = 0.01
    require_all_stress_cells_positive: bool = True
    max_stress_fee_side_bps: float = 10.0
    max_stress_latency_sec: float = 5.0
    missed_trade_gate_probability: float = 0.50
    missed_trade_min_p05_total_bps: float = 0.0
    extra_cost_gate_bps: float = 16.0
    extra_cost_min_total_bps: float = 0.0
    promoted_leverage_cap: float = 3.0
    shock_buffer_bps: float = 250.0
    maintenance_margin_bps: float = 50.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_v23_adaptive_exit_spec() -> BTCAdaptiveExitSpec:
    return BTCAdaptiveExitSpec()


def run_btc_adaptive_exit_lock(
    *,
    v17_run_dir: str | Path,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    side_guard: BTCSideGuardSpec | None = None,
    rescue_lane: BTCRescueLaneSpec | None = None,
    exit_spec: BTCAdaptiveExitSpec | None = None,
    horizon_sec: float = 90.0,
    latency_sec: float = 0.5,
    stress_fee_side_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    leverage_values: list[float] | None = None,
    shift_null_runs: int = 1000,
    random_scenarios: int = 10000,
    seed: int = 23023,
    gate: BTCAdaptiveExitGate | None = None,
    write_data_plan: bool = True,
    clean: bool = False,
) -> dict[str, object]:
    run = Path(v17_run_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    fee_spec = fee_spec or RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000)
    side_guard = side_guard or default_btc_side_guard()
    rescue_lane = rescue_lane or default_v22_rescue_lane()
    exit_spec = exit_spec or default_v23_adaptive_exit_spec()
    stress_fee_side_bps_values = _dedupe_float(stress_fee_side_bps_values or [4.0, 5.0, 6.0, 7.5, 10.0])
    stress_latency_sec_values = _dedupe_float(stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    leverage_values = _dedupe_float(leverage_values or [1.0, 2.0, 3.0, 5.0, 10.0, 20.0])
    gate = gate or BTCAdaptiveExitGate()

    source_path = run / "execution_lock_oof_backtest.csv"
    if not source_path.exists():
        raise FileNotFoundError(f"missing frozen V17 ledger: {source_path}")
    frame = pd.read_csv(source_path)
    if "timestamp" not in frame.columns:
        raise ValueError("execution_lock_oof_backtest.csv must contain timestamp")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    raw_signal = pd.to_numeric(frame.get("signal", 0), errors="coerce").fillna(0).astype(int).clip(-1, 1).to_numpy()
    selected_signal, component_masks = _selected_signal(frame, raw_signal, side_guard, rescue_lane)
    take_profit_by_row = assign_adaptive_take_profit_bps(frame, selected_signal, exit_spec)

    selected_bt, selected_metrics = backtest_dynamic_take_profit(
        frame,
        signal=selected_signal,
        take_profit_bps_by_row=take_profit_by_row,
        cost_bps=float(fee_spec.taker_taker_roundtrip_bps),
        horizon_sec=float(horizon_sec),
        latency_sec=float(latency_sec),
        stop_loss_bps=float(exit_spec.stop_loss_bps),
        reserve_horizon=bool(exit_spec.reserve_horizon),
    )
    selected_bt["real_taker_fee_bps_per_side"] = fee_spec.taker_fee_bps_per_side
    selected_bt["real_maker_fee_bps_per_side"] = fee_spec.maker_fee_bps_per_side
    selected_bt["real_roundtrip_fee_bps"] = selected_bt["traded"].astype(float) * fee_spec.taker_taker_roundtrip_bps
    selected_bt["v24_core_lane"] = component_masks["core"].astype(int)
    selected_bt["v24_rescue_lane"] = component_masks["rescue"].astype(int)
    selected_bt.to_csv(out / "btc_adaptive_exit_oof_backtest.csv", index=False)
    trades = selected_bt.loc[selected_bt["traded"].astype(int) == 1].copy().reset_index(drop=True)
    trades.to_csv(out / "btc_adaptive_exit_trade_ledger.csv", index=False)

    comparison = _comparison_rows(frame=frame, selected_signal=selected_signal, selected_exit=exit_spec, cost_bps=fee_spec.taker_taker_roundtrip_bps, horizon_sec=horizon_sec, latency_sec=latency_sec)
    comparison.to_csv(out / "btc_v22_v24_exit_comparison.csv", index=False)

    fold_metrics = _fold_metrics(trades)
    fold_metrics.to_csv(out / "fold_metrics.csv", index=False)
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    bootstrap = block_bootstrap_pnl(pnl, iterations=5000, block_size=5, seed=seed)
    stability = _stability(selected_bt)
    fold_arr = pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy()
    path = _path_diagnostics(pnl, fold_arr)

    stress = _stress_dynamic(frame=frame, selected_signal=selected_signal, exit_spec=exit_spec, fee_side_values=stress_fee_side_bps_values, latency_values=stress_latency_sec_values, horizon_sec=horizon_sec)
    stress.to_csv(out / "btc_adaptive_fee_latency_stress.csv", index=False)
    stress_summary = _stress_summary(stress, RealFeeLockGate(max_stress_fee_side_bps=gate.max_stress_fee_side_bps, max_stress_latency_sec=gate.max_stress_latency_sec))

    miss = _missed_trade_stress(trades, miss_probabilities=[0.1, 0.2, 0.3, 0.4, gate.missed_trade_gate_probability, 0.6, 0.7], scenarios=random_scenarios, seed=seed)
    miss.to_csv(out / "btc_adaptive_missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_cost_bps_values=[0, 1, 2, 3, 5, 7.5, 10, 12, 14, gate.extra_cost_gate_bps])
    extra.to_csv(out / "btc_adaptive_extra_cost_reserve.csv", index=False)

    leverage = _leverage_scenarios(
        trades=trades,
        leverage_values=leverage_values,
        fee_roundtrip_bps=fee_spec.taker_taker_roundtrip_bps,
        maintenance_margin_bps=float(gate.maintenance_margin_bps),
        shock_buffer_bps=float(gate.shock_buffer_bps),
    )
    leverage.to_csv(out / "btc_adaptive_leverage_scenarios.csv", index=False)

    candidate_df = _adaptive_exit_candidate_scan(frame, raw_signal, side_guard, rescue_lane, fee_spec.taker_taker_roundtrip_bps, horizon_sec, latency_sec)
    candidate_df.to_csv(out / "btc_adaptive_entry_exit_candidate_scan.csv", index=False)

    family_df, family_null = _adaptive_entry_exit_family_shift_null(
        frame=frame,
        raw_signal=raw_signal,
        selected_side_guard=side_guard,
        selected_rescue_lane=rescue_lane,
        selected_exit_spec=exit_spec,
        selected_total=float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        selected_mean=float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        cost_bps=fee_spec.taker_taker_roundtrip_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        shift_null_runs=shift_null_runs,
        min_trades=gate.min_trades,
    )
    family_df.to_csv(out / "btc_adaptive_entry_exit_family_shift_null.csv", index=False)

    data_plan = write_btc_contract_data_plan(out_dir=out / "btc_contract_data_plan") if write_data_plan else {}

    aggregate = _aggregate(
        selected_metrics=selected_metrics,
        folds=fold_metrics,
        bootstrap=bootstrap,
        stability=stability,
        path=path,
        stress_summary=stress_summary,
        miss=miss,
        extra=extra,
        leverage=leverage,
        family_null=family_null,
        gate=gate,
    )

    result: dict[str, object] = {
        "version": "v24_btc_adaptive_exit_lock",
        "v17_run_dir": str(run),
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "horizon_sec": float(horizon_sec),
        "latency_sec": float(latency_sec),
        "v19_filters": [f.to_dict() for f in default_v19_fee_filters()],
        "btc_side_guard": side_guard.to_dict(),
        "btc_rescue_lane": rescue_lane.to_dict(),
        "btc_adaptive_exit_spec": exit_spec.to_dict(),
        "entry_components": {k: int(v.sum()) for k, v in component_masks.items()},
        "stress_fee_side_bps_values": [float(x) for x in stress_fee_side_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "leverage_values": [float(x) for x in leverage_values],
        "adaptive_exit_candidate_count": int(len(_adaptive_exit_specs())),
        "entry_exit_family_candidate_count": int(family_null.get("candidate_count", 0)),
        "predeclared_full_entry_exit_candidate_count": int(len(_side_guard_candidates()) * len(_rescue_lane_candidates_v23()) * len(_adaptive_exit_specs())),
        "shift_null_runs": int(shift_null_runs),
        "data_plan": data_plan,
        "aggregate": aggregate,
        "gate_config": gate.to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, comparison, candidate_df, fold_metrics, stress, miss, extra, leverage)
    (out / "DONE.marker").write_text("ok\n", encoding="utf-8")
    return _jsonable(result)


def assign_adaptive_take_profit_bps(frame: pd.DataFrame, signal: np.ndarray, spec: BTCAdaptiveExitSpec) -> np.ndarray:
    dirs = np.asarray(signal, dtype=int)
    out = np.zeros(len(frame), dtype=float)
    out[dirs > 0] = float(spec.long_default_tp_bps)
    out[dirs < 0] = float(spec.short_default_tp_bps)
    k15 = pd.to_numeric(frame.get("kline_15s_signal", np.nan), errors="coerce").to_numpy(dtype=float)
    edge = pd.to_numeric(frame.get("prob_edge", np.nan), errors="coerce").to_numpy(dtype=float)
    short_opposing = (dirs < 0) & np.isfinite(k15) & (k15 >= float(spec.short_opposing_signal_threshold))
    long_soft = (dirs > 0) & np.isfinite(k15) & np.isfinite(edge) & (edge <= float(spec.long_soft_prob_edge_max)) & (k15 <= float(spec.long_soft_kline_signal_max))
    out[short_opposing] = float(spec.short_opposing_tp_bps)
    out[long_soft] = float(spec.long_soft_tp_bps)
    return out


def backtest_dynamic_take_profit(
    predictions: pd.DataFrame,
    *,
    signal: np.ndarray,
    take_profit_bps_by_row: np.ndarray,
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    stop_loss_bps: float = 0.0,
    reserve_horizon: bool = True,
) -> tuple[pd.DataFrame, dict[str, float]]:
    frame = predictions.copy().sort_values("timestamp").reset_index(drop=True)
    if len(signal) != len(frame) or len(take_profit_bps_by_row) != len(frame):
        raise ValueError("signal and take_profit_bps_by_row must match frame length")
    raw = np.asarray(signal, dtype=int).clip(-1, 1)
    tps = np.asarray(take_profit_bps_by_row, dtype=float)
    ts, bid, ask, entry_idx, exit_idx, valid, horizon_ns = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    kept = np.zeros(len(frame), dtype=int)
    entry_px = np.full(len(frame), np.nan, dtype=float)
    exit_px = np.full(len(frame), np.nan, dtype=float)
    gross = np.zeros(len(frame), dtype=float)
    hold_sec = np.zeros(len(frame), dtype=float)
    exit_reason = ["" for _ in range(len(frame))]
    applied_tp = np.zeros(len(frame), dtype=float)
    next_allowed = -10**30
    sl_on = np.isfinite(float(stop_loss_bps)) and float(stop_loss_bps) > 0.0
    sl_bps = float(stop_loss_bps)
    for i, sig in enumerate(raw):
        sig = int(np.clip(sig, -1, 1))
        if sig == 0 or int(ts[i]) < next_allowed or not bool(valid[i]):
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if xi <= ei:
            continue
        tp_bps = float(tps[i])
        tp_on = np.isfinite(tp_bps) and tp_bps > 0.0
        reason = "horizon"
        x = xi
        if sig > 0:
            ep = float(ask[ei])
            if not (np.isfinite(ep) and ep > 0.0):
                continue
            tp_px = ep * (1.0 + tp_bps / 10000.0) if tp_on else np.inf
            sl_px = ep * (1.0 - sl_bps / 10000.0) if sl_on else -np.inf
            for j in range(ei + 1, xi + 1):
                if sl_on and float(bid[j]) <= sl_px:
                    x = j; reason = "stop_loss"; break
                if tp_on and float(bid[j]) >= tp_px:
                    x = j; reason = "take_profit"; break
            xp = float(bid[x])
            pnl = (xp - ep) / ep * 10000.0
        else:
            ep = float(bid[ei])
            if not (np.isfinite(ep) and ep > 0.0):
                continue
            tp_px = ep * (1.0 - tp_bps / 10000.0) if tp_on else -np.inf
            sl_px = ep * (1.0 + sl_bps / 10000.0) if sl_on else np.inf
            for j in range(ei + 1, xi + 1):
                if sl_on and float(ask[j]) >= sl_px:
                    x = j; reason = "stop_loss"; break
                if tp_on and float(ask[j]) <= tp_px:
                    x = j; reason = "take_profit"; break
            xp = float(ask[x])
            pnl = (ep - xp) / ep * 10000.0
        if not (np.isfinite(xp) and xp > 0.0):
            continue
        kept[i] = sig
        entry_px[i] = ep
        exit_px[i] = xp
        gross[i] = float(pnl)
        exit_reason[i] = reason
        hold_sec[i] = float((int(ts[x]) - int(ts[ei])) / 1_000_000_000.0)
        applied_tp[i] = tp_bps
        next_allowed = int(ts[i]) + int(horizon_ns) if reserve_horizon else int(ts[x])
    frame["raw_selective_signal"] = raw
    frame["signal"] = kept
    frame["traded"] = (kept != 0).astype(int)
    frame["entry_px_taker"] = entry_px
    frame["exit_px_taker"] = exit_px
    frame["latency_sec"] = float(latency_sec)
    frame["gross_pnl_bps"] = gross
    frame["cost_bps"] = frame["traded"].astype(float) * float(cost_bps)
    frame["net_pnl_bps"] = frame["gross_pnl_bps"] - frame["cost_bps"]
    frame["equity_bps"] = frame["net_pnl_bps"].cumsum()
    frame["exit_reason"] = exit_reason
    frame["hold_sec"] = hold_sec
    frame["take_profit_bps"] = applied_tp
    frame["stop_loss_bps"] = float(stop_loss_bps)
    frame["reserve_horizon"] = bool(reserve_horizon)
    metrics = _summarize_dynamic(frame)
    return frame, metrics


def _summarize_dynamic(bt: pd.DataFrame) -> dict[str, float]:
    trades = bt.loc[bt["traded"].astype(int) == 1].copy()
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    if len(pnl) == 0:
        return {"events": float(len(bt)), "trades": 0.0, "trade_rate": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "median_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0, "sharpe_like": 0.0, "max_drawdown_bps": 0.0, "profit_factor": 0.0, "take_profit_exits": 0.0, "stop_loss_exits": 0.0, "horizon_exits": 0.0, "mean_hold_sec": 0.0}
    equity = np.cumsum(pnl)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float(-pnl[pnl < 0].sum())
    std = float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0
    return {
        "events": float(len(bt)),
        "trades": float(len(pnl)),
        "trade_rate": float(len(pnl) / len(bt)) if len(bt) else 0.0,
        "hit_rate": float((pnl > 0).mean()),
        "mean_net_pnl_bps": float(pnl.mean()),
        "median_net_pnl_bps": float(np.median(pnl)),
        "total_net_pnl_bps": float(pnl.sum()),
        "sharpe_like": float(pnl.mean() / std * np.sqrt(len(pnl))) if std > 0 else 0.0,
        "max_drawdown_bps": float(dd.min()) if len(dd) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0),
        "take_profit_exits": float((trades.get("exit_reason") == "take_profit").sum()),
        "stop_loss_exits": float((trades.get("exit_reason") == "stop_loss").sum()),
        "horizon_exits": float((trades.get("exit_reason") == "horizon").sum()),
        "mean_hold_sec": float(pd.to_numeric(trades.get("hold_sec", 0), errors="coerce").mean()),
    }


def _comparison_rows(*, frame: pd.DataFrame, selected_signal: np.ndarray, selected_exit: BTCAdaptiveExitSpec, cost_bps: float, horizon_sec: float, latency_sec: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    fixed_specs = [("v22_fixed_tp52", 52.0), ("v24_short_tp45_long_tp52_no_compress", np.nan)]
    for label, fixed_tp in fixed_specs:
        if np.isfinite(fixed_tp):
            tps = np.where(np.asarray(selected_signal) != 0, float(fixed_tp), 0.0)
        else:
            base_spec = BTCAdaptiveExitSpec(short_opposing_signal_threshold=9e9, long_soft_prob_edge_max=-9e9)
            tps = assign_adaptive_take_profit_bps(frame, selected_signal, base_spec)
        bt, met = backtest_dynamic_take_profit(frame, signal=selected_signal, take_profit_bps_by_row=tps, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec)
        trades = bt.loc[bt["traded"].astype(int) == 1]
        rows.append({"label": label, **_jsonable(met), "min_trade_net_pnl_bps": float(pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").min()) if not trades.empty else 0.0})
    tps = assign_adaptive_take_profit_bps(frame, selected_signal, selected_exit)
    bt, met = backtest_dynamic_take_profit(frame, signal=selected_signal, take_profit_bps_by_row=tps, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, stop_loss_bps=selected_exit.stop_loss_bps, reserve_horizon=selected_exit.reserve_horizon)
    trades = bt.loc[bt["traded"].astype(int) == 1]
    rows.append({"label": "v24_adaptive_exit_ladder", **_jsonable(met), "min_trade_net_pnl_bps": float(pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").min()) if not trades.empty else 0.0})
    return pd.DataFrame(rows)


def _stress_dynamic(*, frame: pd.DataFrame, selected_signal: np.ndarray, exit_spec: BTCAdaptiveExitSpec, fee_side_values: list[float], latency_values: list[float], horizon_sec: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    tps = assign_adaptive_take_profit_bps(frame, selected_signal, exit_spec)
    for fee_side in fee_side_values:
        for latency in latency_values:
            bt, met = backtest_dynamic_take_profit(frame, signal=selected_signal, take_profit_bps_by_row=tps, cost_bps=2.0 * float(fee_side), horizon_sec=horizon_sec, latency_sec=float(latency), stop_loss_bps=exit_spec.stop_loss_bps, reserve_horizon=exit_spec.reserve_horizon)
            rows.append({"taker_fee_bps_per_side": float(fee_side), "roundtrip_fee_bps": 2.0 * float(fee_side), "latency_sec": float(latency), **_jsonable(met)})
    return pd.DataFrame(rows)


def _adaptive_exit_specs() -> list[BTCAdaptiveExitSpec]:
    """Pre-declared compact exit family for V24.

    The family is deliberately small.  It includes the fixed V22 target, the
    side-asymmetric ladder, and small one-feature compressor variants around the
    selected V24 rule.  This avoids unbounded mining on the bundled sample while
    still correcting the adaptive exit choice.
    """
    specs: list[BTCAdaptiveExitSpec] = []
    # V22 fixed-exit baseline and simple side ladder.
    specs.append(BTCAdaptiveExitSpec(long_default_tp_bps=52.0, short_default_tp_bps=52.0, short_opposing_signal_threshold=9e9, long_soft_prob_edge_max=-9e9))
    specs.append(BTCAdaptiveExitSpec(long_default_tp_bps=52.0, short_default_tp_bps=45.0, short_opposing_signal_threshold=9e9, long_soft_prob_edge_max=-9e9))
    # Short compressor variants.
    for sth in [0.35, 0.45, 0.55]:
        for stp in [20.0, 25.0, 30.0]:
            specs.append(BTCAdaptiveExitSpec(long_default_tp_bps=52.0, short_default_tp_bps=45.0, short_opposing_signal_threshold=sth, short_opposing_tp_bps=stp, long_soft_prob_edge_max=-9e9))
    # Long-soft compressor variants.
    for lpe in [0.15, 0.20, 0.25]:
        for lks in [-0.30, -0.40, -0.50]:
            for ltp in [20.0, 25.0]:
                specs.append(BTCAdaptiveExitSpec(long_default_tp_bps=52.0, short_default_tp_bps=45.0, short_opposing_signal_threshold=9e9, long_soft_prob_edge_max=lpe, long_soft_kline_signal_max=lks, long_soft_tp_bps=ltp))
    # Combined variants around the selected short compressor.
    for lpe in [0.15, 0.20, 0.25]:
        for lks in [-0.30, -0.40, -0.50]:
            for ltp in [20.0, 25.0]:
                specs.append(BTCAdaptiveExitSpec(long_default_tp_bps=52.0, short_default_tp_bps=45.0, short_opposing_signal_threshold=0.45, short_opposing_tp_bps=25.0, long_soft_prob_edge_max=lpe, long_soft_kline_signal_max=lks, long_soft_tp_bps=ltp))
    out: list[BTCAdaptiveExitSpec] = []
    seen: set[str] = set()
    for spec in specs:
        key = json.dumps(spec.to_dict(), sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(spec)
    return out

def _rescue_lane_candidates_v23() -> list[BTCRescueLaneSpec | None]:
    out: list[BTCRescueLaneSpec | None] = [None]
    for signal_th in [-0.75, -0.70, -0.65, -0.60]:
        for rv_th in [18.0, 20.0, 22.0, 24.0]:
            out.append(BTCRescueLaneSpec(signal_threshold=float(signal_th), volatility_threshold=float(rv_th)))
    return out


def _adaptive_exit_candidate_scan(frame: pd.DataFrame, raw_signal: np.ndarray, side_guard: BTCSideGuardSpec, rescue_lane: BTCRescueLaneSpec, cost_bps: float, horizon_sec: float, latency_sec: float) -> pd.DataFrame:
    selected_signal, _ = _selected_signal(frame, raw_signal, side_guard, rescue_lane)
    rows: list[dict[str, object]] = []
    for spec in _adaptive_exit_specs():
        tps = assign_adaptive_take_profit_bps(frame, selected_signal, spec)
        bt, metrics = backtest_dynamic_take_profit(frame, signal=selected_signal, take_profit_bps_by_row=tps, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, stop_loss_bps=spec.stop_loss_bps, reserve_horizon=spec.reserve_horizon)
        trades = bt.loc[bt["traded"].astype(int) == 1]
        folds = _fold_metrics(trades)
        rows.append({
            "exit_spec_json": json.dumps(spec.to_dict(), sort_keys=True),
            **_jsonable(metrics),
            "fold_min_total_net_pnl_bps": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
            "fold_min_mean_net_pnl_bps": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
            "min_trade_net_pnl_bps": float(pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").min()) if not trades.empty else 0.0,
        })
    return pd.DataFrame(rows).sort_values(["total_net_pnl_bps", "mean_net_pnl_bps"], ascending=False).reset_index(drop=True)


def _same_dict(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a.to_dict() == b.to_dict()


def _same_exit(a: BTCAdaptiveExitSpec, b: BTCAdaptiveExitSpec) -> bool:
    return a.to_dict() == b.to_dict()


def _adaptive_entry_exit_family_shift_null(
    *,
    frame: pd.DataFrame,
    raw_signal: np.ndarray,
    selected_side_guard: BTCSideGuardSpec,
    selected_rescue_lane: BTCRescueLaneSpec,
    selected_exit_spec: BTCAdaptiveExitSpec,
    selected_total: float,
    selected_mean: float,
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    shift_null_runs: int,
    min_trades: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    arrays = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    tp_values = sorted({
        20.0, 25.0, 30.0, 40.0, 45.0, 50.0, 52.0,
        selected_exit_spec.long_default_tp_bps,
        selected_exit_spec.short_default_tp_bps,
        selected_exit_spec.short_opposing_tp_bps,
        selected_exit_spec.long_soft_tp_bps,
    })
    pnl_by_tp: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for tp in tp_values:
        pnl_by_tp[float(tp)] = _precompute_exit_pnl_by_row(arrays, cost_bps=cost_bps, spec=ExitLockSpec(take_profit_bps=float(tp), stop_loss_bps=selected_exit_spec.stop_loss_bps, reserve_horizon=selected_exit_spec.reserve_horizon))
    idx = np.flatnonzero(np.asarray(raw_signal, dtype=int) != 0).astype(int)
    sig = np.asarray(raw_signal, dtype=int)[idx]
    min_shift = max(1, int(round(float(horizon_sec) / 0.5)))
    shifts = _shift_values(n=len(frame), shifts=int(shift_null_runs), min_shift=min_shift)
    # V24 does not retune entries.  V22 already corrected the entry family; here we
    # hold the V22 entry rule fixed and correct only the new adaptive-exit ladder.
    side_candidates = [selected_side_guard]
    rescue_candidates = [selected_rescue_lane]
    exit_candidates = _adaptive_exit_specs()
    candidate_count = len(side_candidates) * len(rescue_candidates) * len(exit_candidates)

    rows: list[dict[str, object]] = []
    exceed_total = exceed_mean = selected_only_exceed_total = selected_only_exceed_mean = 0
    null_max_total = null_max_mean = selected_null_max_total = selected_null_max_mean = -np.inf
    for shift in shifts:
        rows_idx, dirs = _accepted_shift_positions(idx, sig, int(shift), arrays)
        best_total = best_mean = selected_total_shift = selected_mean_shift = -np.inf
        best_trades = selected_trades_shift = 0
        if len(rows_idx):
            sub = frame.iloc[rows_idx].reset_index(drop=True)
            dirs = np.asarray(dirs, dtype=int)
            v19_mask = _mask_for_filters(sub, dirs, default_v19_fee_filters()) & (dirs != 0)
            side_masks: list[np.ndarray] = []
            for side in side_candidates:
                m = v19_mask.copy()
                if side is not None:
                    m &= _mask_for_btc_side_guard(sub, dirs, side)
                side_masks.append(m)
            rescue_masks = [_mask_for_rescue_lane(sub, dirs, rescue) if rescue is not None else np.zeros(len(sub), dtype=bool) for rescue in rescue_candidates]
            k15 = pd.to_numeric(sub.get("kline_15s_signal", np.nan), errors="coerce").to_numpy(dtype=float)
            edge = pd.to_numeric(sub.get("prob_edge", np.nan), errors="coerce").to_numpy(dtype=float)
            for side, side_mask in zip(side_candidates, side_masks):
                for rescue, rescue_mask in zip(rescue_candidates, rescue_masks):
                    entry_mask = side_mask | rescue_mask
                    if not entry_mask.any():
                        continue
                    for ex in exit_candidates:
                        tps = _assign_tp_arrays(dirs, k15, edge, ex)
                        pnl_all = np.full(len(rows_idx), np.nan, dtype=float)
                        for tp in tp_values:
                            use = np.isclose(tps, float(tp))
                            if not use.any():
                                continue
                            p_long, p_short = pnl_by_tp[float(tp)]
                            pnl_all[use] = np.where(dirs[use] > 0, p_long[rows_idx[use]], p_short[rows_idx[use]])
                        pnl = pnl_all[entry_mask]
                        pnl = pnl[np.isfinite(pnl)]
                        if len(pnl) < int(min_trades):
                            continue
                        total = float(pnl.sum())
                        mean = float(pnl.mean()) if len(pnl) else 0.0
                        if total > best_total:
                            best_total = total; best_trades = int(len(pnl))
                        if mean > best_mean:
                            best_mean = mean
                        if _same_dict(side, selected_side_guard) and _same_dict(rescue, selected_rescue_lane) and _same_exit(ex, selected_exit_spec):
                            selected_total_shift = total; selected_mean_shift = mean; selected_trades_shift = int(len(pnl))
        best_total = float(best_total if np.isfinite(best_total) else 0.0)
        best_mean = float(best_mean if np.isfinite(best_mean) else 0.0)
        selected_total_shift = float(selected_total_shift if np.isfinite(selected_total_shift) else 0.0)
        selected_mean_shift = float(selected_mean_shift if np.isfinite(selected_mean_shift) else 0.0)
        null_max_total = max(null_max_total, best_total)
        null_max_mean = max(null_max_mean, best_mean)
        selected_null_max_total = max(selected_null_max_total, selected_total_shift)
        selected_null_max_mean = max(selected_null_max_mean, selected_mean_shift)
        if best_total >= float(selected_total):
            exceed_total += 1
        if best_mean >= float(selected_mean):
            exceed_mean += 1
        if selected_total_shift >= float(selected_total):
            selected_only_exceed_total += 1
        if selected_mean_shift >= float(selected_mean):
            selected_only_exceed_mean += 1
        rows.append({
            "shift_rows": int(shift),
            "candidate_count": int(candidate_count),
            "best_family_trades": int(best_trades),
            "entry_exit_family_max_total_bps": best_total,
            "entry_exit_family_max_mean_bps": best_mean,
            "selected_only_trades": int(selected_trades_shift),
            "selected_only_total_bps": selected_total_shift,
            "selected_only_mean_bps": selected_mean_shift,
        })
    df = pd.DataFrame(rows)
    denom = len(df) + 1
    summary = {
        "selected_total_net_pnl_bps": float(selected_total),
        "selected_mean_net_pnl_bps": float(selected_mean),
        "shift_null_runs": int(len(df)),
        "candidate_count": int(candidate_count),
        "side_candidate_count": int(len(side_candidates)),
        "rescue_candidate_count": int(len(rescue_candidates)),
        "adaptive_exit_candidate_count": int(len(exit_candidates)),
        "family_null_total_max_bps": float(null_max_total if np.isfinite(null_max_total) else 0.0),
        "family_null_mean_max_bps": float(null_max_mean if np.isfinite(null_max_mean) else 0.0),
        "family_exceed_total_count": int(exceed_total),
        "family_exceed_mean_count": int(exceed_mean),
        "family_addone_p_total_ge_selected": float((exceed_total + 1) / denom),
        "family_addone_p_mean_ge_selected": float((exceed_mean + 1) / denom),
        "selected_only_null_total_max_bps": float(selected_null_max_total if np.isfinite(selected_null_max_total) else 0.0),
        "selected_only_null_mean_max_bps": float(selected_null_max_mean if np.isfinite(selected_null_max_mean) else 0.0),
        "selected_only_exceed_total_count": int(selected_only_exceed_total),
        "selected_only_exceed_mean_count": int(selected_only_exceed_mean),
        "selected_only_addone_p_total_ge_selected": float((selected_only_exceed_total + 1) / denom),
        "selected_only_addone_p_mean_ge_selected": float((selected_only_exceed_mean + 1) / denom),
    }
    return df, summary


def _assign_tp_arrays(dirs: np.ndarray, k15: np.ndarray, edge: np.ndarray, spec: BTCAdaptiveExitSpec) -> np.ndarray:
    out = np.zeros(len(dirs), dtype=float)
    out[dirs > 0] = float(spec.long_default_tp_bps)
    out[dirs < 0] = float(spec.short_default_tp_bps)
    out[(dirs < 0) & np.isfinite(k15) & (k15 >= float(spec.short_opposing_signal_threshold))] = float(spec.short_opposing_tp_bps)
    out[(dirs > 0) & np.isfinite(k15) & np.isfinite(edge) & (edge <= float(spec.long_soft_prob_edge_max)) & (k15 <= float(spec.long_soft_kline_signal_max))] = float(spec.long_soft_tp_bps)
    return out


def _row_for(df: pd.DataFrame, column: str, value: float) -> dict[str, object]:
    if df.empty or column not in df.columns:
        return {}
    vals = pd.to_numeric(df[column], errors="coerce")
    rows = df.loc[np.isclose(vals, float(value))]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _aggregate(*, selected_metrics, folds, bootstrap, stability, path, stress_summary, miss, extra, leverage, family_null, gate: BTCAdaptiveExitGate) -> dict[str, object]:
    miss_row = _row_for(miss, "miss_probability", gate.missed_trade_gate_probability)
    extra_row = _row_for(extra, "extra_cost_bps_per_trade", gate.extra_cost_gate_bps)
    lev_rows = leverage.loc[pd.to_numeric(leverage.get("leverage", 0), errors="coerce") <= float(gate.promoted_leverage_cap)] if not leverage.empty else pd.DataFrame()
    agg = {
        "trades": int(selected_metrics.get("trades", 0)),
        "hit_rate": float(selected_metrics.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        "median_net_pnl_bps": float(selected_metrics.get("median_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        "profit_factor": float(selected_metrics.get("profit_factor", 0.0)) if np.isfinite(float(selected_metrics.get("profit_factor", 0.0))) else "inf",
        "max_drawdown_bps": float(selected_metrics.get("max_drawdown_bps", 0.0)),
        "take_profit_exits": int(selected_metrics.get("take_profit_exits", 0)),
        "horizon_exits": int(selected_metrics.get("horizon_exits", 0)),
        "folds_with_trades": int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0,
        "fold_min_total_net_pnl_bps": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "fold_min_mean_net_pnl_bps": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "positive_equal_trade_blocks_5": int(stability.get("positive_equal_trade_blocks_5", 0)),
        "positive_equal_trade_blocks_10": int(stability.get("positive_equal_trade_blocks_10", 0)),
        "equal_trade_block_5_min_total_bps": float(stability.get("equal_trade_block_5_min_total_bps", 0.0)),
        "equal_trade_block_10_min_total_bps": float(stability.get("equal_trade_block_10_min_total_bps", 0.0)),
        "top5_winner_removed_total_bps": float(path.get("top5_winner_removed_total_bps", 0.0)),
        "top7_winner_removed_total_bps": float(path.get("top7_winner_removed_total_bps", 0.0)),
        "leave_one_trade_out_min_total_bps": float(path.get("leave_one_trade_out_min_total_bps", 0.0)),
        "leave_one_fold_out_min_total_bps": float(path.get("leave_one_fold_out_min_total_bps", 0.0)),
        "stress_gate_min_mean_net_pnl_bps": float(stress_summary.get("gate_min_mean_net_pnl_bps", 0.0)),
        "stress_gate_min_total_net_pnl_bps": float(stress_summary.get("gate_min_total_net_pnl_bps", 0.0)),
        "stress_gate_all_positive": bool(stress_summary.get("gate_all_positive", False)),
        "stress_all_cells_min_mean_net_pnl_bps": float(stress_summary.get("all_cells_min_mean_net_pnl_bps", 0.0)),
        "stress_all_cells_min_total_net_pnl_bps": float(stress_summary.get("all_cells_min_total_net_pnl_bps", 0.0)),
        "stress_all_cells_positive": bool(stress_summary.get("all_cells_positive", False)),
        "missed_trade_gate_p05_total_bps": float(miss_row.get("p05_total_bps", 0.0)),
        "missed_trade_gate_positive_rate": float(miss_row.get("positive_scenario_rate", 0.0)),
        "extra_cost_gate_total_bps": float(extra_row.get("total_net_pnl_bps", 0.0)),
        "extra_cost_gate_hit_rate": float(extra_row.get("hit_rate", 0.0)),
        "entry_exit_family_addone_p_total": float(family_null.get("family_addone_p_total_ge_selected", 1.0)),
        "entry_exit_family_addone_p_mean": float(family_null.get("family_addone_p_mean_ge_selected", 1.0)),
        "selected_only_addone_p_total": float(family_null.get("selected_only_addone_p_total_ge_selected", 1.0)),
        "selected_only_addone_p_mean": float(family_null.get("selected_only_addone_p_mean_ge_selected", 1.0)),
        "entry_exit_family_null": family_null,
        "leverage_promoted_cap": float(gate.promoted_leverage_cap),
        "leverage_promoted_rows_all_pass_shock_buffer": bool(lev_rows["passes_shock_buffer"].astype(bool).all()) if not lev_rows.empty else False,
        "stress_summary": stress_summary,
    }
    checks = {
        "enough_trades": int(agg["trades"]) >= int(gate.min_trades),
        "hit_rate": float(agg["hit_rate"]) >= float(gate.min_hit_rate),
        "mean_profit": float(agg["mean_net_pnl_bps"]) >= float(gate.min_mean_net_pnl_bps),
        "total_profit": float(agg["total_net_pnl_bps"]) >= float(gate.min_total_net_pnl_bps),
        "fold_total_positive": float(agg["fold_min_total_net_pnl_bps"]) > float(gate.min_fold_total_net_pnl_bps),
        "fold_mean_positive": float(agg["fold_min_mean_net_pnl_bps"]) > float(gate.min_fold_mean_net_pnl_bps),
        "bootstrap_p05_positive": float(agg["bootstrap_mean_p05_bps"]) > float(gate.min_bootstrap_mean_p05_bps),
        "selected_only_null": max(float(agg["selected_only_addone_p_total"]), float(agg["selected_only_addone_p_mean"])) <= float(gate.max_entry_exit_family_addone_p),
        "entry_exit_family_null": max(float(agg["entry_exit_family_addone_p_total"]), float(agg["entry_exit_family_addone_p_mean"])) <= float(gate.max_entry_exit_family_addone_p),
        "fee_latency_stress_gate": bool(agg["stress_gate_all_positive"]) and float(agg["stress_gate_min_mean_net_pnl_bps"]) > 0 and float(agg["stress_gate_min_total_net_pnl_bps"]) > 0,
        "fee_latency_all_cells": (not bool(gate.require_all_stress_cells_positive)) or bool(agg["stress_all_cells_positive"]),
        "missed_trade_p05_positive": float(agg["missed_trade_gate_p05_total_bps"]) > float(gate.missed_trade_min_p05_total_bps),
        "extra_cost_positive": float(agg["extra_cost_gate_total_bps"]) > float(gate.extra_cost_min_total_bps),
        "promoted_leverage_buffer": bool(agg["leverage_promoted_rows_all_pass_shock_buffer"]),
    }
    agg["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return _jsonable(agg)


def _write_report(path: Path, result: dict[str, object], comparison: pd.DataFrame, candidates: pd.DataFrame, folds: pd.DataFrame, stress: pd.DataFrame, miss: pd.DataFrame, extra: pd.DataFrame, leverage: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V24 BTC Adaptive Exit Lock",
        "",
        "V24 keeps the V22 BTC entries frozen and changes only the slot-preserving take-profit ladder. It does not add trades and it does not release early-exit slots for overlapping replacement trades.",
        "",
        "## Frozen inputs",
        "",
        "```json",
        json.dumps({
            "fee_spec": result["fee_spec"],
            "horizon_sec": result["horizon_sec"],
            "latency_sec": result["latency_sec"],
            "v19_filters": result["v19_filters"],
            "btc_side_guard": result["btc_side_guard"],
            "btc_rescue_lane": result["btc_rescue_lane"],
            "btc_adaptive_exit_spec": result["btc_adaptive_exit_spec"],
        }, indent=2),
        "```",
        "",
        "## Aggregate gate",
        "",
        "```json",
        json.dumps(_jsonable(agg), indent=2),
        "```",
        "",
        "## V22/V24 comparison",
        "",
        comparison.to_csv(index=False).strip(),
        "",
        "## Top adaptive-exit candidates",
        "",
        candidates.head(20).to_csv(index=False).strip() if not candidates.empty else "No candidates.",
        "",
        "## Fold metrics",
        "",
        folds.to_csv(index=False).strip() if not folds.empty else "No folds.",
        "",
        "## Fee and latency stress",
        "",
        stress.to_csv(index=False).strip(),
        "",
        "## Missed-trade stress",
        "",
        miss.to_csv(index=False).strip(),
        "",
        "## Extra-cost reserve",
        "",
        extra.to_csv(index=False).strip(),
        "",
        "## Leverage scenarios",
        "",
        leverage.to_csv(index=False).strip(),
        "",
        "## Caveat",
        "",
        "This remains a bundled-sample research result. The entry policy and adaptive exit ladder should now be frozen before independent BTC contract days are used.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
