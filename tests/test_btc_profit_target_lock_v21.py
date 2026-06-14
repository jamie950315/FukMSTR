from __future__ import annotations

from pathlib import Path

from lob_microprice_lab.btc_profit_target_lock import BTCProfitTargetGate, run_btc_profit_target_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def test_btc_profit_target_lock_v21(tmp_path: Path) -> None:
    result = run_btc_profit_target_lock(
        v17_run_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        out_dir=tmp_path,
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        take_profit_bps=45.0,
        exit_take_profit_candidates=[0, 40, 45, 50],
        leverage_values=[1.0, 2.0, 3.0],
        shift_null_runs=20,
        random_scenarios=200,
        gate=BTCProfitTargetGate(max_side_exit_family_addone_p=0.2),
        write_data_plan=False,
        clean=True,
    )
    agg = result["aggregate"]
    assert agg["trades"] == 10
    assert agg["hit_rate"] == 1.0
    assert agg["total_net_pnl_bps"] > 130.0
    assert agg["stress_all_cells_positive"] is True
    assert agg["gate"]["passed"] is True
    assert (tmp_path / "btc_profit_target_trade_ledger.csv").exists()
    assert (tmp_path / "btc_exit_target_family_scan.csv").exists()
    assert (tmp_path / "btc_side_exit_family_shift_null.csv").exists()
