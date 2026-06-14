from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .kline_guard import KlineGuardSpec
from .profit_stability import _fast_signal_metrics, _prepare_execution_arrays
from .selective import backtest_fixed_signals_taker_bidask_non_overlapping, fixed_signal_robust_gate, stress_fixed_signals
from .slot_veto import _shift_values
from .stress import block_bootstrap_pnl

PROBS = ["prob_down", "prob_flat", "prob_up"]


@dataclass(frozen=True)
class ProfitSuccessFastGate:
    min_oof_trades: int = 20
    min_folds_with_trades: int = 5
    min_fold_mean_net_bps: float = 0.0
    min_fold_total_net_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    max_family_p: float = 0.05

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_profit_success_fast(
    *,
    base_ensemble_dir: str | Path,
    kline_ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float = 90.0,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    selected_spec: KlineGuardSpec | None = None,
    alpha_grid: list[float] | None = None,
    ofi_cols: list[str] | None = None,
    ofi_quantiles: list[float] | None = None,
    kline_cols: list[str] | None = None,
    kline_quantiles: list[float] | None = None,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 40,
    gate: ProfitSuccessFastGate | None = None,
    clean: bool = False,
) -> dict[str, object]:
    base = Path(base_ensemble_dir)
    kline = Path(kline_ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    selected_spec = selected_spec or KlineGuardSpec(kline_alpha=0.125, kline_col="kline_15s_rv_6_bps", kline_quantile=0.0)
    alpha_grid = _dedupe(alpha_grid or [0, 0.025, 0.05, 0.075, 0.1, 0.125, 0.15] + [selected_spec.kline_alpha])
    ofi_cols = ofi_cols or ["ofi_sum_l3_norm", "ofi_sum_l5_norm", "ofi_sum_l10_norm"]
    ofi_quantiles = _dedupe(ofi_quantiles or [0.5, 0.6, 0.7, 0.8, 0.9])
    kline_cols = kline_cols or ["kline_15s_rv_6_bps", "kline_15s_rv_12_bps", "kline_1m_rv_3_bps", "kline_1m_range_z_6", "kline_1s_rv_1_bps", "kline_15m_ret_3_bps", "kline_15s_signal"]
    kline_quantiles = _dedupe(kline_quantiles or [0.0])
    stress_cost_bps_values = stress_cost_bps_values or [1.5, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0]
    gate = gate or ProfitSuccessFastGate()

    specs = _family_specs(selected_spec, alpha_grid, ofi_cols, ofi_quantiles, kline_cols, kline_quantiles)
    required = sorted({selected_spec.ofi_col, selected_spec.kline_col, *ofi_cols, *kline_cols})
    alphas = sorted({float(a) for a, _, _ in specs})
    data = _load_alpha_data(base, kline, alphas, required, selected_spec.edge_threshold, horizon_sec, cost_bps, latency_sec)
    selected_alpha = float(selected_spec.kline_alpha)
    canonical = data[selected_alpha]["oof"].copy()
    arrays = _prepare_execution_arrays(canonical, horizon_sec=horizon_sec, latency_sec=latency_sec)

    candidates = []
    selected = None
    for alpha, spec, tags in specs:
        cand = _candidate(alpha, spec, tags, data[float(alpha)], arrays, cost_bps, horizon_sec, latency_sec)
        candidates.append(cand)
        if _key(alpha, spec) == _key(selected_spec.kline_alpha, selected_spec):
            selected = cand
    if selected is None:
        raise RuntimeError("selected candidate missing")

    selected_oof = canonical.copy()
    selected_oof["signal"] = selected["raw"]
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(selected_oof, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec)
    selected_bt["fold"] = canonical["fold"].to_numpy()
    selected_bt.to_csv(out / "profit_success_oof_backtest.csv", index=False)
    folds = pd.DataFrame(selected["fold_rows"]).sort_values("fold")
    folds.to_csv(out / "fold_metrics.csv", index=False)
    cand_df = pd.DataFrame([{**c["spec"].to_dict(), "alpha": c["alpha"], "family_tags": ";".join(c["tags"]), **c["metrics"]} for c in candidates]).sort_values(["total_net_pnl_bps", "mean_net_pnl_bps"], ascending=False)
    cand_df.to_csv(out / "triple_family_candidates.csv", index=False)

    trades = selected_bt[selected_bt["traded"].astype(int) == 1].reset_index(drop=True)
    bootstrap = block_bootstrap_pnl(trades["net_pnl_bps"], iterations=2000, block_size=5, seed=45015)
    stability = _stability(selected_bt)
    stress = stress_fixed_signals(selected_oof, horizon_sec=horizon_sec, cost_bps_values=stress_cost_bps_values, latency_sec_values=stress_latency_sec_values)
    stress.to_csv(out / "profit_success_stress.csv", index=False)
    stress_gate = fixed_signal_robust_gate(stress, min_trades=gate.min_oof_trades)
    null_df, family = _family_null(selected, candidates, arrays, cost_bps, horizon_sec, shift_null_runs, gate.min_oof_trades)
    null_df.to_csv(out / "triple_family_shift_null.csv", index=False)
    aggregate = _aggregate(selected_metrics, folds, bootstrap, stability, stress_gate, family, gate)

    result = {
        "base_ensemble_dir": str(base),
        "kline_ensemble_dir": str(kline),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "selected_alpha": float(selected_spec.kline_alpha),
        "selected_spec": selected_spec.to_dict(),
        "alpha_grid": alpha_grid,
        "ofi_cols": ofi_cols,
        "ofi_quantiles": ofi_quantiles,
        "kline_cols": kline_cols,
        "kline_quantiles": kline_quantiles,
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


def _load_alpha_data(base: Path, kline: Path, alphas, required, edge_threshold, horizon_sec, cost_bps, latency_sec):
    folds = [int(p.name.replace("fold_", "")) for p in sorted(base.glob("fold_*")) if p.is_dir() and (kline / p.name).is_dir()]
    raw = {}
    for fold in folds:
        for split, name in [("cal", "calibration_predictions.csv"), ("val", "validation_predictions.csv")]:
            raw[(fold, split, "b")] = _read_lite(base / f"fold_{fold:02d}" / name, required, True)
            raw[(fold, split, "k")] = _read_lite(kline / f"fold_{fold:02d}" / name, required, False)
    out = {}
    for alpha in alphas:
        cal = {}; cslots = {}; vslots = {}
        for fold in folds:
            cf = _blend_lite(raw[(fold, "cal", "b")], raw[(fold, "cal", "k")], alpha)
            vf = _blend_lite(raw[(fold, "val", "b")], raw[(fold, "val", "k")], alpha)
            cal[fold] = cf
            cslots[fold] = _base_slots(cf, fold, edge_threshold, horizon_sec, cost_bps, latency_sec)
            vslots[fold] = _base_slots(vf, fold, edge_threshold, horizon_sec, cost_bps, latency_sec)
        out[float(alpha)] = {"folds": folds, "cal": cal, "cslots": cslots, "vslots": vslots, "oof": pd.concat([vslots[f] for f in folds], ignore_index=True).sort_values("timestamp").reset_index(drop=True)}
    return out


def _read_lite(path: Path, required: list[str], is_base: bool) -> pd.DataFrame:
    cols = pd.read_csv(path, nrows=0).columns.tolist()
    wanted = {"timestamp", *PROBS, *required} if is_base else {"timestamp", "best_bid", "best_ask", *PROBS, *required}
    return pd.read_csv(path, usecols=[c for c in cols if c in wanted])


def _blend_lite(base: pd.DataFrame, kline: pd.DataFrame, alpha: float) -> pd.DataFrame:
    merged = kline.merge(base[["timestamp"] + [c for c in base.columns if c != "timestamp"]], on="timestamp", how="inner", suffixes=("", "_base"))
    if len(merged) != len(kline) or len(merged) != len(base):
        raise ValueError("base and kline timestamps do not match")
    out = merged.copy()
    for c in PROBS:
        out[c] = (1 - alpha) * pd.to_numeric(out[f"{c}_base"], errors="coerce") + alpha * pd.to_numeric(out[c], errors="coerce")
        out = out.drop(columns=[f"{c}_base"], errors="ignore")
    for c in list(out.columns):
        if c.endswith("_base") and c[:-5] not in out.columns:
            out[c[:-5]] = out[c]
            out = out.drop(columns=[c])
    s = out[PROBS].sum(axis=1).replace(0, np.nan)
    for c in PROBS:
        out[c] = (out[c] / s).fillna(1 / 3).clip(0, 1)
    out["prob_edge"] = out["prob_up"] - out["prob_down"]
    out["kline_blend_alpha"] = float(alpha)
    return out


def _base_slots(frame, fold, edge, horizon_sec, cost_bps, latency_sec):
    e = frame["prob_up"].astype(float) - frame["prob_down"].astype(float)
    raw = np.where(e >= edge, 1, np.where(e <= -edge, -1, 0)).astype(int)
    bt, _ = backtest_fixed_signals_taker_bidask_non_overlapping(frame.assign(signal=raw, fold=fold), cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec)
    bt["fold"] = int(fold)
    return bt


def _family_specs(sel, alphas, ofi_cols, ofi_qs, k_cols, k_qs):
    d = {}
    def add(alpha, spec, tag):
        k = _key(alpha, spec)
        if k not in d:
            d[k] = [float(alpha), spec, set()]
        d[k][2].add(tag)
    for a in alphas:
        add(a, KlineGuardSpec(sel.edge_threshold, a, sel.ofi_col, sel.ofi_quantile, sel.kline_col, sel.kline_quantile, sel.kline_operator, sel.directional), "alpha_family")
    for c in ofi_cols:
        for q in ofi_qs:
            add(sel.kline_alpha, KlineGuardSpec(sel.edge_threshold, sel.kline_alpha, c, q, sel.kline_col, sel.kline_quantile, sel.kline_operator, sel.directional), "ofi_family")
    for c in k_cols:
        for q in k_qs:
            add(sel.kline_alpha, KlineGuardSpec(sel.edge_threshold, sel.kline_alpha, sel.ofi_col, sel.ofi_quantile, c, q, sel.kline_operator, sel.directional), "kline_family")
    add(sel.kline_alpha, sel, "selected_only")
    return [(a, s, tuple(sorted(t))) for a, s, t in d.values()]


def _candidate(alpha, spec, tags, data, arrays, cost_bps, horizon_sec, latency_sec):
    pieces = []; folds = []
    for f in data["folds"]:
        raw, th = _raw_fold(data["cal"][f], data["cslots"][f], data["vslots"][f], spec)
        ff = data["vslots"][f][["fold", "timestamp", "best_bid", "best_ask"]].copy(); ff["signal"] = raw
        fm, _ = _fast_signal_metrics(raw, _prepare_execution_arrays(ff, horizon_sec=horizon_sec, latency_sec=latency_sec), cost_bps=cost_bps)
        folds.append({"fold": f, "alpha": alpha, "ofi_col": spec.ofi_col, "ofi_quantile": spec.ofi_quantile, "ofi_threshold": th[0], "kline_col": spec.kline_col, "kline_quantile": spec.kline_quantile, "kline_threshold": th[1], "trades": int(fm.get("trades", 0)), "hit_rate": fm.get("hit_rate", 0), "mean_net_pnl_bps": fm.get("mean_net_pnl_bps", 0), "total_net_pnl_bps": fm.get("total_net_pnl_bps", 0)})
        pieces.append(ff)
    oof = pd.concat(pieces, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    raw = oof["signal"].astype(int).to_numpy()
    metrics, _ = _fast_signal_metrics(raw, arrays, cost_bps=cost_bps)
    return {"alpha": float(alpha), "spec": spec, "tags": tags, "raw": raw, "metrics": metrics, "fold_rows": folds}


def _raw_fold(cal, cslots, vslots, spec):
    ofi_thr = float(pd.to_numeric(cal[spec.ofi_col], errors="coerce").quantile(spec.ofi_quantile))
    cmask = (cslots["traded"].astype(int) == 1) & (pd.to_numeric(cslots[spec.ofi_col], errors="coerce") <= ofi_thr)
    gv = _guard(cslots.loc[cmask], spec); gv = gv[np.isfinite(gv)]
    k_thr = float(np.quantile(gv, spec.kline_quantile)) if len(gv) else 0.0
    keep = (vslots["traded"].astype(int).to_numpy() == 1) & (pd.to_numeric(vslots[spec.ofi_col], errors="coerce").fillna(np.inf).to_numpy() <= ofi_thr)
    vg = _guard(vslots, spec)
    keep &= (vg >= k_thr) if spec.kline_operator == ">=" else (vg <= k_thr)
    raw = np.zeros(len(vslots), dtype=int)
    raw[keep] = vslots.loc[keep, "signal"].astype(int).to_numpy()
    return raw, (ofi_thr, k_thr)


def _guard(frame, spec):
    v = pd.to_numeric(frame[spec.kline_col], errors="coerce").fillna(0.0).to_numpy(float)
    if spec.directional:
        v = frame.get("signal", pd.Series(0, index=frame.index)).fillna(0).astype(int).clip(-1, 1).to_numpy() * v
    return v


def _family_null(selected, candidates, arrays, cost_bps, horizon_sec, runs, min_trades):
    subsets = {"selected_only": [selected], "alpha_family": [c for c in candidates if "alpha_family" in c["tags"]], "ofi_family": [c for c in candidates if "ofi_family" in c["tags"]], "kline_family": [c for c in candidates if "kline_family" in c["tags"]], "triple_union_family": candidates}
    st = selected["metrics"]["total_net_pnl_bps"]; sm = selected["metrics"]["mean_net_pnl_bps"]
    shifts = _shift_values(n=len(selected["raw"]), shifts=runs, min_shift=max(1, int(round(horizon_sec / 0.5))))
    rows = []
    for sh in shifts:
        row = {"shift_rows": int(sh)}
        for name, subset in subsets.items():
            mt = mm = mtc = mmc = -1e18
            for c in subset:
                m, _ = _fast_signal_metrics(np.roll(c["raw"], int(sh) % len(c["raw"])), arrays, cost_bps=cost_bps)
                t = float(m.get("total_net_pnl_bps", 0)); mean = float(m.get("mean_net_pnl_bps", 0)); tr = float(m.get("trades", 0))
                mt = max(mt, t); mm = max(mm, mean)
                if tr >= min_trades:
                    mtc = max(mtc, t); mmc = max(mmc, mean)
            row[f"{name}_max_total_net_pnl_bps"] = mt; row[f"{name}_max_mean_net_pnl_bps"] = mm; row[f"{name}_max_total_net_pnl_bps_constrained"] = mtc; row[f"{name}_max_mean_net_pnl_bps_constrained"] = mmc
        rows.append(row)
    df = pd.DataFrame(rows)
    fam = {"selected_total_net_pnl_bps": st, "selected_mean_net_pnl_bps": sm, "shift_null_runs": len(df)}
    for name, subset in subsets.items():
        total = pd.to_numeric(df[f"{name}_max_total_net_pnl_bps"]); mean = pd.to_numeric(df[f"{name}_max_mean_net_pnl_bps"])
        fam[name] = {"candidate_count": len(subset), "p_total_ge_selected": float((total >= st).mean()), "p_mean_ge_selected": float((mean >= sm).mean()), "null_total_p95_bps": float(total.quantile(.95)), "null_mean_p95_bps": float(mean.quantile(.95)), "null_total_max_bps": float(total.max()), "null_mean_max_bps": float(mean.max())}
    return df, fam


def _stability(bt):
    t = bt[bt["traded"].astype(int) == 1].reset_index(drop=True)
    pnl = t["net_pnl_bps"].astype(float).to_numpy()
    def blocks(n):
        out = []
        for i, idx in enumerate(np.array_split(np.arange(len(pnl)), n), 1):
            vals = pnl[idx] if len(idx) else np.array([])
            out.append({"block": i, "trades": len(vals), "mean_net_pnl_bps": float(vals.mean()) if len(vals) else 0.0, "total_net_pnl_bps": float(vals.sum()) if len(vals) else 0.0})
        return out
    b5 = pd.DataFrame(blocks(5)); b10 = pd.DataFrame(blocks(10))
    loo = []
    for f in sorted(t["fold"].unique()) if "fold" in t.columns else []:
        rest = t[t["fold"] != f]["net_pnl_bps"].astype(float)
        loo.append({"removed_fold": int(f), "remaining_trades": len(rest), "remaining_total_net_pnl_bps": float(rest.sum()), "remaining_mean_net_pnl_bps": float(rest.mean())})
    return {"equal_trade_blocks_5": b5.to_dict("records"), "equal_trade_blocks_10": b10.to_dict("records"), "positive_equal_trade_blocks_5": int((b5.total_net_pnl_bps > 0).sum()), "positive_equal_trade_blocks_10": int((b10.total_net_pnl_bps > 0).sum()), "equal_trade_block_5_min_total_bps": float(b5.total_net_pnl_bps.min()), "equal_trade_block_10_min_total_bps": float(b10.total_net_pnl_bps.min()), "leave_one_fold_out": loo, "leave_one_fold_out_min_total_bps": float(min([x["remaining_total_net_pnl_bps"] for x in loo]) if loo else 0.0)}


def _aggregate(metrics, folds, boot, stability, stress_gate, fam, gate):
    def p(name, field): return float(fam.get(name, {}).get(field, 1.0))
    summary = {"trades": int(metrics.get("trades", 0)), "hit_rate": float(metrics.get("hit_rate", 0)), "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0)), "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0)), "folds_with_trades": int((folds.trades.astype(float) > 0).sum()), "fold_min_mean_net_pnl_bps": float(folds.mean_net_pnl_bps.min()), "fold_min_total_net_pnl_bps": float(folds.total_net_pnl_bps.min()), "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0)), "bootstrap_total_p05_bps": float(boot.get("total_p05_bps", 0)), "stress_gate_passed": bool(stress_gate.get("passed")), "stress_min_mean_net_pnl_bps": float(stress_gate.get("min_mean_net_pnl_bps", 0)), "stress_min_total_net_pnl_bps": float(stress_gate.get("min_total_net_pnl_bps", 0)), **{k: stability[k] for k in ["positive_equal_trade_blocks_5", "positive_equal_trade_blocks_10", "equal_trade_block_5_min_total_bps", "equal_trade_block_10_min_total_bps", "leave_one_fold_out_min_total_bps"]}, "selected_shift_p_total": p("selected_only", "p_total_ge_selected"), "selected_shift_p_mean": p("selected_only", "p_mean_ge_selected"), "alpha_family_p_total": p("alpha_family", "p_total_ge_selected"), "alpha_family_p_mean": p("alpha_family", "p_mean_ge_selected"), "ofi_family_p_total": p("ofi_family", "p_total_ge_selected"), "ofi_family_p_mean": p("ofi_family", "p_mean_ge_selected"), "kline_family_p_total": p("kline_family", "p_total_ge_selected"), "kline_family_p_mean": p("kline_family", "p_mean_ge_selected"), "union_family_p_total": p("triple_union_family", "p_total_ge_selected"), "union_family_p_mean": p("triple_union_family", "p_mean_ge_selected")}
    checks = {"enough_oof_trades": summary["trades"] >= gate.min_oof_trades, "enough_folds_with_trades": summary["folds_with_trades"] >= gate.min_folds_with_trades, "positive_fold_min_mean": summary["fold_min_mean_net_pnl_bps"] > gate.min_fold_mean_net_bps, "positive_fold_min_total": summary["fold_min_total_net_pnl_bps"] > gate.min_fold_total_net_bps, "positive_bootstrap_mean_p05": summary["bootstrap_mean_p05_bps"] > gate.min_bootstrap_mean_p05_bps, "stress_gate_ok": summary["stress_gate_passed"], "positive_equal_trade_blocks_5": summary["positive_equal_trade_blocks_5"] >= 5, "positive_equal_trade_blocks_10": summary["positive_equal_trade_blocks_10"] >= 10, "positive_leave_one_fold_out": summary["leave_one_fold_out_min_total_bps"] > 0}
    for n in ["selected_shift", "alpha_family", "ofi_family", "kline_family", "union_family"]:
        checks[f"{n}_total_ok"] = summary[f"{n}_p_total"] <= gate.max_family_p
        checks[f"{n}_mean_ok"] = summary[f"{n}_p_mean"] <= gate.max_family_p
    summary["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return summary


def _write_report(path, result, folds, cand):
    st = result["stability"]; agg = result["aggregate"]; fam = result["family_null"]
    lines = ["# V15 Profit Success Fast Audit", "", "## Aggregate", "", "```json", json.dumps(agg, indent=2), "```", "", "## Fold metrics", "", folds.to_markdown(index=False), "", "## 5 equal-trade blocks", "", pd.DataFrame(st["equal_trade_blocks_5"]).to_markdown(index=False), "", "## 10 pair blocks", "", pd.DataFrame(st["equal_trade_blocks_10"]).to_markdown(index=False), "", "## Family null", "", "```json", json.dumps(fam, indent=2), "```", "", "## Candidate leaderboard", "", cand.head(30).to_markdown(index=False), ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _key(alpha, spec): return (round(float(alpha), 12), round(spec.edge_threshold, 12), spec.ofi_col, round(spec.ofi_quantile, 12), spec.kline_col, round(spec.kline_quantile, 12), spec.kline_operator, bool(spec.directional))
def _dedupe(xs):
    out = []
    for x in xs:
        y = round(float(x), 12)
        if y not in [round(float(z), 12) for z in out]: out.append(float(x))
    return out
