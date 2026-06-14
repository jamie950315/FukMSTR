from __future__ import annotations

from pathlib import Path

import pandas as pd

from lob_microprice_lab.slot_veto import SlotVetoGateConfig, SlotVetoSpec, run_slot_veto_audit


def _fold_frame(start: int, n: int = 24) -> pd.DataFrame:
    ts = pd.date_range("2020-01-01", periods=n, freq="1s", tz="UTC") + pd.Timedelta(seconds=start)
    mid = 100.0 + pd.Series(range(n), dtype=float) * 0.01
    frame = pd.DataFrame(
        {
            "timestamp": ts.astype(str),
            "best_bid": mid - 0.01,
            "best_ask": mid + 0.01,
            "mid": mid,
            "future_best_bid": mid.shift(-2).fillna(mid.iloc[-1]) - 0.01,
            "future_best_ask": mid.shift(-2).fillna(mid.iloc[-1]) + 0.01,
            "future_mid": mid.shift(-2).fillna(mid.iloc[-1]),
            "future_return_bps": 0.0,
            "label": 0,
            "prob_down": [0.1, 0.6, 0.1, 0.1] * 6,
            "prob_flat": [0.1] * n,
            "prob_up": [0.8, 0.1, 0.8, 0.8] * 6,
            "ofi_sum_l3_norm": [-0.2, 0.1, 0.4, -0.1] * 6,
            "ofi_sum_l5_norm": [-0.3, 0.2, 0.5, -0.2] * 6,
            "ofi_sum_l10_norm": [-0.4, 0.3, 0.6, -0.3] * 6,
            "spread_bps": 2.0,
        }
    )
    return frame


def test_slot_veto_audit_outputs_files(tmp_path: Path) -> None:
    src = tmp_path / "ensemble"
    for fold in [1, 2]:
        fd = src / f"fold_{fold:02d}"
        fd.mkdir(parents=True)
        _fold_frame(start=fold * 100).iloc[:12].to_csv(fd / "calibration_predictions.csv", index=False)
        _fold_frame(start=fold * 100 + 50).iloc[12:].reset_index(drop=True).to_csv(fd / "validation_predictions.csv", index=False)

    out = tmp_path / "slot_veto"
    result = run_slot_veto_audit(
        ensemble_dir=src,
        out_dir=out,
        horizon_sec=2.0,
        cost_bps=0.0,
        latency_sec=0.0,
        spec=SlotVetoSpec(edge_threshold=0.2, filter_col="ofi_sum_l5_norm", filter_operator="<=", filter_quantile=0.9),
        family_filter_cols=["ofi_sum_l3_norm", "ofi_sum_l5_norm"],
        family_quantiles=[0.5, 0.9],
        shift_null_runs=3,
        family_shift_runs=3,
        gate_config=SlotVetoGateConfig(min_oof_trades=1, min_periods_with_trades=1, max_family_null_p_total=1.0, max_family_null_p_mean=1.0),
        clean=True,
    )

    assert (out / "summary.json").exists()
    assert (out / "slot_veto_oof_backtest.csv").exists()
    assert result["aggregate"]["trades"] >= 1
    assert "gate" in result["aggregate"]
