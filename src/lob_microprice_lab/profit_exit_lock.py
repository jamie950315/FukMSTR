from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .exit_lock import ExitLockSpec, backtest_fixed_signals_taker_bidask_exit_lock, execution_path_arrays, fast_exit_lock_metrics
from .kline_guard import KlineGuardSpec
from .profit_success_fast import _candidate, _dedupe, _family_specs, _key, _load_alpha_data, _stability
from .selective import fixed_signal_robust_gate
from .slot_veto import _shift_values
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class ProfitExitLockGate:
    min_oof_trades: int = 20
    min_folds_with_trades: int = 5
    min_fold_mean_net_bps: float = 0.0
    min_fold_total_net_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_family_p: float = 0.05

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_profit_exit_lock(
    *,
    base_ensemble_dir: str | Path,
    kline_ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float = 90.0,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    selected_signal_spec: KlineGuardSpec | None = None,
    selected_exit_spec: ExitLockSpec | None = None,
    alpha_grid: list[float] | None = None,
    ofi_cols: list[str] | None = None,
    ofi_quantiles: list[float] | None = None,
    kline_cols: list[str] | None = None,
    kline_quantiles: list[float] | None = None,
    exit_take_profit_bps_values: list[float] | None = None,
    exit_stop_loss_bps_values: list[float] | None = None,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 40,
    gate: ProfitExitLockGate | None = None,
    clean: bool = False,
) -> dict[str, object]:
    base = Path(base_ensemble_dir)
    kline = Path(kline_ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    selected_signal_spec = selected_signal_spec or KlineGuardSpec(
        edge_threshold=0.1,
        kline_alpha=0.125,
        ofi_col="ofi_sum_l5_norm",
        ofi_quantile=0.9,
        kline_col="kline_15s_rv_6_bps",
        kline_quantile=0.0,
    )
    selected_exit_spec = selected_exit_spec or ExitLockSpec(take_profit_bps=40.0, stop_loss_bps=0.0, reserve_horizon=True)
    alpha_grid = _dedupe(alpha_grid or [0, 0.025, 0.05, 0.075, 0.1, 0.125, 0.15] + [selected_signal_spec.kline_alpha])
    ofi_cols = ofi_cols or ["ofi_sum_l3_norm", "ofi_sum_l5_norm", "ofi_sum_l10_norm"]
    ofi_quantiles = _dedupe(ofi_quantiles or [0.5, 0.6, 0.7, 0.8, 0.9])
    kline_cols = kline_cols or ["kline_15s_rv_6_bps", "kline_15s_rv_12_bps", "kline_1m_rv_3_bps", "kline_1m_range_z_6", "kline_1s_rv_1_bps", "kline_15m_ret_3_bps", "kline_15s_signal"]
    kline_quantiles = _dedupe(kline_quantiles or [0.0])
    exit_take_profit_bps_values = _dedupe(exit_take_profit_bps_values or [0.0, 20.0, 30.0, 40.0, 60.0, 90.0] + [selected_exit_spec.take_profit_bps])
    exit_stop_loss_bps_values = _dedupe(exit_stop_loss_bps_values or [0.0] + [selected_exit_spec.stop_loss_bps])
    stress_cost_bps_values = stress_cost_bps_values or [1.5, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0]
    gate = gate or ProfitExitLockGate()

    signal_specs = _family_specs(selected_signal_spec, alpha_grid, ofi_cols, ofi_quantiles, kline_cols, kline_quantiles)
    required = sorted({selected_signal_spec.ofi_col, selected_signal_spec.kline_col, *ofi_cols, *kline_cols})
    alphas = sorted({float(a) for a, _, _ in signal_specs})
    data = _load_alpha_data(base, kline, alphas, required, selected_signal_spec.edge_threshold, horizon_sec, cost_bps, latency_sec)
    canonical = data[float(selected_signal_spec.kline_alpha)]["oof"].copy().sort_values("timestamp").reset_index(drop=True)
    arrays = execution_path_arrays(canonical, horizon_sec=horizon_sec, latency_sec=latency_sec)

    signal_candidates = []
    selected_signal = None
    # Use the fixed-horizon fast arrays only to reuse the v15 signal construction. Exit metrics are recomputed below.
    from .profit_stability import _prepare_execution_arrays

    fixed_arrays = _prepare_execution_arrays(canonical, horizon_sec=horizon_sec, latency_sec=latency_sec)
    for alpha, spec, tags in signal_specs:
        cand = _candidate(alpha, spec, tags, data[float(alpha)], fixed_arrays, cost_bps, horizon_sec, latency_sec)
        signal_candidates.append(cand)
        if _key(alpha, spec) == _key(selected_signal_spec.kline_alpha, selected_signal_spec):
            selected_signal = cand
    if selected_signal is None:
        raise RuntimeError("selected signal candidate missing")

    exit_specs = [ExitLockSpec(take_profit_bps=tp, stop_loss_bps=sl, reserve_horizon=True) for tp in exit_take_profit_bps_values for sl in exit_stop_loss_bps_values]
    exit_specs = _dedupe_exit_specs(exit_specs)

    combos = []
    selected_combo = None
    for sc in signal_candidates:
        for ex in exit_specs:
            metrics, pnl, reasons, holds = fast_exit_lock_metrics(sc["raw"], arrays, cost_bps=cost_bps, spec=ex)
            combo_tags = set(sc["tags"])
            if _same_exit(ex, selected_exit_spec):
                combo_tags.add("selected_exit")
            else:
                combo_tags.add("exit_family")
            combo = {"signal": sc, "exit": ex, "raw": sc["raw"], "tags": tuple(sorted(combo_tags)), "metrics": metrics}
            combos.append(combo)
            if _key(sc["alpha"], sc["spec"]) == _key(selected_signal_spec.kline_alpha, selected_signal_spec) and _same_exit(ex, selected_exit_spec):
                selected_combo = combo
    if selected_combo is None:
        raise RuntimeError("selected exit-lock candidate missing")

    selected_oof = canonical.copy()
    selected_oof["signal"] = selected_combo["raw"]
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_exit_lock(
        selected_oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        spec=selected_exit_spec,
    )
    selected_bt["fold"] = canonical["fold"].to_numpy()
    selected_bt.to_csv(out / "profit_exit_lock_oof_backtest.csv", index=False)

    folds = _fold_metrics(canonical, selected_combo["raw"], selected_exit_spec, cost_bps, horizon_sec, latency_sec)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    cand_df = _candidate_frame(combos)
    cand_df.to_csv(out / "exit_lock_family_candidates.csv", index=False)

    trades = selected_bt[selected_bt["traded"].astype(int) == 1].reset_index(drop=True)
    bootstrap = block_bootstrap_pnl(trades["net_pnl_bps"], iterations=2000, block_size=5, seed=46016)
    stability = _stability(selected_bt)
    stress = _stress_exit_lock(canonical, selected_combo["raw"], selected_exit_spec, horizon_sec, cost_bps_values=stress_cost_bps_values, latency_sec_values=stress_latency_sec_values)
    stress.to_csv(out / "profit_exit_lock_stress.csv", index=False)
    stress_gate = fixed_signal_robust_gate(stress, min_trades=gate.min_oof_trades)
    null_df, family = _family_null(selected_combo, combos, arrays, cost_bps, horizon_sec, shift_null_runs, gate.min_oof_trades)
    null_df.to_csv(out / "exit_lock_family_shift_null.csv", index=False)
    aggregate = _aggregate(selected_metrics, folds, bootstrap, stability, stress_gate, family, gate)

    result = {
        "base_ensemble_dir": str(base),
        "kline_ensemble_dir": str(kline),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "selected_signal_spec": selected_signal_spec.to_dict(),
        "selected_exit_spec": selected_exit_spec.to_dict(),
        "alpha_grid": alpha_grid,
        "ofi_cols": ofi_cols,
        "ofi_quantiles": ofi_quantiles,
        "kline_cols": kline_cols,
        "kline_quantiles": kline_quantiles,
        "exit_take_profit_bps_values": exit_take_profit_bps_values,
        "exit_stop_loss_bps_values": exit_stop_loss_bps_values,
        "shift_null_runs": int(len(null_df)),
        "selected_metrics": selected_metrics,
        "bootstrap": bootstrap,
        "stability": stability,
        "stress_gate": stress_gate,
        "family_null": family,
        "aggregate": aggregate,
        "gate_config": gate.to_dict(),
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, folds, cand_df)
    return result


def _fold_metrics(canonical: pd.DataFrame, raw: np.ndarray, spec: ExitLockSpec, cost_bps: float, horizon_sec: float, latency_sec: float) -> pd.DataFrame:
    rows = []
    frame = canonical.copy()
    frame["signal"] = raw
    for fold in sorted(frame["fold"].unique()):
        sub = frame[frame["fold"] == fold].copy()
        _, m = backtest_fixed_signals_taker_bidask_exit_lock(sub, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec, spec=spec)
        rows.append({"fold": int(fold), **_jsonable_metrics(m)})
    return pd.DataFrame(rows)


def _stress_exit_lock(canonical: pd.DataFrame, raw: np.ndarray, spec: ExitLockSpec, horizon_sec: float, *, cost_bps_values: list[float], latency_sec_values: list[float]) -> pd.DataFrame:
    rows = []
    for cost in cost_bps_values:
        for lat in latency_sec_values:
            arrays = execution_path_arrays(canonical, horizon_sec=horizon_sec, latency_sec=float(lat))
            m, _, _, _ = fast_exit_lock_metrics(raw, arrays, cost_bps=float(cost), spec=spec)
            rows.append({"cost_bps": float(cost), "latency_sec": float(lat), **m})
    return pd.DataFrame(rows)


def _candidate_frame(combos: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for c in combos:
        sc = c["signal"]
        ex = c["exit"]
        assert isinstance(ex, ExitLockSpec)
        rows.append({
            "alpha": float(sc["alpha"]),
            **sc["spec"].to_dict(),
            **{f"exit_{k}": v for k, v in ex.to_dict().items()},
            "family_tags": ";".join(c["tags"]),
            **_jsonable_metrics(c["metrics"]),
        })
    return pd.DataFrame(rows).sort_values(["total_net_pnl_bps", "mean_net_pnl_bps"], ascending=False).reset_index(drop=True)



def _family_null(selected: dict[str, object], combos: list[dict[str, object]], arrays, cost_bps: float, horizon_sec: float, runs: int, min_trades: int):
    """Shifted-signal null for the exit-lock family.

    V17 uses a cached path-exit table so larger shifted-signal nulls can be run without
    repeatedly scanning the bid/ask path for each candidate/shift combination.  The
    non-overlap cooldown is still recomputed after each shift.
    """
    selected_signal = selected["signal"]
    selected_exit = selected["exit"]
    subsets = {
        "selected_only": [selected],
        "alpha_family": [c for c in combos if "alpha_family" in c["tags"] and _same_exit(c["exit"], selected_exit)],
        "ofi_family": [c for c in combos if "ofi_family" in c["tags"] and _same_exit(c["exit"], selected_exit)],
        "kline_family": [c for c in combos if "kline_family" in c["tags"] and _same_exit(c["exit"], selected_exit)],
        "exit_family": [c for c in combos if _same_signal(c["signal"], selected_signal)],
        "signal_union_family": [c for c in combos if _same_exit(c["exit"], selected_exit)],
        "exit_signal_union_family": combos,
    }
    st = float(selected["metrics"].get("total_net_pnl_bps", 0.0))
    sm = float(selected["metrics"].get("mean_net_pnl_bps", 0.0))
    shifts = _shift_values(n=len(selected["raw"]), shifts=runs, min_shift=max(1, int(round(float(horizon_sec) / 0.5))))
    tables: dict[tuple[float, float, bool], dict[str, np.ndarray]] = {}
    for c in combos:
        key = _exit_key(c["exit"])
        if key not in tables:
            tables[key] = _precompute_exit_table(arrays, c["exit"])
    sparse = {id(c): _nonzero_signal_locations(c["raw"]) for c in combos}
    rows = []
    for sh in shifts:
        row = {"shift_rows": int(sh)}
        for name, subset in subsets.items():
            mt = mm = mtc = mmc = -1e18
            for c in subset:
                idx, sig = sparse[id(c)]
                m = _shifted_metrics_from_table(idx, sig, int(sh), arrays, tables[_exit_key(c["exit"])], cost_bps)
                t = float(m.get("total_net_pnl_bps", 0.0))
                mean = float(m.get("mean_net_pnl_bps", 0.0))
                tr = float(m.get("trades", 0.0))
                mt = max(mt, t)
                mm = max(mm, mean)
                if tr >= min_trades:
                    mtc = max(mtc, t)
                    mmc = max(mmc, mean)
            row[f"{name}_max_total_net_pnl_bps"] = mt
            row[f"{name}_max_mean_net_pnl_bps"] = mm
            row[f"{name}_max_total_net_pnl_bps_constrained"] = mtc
            row[f"{name}_max_mean_net_pnl_bps_constrained"] = mmc
        rows.append(row)
    df = pd.DataFrame(rows)
    fam: dict[str, object] = {"selected_total_net_pnl_bps": st, "selected_mean_net_pnl_bps": sm, "shift_null_runs": len(df)}
    denom = len(df) + 1
    for name, subset in subsets.items():
        total = pd.to_numeric(df[f"{name}_max_total_net_pnl_bps"])
        mean = pd.to_numeric(df[f"{name}_max_mean_net_pnl_bps"])
        exceed_t = int((total >= st).sum())
        exceed_m = int((mean >= sm).sum())
        fam[name] = {
            "candidate_count": int(len(subset)),
            "exceed_total_count": exceed_t,
            "exceed_mean_count": exceed_m,
            "p_total_ge_selected": float(exceed_t / len(df)) if len(df) else 1.0,
            "p_mean_ge_selected": float(exceed_m / len(df)) if len(df) else 1.0,
            "addone_p_total_ge_selected": float((exceed_t + 1) / denom) if len(df) else 1.0,
            "addone_p_mean_ge_selected": float((exceed_m + 1) / denom) if len(df) else 1.0,
            "null_total_p95_bps": float(total.quantile(0.95)),
            "null_mean_p95_bps": float(mean.quantile(0.95)),
            "null_total_max_bps": float(total.max()),
            "null_mean_max_bps": float(mean.max()),
        }
    return df, fam


def _exit_key(spec: ExitLockSpec) -> tuple[float, float, bool]:
    return (round(float(spec.take_profit_bps), 12), round(float(spec.stop_loss_bps), 12), bool(spec.reserve_horizon))


def _nonzero_signal_locations(raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(raw, dtype=int)
    idx = np.flatnonzero(arr != 0)
    return idx.astype(int), arr[idx].astype(int)


def _precompute_exit_table(arrays, spec: ExitLockSpec) -> dict[str, np.ndarray]:
    ts, bid, ask, entry_idx, exit_idx, valid, horizon_ns = arrays
    n = len(ts)
    long_gross = np.full(n, np.nan, dtype=float)
    short_gross = np.full(n, np.nan, dtype=float)
    valid_arr = np.asarray(valid, dtype=bool)
    tp_on = spec.has_take_profit
    sl_on = spec.has_stop_loss
    tp_bps = float(spec.take_profit_bps)
    sl_bps = float(spec.stop_loss_bps)
    for i in range(n):
        if not bool(valid_arr[i]):
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if xi <= ei:
            continue
        ep = float(ask[ei])
        if np.isfinite(ep) and ep > 0:
            x = xi
            tp_px = ep * (1.0 + tp_bps / 10000.0) if tp_on else np.inf
            sl_px = ep * (1.0 - sl_bps / 10000.0) if sl_on else -np.inf
            for j in range(ei + 1, xi + 1):
                if sl_on and float(bid[j]) <= sl_px:
                    x = j
                    break
                if tp_on and float(bid[j]) >= tp_px:
                    x = j
                    break
            xp = float(bid[x])
            if np.isfinite(xp) and xp > 0:
                long_gross[i] = (xp - ep) / ep * 10000.0
        ep = float(bid[ei])
        if np.isfinite(ep) and ep > 0:
            x = xi
            tp_px = ep * (1.0 - tp_bps / 10000.0) if tp_on else -np.inf
            sl_px = ep * (1.0 + sl_bps / 10000.0) if sl_on else np.inf
            for j in range(ei + 1, xi + 1):
                if sl_on and float(ask[j]) >= sl_px:
                    x = j
                    break
                if tp_on and float(ask[j]) <= tp_px:
                    x = j
                    break
            xp = float(ask[x])
            if np.isfinite(xp) and xp > 0:
                short_gross[i] = (ep - xp) / ep * 10000.0
    return {"long_gross_bps": long_gross, "short_gross_bps": short_gross, "valid": valid_arr}


def _shifted_metrics_from_table(original_idx: np.ndarray, sig: np.ndarray, shift: int, arrays, table: dict[str, np.ndarray], cost_bps: float) -> dict[str, float]:
    ts, _bid, _ask, _entry_idx, _exit_idx, _valid, horizon_ns = arrays
    n = len(ts)
    if n == 0 or len(original_idx) == 0:
        return {"events": float(n), "trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    shifted = (original_idx + int(shift)) % n
    order = np.argsort(shifted, kind="mergesort")
    long_gross = table["long_gross_bps"]
    short_gross = table["short_gross_bps"]
    valid = table["valid"]
    pnls: list[float] = []
    next_allowed = -10**30
    for pos in order:
        i = int(shifted[pos])
        direction = int(sig[pos])
        if int(ts[i]) < next_allowed or not bool(valid[i]):
            continue
        gross = float(long_gross[i]) if direction > 0 else float(short_gross[i])
        if np.isfinite(gross):
            pnls.append(gross - float(cost_bps))
            next_allowed = int(ts[i]) + int(horizon_ns)
    arr = np.asarray(pnls, dtype=float)
    if len(arr) == 0:
        return {"events": float(n), "trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    return {
        "events": float(n),
        "trades": float(len(arr)),
        "hit_rate": float((arr > 0.0).mean()),
        "mean_net_pnl_bps": float(arr.mean()),
        "total_net_pnl_bps": float(arr.sum()),
    }

def _aggregate(metrics, folds, boot, stability, stress_gate, fam, gate):
    def p(name, field):
        return float(fam.get(name, {}).get(field, 1.0))

    summary = {
        "trades": int(metrics.get("trades", 0)),
        "hit_rate": float(metrics.get("hit_rate", 0)),
        "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0)),
        "median_net_pnl_bps": float(metrics.get("median_net_pnl_bps", 0)),
        "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0)),
        "profit_factor": float(metrics.get("profit_factor", 0)),
        "max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0)),
        "take_profit_exits": int(metrics.get("take_profit_exits", 0)),
        "stop_loss_exits": int(metrics.get("stop_loss_exits", 0)),
        "horizon_exits": int(metrics.get("horizon_exits", 0)),
        "mean_hold_sec": float(metrics.get("mean_hold_sec", 0)),
        "folds_with_trades": int((folds.trades.astype(float) > 0).sum()),
        "fold_min_mean_net_pnl_bps": float(folds.mean_net_pnl_bps.min()),
        "fold_min_total_net_pnl_bps": float(folds.total_net_pnl_bps.min()),
        "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0)),
        "bootstrap_total_p05_bps": float(boot.get("total_p05_bps", 0)),
        "stress_gate_passed": bool(stress_gate.get("passed")),
        "stress_min_mean_net_pnl_bps": float(stress_gate.get("min_mean_net_pnl_bps", 0)),
        "stress_min_total_net_pnl_bps": float(stress_gate.get("min_total_net_pnl_bps", 0)),
        **{k: stability[k] for k in ["positive_equal_trade_blocks_5", "positive_equal_trade_blocks_10", "equal_trade_block_5_min_total_bps", "equal_trade_block_10_min_total_bps", "leave_one_fold_out_min_total_bps"]},
        "selected_shift_p_total": p("selected_only", "p_total_ge_selected"),
        "selected_shift_p_mean": p("selected_only", "p_mean_ge_selected"),
        "alpha_family_p_total": p("alpha_family", "p_total_ge_selected"),
        "alpha_family_p_mean": p("alpha_family", "p_mean_ge_selected"),
        "ofi_family_p_total": p("ofi_family", "p_total_ge_selected"),
        "ofi_family_p_mean": p("ofi_family", "p_mean_ge_selected"),
        "kline_family_p_total": p("kline_family", "p_total_ge_selected"),
        "kline_family_p_mean": p("kline_family", "p_mean_ge_selected"),
        "exit_family_p_total": p("exit_family", "p_total_ge_selected"),
        "exit_family_p_mean": p("exit_family", "p_mean_ge_selected"),
        "signal_union_family_p_total": p("signal_union_family", "p_total_ge_selected"),
        "signal_union_family_p_mean": p("signal_union_family", "p_mean_ge_selected"),
        "exit_signal_union_family_p_total": p("exit_signal_union_family", "p_total_ge_selected"),
        "exit_signal_union_family_p_mean": p("exit_signal_union_family", "p_mean_ge_selected"),
    }
    checks = {
        "enough_oof_trades": summary["trades"] >= gate.min_oof_trades,
        "enough_folds_with_trades": summary["folds_with_trades"] >= gate.min_folds_with_trades,
        "positive_fold_min_mean": summary["fold_min_mean_net_pnl_bps"] > gate.min_fold_mean_net_bps,
        "positive_fold_min_total": summary["fold_min_total_net_pnl_bps"] > gate.min_fold_total_net_bps,
        "positive_bootstrap_mean_p05": summary["bootstrap_mean_p05_bps"] > gate.min_bootstrap_mean_p05_bps,
        "stress_gate_ok": summary["stress_gate_passed"],
        "positive_equal_trade_blocks_5": summary["positive_equal_trade_blocks_5"] >= 5,
        "positive_equal_trade_blocks_10": summary["positive_equal_trade_blocks_10"] >= 10,
        "positive_leave_one_fold_out": summary["leave_one_fold_out_min_total_bps"] > 0,
    }
    for n in ["selected_shift", "alpha_family", "ofi_family", "kline_family", "exit_family", "signal_union_family", "exit_signal_union_family"]:
        checks[f"{n}_total_ok"] = summary[f"{n}_p_total"] <= gate.max_family_p
        checks[f"{n}_mean_ok"] = summary[f"{n}_p_mean"] <= gate.max_family_p
    summary["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return summary


def _same_signal(left: dict[str, object], right: dict[str, object]) -> bool:
    return _key(left["alpha"], left["spec"]) == _key(right["alpha"], right["spec"])


def _same_exit(left: object, right: object) -> bool:
    return isinstance(left, ExitLockSpec) and isinstance(right, ExitLockSpec) and abs(float(left.take_profit_bps) - float(right.take_profit_bps)) < 1e-12 and abs(float(left.stop_loss_bps) - float(right.stop_loss_bps)) < 1e-12 and bool(left.reserve_horizon) == bool(right.reserve_horizon)


def _dedupe_exit_specs(specs: list[ExitLockSpec]) -> list[ExitLockSpec]:
    out = []
    seen = set()
    for s in specs:
        k = (round(float(s.take_profit_bps), 12), round(float(s.stop_loss_bps), 12), bool(s.reserve_horizon))
        if k not in seen:
            out.append(s)
            seen.add(k)
    return out


def _jsonable_metrics(metrics: dict[str, object]) -> dict[str, object]:
    out = {}
    for k, v in metrics.items():
        if isinstance(v, (np.floating, float)):
            out[k] = float(v)
        elif isinstance(v, (np.integer, int)):
            out[k] = int(v)
        elif isinstance(v, (np.bool_, bool)):
            out[k] = bool(v)
        else:
            out[k] = v
    return out


def _write_report(path: str | Path, result: dict[str, object], folds: pd.DataFrame, cand: pd.DataFrame) -> None:
    st = result["stability"]
    agg = result["aggregate"]
    fam = result["family_null"]
    lines = [
        "# V16 Profit Exit-Lock Audit",
        "",
        "## Selected policy",
        "",
        "```json",
        json.dumps({"signal": result["selected_signal_spec"], "exit": result["selected_exit_spec"]}, indent=2),
        "```",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(agg, indent=2),
        "```",
        "",
        "## Fold metrics",
        "",
        folds.to_markdown(index=False),
        "",
        "## 5 equal-trade blocks",
        "",
        pd.DataFrame(st["equal_trade_blocks_5"]).to_markdown(index=False),
        "",
        "## 10 pair blocks",
        "",
        pd.DataFrame(st["equal_trade_blocks_10"]).to_markdown(index=False),
        "",
        "## Family null",
        "",
        "```json",
        json.dumps(fam, indent=2),
        "```",
        "",
        "## Candidate leaderboard",
        "",
        cand.head(30).to_markdown(index=False),
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
