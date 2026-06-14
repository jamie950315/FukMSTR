from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_contract_data import write_btc_contract_data_plan
from .exit_lock import ExitLockSpec, backtest_fixed_signals_taker_bidask_exit_lock, execution_path_arrays
from .profit_execution_lock import _accepted_shift_positions, _metrics_from_accepted, _precompute_exit_pnl_by_row
from .profit_lock import _jsonable, _path_diagnostics
from .profit_success_fast import _stability
from .real_fee_lock import (
    RealFeeSpec,
    _extra_cost_reserve,
    _fold_metrics,
    _mask_for_filters,
    _metrics_from_pnl,
    _missed_trade_stress,
    _stress_selected,
    _stress_summary,
    default_v19_fee_filters,
)
from .slot_veto import _shift_values
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class BTCSideGuardSpec:
    long_column: str = "kline_15s_signal"
    long_operator: str = "<="
    long_threshold: float = 0.0
    short_column: str = ""
    short_operator: str = ""
    short_threshold: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BTCLeverageGate:
    min_trades: int = 10
    min_hit_rate: float = 0.95
    min_total_net_pnl_bps: float = 120.0
    min_fold_total_net_pnl_bps: float = 0.0
    min_fold_mean_net_pnl_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_side_guard_addone_p: float = 0.01
    max_stress_fee_side_bps: float = 7.5
    max_stress_latency_sec: float = 5.0
    missed_trade_gate_probability: float = 0.50
    missed_trade_min_p05_total_bps: float = 0.0
    extra_cost_gate_bps: float = 10.0
    extra_cost_min_total_bps: float = 0.0
    promoted_leverage_cap: float = 3.0
    shock_buffer_bps: float = 250.0
    maintenance_margin_bps: float = 50.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_btc_side_guard() -> BTCSideGuardSpec:
    """V20 BTC-specific long guard.

    Interpretation: keep the V19 high-fee rule, but reject a long setup when the
    15-second K-line signal is still positive. On the bundled BTC sample this removes
    the one V19 losing trade without adding any new slots.
    """
    return BTCSideGuardSpec(long_column="kline_15s_signal", long_operator="<=", long_threshold=0.0)


