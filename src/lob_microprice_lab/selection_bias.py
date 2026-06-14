from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data_schema import timestamps_to_ns
from .fixed_template import _build_template_pool, candidate_signature, load_ensemble_fold_predictions, rank_fixed_template_leaderboard, summarize_fixed_template_candidate
from .selective import (
    SelectiveCandidate,
    backtest_fixed_signals_taker_bidask_non_overlapping,
    backtest_selective_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    stress_fixed_signals,
)
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class FamilyNullGateConfig:
    """Promotion-style gate for a whole searched template family.

    This is intentionally stricter than a single-template backtest because it corrects for
    selecting the best result from a large candidate pool.
    """

    min_oof_trades: int = 100
    min_fold_trades: int = 8
    min_oof_mean_net_bps: float = 0.0
    min_fold_mean_net_bps: float = 0.0
    max_familywise_p_mean: float = 0.05
    max_familywise_p_total: float = 0.05
    require_stress_gate: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_template_family_null_audit(
    *,
    ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    edge_thresholds: list[float] | None = None,
    signed_columns: list[str] | None = None,
    spread_quantiles: list[float] | None = None,
    vol_modes: list[str] | None = None,
    template_source: str = "first_fold",
    min_source_trades: int = 4,
    top_k_templates: int = 80,
    shift_runs: int = 80,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    gate_config: FamilyNullGateConfig | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Audit whether the best long-window template survives family-wise null correction.

    V08/V09 created many selective templates and then studied the good-looking ones.  This audit
    asks a stricter question: after preserving each template's signal frequency and clustering but
    circularly shifting those signals across the price path, how often does *some* template in the
    family look at least as good as the actual best template?
    """
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    edge_thresholds = edge_thresholds or [0.1, 0.2, 0.3, 0.5, 0.7]
    spread_quantiles = spread_quantiles or [1.0]
    vol_modes = vol_modes or ["none"]
    stress_cost_bps_values = stress_cost_bps_values or [1.5, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0]
    gate_config = gate_config or FamilyNullGateConfig()

    folds = load_ensemble_fold_predictions(ensemble_dir)
    templates = _build_template_pool(
        folds,
        template_source=template_source,
        edge_thresholds=edge_thresholds,
        signed_columns=signed_columns,
        spread_quantiles=spread_quantiles,
        vol_modes=vol_modes,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        min_source_trades=min_source_trades,
        top_k_templates=top_k_templates,
    )
    if not templates:
        raise ValueError("no templates available for family null audit")

    candidate_rows: list[dict[str, object]] = []
    candidate_ledgers: dict[str, pd.DataFrame] = {}
    candidate_fold_metrics: dict[str, pd.DataFrame] = {}
    for source_rank, candidate in enumerate(templates, start=1):
        sig = candidate_signature(candidate)
        ledgers: list[pd.DataFrame] = []
        fold_rows: list[dict[str, object]] = []
        for fold_num, _calib, validation in folds:
            bt, metrics = backtest_selective_taker_bidask_non_overlapping(
                validation,
                candidate=candidate,
                cost_bps=cost_bps,
                horizon_sec=horizon_sec,
                latency_sec=latency_sec,
            )
            bt.insert(0, "fold", fold_num) if "fold" not in bt.columns else None
            bt["template_signature"] = sig
            bt["candidate_json"] = json.dumps(candidate.to_dict(), sort_keys=True)
            ledgers.append(bt)
            trades = bt.loc[bt["traded"].astype(int) == 1, "net_pnl_bps"] if "traded" in bt.columns else pd.Series(dtype=float)
            boot = block_bootstrap_pnl(trades, iterations=300, block_size=10, seed=91000 + int(fold_num) + source_rank)
            fold_rows.append(
                {
                    "fold": int(fold_num),
                    "trades": float(metrics.get("trades", 0.0)),
                    "hit_rate": float(metrics.get("hit_rate", 0.0)),
                    "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
                    "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
                    "max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
                    "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0.0)),
                    "bootstrap_prob_mean_gt_0": float(boot.get("prob_mean_gt_0", 0.0)),
                }
            )
        oof = pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()
        folds_df = pd.DataFrame(fold_rows)
        aggregate = summarize_fixed_template_candidate(folds_df, oof)
        traded_pnl = pd.to_numeric(oof.loc[oof.get("traded", pd.Series(dtype=int)).astype(int) == 1, "net_pnl_bps"], errors="coerce") if "traded" in oof.columns and "net_pnl_bps" in oof.columns else pd.Series(dtype=float)
        aggregate["oof_std_net_pnl_bps"] = float(traded_pnl.std(ddof=0)) if len(traded_pnl) else 0.0
        aggregate["oof_required_trades_95_one_sided"] = estimate_required_trades_for_positive_ci(float(aggregate.get("oof_mean_net_pnl_bps", 0.0)), float(aggregate.get("oof_std_net_pnl_bps", 0.0)))
        candidate_ledgers[sig] = oof
        candidate_fold_metrics[sig] = folds_df
        candidate_rows.append(
            {
                "source_rank": int(source_rank),
                "template_signature": sig,
                "candidate_json": json.dumps(candidate.to_dict(), sort_keys=True),
                **_candidate_fields(candidate),
                **aggregate,
            }
        )

    actual = rank_fixed_template_leaderboard(pd.DataFrame(candidate_rows))
    actual.to_csv(out / "candidate_family_actual.csv", index=False)
    if actual.empty:
        raise ValueError("candidate family produced no actual results")
    selected = actual.iloc[0].to_dict()
    selected_sig = str(selected["template_signature"])
    selected_oof = candidate_ledgers[selected_sig]
    selected_folds = candidate_fold_metrics[selected_sig]
    selected_oof.to_csv(out / "selected_oracle_oof_backtest.csv", index=False)
    selected_folds.to_csv(out / "selected_oracle_fold_metrics.csv", index=False)
    (out / "selected_oracle_candidate.json").write_text(json.dumps(json.loads(str(selected["candidate_json"])), indent=2), encoding="utf-8")

    source_first = actual.sort_values(["source_rank", "v08_rank_score"], ascending=[True, False]).iloc[0].to_dict()
    source_sig = str(source_first["template_signature"])
    source_oof = candidate_ledgers[source_sig]
    source_folds = candidate_fold_metrics[source_sig]
    source_oof.to_csv(out / "source_rank1_oof_backtest.csv", index=False)
    source_folds.to_csv(out / "source_rank1_fold_metrics.csv", index=False)
    (out / "source_rank1_candidate.json").write_text(json.dumps(json.loads(str(source_first["candidate_json"])), indent=2), encoding="utf-8")

    rank_corr = _fold_rank_correlation(actual, candidate_fold_metrics)
    rank_corr.to_csv(out / "fold_rank_correlation.csv", index=False)

    null = _familywise_shift_null(
        candidate_ledgers,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        shifts=shift_runs,
    )
    null.to_csv(out / "familywise_shift_null.csv", index=False)

    selected_stress = stress_fixed_signals(
        selected_oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    )
    selected_stress.to_csv(out / "selected_oracle_stress.csv", index=False)
    selected_stress_gate = fixed_signal_robust_gate(selected_stress, min_trades=max(1, gate_config.min_fold_trades))

    source_stress = stress_fixed_signals(
        source_oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    )
    source_stress.to_csv(out / "source_rank1_stress.csv", index=False)
    source_stress_gate = fixed_signal_robust_gate(source_stress, min_trades=max(1, gate_config.min_fold_trades))

    family_summary = _summarize_familywise_null(selected, source_first, null)
    selected_gate = _evaluate_family_null_gate(selected, family_summary, selected_stress_gate, gate_config)
    source_gate = _evaluate_family_null_gate(source_first, family_summary, source_stress_gate, gate_config, prefix="source_rank1")

    result = {
        "source_ensemble_dir": str(ensemble_dir),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "template_source": template_source,
        "templates_tested": int(len(templates)),
        "edge_thresholds": [float(x) for x in edge_thresholds],
        "signed_columns": signed_columns,
        "spread_quantiles": [float(x) for x in spread_quantiles],
        "vol_modes": list(vol_modes),
        "min_source_trades": int(min_source_trades),
        "top_k_templates": int(top_k_templates),
        "shift_runs": int(len(null)),
        "gate_config": gate_config.to_dict(),
        "selected_oracle": _compact_candidate_summary(selected),
        "source_rank1": _compact_candidate_summary(source_first),
        "familywise_null": family_summary,
        "selected_oracle_stress_gate": selected_stress_gate,
        "source_rank1_stress_gate": source_stress_gate,
        "selected_oracle_gate": selected_gate,
        "source_rank1_gate": source_gate,
        "rank_correlation": _rank_correlation_summary(rank_corr),
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_family_null_report(out / "REPORT.md", result, actual, rank_corr, null, selected_stress, source_stress)
    return result


def estimate_required_trades_for_positive_ci(mean_bps: float, std_bps: float, *, z: float = 1.645) -> float:
    """Approximate trades needed for a one-sided positive mean CI under IID assumptions.

    The estimate is optimistic for clustered market data; block bootstrap remains the preferred gate.
    """
    mean = float(mean_bps)
    std = float(std_bps)
    if mean <= 0:
        return math.inf
    if std <= 0:
        return 1.0
    return float((z * std / mean) ** 2)


def _familywise_shift_null(
    candidate_ledgers: dict[str, pd.DataFrame],
    *,
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
    shifts: int,
) -> pd.DataFrame:
    if not candidate_ledgers:
        return pd.DataFrame()
    first = next(iter(candidate_ledgers.values()))
    shift_values = _shift_values(first, horizon_sec=horizon_sec, shifts=shifts)
    prepared = {sig: _prepare_fast_backtest_arrays(frame, horizon_sec=horizon_sec, latency_sec=latency_sec) for sig, frame in candidate_ledgers.items()}
    rows: list[dict[str, object]] = []
    for shift in shift_values:
        best_total: dict[str, object] | None = None
        best_mean: dict[str, object] | None = None
        for sig, arrays in prepared.items():
            raw = arrays["raw"]
            if len(raw) == 0:
                continue
            metrics = _fast_metrics_from_arrays(arrays, np.roll(raw, int(shift)), cost_bps=cost_bps)
            metrics["template_signature"] = sig
            if best_total is None or (float(metrics["total_net_pnl_bps"]), float(metrics["mean_net_pnl_bps"])) > (float(best_total["total_net_pnl_bps"]), float(best_total["mean_net_pnl_bps"])):
                best_total = metrics
            if best_mean is None or (float(metrics["mean_net_pnl_bps"]), float(metrics["total_net_pnl_bps"])) > (float(best_mean["mean_net_pnl_bps"]), float(best_mean["total_net_pnl_bps"])):
                best_mean = metrics
        if best_total is None or best_mean is None:
            continue
        rows.append(
            {
                "shift_rows": int(shift),
                "max_total_net_pnl_bps": float(best_total["total_net_pnl_bps"]),
                "max_total_mean_net_pnl_bps": float(best_total["mean_net_pnl_bps"]),
                "max_total_trades": float(best_total["trades"]),
                "max_total_template_signature": str(best_total["template_signature"]),
                "max_mean_net_pnl_bps": float(best_mean["mean_net_pnl_bps"]),
                "max_mean_total_net_pnl_bps": float(best_mean["total_net_pnl_bps"]),
                "max_mean_trades": float(best_mean["trades"]),
                "max_mean_template_signature": str(best_mean["template_signature"]),
            }
        )
    return pd.DataFrame(rows)


def _prepare_fast_backtest_arrays(frame: pd.DataFrame, *, horizon_sec: float, latency_sec: float) -> dict[str, np.ndarray]:
    raw_col = "raw_selective_signal" if "raw_selective_signal" in frame.columns else "signal"
    ts_ns = timestamps_to_ns(frame["timestamp"])
    bid = pd.to_numeric(frame["best_bid"], errors="coerce").to_numpy(dtype=float)
    ask = pd.to_numeric(frame["best_ask"], errors="coerce").to_numpy(dtype=float)
    raw = pd.to_numeric(frame[raw_col], errors="coerce").fillna(0).astype(int).clip(-1, 1).to_numpy(dtype=int)
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    latency_ns = int(float(latency_sec) * 1_000_000_000)
    entry_target = ts_ns + latency_ns
    exit_target = ts_ns + horizon_ns
    entry_idx = np.searchsorted(ts_ns, entry_target, side="left")
    exit_idx = np.searchsorted(ts_ns, exit_target, side="left")
    valid = (entry_idx < len(ts_ns)) & (exit_idx < len(ts_ns)) & (entry_target < exit_target)
    return {"ts_ns": ts_ns, "bid": bid, "ask": ask, "raw": raw, "entry_idx": entry_idx, "exit_idx": exit_idx, "valid": valid, "horizon_ns": np.array([horizon_ns], dtype=np.int64)}


def _fast_metrics_from_arrays(arrays: dict[str, np.ndarray], signal: np.ndarray, *, cost_bps: float) -> dict[str, float]:
    ts_ns = arrays["ts_ns"]
    bid = arrays["bid"]
    ask = arrays["ask"]
    entry_idx = arrays["entry_idx"]
    exit_idx = arrays["exit_idx"]
    valid = arrays["valid"]
    horizon_ns = int(arrays["horizon_ns"][0])
    next_allowed = -np.inf
    pnl_values: list[float] = []
    for i, (sig, ts) in enumerate(zip(signal.astype(int), ts_ns)):
        if sig == 0 or ts < next_allowed or not bool(valid[i]):
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if sig > 0:
            ep = float(ask[ei])
            xp = float(bid[xi])
            gross = (xp - ep) / ep * 10000.0
        else:
            ep = float(bid[ei])
            xp = float(ask[xi])
            gross = (ep - xp) / ep * 10000.0
        if not (np.isfinite(ep) and np.isfinite(xp) and ep > 0 and xp > 0):
            continue
        pnl_values.append(float(gross - cost_bps))
        next_allowed = int(ts) + horizon_ns
    if not pnl_values:
        return {"trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0, "max_drawdown_bps": 0.0}
    pnl = np.asarray(pnl_values, dtype=float)
    equity = np.cumsum(pnl)
    peak = np.maximum.accumulate(equity)
    return {
        "trades": float(len(pnl)),
        "hit_rate": float(np.mean(pnl > 0)),
        "mean_net_pnl_bps": float(np.mean(pnl)),
        "total_net_pnl_bps": float(np.sum(pnl)),
        "max_drawdown_bps": float(np.min(equity - peak)),
    }

def _shift_values(frame: pd.DataFrame, *, horizon_sec: float, shifts: int) -> list[int]:
    if frame.empty:
        return []
    n = len(frame)
    if n < 10:
        return list(range(1, n))
    ts = timestamps_to_ns(frame["timestamp"])
    diffs = np.diff(ts)
    diffs = diffs[diffs > 0]
    step = float(np.median(diffs) / 1_000_000_000) if len(diffs) else 1.0
    min_shift = max(1, int(round(float(horizon_sec) / max(step, 1e-9))))
    min_shift = min(min_shift, n - 1)
    max_shift = max(min_shift, n - min_shift - 1)
    if max_shift <= min_shift:
        return sorted(set(int(x) for x in range(1, min(n, shifts + 1))))
    return sorted(set(int(x) for x in np.linspace(min_shift, max_shift, num=min(int(shifts), max_shift - min_shift + 1), dtype=int) if 0 < int(x) < n))


def _fold_rank_correlation(actual: pd.DataFrame, fold_metrics: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    sig_order = list(actual["template_signature"].astype(str)) if "template_signature" in actual.columns else list(fold_metrics.keys())
    fold_ids = sorted({int(f) for df in fold_metrics.values() for f in df.get("fold", pd.Series(dtype=int)).astype(int).tolist()})
    for a_idx, fold_a in enumerate(fold_ids):
        for fold_b in fold_ids[a_idx + 1 :]:
            a_vals = []
            b_vals = []
            for sig in sig_order:
                df = fold_metrics.get(sig, pd.DataFrame())
                if df.empty:
                    continue
                row_a = df[df["fold"].astype(int) == int(fold_a)]
                row_b = df[df["fold"].astype(int) == int(fold_b)]
                if row_a.empty or row_b.empty:
                    continue
                a_vals.append(float(row_a.iloc[0].get("mean_net_pnl_bps", 0.0)))
                b_vals.append(float(row_b.iloc[0].get("mean_net_pnl_bps", 0.0)))
            if len(a_vals) < 3:
                corr = math.nan
            else:
                corr = float(pd.Series(a_vals).corr(pd.Series(b_vals), method="spearman"))
            rows.append({"fold_a": int(fold_a), "fold_b": int(fold_b), "templates": int(len(a_vals)), "spearman_mean_pnl": corr})
    return pd.DataFrame(rows)


def _summarize_familywise_null(selected: dict[str, object], source_first: dict[str, object], null: pd.DataFrame) -> dict[str, object]:
    if null.empty:
        return {"null_runs": 0}
    selected_total = float(selected.get("oof_total_net_pnl_bps", 0.0))
    selected_mean = float(selected.get("oof_mean_net_pnl_bps", 0.0))
    source_total = float(source_first.get("oof_total_net_pnl_bps", 0.0))
    source_mean = float(source_first.get("oof_mean_net_pnl_bps", 0.0))
    max_total = pd.to_numeric(null["max_total_net_pnl_bps"], errors="coerce")
    max_mean = pd.to_numeric(null["max_mean_net_pnl_bps"], errors="coerce")
    return {
        "null_runs": int(len(null)),
        "selected_actual_total_net_pnl_bps": selected_total,
        "selected_actual_mean_net_pnl_bps": selected_mean,
        "source_rank1_actual_total_net_pnl_bps": source_total,
        "source_rank1_actual_mean_net_pnl_bps": source_mean,
        "family_null_max_total_p50_bps": float(max_total.quantile(0.50)),
        "family_null_max_total_p90_bps": float(max_total.quantile(0.90)),
        "family_null_max_total_p95_bps": float(max_total.quantile(0.95)),
        "family_null_max_total_max_bps": float(max_total.max()),
        "family_null_max_mean_p50_bps": float(max_mean.quantile(0.50)),
        "family_null_max_mean_p90_bps": float(max_mean.quantile(0.90)),
        "family_null_max_mean_p95_bps": float(max_mean.quantile(0.95)),
        "family_null_max_mean_max_bps": float(max_mean.max()),
        "p_family_null_max_total_ge_selected": float((max_total >= selected_total).mean()),
        "p_family_null_max_mean_ge_selected": float((max_mean >= selected_mean).mean()),
        "p_family_null_max_total_ge_source_rank1": float((max_total >= source_total).mean()),
        "p_family_null_max_mean_ge_source_rank1": float((max_mean >= source_mean).mean()),
    }


def _evaluate_family_null_gate(
    row: dict[str, object],
    family_summary: dict[str, object],
    stress_gate: dict[str, object],
    gate_config: FamilyNullGateConfig,
    *,
    prefix: str = "selected",
) -> dict[str, object]:
    if prefix == "source_rank1":
        p_total_key = "p_family_null_max_total_ge_source_rank1"
        p_mean_key = "p_family_null_max_mean_ge_source_rank1"
    else:
        p_total_key = "p_family_null_max_total_ge_selected"
        p_mean_key = "p_family_null_max_mean_ge_selected"
    checks = {
        "enough_oof_trades": float(row.get("oof_trades", 0.0)) >= float(gate_config.min_oof_trades),
        "enough_min_fold_trades": float(row.get("fold_trades_min", 0.0)) >= float(gate_config.min_fold_trades),
        "positive_oof_mean": float(row.get("oof_mean_net_pnl_bps", -999.0)) > float(gate_config.min_oof_mean_net_bps),
        "positive_fold_mean_min": float(row.get("fold_mean_net_pnl_bps_min", -999.0)) > float(gate_config.min_fold_mean_net_bps),
        "familywise_mean_ok": float(family_summary.get(p_mean_key, 1.0)) <= float(gate_config.max_familywise_p_mean),
        "familywise_total_ok": float(family_summary.get(p_total_key, 1.0)) <= float(gate_config.max_familywise_p_total),
        "stress_gate_ok": bool(stress_gate.get("passed")) if gate_config.require_stress_gate else True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {"passed": not failed, "failed_checks": failed, "checks": checks}


def _compact_candidate_summary(row: dict[str, object]) -> dict[str, object]:
    out = {k: row.get(k) for k in [
        "source_rank",
        "template_signature",
        "edge_threshold",
        "direction_mode",
        "signed_col",
        "signed_mode",
        "signed_abs_threshold",
        "oof_trades",
        "oof_hit_rate",
        "oof_mean_net_pnl_bps",
        "oof_total_net_pnl_bps",
        "fold_trades_min",
        "fold_mean_net_pnl_bps_min",
        "fold_bootstrap_mean_p05_bps_min",
    ] if k in row}
    std = float(row.get("oof_std_net_pnl_bps", 0.0)) if "oof_std_net_pnl_bps" in row else math.nan
    mean = float(row.get("oof_mean_net_pnl_bps", 0.0)) if "oof_mean_net_pnl_bps" in row else 0.0
    if math.isnan(std):
        out["approx_required_trades_95_one_sided"] = None
    else:
        required = estimate_required_trades_for_positive_ci(mean, std)
        out["approx_required_trades_95_one_sided"] = None if math.isinf(required) else required
    return out


def _candidate_fields(candidate: SelectiveCandidate) -> dict[str, object]:
    return {
        "edge_threshold": float(candidate.edge_threshold),
        "direction_mode": candidate.direction_mode,
        "signed_col": candidate.signed_col,
        "signed_mode": candidate.signed_mode,
        "signed_abs_threshold": float(candidate.signed_abs_threshold or 0.0),
        "spread_max_bps": candidate.spread_max_bps,
        "vol_col": candidate.vol_col,
        "vol_mode": candidate.vol_mode,
        "vol_min": candidate.vol_min,
        "vol_max": candidate.vol_max,
    }


def _rank_correlation_summary(rank_corr: pd.DataFrame) -> dict[str, object]:
    if rank_corr.empty:
        return {"pairs": 0}
    vals = pd.to_numeric(rank_corr["spearman_mean_pnl"], errors="coerce").dropna()
    return {
        "pairs": int(len(rank_corr)),
        "valid_pairs": int(len(vals)),
        "spearman_mean": float(vals.mean()) if len(vals) else math.nan,
        "spearman_min": float(vals.min()) if len(vals) else math.nan,
        "spearman_max": float(vals.max()) if len(vals) else math.nan,
    }


def _write_family_null_report(
    path: str | Path,
    result: dict[str, object],
    actual: pd.DataFrame,
    rank_corr: pd.DataFrame,
    null: pd.DataFrame,
    selected_stress: pd.DataFrame,
    source_stress: pd.DataFrame,
) -> None:
    lines = [
        "# Research V10 Template-family Null Audit",
        "",
        "This audit corrects for searching over a family of long-window selective templates.",
        "It compares the best actual template against a family-wise shifted-signal null, where every null run is allowed to pick the best-looking shifted template from the same pool.",
        "",
        "## Settings",
        "",
        "```json",
        json.dumps({k: result.get(k) for k in ["source_ensemble_dir", "horizon_sec", "cost_bps", "latency_sec", "template_source", "templates_tested", "shift_runs", "edge_thresholds", "signed_columns", "spread_quantiles", "vol_modes"]}, indent=2),
        "```",
        "",
        "## Selected oracle candidate",
        "",
        "```json",
        json.dumps(result.get("selected_oracle", {}), indent=2),
        "```",
        "",
        "## Source-rank-1 candidate",
        "",
        "```json",
        json.dumps(result.get("source_rank1", {}), indent=2),
        "```",
        "",
        "## Family-wise null summary",
        "",
        "```json",
        json.dumps(result.get("familywise_null", {}), indent=2),
        "```",
        "",
        "## Gates",
        "",
        "```json",
        json.dumps({"selected_oracle_gate": result.get("selected_oracle_gate"), "source_rank1_gate": result.get("source_rank1_gate")}, indent=2),
        "```",
        "",
        "## Fold rank correlation",
        "",
    ]
    lines.append(rank_corr.to_markdown(index=False) if not rank_corr.empty else "No fold rank correlation rows.")
    lines.extend(["", "## Top actual candidates", ""])
    cols = [
        "source_rank",
        "edge_threshold",
        "direction_mode",
        "signed_col",
        "signed_mode",
        "signed_abs_threshold",
        "oof_trades",
        "oof_hit_rate",
        "oof_mean_net_pnl_bps",
        "oof_total_net_pnl_bps",
        "fold_trades_min",
        "fold_mean_net_pnl_bps_min",
        "v08_rank_score",
    ]
    lines.append(actual[[c for c in cols if c in actual.columns]].head(12).to_markdown(index=False) if not actual.empty else "No candidates.")
    lines.extend(["", "## Null distribution head", ""])
    lines.append(null.head(12).to_markdown(index=False) if not null.empty else "No null rows.")
    lines.extend(["", "## Selected oracle stress", ""])
    stress_cols = ["cost_bps", "latency_sec", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
    lines.append(selected_stress[[c for c in stress_cols if c in selected_stress.columns]].to_markdown(index=False) if not selected_stress.empty else "No selected stress rows.")
    lines.extend(["", "## Source-rank-1 stress", ""])
    lines.append(source_stress[[c for c in stress_cols if c in source_stress.columns]].to_markdown(index=False) if not source_stress.empty else "No source stress rows.")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "A robust long-window edge should remain positive after costs, survive stress settings, show positive fold-level behavior, and beat the family-wise shifted-signal null.  A high family-wise p-value means that template search alone can often manufacture an equally good-looking result on this sample.",
    ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")
