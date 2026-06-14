from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .backtest import summarize_trades
from .execution import backtest_taker_bidask_non_overlapping, robust_profit_gate
from .kline_features import parse_timeframe_seconds
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class KlineWeightGateConfig:
    min_oof_trades: int = 20
    min_folds_with_trades: int = 5
    min_fold_mean_net_bps: float = 0.0
    min_bootstrap_p05_bps: float = 0.0
    max_shift_null_p_total: float = 0.10
    max_shift_null_p_mean: float = 0.10
    require_stress_gate: bool = True


def run_kline_weight_audit(
    *,
    ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    edge_thresholds: list[float] | None = None,
    base_weight_values: list[float] | None = None,
    kline_signs: list[int] | None = None,
    min_calibration_trades: int = 4,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 80,
    gate_config: KlineWeightGateConfig | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Learn fold-local weights for base probability edge plus K-line timeframe signals.

    The training contract is intentionally conservative:
    weights and the execution edge are selected on each fold's calibration file,
    then frozen before validation.  No validation rows are used to choose weights.
    """
    src = Path(ensemble_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    edge_thresholds = edge_thresholds or [0.05, 0.1, 0.2, 0.3, 0.5]
    base_weight_values = base_weight_values or [0.0, 0.25, 0.5, 0.75, 1.0]
    kline_signs = kline_signs or [-1, 1]
    stress_cost_bps_values = stress_cost_bps_values or [cost_bps, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, latency_sec, 1.0, 2.0]
    gate_config = gate_config or KlineWeightGateConfig()

    fold_dirs = sorted([p for p in src.glob("fold_*") if p.is_dir()])
    if not fold_dirs:
        raise ValueError(f"no fold directories found in {src}")

    fold_records: list[dict[str, object]] = []
    weight_records: list[dict[str, object]] = []
    validation_frames: list[pd.DataFrame] = []
    primary_bt_frames: list[pd.DataFrame] = []
    selected_by_fold: dict[int, dict[str, object]] = {}

    for fold_dir in fold_dirs:
        fold_num = int(str(fold_dir.name).split("_")[-1])
        calib_path = fold_dir / "calibration_predictions.csv"
        valid_path = fold_dir / "validation_predictions.csv"
        if not calib_path.exists() or not valid_path.exists():
            continue
        calib = pd.read_csv(calib_path)
        valid = pd.read_csv(valid_path)
        signal_cols = detect_kline_signal_columns(calib)
        if not signal_cols:
            raise ValueError(f"{calib_path} has no kline_*_signal columns; rerun ensemble with --kline-timeframes")
        candidates = generate_weight_candidates(signal_cols, base_weight_values=base_weight_values, kline_signs=kline_signs)
        scored = score_weight_candidates(
            calib,
            candidates=candidates,
            edge_thresholds=edge_thresholds,
            horizon_sec=horizon_sec,
            cost_bps=cost_bps,
            latency_sec=latency_sec,
            min_trades=min_calibration_trades,
        )
        scored.to_csv(out / f"fold_{fold_num:02d}_calibration_weight_sweep.csv", index=False)
        feasible = scored[scored["trades"].astype(float) >= float(min_calibration_trades)].copy()
        selected = feasible.head(1) if not feasible.empty else scored.head(1)
        if selected.empty:
            raise ValueError(f"no kline weight candidates scored for fold {fold_num}")
        row = selected.iloc[0].to_dict()
        weights = json.loads(str(row["weights_json"]))
        selected_edge = float(row["edge_threshold"])
        adjusted_valid = apply_kline_weights(valid, weights=weights)
        if "fold" in adjusted_valid.columns:
            adjusted_valid["fold"] = fold_num
        else:
            adjusted_valid.insert(0, "fold", fold_num)
        adjusted_valid["selected_edge_threshold"] = selected_edge
        adjusted_valid["selected_weights_json"] = json.dumps(weights, sort_keys=True)
        bt_frame, bt = backtest_taker_bidask_non_overlapping(
            adjusted_valid,
            cost_bps=cost_bps,
            edge_threshold=selected_edge,
            horizon_sec=horizon_sec,
            latency_sec=latency_sec,
        )
        fold_out = out / f"fold_{fold_num:02d}"
        fold_out.mkdir(exist_ok=True)
        adjusted_valid.to_csv(fold_out / "validation_predictions_kline_weighted.csv", index=False)
        bt_frame.to_csv(fold_out / "validation_taker_backtest_kline_weighted.csv", index=False)
        validation_frames.append(adjusted_valid)
        primary_bt_frames.append(bt_frame)
        trades = bt_frame[bt_frame["traded"] == 1]
        boot = block_bootstrap_pnl(trades["net_pnl_bps"], iterations=500, block_size=10, seed=13000 + fold_num)
        acc_all = _accuracy(adjusted_valid)
        traded_idx = bt_frame["traded"].astype(int) == 1
        acc_traded = _accuracy(adjusted_valid.loc[traded_idx]) if traded_idx.any() else 0.0
        rec = {
            "fold": fold_num,
            "signal_columns": json.dumps(signal_cols),
            "candidate_count": int(len(scored)),
            "selected_edge_threshold": selected_edge,
            "selected_weights_json": json.dumps(weights, sort_keys=True),
            "calib_trades": _float(row.get("trades")),
            "calib_mean_net_pnl_bps": _float(row.get("mean_net_pnl_bps")),
            "calib_total_net_pnl_bps": _float(row.get("total_net_pnl_bps")),
            "valid_trades": _float(bt.get("trades")),
            "valid_hit_rate": _float(bt.get("hit_rate")),
            "valid_mean_net_pnl_bps": _float(bt.get("mean_net_pnl_bps")),
            "valid_total_net_pnl_bps": _float(bt.get("total_net_pnl_bps")),
            "valid_max_drawdown_bps": _float(bt.get("max_drawdown_bps")),
            "accuracy_all": acc_all,
            "accuracy_traded": acc_traded,
            "bootstrap_mean_p05_bps": _float(boot.get("mean_p05_bps")),
            "bootstrap_prob_mean_gt_0": _float(boot.get("prob_mean_gt_0")),
        }
        fold_records.append(rec)
        for key, val in weights.items():
            weight_records.append({"fold": fold_num, "feature": key, "weight": float(val)})
        selected_by_fold[fold_num] = {"weights": weights, "edge_threshold": selected_edge}

    folds_df = pd.DataFrame(fold_records).sort_values("fold") if fold_records else pd.DataFrame()
    weights_df = pd.DataFrame(weight_records).sort_values(["fold", "feature"]) if weight_records else pd.DataFrame()
    oof_bt = pd.concat(primary_bt_frames, ignore_index=True) if primary_bt_frames else pd.DataFrame()
    oof_pred = pd.concat(validation_frames, ignore_index=True) if validation_frames else pd.DataFrame()
    folds_df.to_csv(out / "fold_metrics.csv", index=False)
    weights_df.to_csv(out / "selected_kline_weights_by_fold.csv", index=False)
    oof_bt.to_csv(out / "oof_taker_backtest.csv", index=False)
    oof_pred.to_csv(out / "oof_predictions_kline_weighted.csv", index=False)

    stress = stress_selected_folds(
        validation_frames,
        selected_by_fold=selected_by_fold,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    )
    stress.to_csv(out / "oof_taker_stress_sweep.csv", index=False)
    stress_gate = robust_profit_gate(stress, min_trades=max(1, int(gate_config.min_oof_trades)), group_col="selected_policy") if not stress.empty else {"passed": False, "reason": "empty stress"}
    shift_null = shifted_signal_null(
        validation_frames,
        selected_by_fold=selected_by_fold,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        runs=shift_null_runs,
        actual_frame=oof_bt,
        seed=9917,
    )
    aggregate = aggregate_kline_weight_results(folds_df, oof_bt, stress, stress_gate, shift_null, gate_config)
    result: dict[str, object] = {
        "ensemble_dir": str(src),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "edge_thresholds": [float(x) for x in edge_thresholds],
        "base_weight_values": [float(x) for x in base_weight_values],
        "kline_signs": [int(x) for x in kline_signs],
        "min_calibration_trades": int(min_calibration_trades),
        "stress_cost_bps_values": [float(x) for x in stress_cost_bps_values],
        "stress_latency_sec_values": [float(x) for x in stress_latency_sec_values],
        "shift_null_runs": int(shift_null_runs),
        "gate_config": gate_config.__dict__,
        "aggregate": aggregate,
        "stress_gate": stress_gate,
        "shift_null": shift_null,
        "selected_by_fold": selected_by_fold,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_kline_weight_report(out / "REPORT.md", result, folds_df, weights_df, stress)
    return result


def detect_kline_signal_columns(frame: pd.DataFrame) -> list[str]:
    cols = [c for c in frame.columns if c.startswith("kline_") and c.endswith("_signal")]
    return sorted(cols, key=_signal_sort_key)


def generate_weight_candidates(
    signal_cols: list[str],
    *,
    base_weight_values: list[float],
    kline_signs: list[int],
) -> list[dict[str, float]]:
    cols = list(signal_cols)
    profiles: list[dict[str, float]] = []
    if cols:
        profiles.append({c: 1.0 / len(cols) for c in cols})
        for c in cols:
            profiles.append({c: 1.0})
        denom_short = sum(1.0 / (i + 1) for i in range(len(cols)))
        profiles.append({c: (1.0 / (i + 1)) / denom_short for i, c in enumerate(cols)})
        denom_long = sum(float(i + 1) for i in range(len(cols)))
        profiles.append({c: float(i + 1) / denom_long for i, c in enumerate(cols)})
    out: list[dict[str, float]] = []
    seen: set[str] = set()
    for bw in base_weight_values:
        bw = float(bw)
        if bw < 0 or bw > 1:
            continue
        if bw >= 0.999 or not profiles:
            cand = {"base": 1.0}
            key = json.dumps(cand, sort_keys=True)
            if key not in seen:
                out.append(cand)
                seen.add(key)
            continue
        for profile in profiles:
            for sign in kline_signs:
                cand = {"base": bw}
                remain = 1.0 - bw
                for col, val in profile.items():
                    cand[col] = float(sign) * remain * float(val)
                total = sum(abs(v) for v in cand.values())
                if total > 0:
                    cand = {k: float(v) / total for k, v in cand.items()}
                key = json.dumps(cand, sort_keys=True)
                if key not in seen:
                    out.append(cand)
                    seen.add(key)
    return out


def score_weight_candidates(
    frame: pd.DataFrame,
    *,
    candidates: list[dict[str, float]],
    edge_thresholds: list[float],
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
    min_trades: int,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for idx, weights in enumerate(candidates):
        adjusted = apply_kline_weights(frame, weights=weights)
        for edge in edge_thresholds:
            _, metrics = backtest_taker_bidask_non_overlapping(
                adjusted,
                cost_bps=cost_bps,
                edge_threshold=float(edge),
                horizon_sec=horizon_sec,
                latency_sec=latency_sec,
            )
            rec = {**metrics, "candidate_id": int(idx), "weights_json": json.dumps(weights, sort_keys=True)}
            rec["eligible"] = bool(float(metrics.get("trades", 0.0)) >= float(min_trades))
            rec["rank_score"] = _rank_score(metrics)
            records.append(rec)
    out = pd.DataFrame(records)
    if out.empty:
        return out
    return out.sort_values(["eligible", "rank_score", "total_net_pnl_bps"], ascending=[False, False, False]).reset_index(drop=True)


def apply_kline_weights(frame: pd.DataFrame, *, weights: dict[str, float]) -> pd.DataFrame:
    out = frame.copy()
    if "prob_edge" in out.columns:
        base_edge = pd.to_numeric(out["prob_edge"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    else:
        base_edge = (pd.to_numeric(out.get("prob_up", 0.0), errors="coerce").fillna(0.0) - pd.to_numeric(out.get("prob_down", 0.0), errors="coerce").fillna(0.0)).to_numpy(dtype=float)
    edge = np.zeros(len(out), dtype=float)
    for key, weight in weights.items():
        w = float(weight)
        if key == "base":
            edge += w * base_edge
        elif key in out.columns:
            edge += w * pd.to_numeric(out[key], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    edge = np.clip(edge, -0.999, 0.999)
    out["prob_edge_base"] = base_edge
    out["prob_edge_kline_weighted"] = edge
    out["prob_edge"] = edge
    out["prob_up"] = np.clip(0.5 + edge / 2.0, 0.0, 1.0)
    out["prob_down"] = np.clip(0.5 - edge / 2.0, 0.0, 1.0)
    out["prob_flat"] = np.maximum(0.0, 1.0 - out["prob_up"] - out["prob_down"])
    out["pred_label"] = np.sign(edge).astype(int)
    out["prob_confidence"] = out[["prob_down", "prob_flat", "prob_up"]].max(axis=1)
    return out


def stress_selected_folds(
    validation_frames: list[pd.DataFrame],
    *,
    selected_by_fold: dict[int, dict[str, object]],
    horizon_sec: float,
    cost_bps_values: list[float],
    latency_sec_values: list[float],
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for cost in cost_bps_values:
        for latency in latency_sec_values:
            frames: list[pd.DataFrame] = []
            for valid in validation_frames:
                if valid.empty or "fold" not in valid.columns:
                    continue
                fold = int(valid["fold"].iloc[0])
                spec = selected_by_fold.get(fold)
                if not spec:
                    continue
                bt, _ = backtest_taker_bidask_non_overlapping(
                    valid,
                    cost_bps=float(cost),
                    edge_threshold=float(spec["edge_threshold"]),
                    horizon_sec=horizon_sec,
                    latency_sec=float(latency),
                )
                frames.append(bt)
            combo = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            metrics = summarize_trades(combo) if not combo.empty else {"events": 0.0, "trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0, "max_drawdown_bps": 0.0}
            metrics.update({"cost_bps": float(cost), "latency_sec": float(latency), "selected_policy": 1.0, "mode": "kline_weighted_selected"})
            metrics["rank_score"] = _rank_score(metrics)
            records.append(metrics)
    return pd.DataFrame(records).sort_values(["rank_score", "total_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)


def shifted_signal_null(
    validation_frames: list[pd.DataFrame],
    *,
    selected_by_fold: dict[int, dict[str, object]],
    horizon_sec: float,
    cost_bps: float,
    latency_sec: float,
    runs: int,
    actual_frame: pd.DataFrame,
    seed: int = 123,
) -> dict[str, object]:
    trades = actual_frame[actual_frame.get("traded", 0) == 1] if not actual_frame.empty else pd.DataFrame()
    actual_total = float(trades["net_pnl_bps"].sum()) if not trades.empty else 0.0
    actual_mean = float(trades["net_pnl_bps"].mean()) if not trades.empty else 0.0
    rng = np.random.default_rng(seed)
    totals: list[float] = []
    means: list[float] = []
    for _ in range(int(runs)):
        frames: list[pd.DataFrame] = []
        for valid in validation_frames:
            if valid.empty or "fold" not in valid.columns:
                continue
            fold = int(valid["fold"].iloc[0])
            spec = selected_by_fold.get(fold)
            if not spec:
                continue
            shifted = _shift_edge(valid, rng=rng)
            bt, _ = backtest_taker_bidask_non_overlapping(
                shifted,
                cost_bps=cost_bps,
                edge_threshold=float(spec["edge_threshold"]),
                horizon_sec=horizon_sec,
                latency_sec=latency_sec,
            )
            frames.append(bt)
        combo = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        m = summarize_trades(combo) if not combo.empty else {"total_net_pnl_bps": 0.0, "mean_net_pnl_bps": 0.0}
        totals.append(float(m.get("total_net_pnl_bps", 0.0)))
        means.append(float(m.get("mean_net_pnl_bps", 0.0)))
    totals_arr = np.asarray(totals, dtype=float)
    means_arr = np.asarray(means, dtype=float)
    return {
        "runs": int(runs),
        "actual_total_net_pnl_bps": actual_total,
        "actual_mean_net_pnl_bps": actual_mean,
        "p_total_ge_actual": float((1.0 + np.sum(totals_arr >= actual_total)) / (len(totals_arr) + 1.0)) if len(totals_arr) else 1.0,
        "p_mean_ge_actual": float((1.0 + np.sum(means_arr >= actual_mean)) / (len(means_arr) + 1.0)) if len(means_arr) else 1.0,
        "null_total_p95_bps": float(np.quantile(totals_arr, 0.95)) if len(totals_arr) else 0.0,
        "null_mean_p95_bps": float(np.quantile(means_arr, 0.95)) if len(means_arr) else 0.0,
    }


def aggregate_kline_weight_results(
    folds_df: pd.DataFrame,
    oof: pd.DataFrame,
    stress: pd.DataFrame,
    stress_gate: dict[str, object],
    shift_null: dict[str, object],
    gate_config: KlineWeightGateConfig,
) -> dict[str, object]:
    out: dict[str, object] = {}
    if not folds_df.empty:
        for col in ["valid_trades", "valid_hit_rate", "valid_mean_net_pnl_bps", "valid_total_net_pnl_bps", "valid_max_drawdown_bps", "accuracy_all", "accuracy_traded", "bootstrap_mean_p05_bps"]:
            if col in folds_df.columns:
                out[f"{col}_mean"] = _finite_mean(folds_df[col])
                out[f"{col}_min"] = _finite_min(folds_df[col])
        out["folds_with_trades"] = int((folds_df.get("valid_trades", pd.Series(dtype=float)).astype(float) > 0).sum())
    trades = oof[oof.get("traded", 0) == 1] if not oof.empty else pd.DataFrame()
    out["trades"] = int(len(trades))
    out["total_net_pnl_bps"] = float(trades["net_pnl_bps"].sum()) if len(trades) else 0.0
    out["mean_net_pnl_bps"] = float(trades["net_pnl_bps"].mean()) if len(trades) else 0.0
    out["hit_rate"] = float((trades["net_pnl_bps"] > 0).mean()) if len(trades) else 0.0
    boot = block_bootstrap_pnl(trades["net_pnl_bps"], iterations=1000, block_size=10, seed=777) if len(trades) else {"mean_p05_bps": 0.0, "prob_mean_gt_0": 0.0}
    out["bootstrap_mean_p05_bps"] = _float(boot.get("mean_p05_bps"))
    out["bootstrap_prob_mean_gt_0"] = _float(boot.get("prob_mean_gt_0"))
    if not stress.empty:
        out["stress_min_mean_net_pnl_bps"] = _finite_min(stress["mean_net_pnl_bps"])
        out["stress_min_total_net_pnl_bps"] = _finite_min(stress["total_net_pnl_bps"])
    checks = {
        "enough_oof_trades": out["trades"] >= int(gate_config.min_oof_trades),
        "enough_folds_with_trades": out.get("folds_with_trades", 0) >= int(gate_config.min_folds_with_trades),
        "positive_fold_min_mean": out.get("valid_mean_net_pnl_bps_min", -999.0) >= float(gate_config.min_fold_mean_net_bps),
        "positive_bootstrap_p05": out.get("bootstrap_mean_p05_bps", -999.0) > float(gate_config.min_bootstrap_p05_bps),
        "stress_gate_ok": (not gate_config.require_stress_gate) or bool(stress_gate.get("passed")),
        "shift_null_total_ok": float(shift_null.get("p_total_ge_actual", 1.0)) <= float(gate_config.max_shift_null_p_total),
        "shift_null_mean_ok": float(shift_null.get("p_mean_ge_actual", 1.0)) <= float(gate_config.max_shift_null_p_mean),
    }
    failed = [k for k, v in checks.items() if not bool(v)]
    out["gate"] = {"passed": len(failed) == 0, "checks": checks, "failed_checks": failed}
    return out


def write_kline_weight_report(path: str | Path, result: dict[str, object], folds_df: pd.DataFrame, weights_df: pd.DataFrame, stress: pd.DataFrame) -> None:
    agg = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    lines = [
        "# V13 K-line Weighted Edge Audit",
        "",
        f"Source ensemble: `{result.get('ensemble_dir')}`",
        f"Horizon seconds: {result.get('horizon_sec')}",
        f"Cost bps: {result.get('cost_bps')}",
        f"Latency seconds: {result.get('latency_sec')}",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(agg, indent=2),
        "```",
        "",
        "## Fold metrics",
        "",
    ]
    display_cols = ["fold", "selected_edge_threshold", "valid_trades", "valid_hit_rate", "valid_mean_net_pnl_bps", "valid_total_net_pnl_bps", "accuracy_all", "accuracy_traded", "bootstrap_mean_p05_bps", "selected_weights_json"]
    existing = [c for c in display_cols if c in folds_df.columns]
    lines.append(folds_df[existing].to_markdown(index=False) if not folds_df.empty else "No folds.")
    lines.extend(["", "## Selected weights", ""])
    if not weights_df.empty:
        pivot = weights_df.pivot_table(index="fold", columns="feature", values="weight", aggfunc="first").fillna(0.0).reset_index()
        lines.append(pivot.to_markdown(index=False))
    else:
        lines.append("No weights.")
    lines.extend(["", "## Shift null", "", "```json", json.dumps(result.get("shift_null", {}), indent=2), "```", ""])
    if not stress.empty:
        cols = ["cost_bps", "latency_sec", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
        lines.extend(["## Stress", "", stress[[c for c in cols if c in stress.columns]].to_markdown(index=False), ""])
    lines.extend([
        "## Interpretation",
        "",
        "Weights are selected only on each fold's calibration predictions and then frozen for validation.  This audit can show whether K-line timeframe signals help the existing H90 edge, but it is still a single-day research test unless rerun across independent sessions.",
        "",
    ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _shift_edge(frame: pd.DataFrame, *, rng: np.random.Generator) -> pd.DataFrame:
    out = frame.copy()
    if len(out) < 3:
        return out
    edge = pd.to_numeric(out.get("prob_edge", 0.0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    min_shift = max(1, int(len(edge) * 0.1))
    max_shift = max(min_shift + 1, len(edge) - min_shift)
    shift = int(rng.integers(min_shift, max_shift)) if max_shift > min_shift else min_shift
    shifted = np.roll(edge, shift)
    out["prob_edge"] = shifted
    out["prob_up"] = np.clip(0.5 + shifted / 2.0, 0.0, 1.0)
    out["prob_down"] = np.clip(0.5 - shifted / 2.0, 0.0, 1.0)
    out["prob_flat"] = np.maximum(0.0, 1.0 - out["prob_up"] - out["prob_down"])
    out["pred_label"] = np.sign(shifted).astype(int)
    return out


def _accuracy(frame: pd.DataFrame) -> float:
    if frame.empty or "label" not in frame.columns or "pred_label" not in frame.columns:
        return 0.0
    y = pd.to_numeric(frame["label"], errors="coerce")
    p = pd.to_numeric(frame["pred_label"], errors="coerce")
    valid = y.notna() & p.notna()
    return float((y[valid].astype(int) == p[valid].astype(int)).mean()) if valid.any() else 0.0


# Keep ranking logic separate from the small _float helper without relying on numpy scalar methods.
def _rank_score(metrics: dict[str, object]) -> float:
    mean = max(-10.0, min(10.0, _float(metrics.get("mean_net_pnl_bps"))))
    total = max(-1000.0, min(1000.0, _float(metrics.get("total_net_pnl_bps"))))
    hit = _float(metrics.get("hit_rate"))
    dd = abs(max(-1000.0, min(0.0, _float(metrics.get("max_drawdown_bps")))))
    return float(mean + 0.002 * total + 0.05 * hit - 0.01 * dd)


def _signal_sort_key(col: str) -> tuple[float, str]:
    # kline_1s_signal -> 1 second, kline_5m_signal -> 300 seconds when possible.
    token = col.removeprefix("kline_").removesuffix("_signal")
    try:
        sec = parse_timeframe_seconds(token.replace("p", "."))
    except Exception:
        sec = float("inf")
    return (sec, col)


def _float(value: object) -> float:
    try:
        f = float(value)
        return f if np.isfinite(f) else 0.0
    except Exception:
        return 0.0


def _finite_mean(series: pd.Series) -> float:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(arr.mean()) if len(arr) else 0.0


def _finite_min(series: pd.Series) -> float:
    arr = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(arr.min()) if len(arr) else 0.0
