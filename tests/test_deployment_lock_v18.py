from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.deployment_lock import DeploymentLockGate, run_deployment_lock_certificate


def _write_run(path: Path, rows: list[dict[str, object]]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path / "execution_lock_oof_backtest.csv", index=False)
    pd.DataFrame([
        {"cost_bps": 10.0, "latency_sec": 5.0, "mean_net_pnl_bps": 1.0, "total_net_pnl_bps": 2.0}
    ]).to_csv(path / "execution_lock_severe_stress.csv", index=False)
    (path / "summary.json").write_text(json.dumps({"aggregate": {"gate": {"passed": True}}}), encoding="utf-8")


def test_deployment_lock_certificate_passes_on_clean_frozen_ledger(tmp_path: Path) -> None:
    run = tmp_path / "v17"
    _write_run(
        run,
        [
            {"timestamp": "2020-01-01 00:00:00+00:00", "traded": 1, "signal": 1, "net_pnl_bps": 12.0, "fold": 1},
            {"timestamp": "2020-01-01 00:01:00+00:00", "traded": 0, "signal": 0, "net_pnl_bps": 0.0, "fold": 1},
            {"timestamp": "2020-01-01 00:02:00+00:00", "traded": 1, "signal": -1, "net_pnl_bps": 8.0, "fold": 2},
        ],
    )
    result = run_deployment_lock_certificate(
        v17_run_dir=run,
        out_dir=tmp_path / "out",
        horizon_sec=90.0,
        miss_probabilities=[0.0],
        extra_cost_bps_values=[1.0],
        combined_miss_probabilities=[0.0],
        combined_extra_cost_bps_values=[1.0],
        clock_block_counts=[2],
        random_scenarios=25,
        seed=1,
        gate=DeploymentLockGate(
            min_trades=2,
            horizon_sec=90.0,
            min_clock_block_count=2,
            miss_trade_gate_probability=0.0,
            combined_miss_probability=0.0,
            combined_extra_cost_bps=1.0,
            extra_cost_gate_bps=1.0,
        ),
        clean=True,
    )
    assert result["aggregate"]["gate"]["passed"] is True
    assert result["trade_integrity"]["non_overlap_slot_reserved"] is True


def test_deployment_lock_certificate_fails_when_reserved_slot_is_broken(tmp_path: Path) -> None:
    run = tmp_path / "v17"
    _write_run(
        run,
        [
            {"timestamp": "2020-01-01 00:00:00+00:00", "traded": 1, "signal": 1, "net_pnl_bps": 12.0, "fold": 1},
            {"timestamp": "2020-01-01 00:00:30+00:00", "traded": 1, "signal": -1, "net_pnl_bps": 8.0, "fold": 2},
        ],
    )
    result = run_deployment_lock_certificate(
        v17_run_dir=run,
        out_dir=tmp_path / "out",
        horizon_sec=90.0,
        miss_probabilities=[0.0],
        extra_cost_bps_values=[1.0],
        combined_miss_probabilities=[0.0],
        combined_extra_cost_bps_values=[1.0],
        clock_block_counts=[1],
        random_scenarios=25,
        seed=1,
        gate=DeploymentLockGate(
            min_trades=2,
            horizon_sec=90.0,
            min_clock_block_count=1,
            miss_trade_gate_probability=0.0,
            combined_miss_probability=0.0,
            combined_extra_cost_bps=1.0,
            extra_cost_gate_bps=1.0,
        ),
        clean=True,
    )
    assert result["trade_integrity"]["non_overlap_slot_reserved"] is False
    assert result["aggregate"]["gate"]["passed"] is False
    assert "trade_integrity" in result["aggregate"]["gate"]["failed_checks"]
