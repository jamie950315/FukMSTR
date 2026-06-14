from __future__ import annotations

import json
from pathlib import Path

from lob_microprice_lab.btc_adaptive_safety_lock import BTCAdaptiveSafetyGate, run_btc_adaptive_safety_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = run_btc_adaptive_safety_lock(
        v17_run_dir=root / "runs" / "research_v17_execution_profit_lock_alpha0125_tp40",
        out_dir=root / "runs" / "research_v23_btc_adaptive_safety_lock",
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        gate=BTCAdaptiveSafetyGate(
            max_promoted_leverage=5.0,
            promoted_shock_buffer_bps=1000.0,
            synthetic_loss_bps=-40.0,
            synthetic_loss_count=3,
            min_synthetic_loss_account_return_pct=1.0,
            min_synthetic_loss_max_drawdown_pct=-5.0,
            min_extreme_stress_account_return_pct=1.0,
            min_missed_trade_p05_account_return_pct=1.0,
            min_extra_cost_account_return_pct=0.25,
        ),
        shift_null_runs=1000,
        random_scenarios=10000,
        seed=23023,
        write_data_plan=True,
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result["aggregate"]["gate"]["passed"],
        "aggregate": result["aggregate"],
        "out_dir": result["out_dir"],
    }, indent=2))
