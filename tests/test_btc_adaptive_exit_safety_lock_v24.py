from __future__ import annotations

from pathlib import Path

from lob_microprice_lab.btc_adaptive_exit_safety_lock import run_btc_adaptive_exit_safety_lock
from lob_microprice_lab.btc_adaptive_safety_lock import BTCAdaptiveSafetyGate
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def test_run_btc_adaptive_exit_safety_lock_smoke(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    run_dir = root / "runs" / "research_v17_execution_profit_lock_alpha0125_tp40"
    if not run_dir.exists():
        return
    result = run_btc_adaptive_exit_safety_lock(
        v17_run_dir=run_dir,
        out_dir=tmp_path / "v24",
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        gate=BTCAdaptiveSafetyGate(
            max_entry_exit_family_addone_p=0.20,
            min_no_loss_account_return_pct=9.5,
            min_synthetic_loss_account_return_pct=1.25,
            min_extreme_stress_account_return_pct=1.5,
            min_missed_trade_p05_account_return_pct=1.0,
            min_extra_cost_account_return_pct=0.5,
        ),
        shift_null_runs=8,
        random_scenarios=300,
        seed=24,
        write_data_plan=False,
        clean=True,
    )
    agg = result["aggregate"]
    assert agg["gate"]["passed"] is True
    assert agg["trades"] == 11
    assert agg["selected_trade_win_rate"] == 1.0
    assert agg["no_loss_account_return_pct"] > 9.5
    assert agg["normal_leverage"] == 5.0
