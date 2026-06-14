from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .fixed_template import load_ensemble_fold_predictions
from .selective import (
    DEFAULT_SIGNED_COLUMNS,
    SelectiveCandidate,
    aggregate_selective_folds,
    backtest_fixed_signals_taker_bidask_non_overlapping,
    backtest_selective_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    generate_candidate_grid,
    shift_null_fixed_signals,
    stress_fixed_signals,
    summarize_shift_null,
)
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class FamilySpec:
    """A deployable selective-rule family.

    The family freezes the qualitative shape of the rule before validation.  Each fold may still
    choose numeric thresholds from its past calibration window only.  This is less rigid than V08's
    fully fixed template, but avoids selecting a new qualitative rule after seeing validation data.
    """

    direction_mode: str = "any"  # any, normal, invert
    signed_col: str | None = None  # None means any available signed column
    signed_mode: str = "any"  # any, none, agree, disagree

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_candidate(cls, candidate: SelectiveCandidate) -> "FamilySpec":
        return cls(
            direction_mode=str(candidate.direction_mode or "any"),
            signed_col=candidate.signed_col,
            signed_mode=str(candidate.signed_mode or "any"),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "FamilySpec":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if "selected_candidate" in payload and isinstance(payload["selected_candidate"], dict):
            payload = payload["selected_candidate"]
        candidate_fields = {"edge_threshold", "direction_mode", "signed_col", "signed_mode", "signed_abs_threshold"}
        if candidate_fields.intersection(payload):
            return cls.from_candidate(SelectiveCandidate.from_dict(payload))
        return cls(**{k: v for k, v in payload.items() if k in {"direction_mode", "signed_col", "signed_mode"}})


def run_family_adaptive_audit(
    *,
    ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    family: FamilySpec,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    edge_thresholds: list[float] | None = None,
    signed_abs_quantiles: list[float] | None = None,
    spread_quantiles: list[float] | None = None,
    vol_modes: list[str] | None = None,
    min_calibration_trades: int = 8,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 80,
    clean: bool = False,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    edge_thresholds = edge_thresholds or [0.1, 0.2, 0.3, 0.5, 0.7]
    signed_abs_quantiles = signed_abs_quantiles or [0.0, 0.5, 0.75]
    spread_quantiles = spread_quantiles or [1.0]
    vol_modes = vol_modes or ["none"]
    stress_cost_bps_values = stress_cost_bps_values or [1.5, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0]

    folds = load_ensemble_fold_predictions(ensemble_dir)
    fold_rows: list[dict[str, object]] = []
    candidate_rows: list[pd.DataFrame] = []
    validation_frames: list[pd.DataFrame] = []

    for fold_num, calibration, validation in folds:
        candidates = search_family_candidates(
            calibration,
            family=family,
            edge_thresholds=edge_thresholds,
            signed_abs_quantiles=signed_abs_quantiles,
            spread_quantiles=spread_quantiles,
            vol_modes=vol_modes,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
            min_trades=min_calibration_trades,
        )
        if candidates.empty:
            selected = _fallback_candidate(calibration, family=family, edge_thresholds=edge_thresholds, signed_abs_quantiles=signed_abs_quantiles)
            candidates = pd.DataFrame([{**_candidate_fields(selected), "rank_score": 0.0, "meets_min_trades": False, "candidate_json": json.dumps(selected.to_dict(), sort_keys=True)}])
        else:
            selected = SelectiveCandidate.from_dict(json.loads(str(candidates.iloc[0]["candidate_json"])))
        candidates.insert(0, "fold", fold_num)
        candidate_rows.append(candidates)

        bt, metrics = backtest_selective_taker_bidask_non_overlapping(
            validation,
            candidate=selected,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
        )
        if "fold" in bt.columns:
            bt["fold"] = fold_num
        else:
            bt.insert(0, "fold", fold_num)
        bt["family_json"] = json.dumps(family.to_dict(), sort_keys=True)
        bt["selected_candidate_json"] = json.dumps(selected.to_dict(), sort_keys=True)
        validation_frames.append(bt)

        trades = bt.loc[bt["traded"] == 1, "net_pnl_bps"] if "traded" in bt.columns else pd.Series(dtype=float)
        boot = block_bootstrap_pnl(trades, iterations=500, block_size=10, seed=30900 + int(fold_num))
        fold_rows.append(
            {
                "fold": fold_num,
                "calibration_candidates": int(len(candidates)),
                "selected_candidate_json": json.dumps(selected.to_dict(), sort_keys=True),
                "selected_edge_threshold": float(selected.edge_threshold),
                "selected_direction_mode": selected.direction_mode,
                "selected_signed_col": selected.signed_col,
                "selected_signed_mode": selected.signed_mode,
                "selected_signed_abs_threshold": float(selected.signed_abs_threshold or 0.0),
                "selected_spread_max_bps": selected.spread_max_bps,
                "selected_vol_mode": selected.vol_mode,
                "valid_trades": float(metrics.get("trades", 0.0)),
                "valid_hit_rate": float(metrics.get("hit_rate", 0.0)),
                "valid_mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
                "valid_total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
                "valid_max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
                "bootstrap_mean_p05_bps": float(boot.get("mean_p05_bps", 0.0)),
                "bootstrap_prob_mean_gt_0": float(boot.get("prob_mean_gt_0", 0.0)),
            }
        )

    folds_df = pd.DataFrame(fold_rows)
    candidates_df = pd.concat(candidate_rows, ignore_index=True) if candidate_rows else pd.DataFrame()
    oof = pd.concat(validation_frames, ignore_index=True) if validation_frames else pd.DataFrame()
    folds_df.to_csv(out / "fold_metrics.csv", index=False)
    candidates_df.to_csv(out / "family_calibration_candidates.csv", index=False)
    oof.to_csv(out / "oof_family_adaptive_backtest.csv", index=False)

    stress = stress_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    ) if not oof.empty else pd.DataFrame()
    stress.to_csv(out / "oof_fixed_signal_stress.csv", index=False)
    robust_gate = fixed_signal_robust_gate(stress, min_trades=max(1, min_calibration_trades)) if not stress.empty else {"passed": False, "reason": "empty stress"}

    actual_repriced, actual_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    ) if not oof.empty else (pd.DataFrame(), {})
    actual_repriced.to_csv(out / "oof_primary_repriced_backtest.csv", index=False)
    shift_null = shift_null_fixed_signals(
        oof,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        shifts=shift_null_runs,
    ) if not oof.empty else pd.DataFrame()
    shift_null.to_csv(out / "shift_null_fixed_signals.csv", index=False)
    shift_summary = summarize_shift_null(actual_metrics, shift_null)

    aggregate = aggregate_selective_folds(folds_df, oof, stress, robust_gate)
    aggregate.update({f"shift_null_{k}": v for k, v in shift_summary.items()})
    gate = evaluate_family_gate(aggregate=aggregate, robust_gate=robust_gate, min_calibration_trades=min_calibration_trades)
    result = {
        "source_ensemble_dir": str(ensemble_dir),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "family": family.to_dict(),
        "edge_thresholds": [float(x) for x in edge_thresholds],
        "signed_abs_quantiles": [float(x) for x in signed_abs_quantiles],
        "spread_quantiles": [float(x) for x in spread_quantiles],
        "vol_modes": list(vol_modes),
        "min_calibration_trades": int(min_calibration_trades),
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "folds": int(len(folds_df)),
        "aggregate": aggregate,
        "robust_gate": robust_gate,
        "gate": gate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_family_adaptive_report(out / "REPORT.md", result, folds_df, stress)
    return result


def search_family_candidates(
    calibration: pd.DataFrame,
    *,
    family: FamilySpec,
    edge_thresholds: list[float],
    signed_abs_quantiles: list[float],
    spread_quantiles: list[float],
    vol_modes: list[str],
    cost_bps: float,
    horizon_sec: float,
    latency_sec: float,
    min_trades: int,
) -> pd.DataFrame:
    signed_columns = _family_signed_columns(calibration, family)
    direction_modes = [family.direction_mode] if family.direction_mode in {"normal", "invert"} else ["normal", "invert"]
    signed_modes = [family.signed_mode] if family.signed_mode in {"none", "agree", "disagree"} else ["agree", "disagree"]
    if signed_modes == ["none"]:
        signed_columns = []
    candidates = generate_candidate_grid(
        calibration,
        edge_thresholds=edge_thresholds,
        signed_columns=signed_columns,
        signed_abs_quantiles=signed_abs_quantiles,
        signed_modes=signed_modes if signed_columns else ["none"],
        spread_quantiles=spread_quantiles,
        vol_modes=vol_modes,
        direction_modes=direction_modes,
    )
    rows: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates):
        if not _candidate_matches_family(candidate, family):
            continue
        _, metrics = backtest_selective_taker_bidask_non_overlapping(
            calibration,
            candidate=candidate,
            cost_bps=cost_bps,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
        )
        row = {
            "candidate_id": idx,
            **_candidate_fields(candidate),
            **metrics,
            "candidate_json": json.dumps(candidate.to_dict(), sort_keys=True),
        }
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["meets_min_trades"] = out["trades"].astype(float) >= float(min_trades)
    out["rank_score"] = (
        out["mean_net_pnl_bps"].astype(float).clip(-20, 20)
        + 0.003 * out["total_net_pnl_bps"].astype(float).clip(-2000, 2000)
        + 0.10 * out["hit_rate"].astype(float)
        - 0.01 * out["max_drawdown_bps"].astype(float).abs().clip(0, 1000)
        + 0.002 * out["trades"].astype(float).clip(0, 300)
    )
    return out.sort_values(["meets_min_trades", "rank_score", "mean_net_pnl_bps", "total_net_pnl_bps"], ascending=[False, False, False, False]).reset_index(drop=True)


