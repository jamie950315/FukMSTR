from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_contract_data import write_btc_contract_data_plan
from .btc_leverage_lock import (
    BTCSideGuardSpec,
    _compare,
    _dedupe_float,
    _leverage_scenarios,
    _mask_for_btc_side_guard,
    _side_guard_candidates,
    default_btc_side_guard,
)
from .exit_lock import ExitLockSpec, backtest_fixed_signals_taker_bidask_exit_lock, execution_path_arrays
from .profit_execution_lock import _accepted_shift_positions, _precompute_exit_pnl_by_row
from .profit_lock import _jsonable, _path_diagnostics
from .profit_success_fast import _stability
from .real_fee_lock import (
    RealFeeLockGate,
    RealFeeSpec,
    _extra_cost_reserve,
    _fold_metrics,
    _mask_for_filters,
    _missed_trade_stress,
    _stress_selected,
    _stress_summary,
    default_v19_fee_filters,
)
from .slot_veto import _shift_values
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class BTCRescueLaneSpec:
    """One conservative add-back lane for high-fee BTC contract use.

    The lane is slot-preserving: it can only re-enable a pre-existing frozen V17
    slot. It never creates a replacement overlapping trade. The default lane is a
    long-only BTC snapback/breakout lane discovered after V20 left a large positive
    long setup out because 1m volatility was too high for the V19 high-fee guard.
    """

    enabled: bool = True
    side: str = "long"
    signal_column: str = "kline_15s_signal"
    signal_operator: str = "<="
    signal_threshold: float = -0.70
    volatility_column: str = "kline_1m_rv_3_bps"
    volatility_operator: str = ">="
    volatility_threshold: float = 20.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BTCRescueProfitGate:
    min_trades: int = 11
    min_hit_rate: float = 1.0
    min_total_net_pnl_bps: float = 180.0
    min_mean_net_pnl_bps: float = 16.0
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


def default_v22_rescue_lane() -> BTCRescueLaneSpec:
    return BTCRescueLaneSpec(
        enabled=True,
        side="long",
        signal_column="kline_15s_signal",
        signal_operator="<=",
        signal_threshold=-0.70,
        volatility_column="kline_1m_rv_3_bps",
        volatility_operator=">=",
        volatility_threshold=20.0,
    )


def default_v22_take_profit_bps() -> float:
    return 52.0


