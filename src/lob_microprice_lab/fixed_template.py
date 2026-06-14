from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .selective import (
    SelectiveCandidate,
    backtest_fixed_signals_taker_bidask_non_overlapping,
    backtest_selective_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    generate_candidate_grid,
    search_selective_candidates,
    shift_null_fixed_signals,
    stress_fixed_signals,
    summarize_shift_null,
)
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class FixedTemplateGateConfig:
    min_folds_with_trades: int = 2
    min_oof_trades: int = 20
    min_fold_trades: int = 3
    min_oof_mean_net_bps: float = 0.0
    min_fold_mean_net_bps: float = 0.0
    min_bootstrap_p05_bps: float = 0.0
    max_shift_null_p_mean: float = 0.10
    max_shift_null_p_total: float = 0.10
    require_stress_gate: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TemplateAuditResult:
    out_dir: str
    selected_candidate: dict[str, object]
    aggregate: dict[str, object]
    gate: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def candidate_signature(candidate: SelectiveCandidate, *, rounded: int = 8) -> str:
    """Stable compact identifier for a frozen selective trading template."""
    payload = candidate.to_dict().copy()
    for key, value in list(payload.items()):
        if isinstance(value, float):
            payload[key] = round(value, rounded)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def candidate_from_signature(signature: str) -> SelectiveCandidate:
    return SelectiveCandidate.from_dict(json.loads(signature))


def load_ensemble_fold_predictions(ensemble_dir: str | Path) -> list[tuple[int, pd.DataFrame, pd.DataFrame]]:
    """Load calibration and validation prediction frames from an ensemble walk-forward run."""
    source = Path(ensemble_dir)
    folds: list[tuple[int, pd.DataFrame, pd.DataFrame]] = []
    for idx, fold_dir in enumerate(sorted(p for p in source.glob("fold_*") if p.is_dir()), start=1):
        tag = fold_dir.name.replace("fold_", "")
        fold_num = int(tag) if tag.isdigit() else idx
        calib_path = fold_dir / "calibration_predictions.csv"
        valid_path = fold_dir / "validation_predictions.csv"
        if calib_path.exists() and valid_path.exists():
            folds.append((fold_num, pd.read_csv(calib_path), pd.read_csv(valid_path)))
    if not folds:
        raise ValueError(f"no calibration/validation prediction pairs found in {source}")
    return folds