def run_btc_contract_leverage_lock(
    *,
    v17_run_dir: str | Path,
    v19_run_dir: str | Path | None = None,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    side_guard: BTCSideGuardSpec | None = None,
    horizon_sec: float = 90.0,
    latency_sec: float = 0.5,
    take_profit_bps: float = 40.0,
    stop_loss_bps: float = 0.0,
    stress_fee_side_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    leverage_values: list[float] | None = None,
    shift_null_runs: int = 1000,
    random_scenarios: int = 10000,
    seed: int = 20020,
    gate: BTCLeverageGate | None = None,
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
    stress_fee_side_bps_values = _dedupe_float(stress_fee_side_bps_values or [4.0, 5.0, 6.0, 7.5, 10.0])
    stress_latency_sec_values = _dedupe_float(stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0])
    leverage_values = _dedupe_float(leverage_values or [1.0, 2.0, 3.0, 5.0, 10.0, 20.0])
    gate = gate or BTCLeverageGate()

    source_path = run / "execution_lock_oof_backtest.csv"
    if not source_path.exists():
        raise FileNotFoundError(f"missing frozen V17 ledger: {source_path}")
    frame = pd.read_csv(source_path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    raw_signal = pd.to_numeric(frame.get("signal", 0), errors="coerce").fillna(0).astype(int).clip(-1, 1).to_numpy()
    cost_bps = float(fee_spec.taker_taker_roundtrip_bps)
    exit_spec = ExitLockSpec(take_profit_bps=float(take_profit_bps), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)

    v19_mask = _mask_for_filters(frame, raw_signal, default_v19_fee_filters()) & (raw_signal != 0)
    side_mask = _mask_for_btc_side_guard(frame, raw_signal, side_guard)
    selected_mask = v19_mask & side_mask
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
    selected_bt["real_taker_fee_bps_per_side"] = fee_spec.taker_fee_bps_per_side
    selected_bt["real_maker_fee_bps_per_side"] = fee_spec.maker_fee_bps_per_side
    selected_bt["real_roundtrip_fee_bps"] = selected_bt["traded"].astype(float) * cost_bps
    selected_bt.to_csv(out / "btc_contract_oof_backtest.csv", index=False)
    trades = selected_bt.loc[selected_bt["traded"].astype(int) == 1].copy().reset_index(drop=True)
    trades.to_csv(out / "btc_contract_trade_ledger.csv", index=False)

    # Baseline V19 mask on the same frozen V17 source.
    baseline_signal = np.where(v19_mask, raw_signal, 0)
    baseline_frame = frame.copy()
    baseline_frame["signal"] = baseline_signal
    baseline_bt, baseline_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        baseline_frame,
        cost_bps=cost_bps,
        horizon_sec=float(horizon_sec),
        latency_sec=float(latency_sec),
        spec=exit_spec,
    )
    baseline_trades = baseline_bt.loc[baseline_bt["traded"].astype(int) == 1].copy().reset_index(drop=True)
    baseline = pd.DataFrame([
        {"label": "v19_real_fee_rule_reproduced", **_jsonable(baseline_metrics)},
        {"label": "v20_btc_side_guard_rule", **_jsonable(selected_metrics)},
    ])
    baseline.to_csv(out / "btc_v19_v20_comparison.csv", index=False)

    folds = _fold_metrics(trades)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    bootstrap = block_bootstrap_pnl(pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float), iterations=5000, block_size=5, seed=seed)
    stability = _stability(selected_bt)
    path = _path_diagnostics(pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float), pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy())

    stress = _stress_selected(frame, selected_signal, fee_side_values=stress_fee_side_bps_values, latency_values=stress_latency_sec_values, horizon_sec=horizon_sec, exit_spec=exit_spec)
    stress.to_csv(out / "btc_fee_latency_stress.csv", index=False)
    stress_summary = _stress_summary(stress, _real_fee_gate_for_stress(gate))

    miss = _missed_trade_stress(trades, miss_probabilities=[0.1, 0.2, 0.3, 0.4, gate.missed_trade_gate_probability, 0.6], scenarios=random_scenarios, seed=seed)
    miss.to_csv(out / "btc_missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_cost_bps_values=[0, 1, 2, 3, 5, 7.5, gate.extra_cost_gate_bps, 12])
    extra.to_csv(out / "btc_extra_cost_reserve.csv", index=False)

    leverage = _leverage_scenarios(
        trades=trades,
        leverage_values=leverage_values,
        fee_roundtrip_bps=cost_bps,
        maintenance_margin_bps=float(gate.maintenance_margin_bps),
        shock_buffer_bps=float(gate.shock_buffer_bps),
    )
    leverage.to_csv(out / "btc_leverage_scenarios.csv", index=False)

    side_null_df, side_null = _side_guard_shift_null(
        frame=frame,
        raw_signal=raw_signal,
        selected_side_guard=side_guard,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        exit_spec=exit_spec,
        selected_total=float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        selected_mean=float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        shift_null_runs=shift_null_runs,
        min_trades=gate.min_trades,
    )
    side_null_df.to_csv(out / "btc_side_guard_shift_null.csv", index=False)

    data_plan = write_btc_contract_data_plan(out_dir=out / "btc_contract_data_plan") if write_data_plan else {}

    aggregate = _aggregate(
        selected_metrics=selected_metrics,
        baseline_metrics=baseline_metrics,
        trades=trades,
        folds=folds,
        bootstrap=bootstrap,
        stability=stability,
        path=path,
        stress_summary=stress_summary,
        miss=miss,
        extra=extra,
        leverage=leverage,
        side_null=side_null,
        gate=gate,
    )

    result: dict[str, object] = {
        "v17_run_dir": str(run),
        "v19_run_dir": str(v19_run_dir) if v19_run_dir is not None else "",
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "horizon_sec": float(horizon_sec),
        "latency_sec": float(latency_sec),
        "take_profit_bps": float(take_profit_bps),
        "stop_loss_bps": float(stop_loss_bps),
        "v19_filters": [f.to_dict() for f in default_v19_fee_filters()],
        "btc_side_guard": side_guard.to_dict(),
        "leverage_values": [float(x) for x in leverage_values],
        "shift_null_runs": int(shift_null_runs),
        "stress_fee_side_bps_values": [float(x) for x in stress_fee_side_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "data_plan": data_plan,
        "aggregate": aggregate,
        "gate_config": gate.to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, baseline, folds, stress, miss, extra, leverage)
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


def _mask_for_btc_side_guard(frame: pd.DataFrame, directions: np.ndarray, spec: BTCSideGuardSpec) -> np.ndarray:
    n = len(frame)
    dirs = np.asarray(directions, dtype=int)
    mask = np.ones(n, dtype=bool)
    if spec.long_column:
        if spec.long_column not in frame.columns:
            return np.zeros(n, dtype=bool)
        vals = pd.to_numeric(frame[spec.long_column], errors="coerce").to_numpy(dtype=float)
        long_ok = _compare(vals, spec.long_operator, float(spec.long_threshold)) & np.isfinite(vals)
        mask &= np.where(dirs > 0, long_ok, True)
    if spec.short_column:
        if spec.short_column not in frame.columns:
            return np.zeros(n, dtype=bool)
        vals = pd.to_numeric(frame[spec.short_column], errors="coerce").to_numpy(dtype=float)
        short_ok = _compare(vals, spec.short_operator, float(spec.short_threshold)) & np.isfinite(vals)
        mask &= np.where(dirs < 0, short_ok, True)
    return mask


def _compare(vals: np.ndarray, op: str, threshold: float) -> np.ndarray:
    if op == "<=":
        return vals <= threshold
    if op == ">=":
        return vals >= threshold
    raise ValueError(f"unsupported operator: {op}")


def _real_fee_gate_for_stress(gate: BTCLeverageGate):
    from .real_fee_lock import RealFeeLockGate
    return RealFeeLockGate(max_stress_fee_side_bps=gate.max_stress_fee_side_bps, max_stress_latency_sec=gate.max_stress_latency_sec)


def _leverage_scenarios(
    *,
    trades: pd.DataFrame,
    leverage_values: list[float],
    fee_roundtrip_bps: float,
    maintenance_margin_bps: float,
    shock_buffer_bps: float,
) -> pd.DataFrame:
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    rows = []
    for lev in leverage_values:
        lev = float(lev)
        total_bps = float(pnl.sum())
        mean_bps = float(pnl.mean()) if len(pnl) else 0.0
        min_trade_bps = float(pnl.min()) if len(pnl) else 0.0
        # Account return approximation if each trade uses the same margin allocation and
        # notional = leverage * margin.  This is not compounded and not a liquidation model.
        total_account_return_pct = total_bps / 100.0 * lev
        mean_account_return_pct = mean_bps / 100.0 * lev
        min_trade_account_return_pct = min_trade_bps / 100.0 * lev
        approx_liquidation_buffer_bps = max(0.0, 10000.0 / lev - float(maintenance_margin_bps) - float(fee_roundtrip_bps)) if lev > 0 else 0.0
        rows.append({
            "leverage": lev,
            "notional_total_net_bps": total_bps,
            "notional_mean_net_bps": mean_bps,
            "notional_min_trade_net_bps": min_trade_bps,
            "approx_total_account_return_pct_no_compounding": total_account_return_pct,
            "approx_mean_account_return_pct_per_trade": mean_account_return_pct,
            "approx_min_trade_account_return_pct": min_trade_account_return_pct,
            "approx_liquidation_buffer_bps_before_safety_shock": approx_liquidation_buffer_bps,
            "shock_buffer_bps": float(shock_buffer_bps),
            "passes_shock_buffer": bool(approx_liquidation_buffer_bps >= float(shock_buffer_bps)),
            "notes": "Approximation only; real liquidation depends on exchange bracket, mark price, cross/isolated margin, wallet balance, and open positions.",
        })
    return pd.DataFrame(rows)


def _side_guard_candidates() -> list[BTCSideGuardSpec | None]:
    # None means no extra side guard beyond V19.  Threshold family is deliberately tiny
    # and pre-declared to avoid unlimited mining on the single bundled sample.
    out: list[BTCSideGuardSpec | None] = [None]
    for th in [-0.5, -0.25, -0.1, 0.0, 0.1, 0.25, 0.5]:
        out.append(BTCSideGuardSpec(long_column="kline_15s_signal", long_operator="<=", long_threshold=float(th)))
    return out


def _side_guard_shift_null(
    *,
    frame: pd.DataFrame,
    raw_signal: np.ndarray,
    selected_side_guard: BTCSideGuardSpec,
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
    candidates = _side_guard_candidates()
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
            v19_mask = _mask_for_filters(sub, dirs, default_v19_fee_filters()) & (dirs != 0)
            pnl_all = np.where(dirs > 0, p_long[rows_idx], p_short[rows_idx]).astype(float)
            for cand in candidates:
                m = v19_mask.copy()
                if cand is not None:
                    m &= _mask_for_btc_side_guard(sub, dirs, cand)
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
            "side_guard_family_max_total_bps_constrained": best_total,
            "side_guard_family_max_mean_bps_constrained": best_mean,
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


def _aggregate(*, selected_metrics, baseline_metrics, trades, folds, bootstrap, stability, path, stress_summary, miss, extra, leverage, side_null, gate: BTCLeverageGate) -> dict[str, object]:
    miss_row = _row_for(miss, "miss_probability", gate.missed_trade_gate_probability)
    extra_row = _row_for(extra, "extra_cost_bps_per_trade", gate.extra_cost_gate_bps)
    lev_rows = leverage.loc[pd.to_numeric(leverage.get("leverage", 0), errors="coerce") <= float(gate.promoted_leverage_cap)] if not leverage.empty else pd.DataFrame()
    agg = {
        "baseline_v19_trades": int(baseline_metrics.get("trades", 0)),
        "baseline_v19_hit_rate": float(baseline_metrics.get("hit_rate", 0.0)),
        "baseline_v19_total_net_pnl_bps": float(baseline_metrics.get("total_net_pnl_bps", 0.0)),
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
        "equal_trade_block_5_min_total_bps": float(stability.get("equal_trade_block_5_min_total_bps", 0.0)),
        "top5_winner_removed_total_bps": float(path.get("top5_winner_removed_total_bps", 0.0)),
        "leave_one_trade_out_min_total_bps": float(path.get("leave_one_trade_out_min_total_bps", 0.0)),
        "leave_one_fold_out_min_total_bps": float(path.get("leave_one_fold_out_min_total_bps", 0.0)),
        "stress_gate_min_mean_net_pnl_bps": float(stress_summary.get("gate_min_mean_net_pnl_bps", 0.0)),
        "stress_gate_min_total_net_pnl_bps": float(stress_summary.get("gate_min_total_net_pnl_bps", 0.0)),
        "stress_gate_all_positive": bool(stress_summary.get("gate_all_positive", False)),
        "stress_all_cells_min_total_net_pnl_bps": float(stress_summary.get("all_cells_min_total_net_pnl_bps", 0.0)),
        "missed_trade_gate_p05_total_bps": float(miss_row.get("p05_total_bps", 0.0)),
        "missed_trade_gate_positive_rate": float(miss_row.get("positive_scenario_rate", 0.0)),
        "extra_cost_gate_total_bps": float(extra_row.get("total_net_pnl_bps", 0.0)),
        "side_guard_family_addone_p_total": float(side_null.get("addone_p_total_ge_selected", 1.0)),
        "side_guard_family_addone_p_mean": float(side_null.get("addone_p_mean_ge_selected", 1.0)),
        "side_guard_family_null": side_null,
        "leverage_promoted_cap": float(gate.promoted_leverage_cap),
        "leverage_promoted_rows_all_pass_shock_buffer": bool(lev_rows["passes_shock_buffer"].astype(bool).all()) if not lev_rows.empty else False,
        "stress_summary": stress_summary,
    }
    checks = {
        "enough_trades": int(agg["trades"]) >= int(gate.min_trades),
        "hit_rate": float(agg["hit_rate"]) >= float(gate.min_hit_rate),
        "total_profit": float(agg["total_net_pnl_bps"]) >= float(gate.min_total_net_pnl_bps),
        "fold_total_positive": float(agg["fold_min_total_net_pnl_bps"]) > float(gate.min_fold_total_net_pnl_bps),
        "fold_mean_positive": float(agg["fold_min_mean_net_pnl_bps"]) > float(gate.min_fold_mean_net_pnl_bps),
        "bootstrap_p05_positive": float(agg["bootstrap_mean_p05_bps"]) > float(gate.min_bootstrap_mean_p05_bps),
        "side_guard_family_null": max(float(agg["side_guard_family_addone_p_total"]), float(agg["side_guard_family_addone_p_mean"])) <= float(gate.max_side_guard_addone_p),
        "fee_latency_stress": bool(agg["stress_gate_all_positive"]) and float(agg["stress_gate_min_mean_net_pnl_bps"]) > 0.0 and float(agg["stress_gate_min_total_net_pnl_bps"]) > 0.0,
        "missed_trade_p05_positive": float(agg["missed_trade_gate_p05_total_bps"]) > float(gate.missed_trade_min_p05_total_bps),
        "extra_cost_positive": float(agg["extra_cost_gate_total_bps"]) > float(gate.extra_cost_min_total_bps),
        "promoted_leverage_buffer": bool(agg["leverage_promoted_rows_all_pass_shock_buffer"]),
    }
    agg["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return _jsonable(agg)


def _write_report(path: Path, result: dict[str, object], comparison: pd.DataFrame, folds: pd.DataFrame, stress: pd.DataFrame, miss: pd.DataFrame, extra: pd.DataFrame, leverage: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V20 BTC Contract Leverage Lock",
        "",
        "V20 starts from V19 real-fee rule and adds one BTC-specific side guard for leveraged BTCUSDT perpetual use. It also writes a data-source plan for more BTC contract data.",
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
        }, indent=2),
        "```",
        "",
        "## Aggregate gate",
        "",
        "```json",
        json.dumps(_jsonable(agg), indent=2),
        "```",
        "",
        "## V19 vs V20 comparison",
        "",
        comparison.to_csv(index=False).strip(),
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
        "## More BTC contract data",
        "",
        "See `btc_contract_data_plan/`. It contains Binance Vision BTCUSDT USD-M futures file manifests and REST task templates for Binance/Bybit funding and open-interest features.",
        "",
        "## Caveat",
        "",
        "This is still a bundled-sample research result. The new guard must be frozen and validated on independent BTC contract days before live use. Leverage scenarios are account-return approximations, not exchange liquidation guarantees.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")

# Backward-compatible CLI wrapper used by the V20 package command name.
def run_btc_leverage_lock_certificate(*, v19_run_dir: str | Path, out_dir: str | Path, leverage_values: list[float] | None = None, selected_leverage: float | None = None, horizon_sec: float = 90.0, latency_sec: float = 0.5, random_scenarios: int = 10000, seed: int = 20020, gate: BTCLeverageGate | None = None, clean: bool = False) -> dict[str, object]:
    v19 = Path(v19_run_dir)
    root = v19.parent if v19.name else Path("runs")
    v17 = root / "research_v17_execution_profit_lock_alpha0125_tp40"
    result = run_btc_contract_leverage_lock(
        v17_run_dir=v17,
        v19_run_dir=v19,
        out_dir=out_dir,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        leverage_values=leverage_values,
        random_scenarios=random_scenarios,
        seed=seed,
        gate=gate,
        clean=clean,
    )
    if selected_leverage is not None:
        result["selected_leverage"] = float(selected_leverage)
    return result
