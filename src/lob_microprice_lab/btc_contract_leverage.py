from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_contract_data import write_btc_contract_data_plan
from .exit_lock import ExitLockSpec, backtest_fixed_signals_taker_bidask_exit_lock, execution_path_arrays
from .profit_lock import _jsonable, _path_diagnostics
from .profit_success_fast import _stability
from .real_fee_lock import (
    FeeGuardFilterSpec,
    RealFeeSpec,
    _candidate_filter_atoms,
    _candidate_filter_combos,
    _dedupe_float,
    _evaluate_candidates,
    _extra_cost_reserve,
    _fee_filter_family_shift_null,
    _fold_metrics,
    _mask_for_filters,
    _missed_trade_stress,
    _stress_selected,
    _stress_summary,
    default_v19_fee_filters,
    RealFeeLockGate,
)
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class BTCContractLockGate:
    min_trades: int = 10
    min_hit_rate: float = 0.75
    min_total_net_pnl_bps: float = 120.0
    min_mean_net_pnl_bps: float = 10.0
    min_fold_total_net_pnl_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_addone_p: float = 0.01
    max_stress_fee_side_bps: float = 7.5
    max_stress_latency_sec: float = 5.0
    missed_trade_probability: float = 0.50
    min_missed_trade_p05_total_bps: float = 0.0
    extra_cost_gate_bps: float = 10.0
    max_promoted_leverage: float = 10.0
    max_research_leverage: float = 50.0
    max_equity_drawdown_pct: float = 5.0
    maintenance_margin_pct: float = 0.50
    liquidation_buffer_pct: float = 0.20
    mae_stress_multiplier: float = 2.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_btc_contract_leverage_lock(
    *,
    v17_run_dir: str | Path,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    take_profit_bps: float = 50.0,
    stop_loss_bps: float = 0.0,
    horizon_sec: float = 90.0,
    latency_sec: float = 0.5,
    candidate_quantiles: list[float] | None = None,
    max_filter_count: int = 2,
    shift_null_runs: int = 1000,
    stress_fee_side_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    leverage_grid: list[float] | None = None,
    random_scenarios: int = 10000,
    seed: int = 20020,
    gate: BTCContractLockGate | None = None,
    clean: bool = False,
) -> dict[str, object]:
    src = Path(v17_run_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    gate = gate or BTCContractLockGate()
    fee_spec = fee_spec or RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000)
    candidate_quantiles = _dedupe_float(candidate_quantiles or [0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9])
    stress_fee_side_bps_values = _dedupe_float(stress_fee_side_bps_values or [4.0,5.0,6.0,7.5,10.0])
    stress_latency_sec_values = _dedupe_float(stress_latency_sec_values or [0.0,0.5,1.0,2.0,3.0,5.0])
    leverage_grid = _dedupe_float(leverage_grid or [1,2,3,5,10,15,20,25,50])

    path = src / "execution_lock_oof_backtest.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing V17 execution ledger: {path}")
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    raw_signal = pd.to_numeric(frame.get("signal", 0), errors="coerce").fillna(0).astype(int).clip(-1,1).to_numpy()
    selected_filters = default_v19_fee_filters()
    selected_mask = _mask_for_filters(frame, raw_signal, selected_filters) & (raw_signal != 0)
    selected_signal = np.where(selected_mask, raw_signal, 0)
    cost_bps = float(fee_spec.taker_taker_roundtrip_bps)
    exit_spec = ExitLockSpec(take_profit_bps=float(take_profit_bps), stop_loss_bps=float(stop_loss_bps), reserve_horizon=True)

    selected_frame = frame.copy()
    selected_frame["signal"] = selected_signal
    bt, metrics = backtest_fixed_signals_taker_bidask_exit_lock(selected_frame, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=exit_spec)
    if "fold" in frame.columns:
        bt["fold"] = frame["fold"].to_numpy()
    bt["real_taker_fee_bps_per_side"] = fee_spec.taker_fee_bps_per_side
    bt["real_maker_fee_bps_per_side"] = fee_spec.maker_fee_bps_per_side
    bt.to_csv(out / "btc_contract_lock_oof_backtest.csv", index=False)
    trades = bt.loc[bt["traded"].astype(int) == 1].copy().reset_index(drop=True)
    trades.to_csv(out / "btc_contract_lock_trade_ledger.csv", index=False)

    folds = _fold_metrics(trades)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    bootstrap = block_bootstrap_pnl(pnl, iterations=5000, block_size=5, seed=seed)
    stability = _stability(bt)
    path_diag = _path_diagnostics(pnl, pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy())

    # Compare V19 TP=40 vs V20 TP=50 on the same frozen entry filters.
    comp_rows = []
    for tp in [0,20,25,30,40,50,60,80,100]:
        tmp = frame.copy(); tmp["signal"] = selected_signal
        bt_tmp, met_tmp = backtest_fixed_signals_taker_bidask_exit_lock(tmp, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=ExitLockSpec(float(tp), 0.0, True))
        tr_tmp = bt_tmp.loc[bt_tmp["traded"].astype(int) == 1]
        comp_rows.append({"take_profit_bps": float(tp), **_jsonable(met_tmp), "fold_min_total_net_pnl_bps": float(_fold_metrics(tr_tmp)["total_net_pnl_bps"].min()) if len(tr_tmp) else 0.0})
    exit_candidates = pd.DataFrame(comp_rows).sort_values(["total_net_pnl_bps","mean_net_pnl_bps"], ascending=False).reset_index(drop=True)
    exit_candidates.to_csv(out / "btc_exit_family_candidates.csv", index=False)

    # Fee-filter family correction with the promoted TP=50 exit.
    atoms = _candidate_filter_atoms(frame, raw_signal, candidate_quantiles)
    combos = _candidate_filter_combos(atoms, selected_filters, max_filter_count=max_filter_count)
    candidates = _evaluate_candidates(frame, raw_signal, combos, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, exit_spec=exit_spec)
    candidates.to_csv(out / "btc_fee_filter_family_candidates.csv", index=False)
    null_df, family_null = _fee_filter_family_shift_null(
        frame=frame,
        raw_signal=raw_signal,
        selected_filters=selected_filters,
        candidate_combos=combos,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        exit_spec=exit_spec,
        shift_null_runs=shift_null_runs,
        selected_total=float(metrics.get("total_net_pnl_bps", 0.0)),
        selected_mean=float(metrics.get("mean_net_pnl_bps", 0.0)),
        min_trades=gate.min_trades,
    )
    null_df.to_csv(out / "btc_fee_filter_shift_null.csv", index=False)

    stress_gate = RealFeeLockGate(max_stress_fee_side_bps=gate.max_stress_fee_side_bps, max_stress_latency_sec=gate.max_stress_latency_sec)
    stress = _stress_selected(frame, selected_signal, fee_side_values=stress_fee_side_bps_values, latency_values=stress_latency_sec_values, horizon_sec=horizon_sec, exit_spec=exit_spec)
    stress.to_csv(out / "btc_fee_latency_stress.csv", index=False)
    stress_summary = _stress_summary(stress, stress_gate)
    miss = _missed_trade_stress(trades, miss_probabilities=[0.1,0.2,0.3,0.4,gate.missed_trade_probability,0.6], scenarios=random_scenarios, seed=seed)
    miss.to_csv(out / "btc_missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_cost_bps_values=[0,1,2,3,5,7.5,gate.extra_cost_gate_bps])
    extra.to_csv(out / "btc_extra_cost_reserve.csv", index=False)

    adverse = _trade_path_excursions(bt, horizon_sec=horizon_sec, latency_sec=latency_sec)
    adverse.to_csv(out / "btc_trade_path_excursions.csv", index=False)
    leverage = _leverage_table(adverse, leverage_grid=leverage_grid, gate=gate)
    leverage.to_csv(out / "btc_leverage_safety_table.csv", index=False)
    safe = leverage.loc[leverage["passes_research_safety"].astype(bool)] if not leverage.empty else pd.DataFrame()
    max_safe = float(safe["leverage"].max()) if not safe.empty else 0.0
    promoted_leverage = float(min(max_safe, float(gate.max_promoted_leverage))) if max_safe > 0 else 0.0

    data_plan = write_btc_contract_data_plan(out / "data_plan", symbol="BTCUSDT", start="2020-04-01", end="2020-04-07", intervals=["1s","1m","5m","15m"])

    agg = _aggregate(metrics=metrics, folds=folds, bootstrap=bootstrap, stability=stability, path_diag=path_diag, stress_summary=stress_summary, family_null=family_null, miss=miss, extra=extra, leverage=leverage, promoted_leverage=promoted_leverage, gate=gate)
    result = {
        "version": "v20_btc_contract_leverage_lock",
        "source_v17_run_dir": str(src),
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "horizon_sec": float(horizon_sec),
        "latency_sec": float(latency_sec),
        "selected_filters": [f.to_dict() for f in selected_filters],
        "selected_exit_spec": exit_spec.to_dict(),
        "candidate_quantiles": [float(x) for x in candidate_quantiles],
        "candidate_count": int(len(candidates)),
        "shift_null_runs": int(len(null_df)),
        "promoted_leverage_cap": promoted_leverage,
        "max_research_safe_leverage": max_safe,
        "data_plan": {"manifest_path": str(out / "data_plan" / "btc_contract_data_manifest.json"), "source_count": len(data_plan.get("sources", [])), "binance_url_count": len(data_plan.get("binance_um_daily_urls", []))},
        "aggregate": agg,
        "gate_config": gate.to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, folds, exit_candidates, stress, miss, extra, leverage)
    (out / "DONE.marker").write_text("ok\n", encoding="utf-8")
    return _jsonable(result)


def _trade_path_excursions(bt: pd.DataFrame, *, horizon_sec: float, latency_sec: float) -> pd.DataFrame:
    frame = bt.copy().sort_values("timestamp").reset_index(drop=True)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, format="mixed")
    arrays = execution_path_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec)
    ts, bid, ask, entry_idx, exit_idx, valid, _ = arrays
    rows: list[dict[str, object]] = []
    for i, r in frame.loc[frame["traded"].astype(int) == 1].iterrows():
        sig = int(r["signal"])
        ei = int(entry_idx[int(i)])
        if ei >= len(ts):
            continue
        exit_ts = int(ts[ei]) + int(float(r.get("hold_sec", 0.0)) * 1_000_000_000)
        x = int(np.searchsorted(ts, exit_ts, side="left"))
        x = min(max(x, ei), len(ts) - 1)
        ep = float(r.get("entry_px_taker", np.nan))
        if not np.isfinite(ep) or ep <= 0:
            continue
        if sig > 0:
            pnl_path = (bid[ei:x+1] - ep) / ep * 10000.0
        else:
            pnl_path = (ep - ask[ei:x+1]) / ep * 10000.0
        rows.append({
            "timestamp": r["timestamp"],
            "fold": int(r.get("fold", 0)),
            "signal": sig,
            "net_pnl_bps": float(r.get("net_pnl_bps", 0.0)),
            "gross_pnl_bps": float(r.get("gross_pnl_bps", 0.0)),
            "mae_bps": float(np.nanmin(pnl_path)) if len(pnl_path) else 0.0,
            "mfe_bps": float(np.nanmax(pnl_path)) if len(pnl_path) else 0.0,
            "hold_sec": float(r.get("hold_sec", 0.0)),
            "exit_reason": str(r.get("exit_reason", "")),
        })
    return pd.DataFrame(rows)