def run_fixed_template_audit(
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
    template_source: str = "first_fold",  # first_fold, all_calibrations
    selection_policy: str = "source_rank",  # source_rank, validation_rank
    min_source_trades: int = 8,
    top_k_templates: int = 50,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    gate_config: FixedTemplateGateConfig | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Freeze selective candidates before validation and audit whether any fixed template survives.

    V07 selected a candidate separately inside each fold.  This is a useful adaptive workflow, but
    it can hide instability when different folds pick incompatible rules.  This audit freezes a
    concrete candidate definition and applies it to every validation fold with no per-fold adaptation.
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
    gate_config = gate_config or FixedTemplateGateConfig()

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
    if selection_policy not in {"source_rank", "validation_rank"}:
        raise ValueError("selection_policy must be source_rank or validation_rank")
    if not templates:
        raise ValueError("no templates generated for fixed-template audit")

    template_rows: list[dict[str, object]] = []
    template_oof: dict[str, pd.DataFrame] = {}
    template_folds: dict[str, pd.DataFrame] = {}

    for rank, candidate in enumerate(templates, start=1):
        signature = candidate_signature(candidate)
        fold_records: list[dict[str, object]] = []
        validation_frames: list[pd.DataFrame] = []
        for fold_num, _calib, validation in folds:
            bt, metrics = backtest_selective_taker_bidask_non_overlapping(
                validation,
                candidate=candidate,
                cost_bps=cost_bps,
                horizon_sec=horizon_sec,
                latency_sec=latency_sec,
            )
            bt.insert(0, "fold", fold_num) if "fold" not in bt.columns else None
            bt["template_signature"] = signature
            validation_frames.append(bt)
            trades = bt.loc[bt["traded"] == 1, "net_pnl_bps"]
            boot = block_bootstrap_pnl(trades, iterations=300, block_size=10, seed=20260 + fold_num + rank)
            fold_records.append(
                {
                    "fold": fold_num,
                    "trades": float(metrics.get("trades", 0.0)),
                    "hit_rate": float(metrics.get("hit_rate", 0.0)),
                    "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
                    "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
                    "max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
                    "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0.0)),
                    "bootstrap_prob_mean_gt_0": float(boot.get("prob_mean_gt_0", 0.0)),
                }
            )
        folds_df = pd.DataFrame(fold_records)
        oof = pd.concat(validation_frames, ignore_index=True) if validation_frames else pd.DataFrame()
        aggregate = summarize_fixed_template_candidate(folds_df, oof)
        row = {
            "template_rank_in_source": rank,
            "template_signature": signature,
            "candidate_json": json.dumps(candidate.to_dict(), sort_keys=True),
            **_flatten_candidate(candidate),
            **aggregate,
        }
        template_rows.append(row)
        template_oof[signature] = oof
        template_folds[signature] = folds_df

    leaderboard = pd.DataFrame(template_rows)
    leaderboard = rank_fixed_template_leaderboard(leaderboard)
    leaderboard.to_csv(out / "fixed_template_leaderboard.csv", index=False)

    if leaderboard.empty:
        selected_row = {}
    elif selection_policy == "source_rank":
        source_ranked = leaderboard.sort_values(["template_rank_in_source", "v08_rank_score"], ascending=[True, False]).reset_index(drop=True)
        selected_row = source_ranked.iloc[0].to_dict()
    else:
        selected_row = leaderboard.iloc[0].to_dict()
    selected_candidate = candidate_from_signature(str(selected_row.get("template_signature")))
    selected_signature = candidate_signature(selected_candidate)
    selected_oof = template_oof[selected_signature]
    selected_folds = template_folds[selected_signature]
    selected_oof.to_csv(out / "selected_oof_backtest.csv", index=False)
    selected_folds.to_csv(out / "selected_fold_metrics.csv", index=False)
    (out / "selected_candidate.json").write_text(json.dumps(selected_candidate.to_dict(), indent=2), encoding="utf-8")

    stress = stress_fixed_signals(
        selected_oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    )
    stress.to_csv(out / "selected_fixed_signal_stress.csv", index=False)
    stress_gate = fixed_signal_robust_gate(stress, min_trades=max(1, gate_config.min_fold_trades))

    actual_repriced, actual_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        selected_oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    actual_repriced.to_csv(out / "selected_primary_repriced_backtest.csv", index=False)
    shift_null = shift_null_fixed_signals(
        selected_oof,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        shifts=80,
    )
    shift_null.to_csv(out / "selected_shift_null.csv", index=False)
    shift_summary = summarize_shift_null(actual_metrics, shift_null)
    aggregate = summarize_fixed_template_candidate(selected_folds, selected_oof)
    gate = evaluate_fixed_template_gate(
        aggregate=aggregate,
        stress_gate=stress_gate,
        shift_summary=shift_summary,
        gate_config=gate_config,
    )
    result = {
        "ensemble_dir": str(ensemble_dir),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "edge_thresholds": [float(x) for x in edge_thresholds],
        "signed_columns": signed_columns,
        "spread_quantiles": [float(x) for x in spread_quantiles],
        "vol_modes": list(vol_modes),
        "template_source": template_source,
        "selection_policy": selection_policy,
        "min_source_trades": int(min_source_trades),
        "top_k_templates": int(top_k_templates),
        "templates_tested": int(len(leaderboard)),
        "selected_candidate": selected_candidate.to_dict(),
        "aggregate": aggregate,
        "stress_gate": stress_gate,
        "shift_null": shift_summary,
        "gate_config": gate_config.to_dict(),
        "gate": gate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_fixed_template_report(out / "REPORT.md", result, leaderboard, selected_folds, stress)
    return result


def _build_template_pool(
    folds: list[tuple[int, pd.DataFrame, pd.DataFrame]],
    *,
    template_source: str,
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
    if template_source not in {"first_fold", "all_calibrations"}:
        raise ValueError("template_source must be first_fold or all_calibrations")
    pool: dict[str, tuple[SelectiveCandidate, float]] = {}
    source_folds = folds[:1] if template_source == "first_fold" else folds
    for fold_num, calibration, _validation in source_folds:
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
            # Fallback to raw generated grid, all with neutral source score.
            generated = generate_candidate_grid(
                calibration,
                edge_thresholds=edge_thresholds,
                signed_columns=signed_columns,
                spread_quantiles=spread_quantiles,
                vol_modes=vol_modes,
            )
            for c in generated:
                pool.setdefault(candidate_signature(c), (c, 0.0))
            continue
        for _, row in candidates.head(max(1, int(top_k_templates))).iterrows():
            candidate = SelectiveCandidate.from_dict(json.loads(str(row["candidate_json"])))
            sig = candidate_signature(candidate)
            score = float(row.get("rank_score", 0.0))
            if sig not in pool or score > pool[sig][1]:
                pool[sig] = (candidate, score)
    ranked = sorted(pool.values(), key=lambda item: item[1], reverse=True)
    return [candidate for candidate, _score in ranked[: max(1, int(top_k_templates))]]


def rank_fixed_template_leaderboard(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    f = frame.copy()
    for col in [
        "oof_mean_net_pnl_bps",
        "oof_total_net_pnl_bps",
        "fold_mean_net_pnl_bps_min",
        "fold_total_net_pnl_bps_min",
        "bootstrap_mean_p05_bps_min",
        "folds_with_trades",
        "oof_trades",
        "fold_trades_min",
    ]:
        if col not in f.columns:
            f[col] = 0.0
    f["meets_v08_trade_floor"] = (f["oof_trades"].astype(float) >= 20.0) & (f["fold_trades_min"].astype(float) >= 3.0)
    f["meets_v08_fold_profit_floor"] = f["fold_mean_net_pnl_bps_min"].astype(float) > 0.0
    f["v08_rank_score"] = (
        f["fold_mean_net_pnl_bps_min"].astype(float).clip(-20, 20)
        + 0.50 * f["oof_mean_net_pnl_bps"].astype(float).clip(-20, 20)
        + 0.002 * f["oof_total_net_pnl_bps"].astype(float).clip(-1000, 1000)
        + 0.05 * f["folds_with_trades"].astype(float).clip(0, 10)
        + 0.002 * f["oof_trades"].astype(float).clip(0, 500)
        + 0.30 * f["bootstrap_mean_p05_bps_min"].astype(float).clip(-20, 20)
    )
    return f.sort_values(
        ["meets_v08_trade_floor", "meets_v08_fold_profit_floor", "v08_rank_score", "fold_mean_net_pnl_bps_min", "oof_mean_net_pnl_bps", "oof_total_net_pnl_bps"],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)


def summarize_fixed_template_candidate(folds: pd.DataFrame, oof: pd.DataFrame) -> dict[str, object]:
    out: dict[str, object] = {}
    if not folds.empty:
        for col in ["trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps", "bootstrap_mean_p05_bps", "bootstrap_prob_mean_gt_0"]:
            values = pd.to_numeric(folds.get(col, pd.Series(dtype=float)), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            out[f"fold_{col}_mean"] = float(values.mean()) if len(values) else 0.0
            out[f"fold_{col}_min"] = float(values.min()) if len(values) else 0.0
        out["folds"] = int(len(folds))
        out["folds_with_trades"] = int((pd.to_numeric(folds["trades"], errors="coerce") > 0).sum()) if "trades" in folds.columns else 0
    trades = oof.loc[oof["traded"] == 1].copy() if "traded" in oof.columns else pd.DataFrame()
    out["oof_trades"] = int(len(trades))
    if len(trades):
        pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
        out["oof_total_net_pnl_bps"] = float(pnl.sum())
        out["oof_mean_net_pnl_bps"] = float(pnl.mean())
        out["oof_median_net_pnl_bps"] = float(pnl.median())
        out["oof_hit_rate"] = float((pnl > 0).mean())
        out["oof_profit_factor"] = _profit_factor(pnl)
        out["oof_long_trades"] = int((trades["signal"].astype(int) > 0).sum()) if "signal" in trades.columns else 0
        out["oof_short_trades"] = int((trades["signal"].astype(int) < 0).sum()) if "signal" in trades.columns else 0
        out["oof_max_drawdown_bps"] = _max_drawdown(pnl)
    else:
        out.update(
            {
                "oof_total_net_pnl_bps": 0.0,
                "oof_mean_net_pnl_bps": 0.0,
                "oof_median_net_pnl_bps": 0.0,
                "oof_hit_rate": 0.0,
                "oof_profit_factor": 0.0,
                "oof_long_trades": 0,
                "oof_short_trades": 0,
                "oof_max_drawdown_bps": 0.0,
            }
        )
    return out


def evaluate_fixed_template_gate(
    *,
    aggregate: dict[str, object],
    stress_gate: dict[str, object],
    shift_summary: dict[str, object],
    gate_config: FixedTemplateGateConfig,
) -> dict[str, object]:
    checks = {
        "enough_folds_with_trades": float(aggregate.get("folds_with_trades", 0)) >= gate_config.min_folds_with_trades,
        "enough_oof_trades": float(aggregate.get("oof_trades", 0)) >= gate_config.min_oof_trades,
        "enough_min_fold_trades": float(aggregate.get("fold_trades_min", 0.0)) >= gate_config.min_fold_trades,
        "positive_oof_mean": float(aggregate.get("oof_mean_net_pnl_bps", -999.0)) > gate_config.min_oof_mean_net_bps,
        "positive_fold_min_mean": float(aggregate.get("fold_mean_net_pnl_bps_min", -999.0)) > gate_config.min_fold_mean_net_bps,
        "positive_bootstrap_p05_min": float(aggregate.get("fold_bootstrap_mean_p05_bps_min", -999.0)) > gate_config.min_bootstrap_p05_bps,
        "shift_null_mean_ok": float(shift_summary.get("p_null_mean_ge_actual", 1.0)) <= gate_config.max_shift_null_p_mean,
        "shift_null_total_ok": float(shift_summary.get("p_null_total_ge_actual", 1.0)) <= gate_config.max_shift_null_p_total,
        "stress_gate_ok": bool(stress_gate.get("passed")) if gate_config.require_stress_gate else True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {"passed": not failed, "failed_checks": failed, "checks": checks}


def write_fixed_template_report(
    path: str | Path,
    result: dict[str, object],
    leaderboard: pd.DataFrame,
    selected_folds: pd.DataFrame,
    stress: pd.DataFrame,
) -> None:
    lines = [
        "# Research V08 Fixed-template Audit",
        "",
        "This report freezes a selective trading template before validation and applies the same rule to every validation fold.",
        "The goal is to detect fold-by-fold over-adaptation from V07's calibration-selected selective filters.",
        "",
        "## Run settings",
        "",
        "```json",
        json.dumps({k: result.get(k) for k in ["ensemble_dir", "horizon_sec", "cost_bps", "latency_sec", "template_source", "selection_policy", "templates_tested", "edge_thresholds", "signed_columns", "spread_quantiles", "vol_modes"]}, indent=2),
        "```",
        "",
        "## Selected candidate",
        "",
        "```json",
        json.dumps(result.get("selected_candidate", {}), indent=2),
        "```",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(result.get("aggregate", {}), indent=2),
        "```",
        "",
        "## Promotion gate",
        "",
        "```json",
        json.dumps(result.get("gate", {}), indent=2),
        "```",
        "",
        "## Shift null",
        "",
        "```json",
        json.dumps(result.get("shift_null", {}), indent=2),
        "```",
        "",
        "## Selected fold metrics",
        "",
    ]
    display_fold_cols = ["fold", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "bootstrap_mean_p05_bps"]
    lines.append(selected_folds[[c for c in display_fold_cols if c in selected_folds.columns]].to_markdown(index=False) if not selected_folds.empty else "No folds.")
    lines.extend(["", "## Stress sweep", ""])
    stress_cols = ["cost_bps", "latency_sec", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
    lines.append(stress[[c for c in stress_cols if c in stress.columns]].to_markdown(index=False) if not stress.empty else "No stress rows.")
    lines.extend(["", "## Top templates", ""])
    display_cols = [
        "v08_rank_score",
        "edge_threshold",
        "direction_mode",
        "signed_col",
        "signed_mode",
        "signed_abs_threshold",
        "oof_trades",
        "oof_hit_rate",
        "oof_mean_net_pnl_bps",
        "oof_total_net_pnl_bps",
        "fold_mean_net_pnl_bps_min",
        "fold_bootstrap_mean_p05_bps_min",
    ]
    existing = [c for c in display_cols if c in leaderboard.columns]
    lines.append(leaderboard[existing].head(20).to_markdown(index=False) if not leaderboard.empty else "No leaderboard rows.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "With `selection_policy=source_rank`, the selected candidate is the highest-ranked source-calibration template and validation results are out-of-sample for template selection. With `selection_policy=validation_rank`, the selected candidate is a diagnostic oracle over the tested validation folds and must be treated as data-snooped.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _flatten_candidate(candidate: SelectiveCandidate) -> dict[str, object]:
    return {k: v for k, v in candidate.to_dict().items()}


def _profit_factor(pnl: pd.Series) -> float:
    gains = float(pnl[pnl > 0].sum())
    losses = float(-pnl[pnl < 0].sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _max_drawdown(pnl: pd.Series) -> float:
    if len(pnl) == 0:
        return 0.0
    equity = pnl.cumsum().to_numpy(dtype=float)
    running_max = np.maximum.accumulate(equity)
    dd = equity - running_max
    return float(dd.min())
