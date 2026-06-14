from __future__ import annotations

import json

from lob_microprice_lab.btc_recovery_leverage import BTCRecoveryGate, run_btc_recovery_leverage_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def main() -> int:
    result = run_btc_recovery_leverage_lock(
        v17_run_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        v20_run_dir="runs/research_v20_btc_contract_leverage_lock",
        out_dir="runs/research_v21_btc_recovery_leverage_lock",
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        horizon_sec=90.0,
        latency_sec=0.5,
        take_profit_bps=40.0,
        stop_loss_bps=0.0,
        stress_fee_side_bps_values=[4.0, 5.0, 6.0, 7.5, 10.0],
        stress_latency_sec_values=[0.0, 0.5, 1.0, 2.0, 3.0, 5.0],
        leverage_values=[1.0, 2.0, 3.0, 5.0, 10.0, 20.0],
        shift_null_runs=1000,
        random_scenarios=10000,
        seed=21021,
        gate=BTCRecoveryGate(
            min_trades=11,
            min_hit_rate=1.0,
            min_total_net_pnl_bps=160.0,
            min_mean_net_pnl_bps=12.0,
            max_recovery_family_addone_p=0.01,
            max_stress_fee_side_bps=10.0,
            max_stress_latency_sec=5.0,
            missed_trade_gate_probability=0.50,
            extra_cost_gate_bps=12.0,
            promoted_leverage_cap=5.0,
            shock_buffer_bps=1000.0,
            maintenance_margin_bps=50.0,
        ),
        write_data_plan=True,
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result["aggregate"]["gate"]["passed"],
        "aggregate": result["aggregate"],
        "out_dir": result["out_dir"],
    }, indent=2))
    return 0 if result["aggregate"]["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
