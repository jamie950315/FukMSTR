from __future__ import annotations

from pathlib import Path

import pandas as pd

from lob_microprice_lab.sequential_selection import run_sequential_template_audit


def _pred_frame(start: int, rows: int, *, drift: float = 1.0) -> pd.DataFrame:
    base = 100.0
    idx = list(range(rows))
    mid = [base + drift * i for i in idx]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01", periods=rows, freq="s", tz="UTC") + pd.Timedelta(seconds=start),
            "best_bid": [m - 0.01 for m in mid],
            "best_ask": [m + 0.01 for m in mid],
            "mid": mid,
            "future_best_bid": [m + 2 * drift - 0.01 for m in mid],
            "future_best_ask": [m + 2 * drift + 0.01 for m in mid],
            "future_mid": [m + 2 * drift for m in mid],
            "future_return_bps": [2 * drift / m * 10000 for m in mid],
            "label": [1] * rows,
            "prob_down": [0.05] * rows,
            "prob_flat": [0.05] * rows,
            "prob_up": [0.90] * rows,
            "prob_edge": [0.85] * rows,
            "prob_confidence": [0.90] * rows,
            "spread_bps": [2.0] * rows,
            "imbalance_l3": [0.5] * rows,
            "microprice_dev_bps_l3": [0.2] * rows,
            "mid_ret_60r_bps": [0.1] * rows,
        }
    )


def _write_fold(root: Path, fold: int, calib: pd.DataFrame, valid: pd.DataFrame) -> None:
    d = root / f"fold_{fold:02d}"
    d.mkdir(parents=True)
    calib.to_csv(d / "calibration_predictions.csv", index=False)
    valid.to_csv(d / "validation_predictions.csv", index=False)


def test_sequential_template_audit_source_rank_runs(tmp_path: Path) -> None:
    ensemble = tmp_path / "ensemble"
    _write_fold(ensemble, 1, _pred_frame(0, 20), _pred_frame(100, 20))
    _write_fold(ensemble, 2, _pred_frame(200, 20), _pred_frame(300, 20))

    result = run_sequential_template_audit(
        ensemble_dir=ensemble,
        out_dir=tmp_path / "out",
        horizon_sec=2,
        cost_bps=0,
        latency_sec=0,
        edge_thresholds=[0.1],
        signed_columns=[],
        spread_quantiles=[1.0],
        vol_modes=["none"],
        template_source="first_fold",
        min_source_trades=1,
        top_k_templates=5,
        ranking_policy="source_rank",
        warmup_periods=0,
        shift_null_runs=4,
        gate_config=None,
        clean=True,
    )
    assert result["selected_online"]["trades"] > 0
    assert Path(result["out_dir"], "online_selections.csv").exists()
    assert Path(result["out_dir"], "period_template_metrics.csv").exists()


def test_sequential_template_audit_can_split_periods(tmp_path: Path) -> None:
    ensemble = tmp_path / "ensemble"
    _write_fold(ensemble, 1, _pred_frame(0, 30), _pred_frame(100, 30))
    result = run_sequential_template_audit(
        ensemble_dir=ensemble,
        out_dir=tmp_path / "out_split",
        horizon_sec=2,
        cost_bps=0,
        latency_sec=0,
        edge_thresholds=[0.1],
        signed_columns=[],
        spread_quantiles=[1.0],
        vol_modes=["none"],
        template_source="first_fold",
        min_source_trades=1,
        top_k_templates=3,
        period_sec=10,
        ranking_policy="source_rank",
        warmup_periods=0,
        shift_null_runs=3,
        clean=True,
    )
    assert result["periods"] >= 3
    periods = pd.read_csv(Path(result["out_dir"], "periods.csv"))
    assert len(periods) == result["periods"]
