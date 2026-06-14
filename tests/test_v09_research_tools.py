from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from lob_microprice_lab.edge_calibration import run_calibrated_edge_audit
from lob_microprice_lab.family_adaptive import FamilySpec, run_family_adaptive_audit
from lob_microprice_lab.template_transfer import run_template_transfer_audit


def _frame(start: int, rows: int, *, drift: float = 0.01) -> pd.DataFrame:
    t0 = pd.Timestamp("2020-01-01T00:00:00Z") + pd.Timedelta(seconds=start)
    idx = np.arange(rows, dtype=float)
    mid = 100.0 + drift * idx + 0.03 * np.sin(idx / 2.0)
    edge = np.sin(idx / 3.0)
    label = np.where(np.roll(mid, -2) > mid + 0.005, 1, -1)
    label[-2:] = 0
    return pd.DataFrame(
        {
            "timestamp": [(t0 + pd.Timedelta(seconds=int(i))).isoformat() for i in range(rows)],
            "best_bid": mid - 0.01,
            "best_ask": mid + 0.01,
            "mid": mid,
            "label": label,
            "prob_down": np.clip((1 - edge) / 2, 0.01, 0.99),
            "prob_flat": 0.0,
            "prob_up": np.clip((1 + edge) / 2, 0.01, 0.99),
            "prob_confidence": np.maximum(np.clip((1 + edge) / 2, 0.01, 0.99), np.clip((1 - edge) / 2, 0.01, 0.99)),
            "spread_bps": 2.0,
            "imbalance_l3": edge,
            "microprice_dev_bps_l3": edge * 2.0,
            "mid_ret_60r_bps": np.r_[0.0, np.diff(mid) / mid[:-1] * 10000.0],
            "mid_vol_60r_bps": 1.0,
            "ofi_sum_l3_norm": edge * 0.5,
        }
    )


def _ensemble_dir(tmp_path: Path) -> Path:
    root = tmp_path / "ensemble"
    for fold in range(1, 4):
        d = root / f"fold_{fold:02d}"
        d.mkdir(parents=True)
        _frame(fold * 100, 24, drift=0.02).to_csv(d / "calibration_predictions.csv", index=False)
        _frame(fold * 100 + 30, 24, drift=0.015).to_csv(d / "validation_predictions.csv", index=False)
    return root


def test_family_adaptive_audit_smoke(tmp_path: Path) -> None:
    result = run_family_adaptive_audit(
        ensemble_dir=_ensemble_dir(tmp_path),
        out_dir=tmp_path / "family",
        horizon_sec=2.0,
        family=FamilySpec(direction_mode="any", signed_col="imbalance_l3", signed_mode="agree"),
        edge_thresholds=[0.1],
        signed_abs_quantiles=[0.0],
        spread_quantiles=[1.0],
        vol_modes=["none"],
        min_calibration_trades=1,
        shift_null_runs=3,
        clean=True,
    )
    assert "aggregate" in result
    assert (tmp_path / "family" / "oof_family_adaptive_backtest.csv").exists()


def test_calibrated_edge_audit_smoke(tmp_path: Path) -> None:
    result = run_calibrated_edge_audit(
        ensemble_dir=_ensemble_dir(tmp_path),
        out_dir=tmp_path / "calibrated",
        horizon_sec=2.0,
        edge_thresholds=[0.1],
        signed_columns=["imbalance_l3"],
        spread_quantiles=[1.0],
        vol_modes=["none"],
        min_calibration_trades=1,
        min_train_labels=4,
        shift_null_runs=3,
        clean=True,
    )
    assert result["calibrator"] == "logistic"
    assert (tmp_path / "calibrated" / "calibrator_coefficients.csv").exists()


def test_template_transfer_audit_smoke(tmp_path: Path) -> None:
    result = run_template_transfer_audit(
        ensemble_dir=_ensemble_dir(tmp_path),
        out_dir=tmp_path / "transfer",
        horizon_sec=2.0,
        edge_thresholds=[0.1],
        signed_columns=["imbalance_l3"],
        spread_quantiles=[1.0],
        vol_modes=["none"],
        min_source_trades=1,
        top_k_templates=4,
        warmup_folds=1,
        min_history_trades=1,
        shift_null_runs=3,
        clean=True,
    )
    assert result["templates_tested"] >= 1
    assert (tmp_path / "transfer" / "template_fold_matrix.csv").exists()
