from __future__ import annotations

from pathlib import Path

from lob_microprice_lab.btc_rescue_profit_lock import BTCRescueProfitGate, run_btc_rescue_profit_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def test_btc_rescue_profit_lock_v22(tmp_path: Path) -> None:
    result = run_btc_rescue_profit_lock(
        v17_run_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        out_dir=tmp_path,
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        take_profit_bps=52.0,
        exit_take_profit_candidates=[40, 45, 52],
        leverage_values=[1.0, 2.0, 3.0],
        shift_null_runs=20,
        random_scenarios=200,
        gate=BTCRescueProfitGate(max_entry_exit_family_addone_p=0.2),
        write_data_plan=False,
        clean=True,
    )
    agg = result["aggregate"]
    assert agg["trades"] == 11
    assert agg["hit_rate"] == 1.0
    assert agg["total_net_pnl_bps"] > 180.0
    assert agg["stress_all_cells_positive"] is True
    assert agg["gate"]["passed"] is True
    assert (tmp_path / "btc_rescue_profit_trade_ledger.csv").exists()
    assert (tmp_path / "btc_entry_exit_family_shift_null.csv").exists()
    assert (tmp_path / "btc_v20_v21_v22_comparison.csv").exists()