def evaluate_family_gate(*, aggregate: dict[str, object], robust_gate: dict[str, object], min_calibration_trades: int) -> dict[str, object]:
    checks = {
        "enough_oof_trades": float(aggregate.get("oof_trades", 0)) >= 20.0,
        "enough_min_fold_trades": float(aggregate.get("valid_trades_min", 0.0)) >= max(3.0, float(min_calibration_trades) / 2.0),
        "positive_oof_mean": float(aggregate.get("oof_mean_net_pnl_bps", -999.0)) > 0.0,
        "positive_fold_min_mean": float(aggregate.get("valid_mean_net_pnl_bps_min", -999.0)) > 0.0,
        "positive_bootstrap_p05_min": float(aggregate.get("bootstrap_mean_p05_bps_min", -999.0)) > 0.0,
        "robust_stress_gate": bool(robust_gate.get("passed")),
        "shift_null_mean_ok": float(aggregate.get("shift_null_p_null_mean_ge_actual", 1.0)) <= 0.10,
        "shift_null_total_ok": float(aggregate.get("shift_null_p_null_total_ge_actual", 1.0)) <= 0.10,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {"passed": not failed, "failed_checks": failed, "checks": checks}


def write_family_adaptive_report(path: str | Path, result: dict[str, object], folds: pd.DataFrame, stress: pd.DataFrame) -> None:
    lines = [
        "# Research V09 Family-adaptive Audit",
        "",
        "This report freezes the qualitative selective-trading family before validation, then lets each fold tune numeric thresholds using that fold's past calibration window only.",
        "This sits between V07 fold-local adaptive filters and V08 fully fixed templates.",
        "",
        "## Settings",
        "",
        "```json",
        json.dumps({k: result.get(k) for k in ["source_ensemble_dir", "horizon_sec", "cost_bps", "latency_sec", "family", "edge_thresholds", "signed_abs_quantiles", "spread_quantiles", "vol_modes"]}, indent=2),
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
        "## Fold metrics",
        "",
    ]
    fold_cols = [
        "fold",
        "selected_edge_threshold",
        "selected_direction_mode",
        "selected_signed_col",
        "selected_signed_mode",
        "selected_signed_abs_threshold",
        "valid_trades",
        "valid_hit_rate",
        "valid_mean_net_pnl_bps",
        "valid_total_net_pnl_bps",
        "bootstrap_mean_p05_bps",
    ]
    lines.append(folds[[c for c in fold_cols if c in folds.columns]].to_markdown(index=False) if not folds.empty else "No folds.")
    lines.extend(["", "## Stress", ""])
    stress_cols = ["cost_bps", "latency_sec", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
    lines.append(stress[[c for c in stress_cols if c in stress.columns]].to_markdown(index=False) if not stress.empty else "No stress rows.")
    lines.extend(["", "## Interpretation", "", "Passing this audit would mean the rule family transfers while its numeric thresholds can adapt to local market state using past data only. Failing this audit means the oracle-looking V08 template has not become a reusable family."])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _family_signed_columns(calibration: pd.DataFrame, family: FamilySpec) -> list[str]:
    if family.signed_col:
        return [family.signed_col] if family.signed_col in calibration.columns and not str(family.signed_col).startswith("future_") else []
    return [c for c in DEFAULT_SIGNED_COLUMNS if c in calibration.columns and not c.startswith("future_")]


def _candidate_matches_family(candidate: SelectiveCandidate, family: FamilySpec) -> bool:
    if family.direction_mode in {"normal", "invert"} and candidate.direction_mode != family.direction_mode:
        return False
    if family.signed_col and candidate.signed_col != family.signed_col:
        return False
    if family.signed_mode in {"none", "agree", "disagree"} and candidate.signed_mode != family.signed_mode:
        return False
    return True


def _fallback_candidate(calibration: pd.DataFrame, *, family: FamilySpec, edge_thresholds: list[float], signed_abs_quantiles: list[float]) -> SelectiveCandidate:
    signed_col = family.signed_col if family.signed_col in calibration.columns else None
    signed_abs = 0.0
    if signed_col:
        vals = pd.to_numeric(calibration[signed_col], errors="coerce").replace([np.inf, -np.inf], np.nan).abs().dropna()
        if len(vals):
            signed_abs = float(vals.quantile(float(signed_abs_quantiles[0])))
    return SelectiveCandidate(
        edge_threshold=float(edge_thresholds[0]),
        direction_mode=family.direction_mode if family.direction_mode in {"normal", "invert"} else "normal",
        signed_col=signed_col,
        signed_mode=family.signed_mode if family.signed_mode in {"none", "agree", "disagree"} else ("agree" if signed_col else "none"),
        signed_abs_threshold=signed_abs,
    )


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
