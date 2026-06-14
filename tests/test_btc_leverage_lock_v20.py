from __future__ import annotations

from pathlib import Path

from lob_microprice_lab.btc_leverage_lock import BTCLeverageGate, run_btc_contract_leverage_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def test_btc_contract_leverage_lock_certificate(tmp_path: Path) -> None:
    result = run_btc_contract_leverage_lock(
        v17_run_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        v19_run_dir="runs/research_v19_real_fee_lock_taker0040_maker0000",
        out_dir=tmp_path,
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        leverage_values=[1.0, 2.0, 3.0],
        shift_null_runs=20,
        random_scenarios=200,
        gate=BTCLeverageGate(max_side_guard_addone_p=0.2),
        write_data_plan=True,
        clean=True,
    )
    agg = result["aggregate"]
    assert agg["trades"] == 10
    assert agg["hit_rate"] == 1.0
    assert agg["gate"]["passed"] is True
    assert (tmp_path / "btc_contract_trade_ledger.csv").exists()
    assert (tmp_path / "btc_leverage_scenarios.csv").exists()
    assert (tmp_path / "btc_contract_data_plan" / "btc_contract_data_manifest.json").exists()
