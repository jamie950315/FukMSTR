from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .selective import (
    backtest_fixed_signals_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    shift_null_fixed_signals,
    stress_fixed_signals,
    summarize_shift_null,
)
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class SlotVetoSpec:
    """A deployable veto applied only to pre-scheduled non-overlap model slots.

    The base model creates a non-overlapping slot schedule from probability edge.  The veto may reject
    a scheduled entry, but rejected slots still reserve the cooldown interval.  This prevents the audit
    from replacing a vetoed losing slot with a later overlapping winner and is therefore deliberately
    conservative.
    """

    edge_threshold: float = 0.1
    filter_col: str = "ofi_sum_l5_norm"
    filter_operator: str = "<="
    filter_quantile: float = 0.9

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SlotVetoGateConfig:
    min_oof_trades: int = 20
    min_periods_with_trades: int = 5
    min_period_mean_net_bps: float = 0.0
    min_bootstrap_p05_bps: float = 0.0
    max_shift_null_p_total: float = 0.10
    max_shift_null_p_mean: float = 0.10
    max_family_null_p_total: float = 0.05
    max_family_null_p_mean: float = 0.10
    require_stress_gate: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_slot_veto_audit(
    *,
    ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    spec: SlotVetoSpec | None = None,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    family_filter_cols: list[str] | None = None,
    family_quantiles: list[float] | None = None,
    shift_null_runs: int = 80,
    family_shift_runs: int = 80,
    gate_config: SlotVetoGateConfig | None = None,
    clean: bool = False,
) -> dict[str, object]:
    source = Path(ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    spec = spec or SlotVetoSpec()
    stress_cost_bps_values = stress_cost_bps_values or [1.5, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0]
    family_filter_cols = family_filter_cols or ["ofi_sum_l3_norm", "ofi_sum_l5_norm", "ofi_sum_l10_norm"]
    family_quantiles = family_quantiles or [0.5, 0.6, 0.7, 0.8, 0.9]
    gate_config = gate_config or SlotVetoGateConfig()

    fold_dirs = sorted(p for p in source.glob("fold_*") if p.is_dir())
    if not fold_dirs:
        raise ValueError(f"no fold directories found under {source}")

    fold_rows: list[dict[str, object]] = []
    oof_frames: list[pd.DataFrame] = []
    for fold_dir in fold_dirs:
        fold = _fold_num(fold_dir)
        calibration = pd.read_csv(fold_dir / "calibration_predictions.csv")
        validation = pd.read_csv(fold_dir / "validation_predictions.csv")
        frame, metrics, threshold = _build_slot_veto_fold(
            calibration=calibration,
            validation=validation,
            spec=spec,
            fold=fold,
            horizon_sec=horizon_sec,
            cost_bps=cost_bps,
            latency_sec=latency_sec,
        )
        frame.to_csv(out / f"fold_{fold:02d}_slot_veto_backtest.csv", index=False)
        trades = frame.loc[frame["traded"] == 1, "net_pnl_bps"]
        boot = block_bootstrap_pnl(trades, iterations=800, block_size=5, seed=1700 + fold)
        fold_rows.append(
            {
                "fold": fold,
                "filter_threshold": float(threshold),
                "events": float(metrics.get("events", 0.0)),
                "trades": int(metrics.get("trades", 0.0)),
                "hit_rate": float(metrics.get("hit_rate", 0.0)),
                "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
                "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
                "max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
                "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0.0)),
                "bootstrap_prob_mean_gt_0": float(boot.get("prob_mean_gt_0", 0.0)),
            }
        )
        oof_frames.append(frame)

    folds = pd.DataFrame(fold_rows)
    folds.to_csv(out / "fold_metrics.csv", index=False)
    oof = pd.concat(oof_frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    oof.to_csv(out / "slot_veto_oof_backtest.csv", index=False)

    stress = stress_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    )
    stress.to_csv(out / "slot_veto_stress.csv", index=False)
    stress_gate = fixed_signal_robust_gate(stress, min_trades=max(1, gate_config.min_oof_trades))

    actual_frame, actual_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    shift_null = shift_null_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        shifts=shift_null_runs,
    )
    shift_null.to_csv(out / "slot_veto_shift_null.csv", index=False)
    shift_summary = summarize_shift_null(actual_metrics, shift_null)

    bootstrap = block_bootstrap_pnl(
        actual_frame.loc[actual_frame["traded"] == 1, "net_pnl_bps"],
        iterations=2000,
        block_size=5,
        seed=2200,
    )

    family_summary, family_metrics, family_null = _run_slot_veto_family_null(
        fold_dirs=fold_dirs,
        selected_spec=spec,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        filter_cols=family_filter_cols,
        quantiles=family_quantiles,
        shifts=family_shift_runs,
        min_trades_for_constrained_null=gate_config.min_oof_trades,
    )
    family_metrics.to_csv(out / "slot_veto_family_candidates.csv", index=False)
    family_null.to_csv(out / "slot_veto_family_shift_null.csv", index=False)

    aggregate = _aggregate_slot_veto(
        folds=folds,
        oof=actual_frame,
        bootstrap=bootstrap,
        stress_gate=stress_gate,
        shift_summary=shift_summary,
        family_summary=family_summary,
        gate_config=gate_config,
    )

    result = {
        "source_ensemble_dir": str(source),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "spec": spec.to_dict(),
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "family_filter_cols": family_filter_cols,
        "family_quantiles": [float(x) for x in family_quantiles],
        "shift_null_runs": int(shift_null_runs),
        "family_shift_runs": int(family_shift_runs),
        "folds": int(len(folds)),
        "bootstrap": bootstrap,
        "shift_null": shift_summary,
        "stress_gate": stress_gate,
        "family_null": family_summary,
        "gate_config": gate_config.to_dict(),
        "aggregate": aggregate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, folds, stress, family_metrics)
    return result


