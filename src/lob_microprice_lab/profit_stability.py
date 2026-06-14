from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .data_schema import timestamps_to_ns
from .kline_blend import blend_prediction_frames, run_kline_blend_ensemble
from .selective import (
    backtest_fixed_signals_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    stress_fixed_signals,
)
from .slot_veto import SlotVetoSpec, _build_slot_veto_fold, _fold_num, _shift_values
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class KlineStabilityGateConfig:
    """Strict single-sample research gate for a K-line overlay.

    This gate is deliberately stronger than the v13 single-day gate. It still does not prove live
    or multi-day stability; it only says that the candidate survived the available blocked OOF
    sample, stress repricing, and alpha/filter family-wise shifted-signal null controls.
    """

    min_oof_trades: int = 20
    min_folds_with_trades: int = 5
    min_fold_mean_net_bps: float = 0.0
    min_fold_total_net_bps: float = 0.0
    min_bootstrap_mean_p05_bps: float = 0.0
    min_equal_trade_blocks: int = 6
    min_equal_trade_block_total_bps: float = 0.0
    min_leave_one_fold_out_total_bps: float = 0.0
    max_selected_shift_p_total: float = 0.05
    max_selected_shift_p_mean: float = 0.05
    max_alpha_family_p_total: float = 0.05
    max_alpha_family_p_mean: float = 0.05
    max_ofi_family_p_total: float = 0.05
    max_ofi_family_p_mean: float = 0.05
    max_union_family_p_total: float = 0.05
    max_union_family_p_mean: float = 0.05
    require_stress_gate: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_kline_stability_lock_audit(
    *,
    base_ensemble_dir: str | Path,
    kline_ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    selected_alpha: float = 0.125,
    alpha_grid: Iterable[float] = (0.0, 0.025, 0.05, 0.075, 0.10, 0.125, 0.15),
    selected_spec: SlotVetoSpec | None = None,
    family_filter_cols: Iterable[str] = ("ofi_sum_l3_norm", "ofi_sum_l5_norm", "ofi_sum_l10_norm"),
    family_quantiles: Iterable[float] = (0.5, 0.6, 0.7, 0.8, 0.9),
    stress_cost_bps_values: Iterable[float] = (1.5, 3.0, 5.0),
    stress_latency_sec_values: Iterable[float] = (0.0, 0.5, 1.0, 2.0),
    shift_null_runs: int = 80,
    gate_config: KlineStabilityGateConfig | None = None,
    write_selected_blend_dir: str | Path | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Audit a fixed K-line alpha overlay with stability and family-wise null controls.

    The selected policy is:

    1. Blend v12 probabilities with a K-line-trained probability model using `selected_alpha`.
    2. Schedule non-overlapping slots from the blended probability edge.
    3. Apply the v12-style slot-preserving OFI veto.

    The alpha family test holds the OFI veto fixed and shifts all alpha candidates. The OFI family
    test holds the selected alpha fixed and shifts all OFI filter candidates. The union family is the
    combined family used as an extra multiple-comparison guardrail.
    """

    base = Path(base_ensemble_dir)
    kline = Path(kline_ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    selected_spec = selected_spec or SlotVetoSpec(edge_threshold=0.1, filter_col="ofi_sum_l5_norm", filter_operator="<=", filter_quantile=0.9)
    gate_config = gate_config or KlineStabilityGateConfig()
    alpha_grid = _dedupe_floats(alpha_grid)
    family_filter_cols = [str(c) for c in family_filter_cols]
    family_quantiles = _dedupe_floats(family_quantiles)
    stress_cost_bps_values = _dedupe_floats(stress_cost_bps_values)
    stress_latency_sec_values = _dedupe_floats(stress_latency_sec_values)

    if selected_alpha not in alpha_grid:
        alpha_grid = sorted(alpha_grid + [float(selected_alpha)])

    if write_selected_blend_dir is not None:
        run_kline_blend_ensemble(
            base_ensemble_dir=base,
            kline_ensemble_dir=kline,
            out_dir=write_selected_blend_dir,
            kline_alpha=float(selected_alpha),
            keep_kline_feature_columns=False,
            clean=clean,
        )

    specs = _audit_specs(
        selected_alpha=float(selected_alpha),
        alpha_grid=alpha_grid,
        selected_spec=selected_spec,
        family_filter_cols=family_filter_cols,
        family_quantiles=family_quantiles,
    )
    blend_cache = _build_blend_cache(base=base, kline=kline, alphas=sorted({a for a, _ in specs}))

    candidates: list[dict[str, object]] = []
    selected_candidate: dict[str, object] | None = None
    for alpha, spec in specs:
        cand = _candidate_oof(
            alpha=alpha,
            spec=spec,
            blend_cache=blend_cache,
            horizon_sec=horizon_sec,
            cost_bps=cost_bps,
            latency_sec=latency_sec,
        )
        candidates.append(cand)
        if _same_candidate(cand, float(selected_alpha), selected_spec):
            selected_candidate = cand

    if selected_candidate is None:
        raise RuntimeError("selected K-line stability candidate was not generated")

    selected_oof = selected_candidate["oof"]  # type: ignore[assignment]
    assert isinstance(selected_oof, pd.DataFrame)
    selected_raw = selected_candidate["raw"]  # type: ignore[assignment]
    selected_bt, selected_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        selected_oof.assign(signal=selected_raw),
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    selected_bt.to_csv(out / "slot_veto_oof_backtest.csv", index=False)

    for fold, frame in selected_candidate["fold_frames"].items():  # type: ignore[union-attr]
        frame.to_csv(out / f"fold_{int(fold):02d}_slot_veto_backtest.csv", index=False)
    folds = pd.DataFrame(selected_candidate["fold_rows"]).sort_values("fold")  # type: ignore[arg-type]
    folds.to_csv(out / "fold_metrics.csv", index=False)

    stress = stress_fixed_signals(
        selected_oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    )
    stress.to_csv(out / "slot_veto_stress.csv", index=False)
    stress_gate = fixed_signal_robust_gate(stress, min_trades=max(1, int(gate_config.min_oof_trades)))

    trades = selected_bt[selected_bt["traded"].astype(int) == 1].copy()
    bootstrap = block_bootstrap_pnl(trades["net_pnl_bps"], iterations=2000, block_size=5, seed=24014)
    stability = summarize_trade_stability(
        selected_bt,
        fold_col="fold",
        equal_trade_blocks=max(2, int(gate_config.min_equal_trade_blocks)),
    )

    candidates_df = _candidate_metrics_frame(candidates)
    candidates_df.to_csv(out / "alpha_ofi_family_candidates.csv", index=False)

    family_null, family_summary, selected_shift = _family_shift_null(
        selected_candidate=selected_candidate,
        candidates=candidates,
        horizon_sec=horizon_sec,
        shift_null_runs=shift_null_runs,
        min_oof_trades=gate_config.min_oof_trades,
        cost_bps=cost_bps,
    )
    family_null.to_csv(out / "alpha_ofi_family_shift_null.csv", index=False)
    selected_shift.to_csv(out / "selected_shift_null.csv", index=False)

    aggregate = _aggregate_stability_gate(
        selected_metrics=selected_metrics,
        folds=folds,
        bootstrap=bootstrap,
        stability=stability,
        stress_gate=stress_gate,
        family_summary=family_summary,
        gate_config=gate_config,
    )

    result: dict[str, object] = {
        "base_ensemble_dir": str(base),
        "kline_ensemble_dir": str(kline),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "selected_alpha": float(selected_alpha),
        "selected_spec": selected_spec.to_dict(),
        "alpha_grid": [float(x) for x in alpha_grid],
        "family_filter_cols": family_filter_cols,
        "family_quantiles": [float(x) for x in family_quantiles],
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "shift_null_runs": int(shift_null_runs),
        "gate_config": gate_config.to_dict(),
        "selected_metrics": {k: _json_float(v) for k, v in selected_metrics.items()},
        "bootstrap": bootstrap,
        "stability": stability,
        "stress_gate": stress_gate,
        "family_null": family_summary,
        "aggregate": aggregate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_stability_report(out / "REPORT.md", result, folds, candidates_df)
    return result


def summarize_trade_stability(
    backtest_frame: pd.DataFrame,
    *,
    fold_col: str = "fold",
    equal_trade_blocks: int = 6,
) -> dict[str, object]:
    trades = backtest_frame[backtest_frame["traded"].astype(int) == 1].copy().reset_index(drop=True)
    pnls = pd.to_numeric(trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    blocks: list[dict[str, object]] = []
    if len(pnls):
        for idx, rows in enumerate(np.array_split(np.arange(len(pnls)), max(1, int(equal_trade_blocks))), start=1):
            vals = pnls[rows] if len(rows) else np.array([], dtype=float)
            blocks.append(
                {
                    "block": int(idx),
                    "trades": int(len(vals)),
                    "mean_net_pnl_bps": float(vals.mean()) if len(vals) else 0.0,
                    "total_net_pnl_bps": float(vals.sum()) if len(vals) else 0.0,
                }
            )
    block_df = pd.DataFrame(blocks)

    rolling: dict[str, float] = {}
    for window in (3, 5, 10):
        if len(pnls) >= window:
            values = pd.Series(pnls).rolling(window).sum().dropna()
            rolling[f"rolling_{window}_trade_min_total_bps"] = float(values.min()) if len(values) else 0.0
        else:
            rolling[f"rolling_{window}_trade_min_total_bps"] = 0.0

    loo_rows: list[dict[str, object]] = []
    if fold_col in trades.columns:
        for fold in sorted(pd.unique(trades[fold_col])):
            rest = trades[trades[fold_col] != fold]
            vals = pd.to_numeric(rest["net_pnl_bps"], errors="coerce").fillna(0.0)
            loo_rows.append(
                {
                    "removed_fold": int(fold),
                    "remaining_trades": int(len(vals)),
                    "remaining_total_net_pnl_bps": float(vals.sum()) if len(vals) else 0.0,
                    "remaining_mean_net_pnl_bps": float(vals.mean()) if len(vals) else 0.0,
                }
            )
    loo_df = pd.DataFrame(loo_rows)

    return {
        "equal_trade_blocks": blocks,
        "equal_trade_block_count": int(len(blocks)),
        "equal_trade_block_min_total_bps": float(block_df["total_net_pnl_bps"].min()) if not block_df.empty else 0.0,
        "equal_trade_block_min_mean_bps": float(block_df["mean_net_pnl_bps"].min()) if not block_df.empty else 0.0,
        "positive_equal_trade_blocks": int((block_df["total_net_pnl_bps"] > 0).sum()) if not block_df.empty else 0,
        "rolling_windows": rolling,
        "leave_one_fold_out": loo_rows,
        "leave_one_fold_out_min_total_bps": float(loo_df["remaining_total_net_pnl_bps"].min()) if not loo_df.empty else 0.0,
        "leave_one_fold_out_min_mean_bps": float(loo_df["remaining_mean_net_pnl_bps"].min()) if not loo_df.empty else 0.0,
    }


def _audit_specs(
    *,
    selected_alpha: float,
    alpha_grid: list[float],
    selected_spec: SlotVetoSpec,
    family_filter_cols: list[str],
    family_quantiles: list[float],
) -> list[tuple[float, SlotVetoSpec]]:
    specs: list[tuple[float, SlotVetoSpec]] = []
    seen: set[tuple[float, str, str, float, float]] = set()

    def add(alpha: float, spec: SlotVetoSpec) -> None:
        key = (round(float(alpha), 12), spec.filter_col, spec.filter_operator, round(float(spec.filter_quantile), 12), round(float(spec.edge_threshold), 12))
        if key not in seen:
            specs.append((float(alpha), spec))
            seen.add(key)

    for alpha in alpha_grid:
        add(float(alpha), selected_spec)
    for col in family_filter_cols:
        for q in family_quantiles:
            add(
                float(selected_alpha),
                SlotVetoSpec(
                    edge_threshold=selected_spec.edge_threshold,
                    filter_col=col,
                    filter_operator=selected_spec.filter_operator,
                    filter_quantile=float(q),
                ),
            )
    return specs


def _build_blend_cache(*, base: Path, kline: Path, alphas: Iterable[float]) -> dict[tuple[float, int, str], pd.DataFrame]:
    cache: dict[tuple[float, int, str], pd.DataFrame] = {}
    folds = sorted([p for p in base.glob("fold_*") if p.is_dir()])
    if not folds:
        raise ValueError(f"no base fold directories found under {base}")
    for alpha in alphas:
        for base_fold in folds:
            fold = _fold_num(base_fold)
            kline_fold = kline / f"fold_{fold:02d}"
            if not kline_fold.exists():
                raise FileNotFoundError(f"missing K-line fold directory: {kline_fold}")
            for split in ("calibration", "validation"):
                name = f"{split}_predictions.csv"
                cache[(float(alpha), fold, split)] = blend_prediction_frames(
                    pd.read_csv(base_fold / name),
                    pd.read_csv(kline_fold / name),
                    kline_alpha=float(alpha),
                )
    return cache


def _candidate_oof(
    *,
    alpha: float,
    spec: SlotVetoSpec,
    blend_cache: dict[tuple[float, int, str], pd.DataFrame],
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
) -> dict[str, object]:
    folds = sorted({k[1] for k in blend_cache.keys() if abs(k[0] - float(alpha)) < 1e-12})
    frames: list[pd.DataFrame] = []
    fold_rows: list[dict[str, object]] = []
    fold_frames: dict[int, pd.DataFrame] = {}
    for fold in folds:
        frame, metrics, threshold = _build_slot_veto_fold(
            calibration=blend_cache[(float(alpha), fold, "calibration")],
            validation=blend_cache[(float(alpha), fold, "validation")],
            spec=spec,
            fold=fold,
            horizon_sec=horizon_sec,
            cost_bps=cost_bps,
            latency_sec=latency_sec,
        )
        frames.append(frame)
        fold_frames[int(fold)] = frame
        fold_rows.append(
            {
                "fold": int(fold),
                "kline_alpha": float(alpha),
                "filter_col": spec.filter_col,
                "filter_quantile": float(spec.filter_quantile),
                "filter_threshold": float(threshold),
                "events": float(metrics.get("events", 0.0)),
                "trades": int(metrics.get("trades", 0.0)),
                "hit_rate": float(metrics.get("hit_rate", 0.0)),
                "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
                "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
                "max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
            }
        )
    oof = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    raw = oof["signal"].fillna(0).astype(int).clip(-1, 1).to_numpy(dtype=int)
    arrays = _prepare_execution_arrays(oof, horizon_sec=horizon_sec, latency_sec=latency_sec)
    metrics, pnls = _fast_signal_metrics(raw, arrays, cost_bps=cost_bps)
    fold_df = pd.DataFrame(fold_rows)
    metrics.update(
        {
            "periods_with_trades": int((fold_df["trades"].astype(float) > 0).sum()) if not fold_df.empty else 0,
            "period_mean_net_pnl_bps_min": float(fold_df["mean_net_pnl_bps"].min()) if not fold_df.empty else 0.0,
            "period_total_net_pnl_bps_min": float(fold_df["total_net_pnl_bps"].min()) if not fold_df.empty else 0.0,
        }
    )
    return {
        "alpha": float(alpha),
        "spec": spec,
        "oof": oof,
        "raw": raw,
        "arrays": arrays,
        "pnls": pnls,
        "metrics": metrics,
        "fold_rows": fold_rows,
        "fold_frames": fold_frames,
    }


def _candidate_metrics_frame(candidates: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for cand in candidates:
        spec = cand["spec"]
        assert isinstance(spec, SlotVetoSpec)
        metrics = cand["metrics"]
        assert isinstance(metrics, dict)
        rows.append(
            {
                "kline_alpha": float(cand["alpha"]),
                "edge_threshold": float(spec.edge_threshold),
                "filter_col": spec.filter_col,
                "filter_operator": spec.filter_operator,
                "filter_quantile": float(spec.filter_quantile),
                **{k: _json_float(v) for k, v in metrics.items()},
            }
        )
    return pd.DataFrame(rows).sort_values(["total_net_pnl_bps", "mean_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)


def _family_shift_null(
    *,
    selected_candidate: dict[str, object],
    candidates: list[dict[str, object]],
    horizon_sec: float,
    shift_null_runs: int,
    min_oof_trades: int,
    cost_bps: float,
) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    selected_alpha = float(selected_candidate["alpha"])
    selected_spec = selected_candidate["spec"]
    assert isinstance(selected_spec, SlotVetoSpec)
    selected_raw = selected_candidate["raw"]
    assert isinstance(selected_raw, np.ndarray)
    selected_metrics = selected_candidate["metrics"]
    assert isinstance(selected_metrics, dict)
    selected_total = float(selected_metrics.get("total_net_pnl_bps", 0.0))
    selected_mean = float(selected_metrics.get("mean_net_pnl_bps", 0.0))

    subsets = {
        "selected_only": [selected_candidate],
        "alpha_fixed_filter": [
            c
            for c in candidates
            if _same_filter(c["spec"], selected_spec)  # type: ignore[arg-type]
        ],
        "ofi_selected_alpha": [
            c
            for c in candidates
            if abs(float(c["alpha"]) - selected_alpha) < 1e-12
        ],
        "union_alpha_or_ofi": candidates,
    }

    shift_values = _shift_values(
        n=len(selected_raw),
        shifts=int(shift_null_runs),
        min_shift=max(1, int(round(float(horizon_sec) / 0.5))),
    )
    null_rows: list[dict[str, object]] = []
    selected_rows: list[dict[str, object]] = []
    for shift in shift_values:
        row: dict[str, object] = {"shift_rows": int(shift)}
        for name, subset in subsets.items():
            max_total = -1e18
            max_mean = -1e18
            max_total_constrained = -1e18
            max_mean_constrained = -1e18
            best_spec = ""
            for cand in subset:
                raw = cand["raw"]
                arrays = cand["arrays"]
                assert isinstance(raw, np.ndarray)
                shifted = np.roll(raw, int(shift) % len(raw))
                metrics, _ = _fast_signal_metrics(shifted, arrays, cost_bps=cost_bps)
                total = float(metrics.get("total_net_pnl_bps", 0.0))
                mean = float(metrics.get("mean_net_pnl_bps", 0.0))
                trades = float(metrics.get("trades", 0.0))
                if total > max_total:
                    max_total = total
                    spec = cand["spec"]
                    assert isinstance(spec, SlotVetoSpec)
                    best_spec = json.dumps({"alpha": float(cand["alpha"]), **spec.to_dict()}, sort_keys=True)
                max_mean = max(max_mean, mean)
                if trades >= float(min_oof_trades):
                    max_total_constrained = max(max_total_constrained, total)
                    max_mean_constrained = max(max_mean_constrained, mean)
                if name == "selected_only":
                    selected_rows.append({"shift_rows": int(shift), **metrics})
            row[f"{name}_max_total_net_pnl_bps"] = float(max_total)
            row[f"{name}_max_mean_net_pnl_bps"] = float(max_mean)
            row[f"{name}_max_total_net_pnl_bps_constrained"] = float(max_total_constrained)
            row[f"{name}_max_mean_net_pnl_bps_constrained"] = float(max_mean_constrained)
            row[f"{name}_best_total_spec_json"] = best_spec
        null_rows.append(row)

    null_df = pd.DataFrame(null_rows)
    summary: dict[str, object] = {
        "selected_total_net_pnl_bps": selected_total,
        "selected_mean_net_pnl_bps": selected_mean,
        "shift_null_runs": int(len(null_df)),
    }
    for name, subset in subsets.items():
        total = pd.to_numeric(null_df[f"{name}_max_total_net_pnl_bps"], errors="coerce")
        mean = pd.to_numeric(null_df[f"{name}_max_mean_net_pnl_bps"], errors="coerce")
        total_c = pd.to_numeric(null_df[f"{name}_max_total_net_pnl_bps_constrained"], errors="coerce")
        mean_c = pd.to_numeric(null_df[f"{name}_max_mean_net_pnl_bps_constrained"], errors="coerce")
        summary[name] = {
            "candidate_count": int(len(subset)),
            "p_total_ge_selected": float((total >= selected_total).mean()) if len(total) else 1.0,
            "p_mean_ge_selected": float((mean >= selected_mean).mean()) if len(mean) else 1.0,
            "p_total_ge_selected_constrained": float((total_c >= selected_total).mean()) if len(total_c) else 1.0,
            "p_mean_ge_selected_constrained": float((mean_c >= selected_mean).mean()) if len(mean_c) else 1.0,
            "null_total_p95_bps": float(total.quantile(0.95)) if len(total) else 0.0,
            "null_mean_p95_bps": float(mean.quantile(0.95)) if len(mean) else 0.0,
            "null_total_max_bps": float(total.max()) if len(total) else 0.0,
            "null_mean_max_bps": float(mean.max()) if len(mean) else 0.0,
        }
    return null_df, summary, pd.DataFrame(selected_rows)


def _aggregate_stability_gate(
    *,
    selected_metrics: dict[str, float],
    folds: pd.DataFrame,
    bootstrap: dict[str, float],
    stability: dict[str, object],
    stress_gate: dict[str, object],
    family_summary: dict[str, object],
    gate_config: KlineStabilityGateConfig,
) -> dict[str, object]:
    trades = int(float(selected_metrics.get("trades", 0.0)))
    fold_min_mean = float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0
    fold_min_total = float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0
    folds_with_trades = int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0

    selected_only = family_summary.get("selected_only", {})
    alpha_family = family_summary.get("alpha_fixed_filter", {})
    ofi_family = family_summary.get("ofi_selected_alpha", {})
    union_family = family_summary.get("union_alpha_or_ofi", {})
    if not isinstance(selected_only, dict):
        selected_only = {}
    if not isinstance(alpha_family, dict):
        alpha_family = {}
    if not isinstance(ofi_family, dict):
        ofi_family = {}
    if not isinstance(union_family, dict):
        union_family = {}

    summary = {
        "trades": trades,
        "hit_rate": float(selected_metrics.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(selected_metrics.get("mean_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(selected_metrics.get("total_net_pnl_bps", 0.0)),
        "folds_with_trades": folds_with_trades,
        "fold_min_mean_net_pnl_bps": fold_min_mean,
        "fold_min_total_net_pnl_bps": fold_min_total,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "stress_gate_passed": bool(stress_gate.get("passed")),
        "stress_min_mean_net_pnl_bps": float(stress_gate.get("min_mean_net_pnl_bps", 0.0)),
        "stress_min_total_net_pnl_bps": float(stress_gate.get("min_total_net_pnl_bps", 0.0)),
        "equal_trade_block_min_total_bps": float(stability.get("equal_trade_block_min_total_bps", 0.0)),
        "equal_trade_block_count": int(stability.get("equal_trade_block_count", 0)),
        "positive_equal_trade_blocks": int(stability.get("positive_equal_trade_blocks", 0)),
        "leave_one_fold_out_min_total_bps": float(stability.get("leave_one_fold_out_min_total_bps", 0.0)),
        "selected_shift_p_total": float(selected_only.get("p_total_ge_selected", 1.0)),
        "selected_shift_p_mean": float(selected_only.get("p_mean_ge_selected", 1.0)),
        "alpha_family_p_total": float(alpha_family.get("p_total_ge_selected", 1.0)),
        "alpha_family_p_mean": float(alpha_family.get("p_mean_ge_selected", 1.0)),
        "ofi_family_p_total": float(ofi_family.get("p_total_ge_selected", 1.0)),
        "ofi_family_p_mean": float(ofi_family.get("p_mean_ge_selected", 1.0)),
        "union_family_p_total": float(union_family.get("p_total_ge_selected", 1.0)),
        "union_family_p_mean": float(union_family.get("p_mean_ge_selected", 1.0)),
    }
    checks = {
        "enough_oof_trades": summary["trades"] >= gate_config.min_oof_trades,
        "enough_folds_with_trades": summary["folds_with_trades"] >= gate_config.min_folds_with_trades,
        "positive_fold_min_mean": summary["fold_min_mean_net_pnl_bps"] > gate_config.min_fold_mean_net_bps,
        "positive_fold_min_total": summary["fold_min_total_net_pnl_bps"] > gate_config.min_fold_total_net_bps,
        "positive_bootstrap_mean_p05": summary["bootstrap_mean_p05_bps"] > gate_config.min_bootstrap_mean_p05_bps,
        "stress_gate_ok": (not gate_config.require_stress_gate) or summary["stress_gate_passed"],
        "enough_equal_trade_blocks": summary["equal_trade_block_count"] >= gate_config.min_equal_trade_blocks,
        "positive_equal_trade_blocks": summary["positive_equal_trade_blocks"] >= gate_config.min_equal_trade_blocks,
        "positive_equal_trade_block_min_total": summary["equal_trade_block_min_total_bps"] > gate_config.min_equal_trade_block_total_bps,
        "positive_leave_one_fold_out": summary["leave_one_fold_out_min_total_bps"] > gate_config.min_leave_one_fold_out_total_bps,
        "selected_shift_total_ok": summary["selected_shift_p_total"] <= gate_config.max_selected_shift_p_total,
        "selected_shift_mean_ok": summary["selected_shift_p_mean"] <= gate_config.max_selected_shift_p_mean,
        "alpha_family_total_ok": summary["alpha_family_p_total"] <= gate_config.max_alpha_family_p_total,
        "alpha_family_mean_ok": summary["alpha_family_p_mean"] <= gate_config.max_alpha_family_p_mean,
        "ofi_family_total_ok": summary["ofi_family_p_total"] <= gate_config.max_ofi_family_p_total,
        "ofi_family_mean_ok": summary["ofi_family_p_mean"] <= gate_config.max_ofi_family_p_mean,
        "union_family_total_ok": summary["union_family_p_total"] <= gate_config.max_union_family_p_total,
        "union_family_mean_ok": summary["union_family_p_mean"] <= gate_config.max_union_family_p_mean,
    }
    summary["gate"] = {
        "passed": bool(all(checks.values())),
        "checks": checks,
        "failed_checks": [k for k, v in checks.items() if not v],
    }
    return summary


def _prepare_execution_arrays(frame: pd.DataFrame, *, horizon_sec: float, latency_sec: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    ts = timestamps_to_ns(frame["timestamp"])
    bid = frame["best_bid"].astype(float).to_numpy()
    ask = frame["best_ask"].astype(float).to_numpy()
    horizon_ns = int(float(horizon_sec) * 1_000_000_000)
    latency_ns = int(float(latency_sec) * 1_000_000_000)
    entry_target = ts + latency_ns
    exit_target = ts + horizon_ns
    entry_idx = np.searchsorted(ts, entry_target, side="left")
    exit_idx = np.searchsorted(ts, exit_target, side="left")
    valid = (entry_idx < len(ts)) & (exit_idx < len(ts)) & (entry_target < exit_target)
    return ts, bid, ask, entry_idx, exit_idx, valid, horizon_ns


def _fast_signal_metrics(
    raw: np.ndarray,
    arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int],
    *,
    cost_bps: float,
) -> tuple[dict[str, float], np.ndarray]:
    ts, bid, ask, entry_idx, exit_idx, valid, horizon_ns = arrays
    pnls: list[float] = []
    next_allowed = -10**30
    for i, sig in enumerate(np.asarray(raw, dtype=int)):
        if sig == 0 or int(ts[i]) < next_allowed or not bool(valid[i]):
            continue
        ei = int(entry_idx[i])
        xi = int(exit_idx[i])
        if sig > 0:
            ep = float(ask[ei])
            xp = float(bid[xi])
            pnl = (xp - ep) / ep * 10000.0
        else:
            ep = float(bid[ei])
            xp = float(ask[xi])
            pnl = (ep - xp) / ep * 10000.0
        if np.isfinite(ep) and np.isfinite(xp) and ep > 0 and xp > 0:
            pnls.append(float(pnl) - float(cost_bps))
            next_allowed = int(ts[i]) + int(horizon_ns)
    arr = np.asarray(pnls, dtype=float)
    if len(arr) == 0:
        return {
            "events": float(len(raw)),
            "trades": 0.0,
            "hit_rate": 0.0,
            "mean_net_pnl_bps": 0.0,
            "total_net_pnl_bps": 0.0,
        }, arr
    return {
        "events": float(len(raw)),
        "trades": float(len(arr)),
        "hit_rate": float((arr > 0.0).mean()),
        "mean_net_pnl_bps": float(arr.mean()),
        "total_net_pnl_bps": float(arr.sum()),
    }, arr


def _same_candidate(cand: dict[str, object], alpha: float, spec: SlotVetoSpec) -> bool:
    return abs(float(cand["alpha"]) - float(alpha)) < 1e-12 and _same_filter(cand["spec"], spec)  # type: ignore[arg-type]


def _same_filter(left: object, right: SlotVetoSpec) -> bool:
    if not isinstance(left, SlotVetoSpec):
        return False
    return (
        left.filter_col == right.filter_col
        and left.filter_operator == right.filter_operator
        and abs(float(left.filter_quantile) - float(right.filter_quantile)) < 1e-12
        and abs(float(left.edge_threshold) - float(right.edge_threshold)) < 1e-12
    )


def _dedupe_floats(values: Iterable[float]) -> list[float]:
    seen: set[float] = set()
    out: list[float] = []
    for value in values:
        val = round(float(value), 12)
        if val not in seen:
            out.append(float(value))
            seen.add(val)
    return out


def _json_float(value: object) -> object:
    if isinstance(value, (np.floating, float)):
        return float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def _write_stability_report(path: str | Path, result: dict[str, object], folds: pd.DataFrame, candidates: pd.DataFrame) -> None:
    aggregate = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    family = result.get("family_null", {}) if isinstance(result.get("family_null"), dict) else {}
    stability = result.get("stability", {}) if isinstance(result.get("stability"), dict) else {}
    lines = [
        "# V14 K-line Stability Lock Audit",
        "",
        f"Base ensemble: `{result.get('base_ensemble_dir')}`",
        f"K-line ensemble: `{result.get('kline_ensemble_dir')}`",
        f"Selected alpha: `{result.get('selected_alpha')}`",
        f"Selected slot veto: `{json.dumps(result.get('selected_spec'), sort_keys=True)}`",
        "",
        "## Research stability gate",
        "",
        "```json",
        json.dumps(aggregate.get("gate", {}), indent=2),
        "```",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps({k: v for k, v in aggregate.items() if k != "gate"}, indent=2),
        "```",
        "",
        "## Fold metrics",
        "",
        folds.to_markdown(index=False) if not folds.empty else "No fold metrics.",
        "",
        "## Equal-trade block stability",
        "",
        pd.DataFrame(stability.get("equal_trade_blocks", [])).to_markdown(index=False) if stability.get("equal_trade_blocks") else "No trade blocks.",
        "",
        "## Family null controls",
        "",
        "```json",
        json.dumps(family, indent=2),
        "```",
        "",
        "## Candidate family leaderboard",
        "",
        candidates.head(25).to_markdown(index=False) if not candidates.empty else "No candidates.",
        "",
        "## Interpretation",
        "",
        "This audit closes the v13 alpha-selection caveat by testing the selected K-line alpha against an alpha family, the OFI-veto family, and their union under shifted-signal nulls. Passing means the candidate has a stronger single-sample research stability result than v13. It still is not a live-trading guarantee and still requires true multi-day validation before deployment.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