def run_btc_rescue_profit_lock(
    *,
    v17_run_dir: str | Path,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    side_guard: BTCSideGuardSpec | None = None,
    rescue_lane: BTCRescueLaneSpec | None = None,
    take_profit_bps: float | None = None,
    stop_loss_bps: float = 0.0,
    horizon_sec: float = 90.0,
    latency_sec: float = 0.5,
    exit_take_profit_candidates: list[float] | None = None,
    stress_fee_side_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    leverage_values: list[float] | None = None,
    shift_null_runs: int = 1000,
    random_scenarios: int = 10000,
    seed: int = 22022,
    gate: BTCRescueProfitGate | None = None,
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
    take_profit_bps = default_v22_take_profit_bps() if take_profit_bps is None else float(take_profit_bps)
    exit_take_profit_candidates = _dedupe_float(exit_take_profit_candidates or [0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 52, 55, 60])
    stress_fee_side_bps_values = _dedupe_float(stress_fee_side_bps_values or [4.0, 5.0, 6.0, 7.5, 10.0])
    stress_latency_sec_values = _dedupe_float(stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    leverage_values = _dedupe_float(leverage_values or [1.0, 2.0, 3.0, 5.0, 10.0, 20.0])
    gate = gate or BTCRescueProfitGate()

    source_path = run / "execution_lock_oof_backtest.csv"
    if not source_path.exists():
        raise FileNotFoundError(f"missing frozen V17 ledger: {source_path}")
    frame = pd.read_csv(source_path)
    if "timestamp" not in frame.columns:
        raise ValueError("execution_lock_oof_backtest.csv must contain timestamp")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    raw_signal = pd.to_numeric(frame.get("signal", 0), errors="coerce").fillna(0).astype(int).clip(-1, 1).to_numpy()

    cost_bps = float(fee_spec.taker_taker_roundtrip_bps)
    selected_signal, component_masks = _selected_signal(frame, raw_signal, side_guard, rescue_lane)
    selected_exit = ExitLockSpec(take_profit_bps=float(take_profit_bps), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)
    selected_frame = frame.copy()
    selected_frame["signal"] = selected_signal
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        selected_frame,
        cost_bps=cost_bps,
        horizon_sec=float(horizon_sec),
        latency_sec=float(latency_sec),
        spec=selected_exit,
    )
    selected_bt["real_taker_fee_bps_per_side"] = fee_spec.taker_fee_bps_per_side
    selected_bt["real_maker_fee_bps_per_side"] = fee_spec.maker_fee_bps_per_side
    selected_bt["real_roundtrip_fee_bps"] = selected_bt["traded"].astype(float) * cost_bps
    selected_bt["v22_core_lane"] = component_masks["core"].astype(int)
    selected_bt["v22_rescue_lane"] = component_masks["rescue"].astype(int)
    selected_bt.to_csv(out / "btc_rescue_profit_oof_backtest.csv", index=False)
    trades = selected_bt.loc[selected_bt["traded"].astype(int) == 1].copy().reset_index(drop=True)
    trades.to_csv(out / "btc_rescue_profit_trade_ledger.csv", index=False)

    comparison = _comparison_rows(frame, raw_signal, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, side_guard=side_guard, rescue_lane=rescue_lane)
    comparison.to_csv(out / "btc_v20_v21_v22_comparison.csv", index=False)

    exit_scan = _exit_target_scan(
        frame=frame,
        selected_signal=selected_signal,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        take_profit_candidates=exit_take_profit_candidates,
        stop_loss_bps=stop_loss_bps,
    )
    exit_scan.to_csv(out / "btc_exit_target_family_scan.csv", index=False)

    folds = _fold_metrics(trades)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    bootstrap = block_bootstrap_pnl(pnl, iterations=5000, block_size=5, seed=seed)
    stability = _stability(selected_bt)
    fold_arr = pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy()
    path = _path_diagnostics(pnl, fold_arr)

    stress = _stress_selected(
        frame,
        selected_signal,
        fee_side_values=stress_fee_side_bps_values,
        latency_values=stress_latency_sec_values,
        horizon_sec=horizon_sec,
        exit_spec=selected_exit,
    )
    stress.to_csv(out / "btc_fee_latency_stress.csv", index=False)
    stress_gate = RealFeeLockGate(max_stress_fee_side_bps=gate.max_stress_fee_side_bps, max_stress_latency_sec=gate.max_stress_latency_sec)
    stress_summary = _stress_summary(stress, stress_gate)

    miss = _missed_trade_stress(trades, miss_probabilities=[0.1, 0.2, 0.3, 0.4, gate.missed_trade_gate_probability, 0.6, 0.7], scenarios=random_scenarios, seed=seed)
    miss.to_csv(out / "btc_missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_cost_bps_values=[0, 1, 2, 3, 5, 7.5, 10, 12, 14, gate.extra_cost_gate_bps])
    extra.to_csv(out / "btc_extra_cost_reserve.csv", index=False)

    leverage = _leverage_scenarios(
        trades=trades,
        leverage_values=leverage_values,
        fee_roundtrip_bps=cost_bps,
        maintenance_margin_bps=float(gate.maintenance_margin_bps),
        shock_buffer_bps=float(gate.shock_buffer_bps),
    )
    leverage.to_csv(out / "btc_leverage_scenarios.csv", index=False)

    family_df, family_null = _entry_exit_family_shift_null(
        frame=frame,
        raw_signal=raw_signal,
        selected_side_guard=side_guard,
        selected_rescue_lane=rescue_lane,
        selected_take_profit_bps=float(take_profit_bps),
        cost_bps=cost_bps,
        horizon_sec=float(horizon_sec),
        latency_sec=float(latency_sec),
        stop_loss_bps=float(stop_loss_bps),
        take_profit_candidates=exit_take_profit_candidates,
        selected_total=float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        selected_mean=float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        shift_null_runs=int(shift_null_runs),
        min_trades=int(gate.min_trades),
    )
    family_df.to_csv(out / "btc_entry_exit_family_shift_null.csv", index=False)

    data_plan = write_btc_contract_data_plan(out_dir=out / "btc_contract_data_plan") if write_data_plan else {}

    aggregate = _aggregate(
        selected_metrics=selected_metrics,
        trades=trades,
        folds=folds,
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
        "version": "v22_btc_rescue_profit_lock",
        "v17_run_dir": str(run),
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "horizon_sec": float(horizon_sec),
        "latency_sec": float(latency_sec),
        "take_profit_bps": float(take_profit_bps),
        "stop_loss_bps": float(stop_loss_bps),
        "v19_filters": [f.to_dict() for f in default_v19_fee_filters()],
        "btc_side_guard": side_guard.to_dict(),
        "btc_rescue_lane": rescue_lane.to_dict(),
        "entry_components": {k: int(v.sum()) for k, v in component_masks.items()},
        "exit_take_profit_candidates": [float(x) for x in exit_take_profit_candidates],
        "stress_fee_side_bps_values": [float(x) for x in stress_fee_side_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "leverage_values": [float(x) for x in leverage_values],
        "shift_null_runs": int(shift_null_runs),
        "data_plan": data_plan,
        "aggregate": aggregate,
        "gate_config": gate.to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, comparison, exit_scan, folds, stress, miss, extra, leverage)
    (out / "DONE.marker").write_text("ok\n", encoding="utf-8")
    return _jsonable(result)


def _selected_signal(frame: pd.DataFrame, raw_signal: np.ndarray, side_guard: BTCSideGuardSpec, rescue_lane: BTCRescueLaneSpec) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    dirs = np.asarray(raw_signal, dtype=int)
    v19_mask = _mask_for_filters(frame, dirs, default_v19_fee_filters()) & (dirs != 0)
    core_mask = v19_mask & _mask_for_btc_side_guard(frame, dirs, side_guard)
    rescue_mask = _mask_for_rescue_lane(frame, dirs, rescue_lane)
    selected = (core_mask | rescue_mask) & (dirs != 0)
    return np.where(selected, dirs, 0), {"core": core_mask & selected, "rescue": rescue_mask & selected, "selected": selected}


def _mask_for_rescue_lane(frame: pd.DataFrame, directions: np.ndarray, spec: BTCRescueLaneSpec | None) -> np.ndarray:
    n = len(frame)
    if spec is None or not bool(spec.enabled):
        return np.zeros(n, dtype=bool)
    dirs = np.asarray(directions, dtype=int)
    if spec.signal_column not in frame.columns or spec.volatility_column not in frame.columns:
        return np.zeros(n, dtype=bool)
    sig_vals = pd.to_numeric(frame[spec.signal_column], errors="coerce").to_numpy(dtype=float)
    vol_vals = pd.to_numeric(frame[spec.volatility_column], errors="coerce").to_numpy(dtype=float)
    side_ok = dirs > 0 if spec.side == "long" else dirs < 0 if spec.side == "short" else dirs != 0
    signal_ok = _compare(sig_vals, spec.signal_operator, float(spec.signal_threshold)) & np.isfinite(sig_vals)
    vol_ok = _compare(vol_vals, spec.volatility_operator, float(spec.volatility_threshold)) & np.isfinite(vol_vals)
    return side_ok & signal_ok & vol_ok


def _comparison_rows(frame: pd.DataFrame, raw_signal: np.ndarray, *, cost_bps: float, horizon_sec: float, latency_sec: float, side_guard: BTCSideGuardSpec, rescue_lane: BTCRescueLaneSpec) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    dirs = np.asarray(raw_signal, dtype=int)
    v19_mask = _mask_for_filters(frame, dirs, default_v19_fee_filters()) & (dirs != 0)
    v20_mask = v19_mask & _mask_for_btc_side_guard(frame, dirs, side_guard)
    rescue_mask = _mask_for_rescue_lane(frame, dirs, rescue_lane)
    specs = [
        ("v20_btc_side_guard_tp40", np.where(v20_mask, dirs, 0), 40.0),
        ("v21_btc_profit_target_tp45", np.where(v20_mask, dirs, 0), 45.0),
        ("v22_btc_rescue_profit_tp52", np.where(v20_mask | rescue_mask, dirs, 0), 52.0),
    ]
    for label, signal, tp in specs:
        tmp = frame.copy()
        tmp["signal"] = signal
        bt, metrics = backtest_fixed_signals_taker_bidask_exit_lock(
            tmp,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
            spec=ExitLockSpec(take_profit_bps=tp, stop_loss_bps=0.0, reserve_horizon=True),
        )
        trades = bt.loc[bt["traded"].astype(int) == 1]
        rows.append({"label": label, "take_profit_bps": tp, **_jsonable(metrics), "min_trade_net_pnl_bps": float(pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").min()) if not trades.empty else 0.0})
    return pd.DataFrame(rows)


def _exit_target_scan(*, frame: pd.DataFrame, selected_signal: np.ndarray, cost_bps: float, horizon_sec: float, latency_sec: float, take_profit_candidates: list[float], stop_loss_bps: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    tmp = frame.copy()
    tmp["signal"] = selected_signal
    for tp in take_profit_candidates:
        spec = ExitLockSpec(take_profit_bps=float(tp), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)
        bt, metrics = backtest_fixed_signals_taker_bidask_exit_lock(tmp, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=spec)
        trades = bt.loc[bt["traded"].astype(int) == 1]
        folds = _fold_metrics(trades)
        pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
        stress = _stress_selected(frame, selected_signal, fee_side_values=[10.0], latency_values=[5.0], horizon_sec=horizon_sec, exit_spec=spec)
        rows.append({
            "take_profit_bps": float(tp),
            **_jsonable(metrics),
            "fold_min_total_net_pnl_bps": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
            "fold_min_mean_net_pnl_bps": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
            "min_trade_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
            "stress_10bps_side_5s_total_bps": float(stress["total_net_pnl_bps"].iloc[0]) if not stress.empty else 0.0,
        })
    return pd.DataFrame(rows).sort_values(["total_net_pnl_bps", "stress_10bps_side_5s_total_bps"], ascending=False).reset_index(drop=True)


def _rescue_lane_candidates() -> list[BTCRescueLaneSpec | None]:
    out: list[BTCRescueLaneSpec | None] = [None]
    for signal_th in [-0.75, -0.70, -0.65, -0.60]:
        for rv_th in [18.0, 20.0, 22.0, 24.0]:
            out.append(BTCRescueLaneSpec(signal_threshold=float(signal_th), volatility_threshold=float(rv_th)))
    return out


def _same_side_guard(a: BTCSideGuardSpec | None, b: BTCSideGuardSpec | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a.to_dict() == b.to_dict()


def _same_rescue_lane(a: BTCRescueLaneSpec | None, b: BTCRescueLaneSpec | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a.to_dict() == b.to_dict()


def _entry_exit_family_shift_null(
    *,
    frame: pd.DataFrame,
    raw_signal: np.ndarray,
    selected_side_guard: BTCSideGuardSpec,
    selected_rescue_lane: BTCRescueLaneSpec,
    selected_take_profit_bps: float,
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    stop_loss_bps: float,
    take_profit_candidates: list[float],
    selected_total: float,
    selected_mean: float,
    shift_null_runs: int,
    min_trades: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    arrays = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    tp_candidates = _dedupe_float(take_profit_candidates)
    pnl_by_tp: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for tp in tp_candidates:
        spec = ExitLockSpec(take_profit_bps=float(tp), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)
        pnl_by_tp[float(tp)] = _precompute_exit_pnl_by_row(arrays, cost_bps=cost_bps, spec=spec)

    idx = np.flatnonzero(np.asarray(raw_signal, dtype=int) != 0).astype(int)
    sig = np.asarray(raw_signal, dtype=int)[idx]
    min_shift = max(1, int(round(float(horizon_sec) / 0.5)))
    shifts = _shift_values(n=len(frame), shifts=int(shift_null_runs), min_shift=min_shift)
    side_candidates = _side_guard_candidates()
    rescue_candidates = _rescue_lane_candidates()

    rows: list[dict[str, object]] = []
    exceed_total = 0
    exceed_mean = 0
    selected_only_exceed_total = 0
    selected_only_exceed_mean = 0
    null_max_total = -np.inf
    null_max_mean = -np.inf
    selected_null_max_total = -np.inf
    selected_null_max_mean = -np.inf

    for shift in shifts:
        rows_idx, dirs = _accepted_shift_positions(idx, sig, int(shift), arrays)
        best_total = -np.inf
        best_mean = -np.inf
        best_trades = 0
        selected_total_shift = -np.inf
        selected_mean_shift = -np.inf
        selected_trades_shift = 0
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
            for tp in tp_candidates:
                p_long, p_short = pnl_by_tp[float(tp)]
                pnl_all = np.where(dirs > 0, p_long[rows_idx], p_short[rows_idx]).astype(float)
                for side, side_mask in zip(side_candidates, side_masks):
                    for rescue, rescue_mask in zip(rescue_candidates, rescue_masks):
                        entry_mask = side_mask | rescue_mask
                        if not entry_mask.any():
                            continue
                        pnl = pnl_all[entry_mask]
                        pnl = pnl[np.isfinite(pnl)]
                        if len(pnl) < int(min_trades):
                            continue
                        total = float(pnl.sum())
                        mean = float(pnl.mean()) if len(pnl) else 0.0
                        if total > best_total:
                            best_total = total
                            best_trades = int(len(pnl))
                        if mean > best_mean:
                            best_mean = mean
                        if _same_side_guard(side, selected_side_guard) and _same_rescue_lane(rescue, selected_rescue_lane) and abs(float(tp) - float(selected_take_profit_bps)) < 1e-9:
                            selected_total_shift = total
                            selected_mean_shift = mean
                            selected_trades_shift = int(len(pnl))
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
            "candidate_count": int(len(side_candidates) * len(rescue_candidates) * len(tp_candidates)),
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
        "candidate_count": int(len(side_candidates) * len(rescue_candidates) * len(tp_candidates)),
        "side_candidate_count": int(len(side_candidates)),
        "rescue_candidate_count": int(len(rescue_candidates)),
        "exit_candidate_count": int(len(tp_candidates)),
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


def _row_for(df: pd.DataFrame, column: str, value: float) -> dict[str, object]:
    if df.empty or column not in df.columns:
        return {}
    vals = pd.to_numeric(df[column], errors="coerce")
    rows = df.loc[np.isclose(vals, float(value))]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _aggregate(*, selected_metrics, trades, folds, bootstrap, stability, path, stress_summary, miss, extra, leverage, family_null, gate: BTCRescueProfitGate) -> dict[str, object]:
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


def _write_report(path: Path, result: dict[str, object], comparison: pd.DataFrame, exit_scan: pd.DataFrame, folds: pd.DataFrame, stress: pd.DataFrame, miss: pd.DataFrame, extra: pd.DataFrame, leverage: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V22 BTC Rescue Profit Lock",
        "",
        "V22 starts from the V20/V21 BTC rule, keeps the V19 high-fee guard and V20 BTC side guard, and adds one slot-preserving BTC long rescue lane plus a 52 bps take-profit target.",
        "",
        "## Frozen inputs",
        "",
        "```json",
        json.dumps({
            "fee_spec": result["fee_spec"],
            "horizon_sec": result["horizon_sec"],
            "latency_sec": result["latency_sec"],
            "take_profit_bps": result["take_profit_bps"],
            "stop_loss_bps": result["stop_loss_bps"],
            "v19_filters": result["v19_filters"],
            "btc_side_guard": result["btc_side_guard"],
            "btc_rescue_lane": result["btc_rescue_lane"],
        }, indent=2),
        "```",
        "",
        "## Aggregate gate",
        "",
        "```json",
        json.dumps(_jsonable(agg), indent=2),
        "```",
        "",
        "## V20/V21/V22 comparison",
        "",
        comparison.to_csv(index=False).strip(),
        "",
        "## Exit target family scan",
        "",
        exit_scan.to_csv(index=False).strip(),
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
        "This remains a bundled-sample research result. V22 must be frozen and validated on independent multi-day BTC contract data before live use. Leverage rows are account-return approximations and not exchange liquidation guarantees.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