def _build_slot_veto_fold(
    *,
    calibration: pd.DataFrame,
    validation: pd.DataFrame,
    spec: SlotVetoSpec,
    fold: int,
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
) -> tuple[pd.DataFrame, dict[str, float], float]:
    if spec.filter_col not in calibration.columns or spec.filter_col not in validation.columns:
        raise ValueError(f"filter_col missing from calibration or validation: {spec.filter_col}")
    threshold = float(pd.to_numeric(calibration[spec.filter_col], errors="coerce").quantile(float(spec.filter_quantile)))
    edge = validation["prob_up"].astype(float) - validation["prob_down"].astype(float)
    base_signal = np.where(edge >= spec.edge_threshold, 1, np.where(edge <= -spec.edge_threshold, -1, 0)).astype(int)
    base_slots, _ = backtest_fixed_signals_taker_bidask_non_overlapping(
        validation.assign(signal=base_signal, fold=fold),
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    filter_values = pd.to_numeric(base_slots[spec.filter_col], errors="coerce")
    if spec.filter_operator == "<=":
        keep = filter_values <= threshold
    elif spec.filter_operator == ">=":
        keep = filter_values >= threshold
    else:
        raise ValueError("filter_operator must be '<=' or '>='")
    slot_mask = (base_slots["traded"].astype(int) == 1) & keep.fillna(False)
    selected_signal = np.zeros(len(base_slots), dtype=int)
    selected_signal[slot_mask.to_numpy()] = base_slots.loc[slot_mask, "signal"].astype(int).to_numpy()
    frame, metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        base_slots.assign(signal=selected_signal, fold=fold),
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    frame["fold"] = int(fold)
    frame["base_slot_signal"] = base_slots["signal"].astype(int).to_numpy()
    frame["base_slot_traded"] = base_slots["traded"].astype(int).to_numpy()
    frame["veto_passed"] = slot_mask.astype(int).to_numpy()
    frame["filter_col"] = spec.filter_col
    frame["filter_operator"] = spec.filter_operator
    frame["filter_quantile"] = float(spec.filter_quantile)
    frame["filter_threshold"] = float(threshold)
    return frame, metrics, threshold


def _run_slot_veto_family_null(
    *,
    fold_dirs: list[Path],
    selected_spec: SlotVetoSpec,
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
    filter_cols: list[str],
    quantiles: list[float],
    shifts: int,
    min_trades_for_constrained_null: int,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    candidates: list[dict[str, object]] = []
    for col in filter_cols:
        for q in quantiles:
            spec = SlotVetoSpec(
                edge_threshold=selected_spec.edge_threshold,
                filter_col=col,
                filter_operator=selected_spec.filter_operator,
                filter_quantile=float(q),
            )
            frames: list[pd.DataFrame] = []
            for fold_dir in fold_dirs:
                fold = _fold_num(fold_dir)
                calibration = pd.read_csv(fold_dir / "calibration_predictions.csv")
                validation = pd.read_csv(fold_dir / "validation_predictions.csv")
                frame, _, _ = _build_slot_veto_fold(
                    calibration=calibration,
                    validation=validation,
                    spec=spec,
                    fold=fold,
                    horizon_sec=horizon_sec,
                    cost_bps=cost_bps,
                    latency_sec=latency_sec,
                )
                frames.append(frame)
            oof = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
            raw = oof["signal"].fillna(0).astype(int).clip(-1, 1).to_numpy(dtype=int)
            _, metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
                oof.assign(signal=raw), cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec
            )
            candidates.append({"spec": spec, "oof": oof, "raw": raw, "metrics": metrics})

    metric_rows = []
    for item in candidates:
        spec = item["spec"]
        metrics = item["metrics"]
        metric_rows.append({**spec.to_dict(), **metrics})
    metrics_df = pd.DataFrame(metric_rows).sort_values(["total_net_pnl_bps", "mean_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)

    selected_key = selected_spec.to_dict()
    selected_item = next(
        item for item in candidates if item["spec"].to_dict() == selected_key
    )
    selected_metrics = selected_item["metrics"]
    n = len(selected_item["raw"])
    shift_values = _shift_values(n=n, shifts=shifts, min_shift=max(1, int(round(float(horizon_sec) / 0.5))))
    null_rows = []
    for shift in shift_values:
        max_total = -1e18
        max_mean = -1e18
        max_total_constrained = -1e18
        max_mean_constrained = -1e18
        best_total_spec = ""
        for item in candidates:
            raw = np.roll(item["raw"], int(shift) % len(item["raw"]))
            _, metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
                item["oof"].assign(signal=raw),
                cost_bps=cost_bps,
                horizon_sec=horizon_sec,
                latency_sec=latency_sec,
            )
            total = float(metrics.get("total_net_pnl_bps", 0.0))
            mean = float(metrics.get("mean_net_pnl_bps", 0.0))
            trades = float(metrics.get("trades", 0.0))
            if total > max_total:
                max_total = total
                best_total_spec = json.dumps(item["spec"].to_dict(), sort_keys=True)
            max_mean = max(max_mean, mean)
            if trades >= float(min_trades_for_constrained_null):
                max_total_constrained = max(max_total_constrained, total)
                max_mean_constrained = max(max_mean_constrained, mean)
        null_rows.append(
            {
                "shift_rows": int(shift),
                "max_total_net_pnl_bps": float(max_total),
                "max_mean_net_pnl_bps": float(max_mean),
                "max_total_net_pnl_bps_constrained": float(max_total_constrained),
                "max_mean_net_pnl_bps_constrained": float(max_mean_constrained),
                "best_total_spec_json": best_total_spec,
            }
        )
    null_df = pd.DataFrame(null_rows)
    total = pd.to_numeric(null_df["max_total_net_pnl_bps"], errors="coerce")
    mean = pd.to_numeric(null_df["max_mean_net_pnl_bps"], errors="coerce")
    total_c = pd.to_numeric(null_df["max_total_net_pnl_bps_constrained"], errors="coerce")
    mean_c = pd.to_numeric(null_df["max_mean_net_pnl_bps_constrained"], errors="coerce")
    selected_total = float(selected_metrics.get("total_net_pnl_bps", 0.0))
    selected_mean = float(selected_metrics.get("mean_net_pnl_bps", 0.0))
    summary = {
        "candidate_count": int(len(candidates)),
        "selected_total_net_pnl_bps": selected_total,
        "selected_mean_net_pnl_bps": selected_mean,
        "selected_trades": float(selected_metrics.get("trades", 0.0)),
        "family_null_runs": int(len(null_df)),
        "p_family_max_total_ge_selected": float((total >= selected_total).mean()) if len(total) else 1.0,
        "p_family_max_mean_ge_selected": float((mean >= selected_mean).mean()) if len(mean) else 1.0,
        "p_family_constrained_max_total_ge_selected": float((total_c >= selected_total).mean()) if len(total_c) else 1.0,
        "p_family_constrained_max_mean_ge_selected": float((mean_c >= selected_mean).mean()) if len(mean_c) else 1.0,
        "family_null_total_p95_bps": float(total.quantile(0.95)) if len(total) else 0.0,
        "family_null_mean_p95_bps": float(mean.quantile(0.95)) if len(mean) else 0.0,
        "family_constrained_null_total_p95_bps": float(total_c.quantile(0.95)) if len(total_c) else 0.0,
        "family_constrained_null_mean_p95_bps": float(mean_c.quantile(0.95)) if len(mean_c) else 0.0,
    }
    return summary, metrics_df, null_df


def _aggregate_slot_veto(
    *,
    folds: pd.DataFrame,
    oof: pd.DataFrame,
    bootstrap: dict[str, float],
    stress_gate: dict[str, object],
    shift_summary: dict[str, object],
    family_summary: dict[str, object],
    gate_config: SlotVetoGateConfig,
) -> dict[str, object]:
    trades = oof[oof["traded"] == 1].copy()
    periods_with_trades = int((folds["trades"].astype(float) > 0).sum()) if not folds.empty else 0
    summary = {
        "trades": int(len(trades)),
        "hit_rate": float((trades["net_pnl_bps"] > 0).mean()) if len(trades) else 0.0,
        "mean_net_pnl_bps": float(trades["net_pnl_bps"].mean()) if len(trades) else 0.0,
        "total_net_pnl_bps": float(trades["net_pnl_bps"].sum()) if len(trades) else 0.0,
        "periods_with_trades": periods_with_trades,
        "period_trades_min": int(folds["trades"].min()) if not folds.empty else 0,
        "period_mean_net_pnl_bps_min": float(folds["mean_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "period_total_net_pnl_bps_min": float(folds["total_net_pnl_bps"].min()) if not folds.empty else 0.0,
        "bootstrap_mean_p05_bps": float(bootstrap.get("mean_p05_bps", 0.0)),
        "bootstrap_total_p05_bps": float(bootstrap.get("total_p05_bps", 0.0)),
        "stress_gate_passed": bool(stress_gate.get("passed")),
        "shift_null_p_total": float(shift_summary.get("p_null_total_ge_actual", 1.0)),
        "shift_null_p_mean": float(shift_summary.get("p_null_mean_ge_actual", 1.0)),
        "family_null_p_total": float(family_summary.get("p_family_max_total_ge_selected", 1.0)),
        "family_null_p_mean": float(family_summary.get("p_family_max_mean_ge_selected", 1.0)),
        "family_constrained_null_p_total": float(family_summary.get("p_family_constrained_max_total_ge_selected", 1.0)),
        "family_constrained_null_p_mean": float(family_summary.get("p_family_constrained_max_mean_ge_selected", 1.0)),
    }
    checks = {
        "enough_oof_trades": summary["trades"] >= gate_config.min_oof_trades,
        "enough_periods_with_trades": summary["periods_with_trades"] >= gate_config.min_periods_with_trades,
        "positive_period_min_mean": summary["period_mean_net_pnl_bps_min"] > gate_config.min_period_mean_net_bps,
        "positive_bootstrap_p05": summary["bootstrap_mean_p05_bps"] > gate_config.min_bootstrap_p05_bps,
        "stress_gate_ok": (not gate_config.require_stress_gate) or summary["stress_gate_passed"],
        "shift_null_total_ok": summary["shift_null_p_total"] <= gate_config.max_shift_null_p_total,
        "shift_null_mean_ok": summary["shift_null_p_mean"] <= gate_config.max_shift_null_p_mean,
        "family_null_total_ok": summary["family_null_p_total"] <= gate_config.max_family_null_p_total,
        "family_null_mean_ok": summary["family_null_p_mean"] <= gate_config.max_family_null_p_mean,
        "family_constrained_null_total_ok": summary["family_constrained_null_p_total"] <= gate_config.max_family_null_p_total,
        "family_constrained_null_mean_ok": summary["family_constrained_null_p_mean"] <= gate_config.max_family_null_p_mean,
    }
    summary["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return summary


def _shift_values(*, n: int, shifts: int, min_shift: int) -> list[int]:
    if n <= 2:
        return []
    lo = max(1, min(int(min_shift), n - 1))
    hi = max(lo, n - lo - 1)
    values = np.linspace(lo, hi, num=min(int(shifts), max(1, hi - lo + 1)), dtype=int)
    return sorted(set(int(x) for x in values if 0 < int(x) < n))


def _fold_num(path: Path) -> int:
    tag = path.name.replace("fold_", "")
    return int(tag) if tag.isdigit() else 0


def _write_report(path: str | Path, result: dict[str, object], folds: pd.DataFrame, stress: pd.DataFrame, family_metrics: pd.DataFrame) -> None:
    aggregate = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    lines = [
        "# V12 Slot-veto Audit Report",
        "",
        f"Source ensemble: `{result.get('source_ensemble_dir')}`",
        f"Horizon: {result.get('horizon_sec')} seconds",
        f"Cost / latency: {result.get('cost_bps')} bps / {result.get('latency_sec')} seconds",
        f"Spec: `{json.dumps(result.get('spec'), sort_keys=True)}`",
        "",
        "## Gate result",
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
        folds.to_markdown(index=False) if not folds.empty else "No folds.",
        "",
        "## Stress gate",
        "",
        "```json",
        json.dumps(result.get("stress_gate", {}), indent=2),
        "```",
        "",
        "## Family null",
        "",
        "```json",
        json.dumps(result.get("family_null", {}), indent=2),
        "```",
        "",
        "## Top family candidates",
        "",
        family_metrics.head(15).to_markdown(index=False) if not family_metrics.empty else "No family metrics.",
        "",
        "## Interpretation",
        "",
        "The base model first creates non-overlapping probability-edge slots. The OFI veto is applied only to those scheduled slots; vetoed slots do not get replaced by later overlapping entries. This is a conservative slot-preserving audit. Passing this single-day gate is research evidence only; multi-day validation is still required before calling the edge stable.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