def _leverage_table(excursions: pd.DataFrame, *, leverage_grid: list[float], gate: BTCContractLockGate) -> pd.DataFrame:
    pnl = pd.to_numeric(excursions.get("net_pnl_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    mae = pd.to_numeric(excursions.get("mae_bps", 0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    maint = float(gate.maintenance_margin_pct) / 100.0
    buffer = float(gate.liquidation_buffer_pct) / 100.0
    mae_mult = float(gate.mae_stress_multiplier)
    for lev in leverage_grid:
        lev = float(lev)
        if lev <= 0:
            continue
        threshold_bps = max(0.0, (1.0 / lev - maint - buffer) * 10000.0)
        stressed_mae_bps = mae * mae_mult
        liq_breaches = int((stressed_mae_bps < -threshold_bps).sum()) if len(stressed_mae_bps) else 0
        eq_bps = np.cumsum(pnl * lev) if len(pnl) else np.asarray([], dtype=float)
        dd_bps = float((eq_bps - np.maximum.accumulate(eq_bps)).min()) if len(eq_bps) else 0.0
        total_bps = float(pnl.sum() * lev) if len(pnl) else 0.0
        max_dd_pct = abs(dd_bps) / 100.0
        total_pct = total_bps / 100.0
        passes = bool(liq_breaches == 0 and max_dd_pct <= float(gate.max_equity_drawdown_pct) and total_pct > 0 and lev <= float(gate.max_research_leverage))
        rows.append({
            "leverage": lev,
            "estimated_equity_total_return_pct": total_pct,
            "estimated_equity_max_drawdown_pct": max_dd_pct,
            "liquidation_threshold_price_move_bps_after_buffer": threshold_bps,
            "worst_mae_bps": float(mae.min()) if len(mae) else 0.0,
            "mae_stress_multiplier": mae_mult,
            "stressed_liquidation_breach_count": liq_breaches,
            "passes_research_safety": passes,
        })
    return pd.DataFrame(rows)


def _row_for(df: pd.DataFrame, col: str, value: float) -> dict[str, object]:
    if df.empty or col not in df.columns:
        return {}
    vals = pd.to_numeric(df[col], errors="coerce")
    rows = df.loc[np.isclose(vals, float(value))]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _aggregate(*, metrics, folds, bootstrap, stability, path_diag, stress_summary, family_null, miss, extra, leverage, promoted_leverage: float, gate: BTCContractLockGate) -> dict[str, object]:
    miss_row = _row_for(miss, "miss_probability", gate.missed_trade_probability)
    extra_row = _row_for(extra, "extra_cost_bps_per_trade", gate.extra_cost_gate_bps)
    agg = {
        "trades": int(metrics.get("trades", 0)),
        "hit_rate": float(metrics.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
        "median_net_pnl_bps": float(metrics.get("median_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
        "profit_factor": float(metrics.get("profit_factor", 0.0)),
        "max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
        "take_profit_exits": int(metrics.get("take_profit_exits", 0)),
        "horizon_exits": int(metrics.get("horizon_exits", 0)),
        "folds_with_trades": int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0,
        "fold_min_mean_net_pnl_bps": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "fold_min_total_net_pnl_bps": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "positive_equal_trade_blocks_5": int(stability.get("positive_equal_trade_blocks_5", 0)),
        "equal_trade_block_5_min_total_bps": float(stability.get("equal_trade_block_5_min_total_bps", 0.0)),
        "top5_winner_removed_total_bps": float(path_diag.get("top5_winner_removed_total_bps", 0.0)),
        "leave_one_trade_out_min_total_bps": float(path_diag.get("leave_one_trade_out_min_total_bps", 0.0)),
        "leave_one_fold_out_min_total_bps": float(path_diag.get("leave_one_fold_out_min_total_bps", 0.0)),
        "stress_gate_min_mean_net_pnl_bps": float(stress_summary.get("gate_min_mean_net_pnl_bps", 0.0)),
        "stress_gate_min_total_net_pnl_bps": float(stress_summary.get("gate_min_total_net_pnl_bps", 0.0)),
        "stress_gate_all_positive": bool(stress_summary.get("gate_all_positive", False)),
        "stress_all_cells_min_total_net_pnl_bps": float(stress_summary.get("all_cells_min_total_net_pnl_bps", 0.0)),
        "missed_trade_gate_p05_total_bps": float(miss_row.get("p05_total_bps", 0.0)),
        "missed_trade_gate_positive_rate": float(miss_row.get("positive_scenario_rate", 0.0)),
        "extra_cost_gate_total_bps": float(extra_row.get("total_net_pnl_bps", 0.0)),
        "selected_only_addone_p_total": float(family_null.get("selected_only", {}).get("addone_p_total_ge_selected", 1.0)),
        "selected_only_addone_p_mean": float(family_null.get("selected_only", {}).get("addone_p_mean_ge_selected", 1.0)),
        "fee_filter_family_constrained_addone_p_total": float(family_null.get("fee_filter_family", {}).get("addone_p_total_ge_selected_constrained", 1.0)),
        "fee_filter_family_constrained_addone_p_mean": float(family_null.get("fee_filter_family", {}).get("addone_p_mean_ge_selected_constrained", 1.0)),
        "family_null": family_null,
        "stress_summary": stress_summary,
        "promoted_leverage_cap": float(promoted_leverage),
        "max_research_safe_leverage": float(leverage.loc[leverage["passes_research_safety"].astype(bool), "leverage"].max()) if not leverage.empty and leverage["passes_research_safety"].any() else 0.0,
    }
    checks = {
        "enough_trades": agg["trades"] >= gate.min_trades,
        "hit_rate": agg["hit_rate"] >= gate.min_hit_rate,
        "positive_mean": agg["mean_net_pnl_bps"] >= gate.min_mean_net_pnl_bps,
        "positive_total": agg["total_net_pnl_bps"] >= gate.min_total_net_pnl_bps,
        "fold_total_positive": agg["fold_min_total_net_pnl_bps"] > gate.min_fold_total_net_pnl_bps,
        "bootstrap_p05_positive": agg["bootstrap_mean_p05_bps"] > gate.min_bootstrap_mean_p05_bps,
        "selected_shift_null": max(agg["selected_only_addone_p_total"], agg["selected_only_addone_p_mean"]) <= gate.max_addone_p,
        "fee_family_shift_null_constrained": max(agg["fee_filter_family_constrained_addone_p_total"], agg["fee_filter_family_constrained_addone_p_mean"]) <= gate.max_addone_p,
        "fee_latency_stress": bool(agg["stress_gate_all_positive"]) and agg["stress_gate_min_mean_net_pnl_bps"] > 0 and agg["stress_gate_min_total_net_pnl_bps"] > 0,
        "missed_trade_p05_positive": agg["missed_trade_gate_p05_total_bps"] > gate.min_missed_trade_p05_total_bps,
        "extra_cost_positive": agg["extra_cost_gate_total_bps"] > 0,
        "leverage_cap_available": float(promoted_leverage) > 0,
    }
    agg["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return _jsonable(agg)


def _write_report(path: Path, result: dict[str, object], folds: pd.DataFrame, exit_candidates: pd.DataFrame, stress: pd.DataFrame, miss: pd.DataFrame, extra: pd.DataFrame, leverage: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V20 BTC Contract + Leverage Lock",
        "",
        "V20 continues from V19 and targets BTC perpetual/contract use with the user's real fee schedule.",
        "It keeps the V19 high-fee entry guard fixed, updates the selected take-profit to 50 bps after an exit-family comparison, and adds leverage/liquidation safety analysis.",
        "",
        "## Fee schedule",
        "",
        "```json",
        json.dumps(_jsonable(result["fee_spec"]), indent=2),
        "```",
        "",
        "## Selected policy",
        "",
        f"- Horizon: {result['horizon_sec']} seconds",
        f"- Latency: {result['latency_sec']} seconds",
        f"- Take profit: {result['selected_exit_spec']['take_profit_bps']} bps",
        f"- Stop loss: {result['selected_exit_spec']['stop_loss_bps']} bps",
        f"- Promoted leverage cap for research sizing: {result['promoted_leverage_cap']}x",
        f"- Max leverage passing sample safety table: {result['max_research_safe_leverage']}x",
        "",
        "## Aggregate gate",
        "",
        "```json",
        json.dumps(_jsonable(agg), indent=2),
        "```",
        "",
        "## Fold metrics",
        "",
        folds.to_csv(index=False).strip() if not folds.empty else "No folds.",
        "",
        "## Exit-family comparison",
        "",
        exit_candidates.to_csv(index=False).strip() if not exit_candidates.empty else "No exit candidates.",
        "",
        "## Fee/latency stress",
        "",
        stress.to_csv(index=False).strip() if not stress.empty else "No stress table.",
        "",
        "## Missed-trade stress",
        "",
        miss.to_csv(index=False).strip() if not miss.empty else "No missed-trade table.",
        "",
        "## Extra-cost reserve",
        "",
        extra.to_csv(index=False).strip() if not extra.empty else "No extra-cost table.",
        "",
        "## Leverage safety table",
        "",
        leverage.to_csv(index=False).strip() if not leverage.empty else "No leverage table.",
        "",
        "## Data expansion plan",
        "",
        "See `data_plan/BTC_CONTRACT_DATA_PLAN.md` and `data_plan/btc_contract_data_manifest.json`.",
        "",
        "## Caveat",
        "",
        "V20 improves the BTC contract system on the bundled sample, but true stable profit still requires independent multi-day BTC contract validation with the V20 policy frozen.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
