from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .fixed_template import candidate_signature, load_ensemble_fold_predictions
from .selective import (
    SelectiveCandidate,
    aggregate_selective_folds,
    backtest_fixed_signals_taker_bidask_non_overlapping,
    backtest_selective_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    search_selective_candidates,
    shift_null_fixed_signals,
    stress_fixed_signals,
    summarize_shift_null,
)
from .stress import block_bootstrap_pnl


def run_template_transfer_audit(
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
    min_source_trades: int = 4,
    top_k_templates: int = 80,
    warmup_folds: int = 1,
    min_history_trades: int = 3,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 80,
    clean: bool = False,
) -> dict[str, object]:
    """Prequential transfer audit for fixed templates.

    Build a template pool from the first calibration window.  For each future fold, rank templates
    using validation folds that have already happened, select one template, and test it on the next
    validation fold.  This tests whether a validation-ranked diagnostic survives one-step-forward
    deployment rather than being selected with full hindsight.
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

    folds = load_ensemble_fold_predictions(ensemble_dir)
    if len(folds) < warmup_folds + 1:
        raise ValueError("template-transfer audit needs at least warmup_folds + 1 folds")
    templates = _first_calibration_templates(
        folds,
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
        raise ValueError("no templates available for transfer audit")

    metrics_rows: list[dict[str, object]] = []
    ledgers: dict[tuple[str, int], pd.DataFrame] = {}
    candidates = []
    for rank, candidate in enumerate(templates, start=1):
        sig = candidate_signature(candidate)
        candidates.append({"source_rank": rank, "template_signature": sig, "candidate_json": json.dumps(candidate.to_dict(), sort_keys=True)})
        for fold_num, _calib, validation in folds:
            bt, metrics = backtest_selective_taker_bidask_non_overlapping(
                validation,
                candidate=candidate,
                cost_bps=cost_bps,
                horizon_sec=horizon_sec,
                latency_sec=latency_sec,
            )
            if "fold" in bt.columns:
                bt["fold"] = fold_num
            else:
                bt.insert(0, "fold", fold_num)
            bt["template_signature"] = sig
            bt["candidate_json"] = json.dumps(candidate.to_dict(), sort_keys=True)
            ledgers[(sig, fold_num)] = bt
            metrics_rows.append({
                "source_rank": rank,
                "template_signature": sig,
                "fold": fold_num,
                **_candidate_fields(candidate),
                **metrics,
            })
    matrix = pd.DataFrame(metrics_rows)
    matrix.to_csv(out / "template_fold_matrix.csv", index=False)
    pd.DataFrame(candidates).to_csv(out / "template_pool.csv", index=False)

    selected_rows: list[dict[str, object]] = []
    selected_ledgers: list[pd.DataFrame] = []
    ordered_fold_nums = [fold_num for fold_num, _c, _v in folds]
    for idx, fold_num in enumerate(ordered_fold_nums):
        if idx < warmup_folds:
            continue
        past = ordered_fold_nums[:idx]
        selected = _select_from_history(matrix, past_folds=past, min_history_trades=min_history_trades)
        sig = str(selected["template_signature"])
        ledger = ledgers[(sig, fold_num)].copy()
        ledger["selected_by_past_folds"] = ",".join(str(x) for x in past)
        ledger["transfer_selected_template_signature"] = sig
        selected_ledgers.append(ledger)
        current_metrics = matrix[(matrix["template_signature"] == sig) & (matrix["fold"] == fold_num)].iloc[0].to_dict()
        selected_rows.append({
            "test_fold": fold_num,
            "past_folds": ",".join(str(x) for x in past),
            "selected_history_score": float(selected["history_score"]),
            "selected_history_trades": float(selected["history_trades"]),
            "selected_history_mean_net_pnl_bps": float(selected["history_mean_net_pnl_bps"]),
            **{f"selected_{k}": v for k, v in selected.items() if k in ["source_rank", "template_signature", "candidate_json"]},
            "test_trades": float(current_metrics.get("trades", 0.0)),
            "test_hit_rate": float(current_metrics.get("hit_rate", 0.0)),
            "test_mean_net_pnl_bps": float(current_metrics.get("mean_net_pnl_bps", 0.0)),
            "test_total_net_pnl_bps": float(current_metrics.get("total_net_pnl_bps", 0.0)),
            "test_max_drawdown_bps": float(current_metrics.get("max_drawdown_bps", 0.0)),
        })

    selected_df = pd.DataFrame(selected_rows)
    selected_df.to_csv(out / "transfer_selection_steps.csv", index=False)
    oof = pd.concat(selected_ledgers, ignore_index=True) if selected_ledgers else pd.DataFrame()
    oof.to_csv(out / "oof_transfer_backtest.csv", index=False)

    folds_for_aggregate = _fold_metrics_from_selected_steps(selected_df)
    folds_for_aggregate.to_csv(out / "selected_fold_metrics.csv", index=False)
    if not folds_for_aggregate.empty:
        boot_rows = []
        for fold_num, ledger in oof.groupby("fold"):
            pnl = ledger.loc[ledger["traded"] == 1, "net_pnl_bps"]
            boot = block_bootstrap_pnl(pnl, iterations=500, block_size=10, seed=50900 + int(fold_num))
            boot_rows.append({"fold": fold_num, **boot})
        boot_df = pd.DataFrame(boot_rows).rename(columns={"mean_p05_bps": "bootstrap_mean_p05_bps", "prob_mean_gt_0": "bootstrap_prob_mean_gt_0"})
        folds_for_aggregate = folds_for_aggregate.merge(boot_df[["fold", "bootstrap_mean_p05_bps", "bootstrap_prob_mean_gt_0"]], on="fold", how="left")
        folds_for_aggregate.to_csv(out / "selected_fold_metrics.csv", index=False)

    stress = stress_fixed_signals(oof, horizon_sec=horizon_sec, cost_bps_values=stress_cost_bps_values, latency_sec_values=stress_latency_sec_values) if not oof.empty else pd.DataFrame()
    stress.to_csv(out / "oof_fixed_signal_stress.csv", index=False)
    robust_gate = fixed_signal_robust_gate(stress, min_trades=max(1, min_history_trades)) if not stress.empty else {"passed": False, "reason": "empty stress"}
    actual_repriced, actual_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(oof, cost_bps=cost_bps, horizon_sec=horizon_sec, latency_sec=latency_sec) if not oof.empty else (pd.DataFrame(), {})
    actual_repriced.to_csv(out / "oof_primary_repriced_backtest.csv", index=False)
    shift_null = shift_null_fixed_signals(oof, horizon_sec=horizon_sec, cost_bps=cost_bps, latency_sec=latency_sec, shifts=shift_null_runs) if not oof.empty else pd.DataFrame()
    shift_null.to_csv(out / "shift_null_fixed_signals.csv", index=False)
    shift_summary = summarize_shift_null(actual_metrics, shift_null)

    aggregate = aggregate_selective_folds(folds_for_aggregate, oof, stress, robust_gate)
    aggregate.update({f"shift_null_{k}": v for k, v in shift_summary.items()})
    gate = _evaluate_transfer_gate(aggregate, robust_gate)
    result = {
        "source_ensemble_dir": str(ensemble_dir),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "edge_thresholds": [float(x) for x in edge_thresholds],
        "signed_columns": signed_columns,
        "spread_quantiles": [float(x) for x in spread_quantiles],
        "vol_modes": list(vol_modes),
        "min_source_trades": int(min_source_trades),
        "top_k_templates": int(top_k_templates),
        "warmup_folds": int(warmup_folds),
        "min_history_trades": int(min_history_trades),
        "templates_tested": int(len(templates)),
        "aggregate": aggregate,
        "robust_gate": robust_gate,
        "gate": gate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, selected_df, folds_for_aggregate, stress)
    return result


def _first_calibration_templates(
    folds: list[tuple[int, pd.DataFrame, pd.DataFrame]],
    *,
    edge_thresholds: list[float],
    signed_columns: list[str] | None,
    spread_quantiles: list[float],
    vol_modes: list[str],
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    min_source_trades: int,
    top_k_templates: int,
) -> list[SelectiveCandidate]:
    _fold_num, calibration, _validation = folds[0]
    candidates = search_selective_candidates(
        calibration,
        edge_thresholds=edge_thresholds,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        min_trades=min_source_trades,
        signed_columns=signed_columns,
        spread_quantiles=spread_quantiles,
        vol_modes=vol_modes,
    )
    if candidates.empty:
        return []
    out = []
    seen: set[str] = set()
    for _, row in candidates.head(max(1, int(top_k_templates))).iterrows():
        candidate = SelectiveCandidate.from_dict(json.loads(str(row["candidate_json"])))
        sig = candidate_signature(candidate)
        if sig not in seen:
            out.append(candidate)
            seen.add(sig)
    return out


def _select_from_history(matrix: pd.DataFrame, *, past_folds: list[int], min_history_trades: int) -> dict[str, object]:
    hist = matrix[matrix["fold"].isin(past_folds)].copy()
    grouped = []
    for sig, group in hist.groupby("template_signature"):
        trades = pd.to_numeric(group["trades"], errors="coerce").fillna(0.0)
        totals = pd.to_numeric(group["total_net_pnl_bps"], errors="coerce").fillna(0.0)
        means = pd.to_numeric(group["mean_net_pnl_bps"], errors="coerce").fillna(0.0)
        dd = pd.to_numeric(group["max_drawdown_bps"], errors="coerce").fillna(0.0).abs()
        history_trades = float(trades.sum())
        history_total = float(totals.sum())
        history_mean = float(history_total / history_trades) if history_trades > 0 else 0.0
        history_fold_min = float(means.min()) if len(means) else 0.0
        score = history_mean + 0.004 * history_total + 0.05 * len(group) - 0.01 * float(dd.max())
        grouped.append({
            "template_signature": sig,
            "history_trades": history_trades,
            "history_total_net_pnl_bps": history_total,
            "history_mean_net_pnl_bps": history_mean,
            "history_fold_min_mean_net_pnl_bps": history_fold_min,
            "history_score": score,
            "source_rank": int(group["source_rank"].iloc[0]),
            "candidate_json": group["candidate_json"].iloc[0] if "candidate_json" in group.columns else "{}",
            "meets_history_trades": history_trades >= float(min_history_trades),
        })
    out = pd.DataFrame(grouped)
    if out.empty:
        raise ValueError("empty history selection table")
    out = out.sort_values(["meets_history_trades", "history_score", "history_mean_net_pnl_bps", "history_total_net_pnl_bps"], ascending=[False, False, False, False]).reset_index(drop=True)
    return out.iloc[0].to_dict()


def _fold_metrics_from_selected_steps(selected: pd.DataFrame) -> pd.DataFrame:
    if selected.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "fold": selected["test_fold"].astype(int),
        "valid_trades": selected["test_trades"].astype(float),
        "valid_hit_rate": selected["test_hit_rate"].astype(float),
        "valid_mean_net_pnl_bps": selected["test_mean_net_pnl_bps"].astype(float),
        "valid_total_net_pnl_bps": selected["test_total_net_pnl_bps"].astype(float),
        "valid_max_drawdown_bps": selected["test_max_drawdown_bps"].astype(float),
    })


def _evaluate_transfer_gate(aggregate: dict[str, object], robust_gate: dict[str, object]) -> dict[str, object]:
    checks = {
        "enough_oof_trades": float(aggregate.get("oof_trades", 0)) >= 12.0,
        "enough_min_fold_trades": float(aggregate.get("valid_trades_min", 0.0)) >= 3.0,
        "positive_oof_mean": float(aggregate.get("oof_mean_net_pnl_bps", -999.0)) > 0.0,
        "positive_fold_min_mean": float(aggregate.get("valid_mean_net_pnl_bps_min", -999.0)) > 0.0,
        "positive_bootstrap_p05_min": float(aggregate.get("bootstrap_mean_p05_bps_min", -999.0)) > 0.0,
        "robust_stress_gate": bool(robust_gate.get("passed")),
        "shift_null_mean_ok": float(aggregate.get("shift_null_p_null_mean_ge_actual", 1.0)) <= 0.10,
        "shift_null_total_ok": float(aggregate.get("shift_null_p_null_total_ge_actual", 1.0)) <= 0.10,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {"passed": not failed, "failed_checks": failed, "checks": checks}


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


def _write_report(path: str | Path, result: dict[str, object], selection_steps: pd.DataFrame, folds: pd.DataFrame, stress: pd.DataFrame) -> None:
    lines = [
        "# Research V09 Template-transfer Audit",
        "",
        "This prequential audit ranks fixed templates using validation folds that have already occurred, then tests the selected template on the next validation fold.",
        "It is stricter than validation_rank oracle selection and checks whether a diagnostic template transfers forward in time.",
        "",
        "## Settings",
        "",
        "```json",
        json.dumps({k: result.get(k) for k in ["source_ensemble_dir", "horizon_sec", "cost_bps", "latency_sec", "edge_thresholds", "signed_columns", "spread_quantiles", "vol_modes", "warmup_folds", "templates_tested"]}, indent=2),
        "```",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(result.get("aggregate", {}), indent=2),
        "```",
        "",
        "## Gate",
        "",
        "```json",
        json.dumps(result.get("gate", {}), indent=2),
        "```",
        "",
        "## Transfer selection steps",
        "",
    ]
    step_cols = ["test_fold", "past_folds", "selected_history_score", "selected_history_trades", "selected_history_mean_net_pnl_bps", "test_trades", "test_hit_rate", "test_mean_net_pnl_bps", "test_total_net_pnl_bps"]
    lines.append(selection_steps[[c for c in step_cols if c in selection_steps.columns]].to_markdown(index=False) if not selection_steps.empty else "No selection steps.")
    lines.extend(["", "## Selected fold metrics", ""])
    fold_cols = ["fold", "valid_trades", "valid_hit_rate", "valid_mean_net_pnl_bps", "valid_total_net_pnl_bps", "bootstrap_mean_p05_bps"]
    lines.append(folds[[c for c in fold_cols if c in folds.columns]].to_markdown(index=False) if not folds.empty else "No folds.")
    lines.extend(["", "## Stress", ""])
    stress_cols = ["cost_bps", "latency_sec", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
    lines.append(stress[[c for c in stress_cols if c in stress.columns]].to_markdown(index=False) if not stress.empty else "No stress rows.")
    lines.extend(["", "## Interpretation", "", "A pass would show that a template selected from earlier validation behavior transfers to later validation behavior. A fail means validation-ranked diagnostics remain hindsight artifacts under this single-day sample."])
    Path(path).write_text("\n".join(lines), encoding="utf-8")
