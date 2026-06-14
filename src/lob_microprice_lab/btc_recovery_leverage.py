from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_contract_data import write_btc_contract_data_plan
from .btc_leverage_lock import (
    BTCLeverageGate,
    BTCSideGuardSpec,
    _leverage_scenarios,
    _mask_for_btc_side_guard,
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
class BTCRecoverySpec:
    """Small V21 recovery sleeve on top of the frozen V20 BTC contract rule.

    The V20 rule removed one high-volatility long that was actually a take-profit win.
    V21 does not loosen the whole high-fee filter.  It only allows a long recovery slot
    when the model edge is large and the short 15s K-line signal is strongly against the
    long direction, which behaved like a BTC mean-reversion/rebound pattern on the
    bundled sample.
    """

    kline_15s_signal_max: float = -0.70
    prob_edge_min: float = 0.50
    kline_1m_range_z_min: float = 0.50
    long_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BTCRecoveryGate:
    min_trades: int = 11
    min_hit_rate: float = 1.0
    min_total_net_pnl_bps: float = 160.0
    min_mean_net_pnl_bps: float = 12.0
    min_fold_total_net_pnl_bps: float = 0.0
    min_fold_mean_net_pnl_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_recovery_family_addone_p: float = 0.01
    max_stress_fee_side_bps: float = 10.0
    max_stress_latency_sec: float = 5.0
    missed_trade_gate_probability: float = 0.50
    missed_trade_min_p05_total_bps: float = 0.0
    extra_cost_gate_bps: float = 12.0
    extra_cost_min_total_bps: float = 0.0
    promoted_leverage_cap: float = 5.0
    shock_buffer_bps: float = 1000.0
    maintenance_margin_bps: float = 50.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_btc_recovery_spec() -> BTCRecoverySpec:
    return BTCRecoverySpec(kline_15s_signal_max=-0.70, prob_edge_min=0.50, kline_1m_range_z_min=0.50, long_only=True)


def run_btc_recovery_leverage_lock(
    *,
    v17_run_dir: str | Path,
    v20_run_dir: str | Path | None = None,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    side_guard: BTCSideGuardSpec | None = None,
    recovery_spec: BTCRecoverySpec | None = None,
    horizon_sec: float = 90.0,
    latency_sec: float = 0.5,
    take_profit_bps: float = 40.0,
    stop_loss_bps: float = 0.0,
    stress_fee_side_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    leverage_values: list[float] | None = None,
    shift_null_runs: int = 1000,
    random_scenarios: int = 10000,
    seed: int = 21021,
    gate: BTCRecoveryGate | None = None,
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
    recovery_spec = recovery_spec or default_btc_recovery_spec()
    gate = gate or BTCRecoveryGate()
    stress_fee_side_bps_values = _dedupe_float(stress_fee_side_bps_values or [4.0, 5.0, 6.0, 7.5, 10.0])
    stress_latency_sec_values = _dedupe_float(stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    leverage_values = _dedupe_float(leverage_values or [1.0, 2.0, 3.0, 5.0, 10.0, 20.0])

    source_path = run / "execution_lock_oof_backtest.csv"
    if not source_path.exists():
        raise FileNotFoundError(f"missing frozen V17 ledger: {source_path}")
    frame = pd.read_csv(source_path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    raw_signal = pd.to_numeric(frame.get("signal", 0), errors="coerce").fillna(0).astype(int).clip(-1, 1).to_numpy()

    cost_bps = float(fee_spec.taker_taker_roundtrip_bps)
    exit_spec = ExitLockSpec(take_profit_bps=float(take_profit_bps), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)

    v20_mask = _v20_mask(frame, raw_signal, side_guard)
    recovery_mask = _mask_for_btc_recovery(frame, raw_signal, recovery_spec) & (~v20_mask)
    selected_mask = v20_mask | recovery_mask
    selected_signal = np.where(selected_mask, raw_signal, 0)

    selected_frame = frame.copy()
    selected_frame["signal"] = selected_signal
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        selected_frame,
        cost_bps=cost_bps,
        horizon_sec=float(horizon_sec),
        latency_sec=float(latency_sec),
        spec=exit_spec,
    )
    selected_bt["v21_selected"] = selected_signal != 0
    selected_bt["v21_recovery_slot"] = recovery_mask
    selected_bt["real_taker_fee_bps_per_side"] = fee_spec.taker_fee_bps_per_side
    selected_bt["real_maker_fee_bps_per_side"] = fee_spec.maker_fee_bps_per_side
    selected_bt["real_roundtrip_fee_bps"] = selected_bt["traded"].astype(float) * cost_bps
    selected_bt.to_csv(out / "btc_recovery_oof_backtest.csv", index=False)
    trades = selected_bt.loc[selected_bt["traded"].astype(int) == 1].copy().reset_index(drop=True)
    trades.to_csv(out / "btc_recovery_trade_ledger.csv", index=False)

    # V20 baseline reconstructed from the frozen V17 source.
    v20_signal = np.where(v20_mask, raw_signal, 0)
    v20_frame = frame.copy()
    v20_frame["signal"] = v20_signal
    v20_bt, v20_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        v20_frame,
        cost_bps=cost_bps,
        horizon_sec=float(horizon_sec),
        latency_sec=float(latency_sec),
        spec=exit_spec,
    )
    comparison = pd.DataFrame([
        {"label": "v20_btc_guard_reproduced", **_jsonable(v20_metrics)},
        {"label": "v21_btc_recovery_leverage", **_jsonable(selected_metrics)},
    ])
    comparison.to_csv(out / "btc_v20_v21_comparison.csv", index=False)

    candidates = _evaluate_recovery_candidates(
        frame=frame,
        raw_signal=raw_signal,
        side_guard=side_guard,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        exit_spec=exit_spec,
        selected=recovery_spec,
    )
    candidates.to_csv(out / "btc_recovery_family_candidates.csv", index=False)

    folds = _fold_metrics(trades)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    fold_values = pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy()
    bootstrap = block_bootstrap_pnl(pnl, iterations=5000, block_size=5, seed=seed)
    stability = _stability(selected_bt)
    path = _path_diagnostics(pnl, fold_values)

    stress = _stress_selected(frame, selected_signal, fee_side_values=stress_fee_side_bps_values, latency_values=stress_latency_sec_values, horizon_sec=horizon_sec, exit_spec=exit_spec)
    stress.to_csv(out / "btc_recovery_fee_latency_stress.csv", index=False)
    stress_summary = _stress_summary(stress, _recovery_gate_for_stress(gate))

    miss = _missed_trade_stress(trades, miss_probabilities=[0.1, 0.2, 0.3, 0.4, gate.missed_trade_gate_probability, 0.6, 0.7], scenarios=random_scenarios, seed=seed)
    miss.to_csv(out / "btc_recovery_missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_cost_bps_values=[0, 1, 2, 3, 5, 7.5, 10, gate.extra_cost_gate_bps, 15])
    extra.to_csv(out / "btc_recovery_extra_cost_reserve.csv", index=False)

    leverage = _leverage_scenarios(
        trades=trades,
        leverage_values=leverage_values,
        fee_roundtrip_bps=cost_bps,
        maintenance_margin_bps=float(gate.maintenance_margin_bps),
        shock_buffer_bps=float(gate.shock_buffer_bps),
    )
    leverage.to_csv(out / "btc_recovery_leverage_scenarios.csv", index=False)

    null_df, recovery_null = _recovery_family_shift_null(
        frame=frame,
        raw_signal=raw_signal,
        side_guard=side_guard,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        exit_spec=exit_spec,
        selected_total=float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        selected_mean=float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        shift_null_runs=shift_null_runs,
        min_trades=gate.min_trades,
    )
    null_df.to_csv(out / "btc_recovery_family_shift_null.csv", index=False)

    data_plan = write_btc_contract_data_plan(out_dir=out / "btc_contract_data_plan", start_date="2024-01-01", end_date="2026-06-10", symbol="BTCUSDT") if write_data_plan else {}

    aggregate = _aggregate(
        selected_metrics=selected_metrics,
        v20_metrics=v20_metrics,
        recovery_added=int(recovery_mask.sum()),
        trades=trades,
        folds=folds,
        bootstrap=bootstrap,
        stability=stability,
        path=path,
        stress_summary=stress_summary,
        miss=miss,
        extra=extra,
        leverage=leverage,
        recovery_null=recovery_null,
        gate=gate,
    )

    result: dict[str, object] = {
        "v17_run_dir": str(run),
        "v20_run_dir": str(v20_run_dir) if v20_run_dir is not None else "",
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "horizon_sec": float(horizon_sec),
        "latency_sec": float(latency_sec),
        "take_profit_bps": float(take_profit_bps),
        "stop_loss_bps": float(stop_loss_bps),
        "v19_filters": [f.to_dict() for f in default_v19_fee_filters()],
        "btc_side_guard": side_guard.to_dict(),
        "btc_recovery_spec": recovery_spec.to_dict(),
        "recovery_family_candidate_count": int(len(_recovery_candidates())),
        "leverage_values": [float(x) for x in leverage_values],
        "shift_null_runs": int(shift_null_runs),
        "stress_fee_side_bps_values": [float(x) for x in stress_fee_side_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "data_plan": data_plan,
        "aggregate": aggregate,
        "gate_config": gate.to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, comparison, folds, stress, miss, extra, leverage, candidates)
    (out / "DONE.marker").write_text("ok\n", encoding="utf-8")
    return _jsonable(result)


def _dedupe_float(values: list[float]) -> list[float]:
    out: list[float] = []
    seen: set[float] = set()
    for x in values:
        v = round(float(x), 12)
        if v not in seen:
            seen.add(v)
            out.append(float(x))
    return out


def _v20_mask(frame: pd.DataFrame, directions: np.ndarray, side_guard: BTCSideGuardSpec) -> np.ndarray:
    dirs = np.asarray(directions, dtype=int)
    return (_mask_for_filters(frame, dirs, default_v19_fee_filters()) & _mask_for_btc_side_guard(frame, dirs, side_guard) & (dirs != 0))


def _mask_for_btc_recovery(frame: pd.DataFrame, directions: np.ndarray, spec: BTCRecoverySpec) -> np.ndarray:
    dirs = np.asarray(directions, dtype=int)
    k = pd.to_numeric(frame.get("kline_15s_signal", np.nan), errors="coerce").to_numpy(dtype=float)
    p = pd.to_numeric(frame.get("prob_edge", np.nan), errors="coerce").to_numpy(dtype=float)
    r = pd.to_numeric(frame.get("kline_1m_range_z_6", np.nan), errors="coerce").to_numpy(dtype=float)
    direction_ok = dirs > 0 if bool(spec.long_only) else dirs != 0
    return (
        direction_ok
        & np.isfinite(k)
        & np.isfinite(p)
        & np.isfinite(r)
        & (k <= float(spec.kline_15s_signal_max))
        & (p >= float(spec.prob_edge_min))
        & (r >= float(spec.kline_1m_range_z_min))
    )


def _recovery_candidates() -> list[BTCRecoverySpec | None]:
    # None means V20 baseline with no recovery sleeve.  The family is intentionally
    # small and pre-declared; V21 then corrects against this whole family in the shift null.
    cands: list[BTCRecoverySpec | None] = [None]
    for k in [-0.4, -0.5, -0.6, -0.7]:
        for p in [0.3, 0.4, 0.5, 0.6]:
            for r in [0.0, 0.25, 0.5, 0.75]:
                cands.append(BTCRecoverySpec(kline_15s_signal_max=float(k), prob_edge_min=float(p), kline_1m_range_z_min=float(r), long_only=True))
    return cands


def _evaluate_recovery_candidates(*, frame: pd.DataFrame, raw_signal: np.ndarray, side_guard: BTCSideGuardSpec, cost_bps: float, horizon_sec: float, latency_sec: float, exit_spec: ExitLockSpec, selected: BTCRecoverySpec) -> pd.DataFrame:
    base = _v20_mask(frame, raw_signal, side_guard)
    rows: list[dict[str, object]] = []
    for cand in _recovery_candidates():
        m = base.copy()
        if cand is not None:
            m = m | (_mask_for_btc_recovery(frame, raw_signal, cand) & (~base))
        sig = np.where(m, raw_signal, 0)
        tmp = frame.copy()
        tmp["signal"] = sig
        bt, metrics = backtest_fixed_signals_taker_bidask_exit_lock(tmp, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=exit_spec)
        trades = bt.loc[bt["traded"].astype(int) == 1].copy()
        fdf = _fold_metrics(trades)
        rows.append({
            "is_v20_baseline": cand is None,
            "is_selected_v21": bool(cand == selected),
            "candidate_json": "null_v20_baseline" if cand is None else json.dumps(cand.to_dict(), sort_keys=True),
            "recovery_rows_pre_backtest": int(((_mask_for_btc_recovery(frame, raw_signal, cand) & (~base)).sum()) if cand is not None else 0),
            **_jsonable(metrics),
            "fold_min_total_net_pnl_bps": float(fdf["total_net_pnl_bps"].min()) if not fdf.empty else 0.0,
            "fold_min_mean_net_pnl_bps": float(fdf["mean_net_pnl_bps"].min()) if not fdf.empty else 0.0,
        })
    return pd.DataFrame(rows).sort_values(["total_net_pnl_bps", "hit_rate", "mean_net_pnl_bps"], ascending=False).reset_index(drop=True)


def _recovery_family_shift_null(
    *,
    frame: pd.DataFrame,
    raw_signal: np.ndarray,
    side_guard: BTCSideGuardSpec,
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    exit_spec: ExitLockSpec,
    selected_total: float,
    selected_mean: float,
    shift_null_runs: int,
    min_trades: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    arrays = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    p_long, p_short = _precompute_exit_pnl_by_row(arrays, cost_bps=cost_bps, spec=exit_spec)
    idx = np.flatnonzero(np.asarray(raw_signal, dtype=int) != 0).astype(int)
    sig = np.asarray(raw_signal, dtype=int)[idx]
    min_shift = max(1, int(round(float(horizon_sec) / 0.5)))
    shifts = _shift_values(n=len(frame), shifts=int(shift_null_runs), min_shift=min_shift)
    candidates = _recovery_candidates()
    rows: list[dict[str, object]] = []
    exceed_total = 0
    exceed_mean = 0
    null_max_total = -np.inf
    null_max_mean = -np.inf
    for shift in shifts:
        rows_idx, dirs = _accepted_shift_positions(idx, sig, int(shift), arrays)
        best_total = -np.inf
        best_mean = -np.inf
        best_trades = 0
        if len(rows_idx):
            sub = frame.iloc[rows_idx].reset_index(drop=True)
            dirs = np.asarray(dirs, dtype=int)
            base = _v20_mask(sub, dirs, side_guard)
            pnl_all = np.where(dirs > 0, p_long[rows_idx], p_short[rows_idx]).astype(float)
            for cand in candidates:
                m = base.copy()
                if cand is not None:
                    m = m | (_mask_for_btc_recovery(sub, dirs, cand) & (~base))
                pnl = pnl_all[m]
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
        best_total = float(best_total if np.isfinite(best_total) else 0.0)
        best_mean = float(best_mean if np.isfinite(best_mean) else 0.0)
        null_max_total = max(null_max_total, best_total)
        null_max_mean = max(null_max_mean, best_mean)
        if best_total >= float(selected_total):
            exceed_total += 1
        if best_mean >= float(selected_mean):
            exceed_mean += 1
        rows.append({
            "shift_rows": int(shift),
            "candidate_count": int(len(candidates)),
            "best_constrained_trades": int(best_trades),
            "recovery_family_max_total_bps_constrained": best_total,
            "recovery_family_max_mean_bps_constrained": best_mean,
        })
    df = pd.DataFrame(rows)
    denom = len(df) + 1
    summary = {
        "selected_total_net_pnl_bps": float(selected_total),
        "selected_mean_net_pnl_bps": float(selected_mean),
        "shift_null_runs": int(len(df)),
        "candidate_count": int(len(candidates)),
        "null_total_max_bps": float(null_max_total if np.isfinite(null_max_total) else 0.0),
        "null_mean_max_bps": float(null_max_mean if np.isfinite(null_max_mean) else 0.0),
        "exceed_total_count": int(exceed_total),
        "exceed_mean_count": int(exceed_mean),
        "addone_p_total_ge_selected": float((exceed_total + 1) / denom),
        "addone_p_mean_ge_selected": float((exceed_mean + 1) / denom),
    }
    return df, summary


def _row_for(df: pd.DataFrame, column: str, value: float) -> dict[str, object]:
    if df.empty or column not in df.columns:
        return {}
    rows = df.loc[np.isclose(pd.to_numeric(df[column], errors="coerce"), float(value))]
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


def _recovery_gate_for_stress(gate: BTCRecoveryGate) -> RealFeeLockGate:
    return RealFeeLockGate(max_stress_fee_side_bps=gate.max_stress_fee_side_bps, max_stress_latency_sec=gate.max_stress_latency_sec)


def _aggregate(*, selected_metrics, v20_metrics, recovery_added: int, trades: pd.DataFrame, folds: pd.DataFrame, bootstrap: dict[str, object], stability: dict[str, object], path: dict[str, object], stress_summary: dict[str, object], miss: pd.DataFrame, extra: pd.DataFrame, leverage: pd.DataFrame, recovery_null: dict[str, object], gate: BTCRecoveryGate) -> dict[str, object]:
    miss_row = _row_for(miss, "miss_probability", gate.missed_trade_gate_probability)
    extra_row = _row_for(extra, "extra_cost_bps_per_trade", gate.extra_cost_gate_bps)
    lev_rows = leverage.loc[pd.to_numeric(leverage.get("leverage", 0), errors="coerce") <= float(gate.promoted_leverage_cap)] if not leverage.empty else pd.DataFrame()
    agg = {
        "baseline_v20_trades": int(v20_metrics.get("trades", 0)),
        "baseline_v20_hit_rate": float(v20_metrics.get("hit_rate", 0.0)),
        "baseline_v20_total_net_pnl_bps": float(v20_metrics.get("total_net_pnl_bps", 0.0)),
        "baseline_v20_mean_net_pnl_bps": float(v20_metrics.get("mean_net_pnl_bps", 0.0)),
        "recovery_added_slots_pre_backtest": int(recovery_added),
        "trades": int(selected_metrics.get("trades", 0)),
        "hit_rate": float(selected_metrics.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        "median_net_pnl_bps": float(selected_metrics.get("median_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        "incremental_total_vs_v20_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)) - float(v20_metrics.get("total_net_pnl_bps", 0.0)),
        "incremental_mean_vs_v20_bps": float(selected_metrics.get("mean_net_pnl_bps", 0.0)) - float(v20_metrics.get("mean_net_pnl_bps", 0.0)),
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
        "equal_trade_block_5_min_total_bps": float(stability.get("equal_trade_block_5_min_total_bps", 0.0)),
        "top5_winner_removed_total_bps": float(path.get("top5_winner_removed_total_bps", 0.0)),
        "leave_one_trade_out_min_total_bps": float(path.get("leave_one_trade_out_min_total_bps", 0.0)),
        "leave_one_fold_out_min_total_bps": float(path.get("leave_one_fold_out_min_total_bps", 0.0)),
        "stress_gate_min_mean_net_pnl_bps": float(stress_summary.get("gate_min_mean_net_pnl_bps", 0.0)),
        "stress_gate_min_total_net_pnl_bps": float(stress_summary.get("gate_min_total_net_pnl_bps", 0.0)),
        "stress_gate_all_positive": bool(stress_summary.get("gate_all_positive", False)),
        "stress_all_cells_min_total_net_pnl_bps": float(stress_summary.get("all_cells_min_total_net_pnl_bps", 0.0)),
        "stress_all_cells_min_mean_net_pnl_bps": float(stress_summary.get("all_cells_min_mean_net_pnl_bps", 0.0)),
        "stress_all_cells_positive": bool(stress_summary.get("all_cells_positive", False)),
        "missed_trade_gate_p05_total_bps": float(miss_row.get("p05_total_bps", 0.0)),
        "missed_trade_gate_positive_rate": float(miss_row.get("positive_scenario_rate", 0.0)),
        "extra_cost_gate_total_bps": float(extra_row.get("total_net_pnl_bps", 0.0)),
        "recovery_family_addone_p_total": float(recovery_null.get("addone_p_total_ge_selected", 1.0)),
        "recovery_family_addone_p_mean": float(recovery_null.get("addone_p_mean_ge_selected", 1.0)),
        "recovery_family_null": recovery_null,
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
        "recovery_family_null": max(float(agg["recovery_family_addone_p_total"]), float(agg["recovery_family_addone_p_mean"])) <= float(gate.max_recovery_family_addone_p),
        "fee_latency_stress": bool(agg["stress_gate_all_positive"]) and float(agg["stress_gate_min_mean_net_pnl_bps"]) > 0.0 and float(agg["stress_gate_min_total_net_pnl_bps"]) > 0.0,
        "missed_trade_p05_positive": float(agg["missed_trade_gate_p05_total_bps"]) > float(gate.missed_trade_min_p05_total_bps),
        "extra_cost_positive": float(agg["extra_cost_gate_total_bps"]) > float(gate.extra_cost_min_total_bps),
        "promoted_leverage_buffer": bool(agg["leverage_promoted_rows_all_pass_shock_buffer"]),
    }
    agg["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return _jsonable(agg)


def _write_report(path: Path, result: dict[str, object], comparison: pd.DataFrame, folds: pd.DataFrame, stress: pd.DataFrame, miss: pd.DataFrame, extra: pd.DataFrame, leverage: pd.DataFrame, candidates: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V21 BTC Recovery Leverage Lock",
        "",
        "V21 continues from the frozen V20 BTC contract rule. It does not replace the V19/V20 fee and BTC side guards. It adds one small long-only recovery sleeve for high-edge BTC rebound slots, then audits that sleeve against a pre-declared recovery family and shifted-signal null.",
        "",
        "## Frozen inputs",
        "",
        "```json",
        json.dumps({
            "fee_spec": result["fee_spec"],
            "horizon_sec": result["horizon_sec"],
            "latency_sec": result["latency_sec"],
            "take_profit_bps": result["take_profit_bps"],
            "v19_filters": result["v19_filters"],
            "btc_side_guard": result["btc_side_guard"],
            "btc_recovery_spec": result["btc_recovery_spec"],
        }, indent=2),
        "```",
        "",
        "## Aggregate gate",
        "",
        "```json",
        json.dumps(_jsonable(agg), indent=2),
        "```",
        "",
        "## V20 vs V21 comparison",
        "",
        comparison.to_csv(index=False).strip(),
        "",
        "## Fold metrics",
        "",
        folds.to_csv(index=False).strip() if not folds.empty else "No folds.",
        "",
        "## Top recovery-family candidates",
        "",
        candidates.head(15).to_csv(index=False).strip() if not candidates.empty else "No candidates.",
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
        "This remains a bundled-sample research result. V21 should be frozen before independent BTC contract days are used. The promoted leverage cap is a research cap using a simplified buffer calculation, not an exchange liquidation guarantee.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
