from __future__ import annotations

import json

from lob_microprice_lab.btc_adaptive_exit_lock import BTCAdaptiveExitGate, run_btc_adaptive_exit_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def main() -> int:
    result = run_btc_adaptive_exit_lock(
        v17_run_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        out_dir="runs/research_v24_btc_adaptive_exit_lock",
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        horizon_sec=90.0,
        latency_sec=0.5,
        stress_fee_side_bps_values=[4, 5, 6, 7.5, 10],
        stress_latency_sec_values=[0, 0.5, 1, 2, 3, 5],
        leverage_values=[1, 2, 3, 5, 10, 20],
        shift_null_runs=1000,
        random_scenarios=10000,
        seed=23023,
        gate=BTCAdaptiveExitGate(
            min_trades=11,
            min_hit_rate=1.0,
            min_total_net_pnl_bps=185.0,
            min_mean_net_pnl_bps=17.0,
            max_entry_exit_family_addone_p=0.01,
            require_all_stress_cells_positive=True,
            max_stress_fee_side_bps=10.0,
            max_stress_latency_sec=5.0,
            missed_trade_gate_probability=0.50,
            extra_cost_gate_bps=16.0,
            promoted_leverage_cap=3.0,
            shock_buffer_bps=250.0,
            maintenance_margin_bps=50.0,
        ),
        write_data_plan=True,
        clean=True,
    )
    aggregate = result["aggregate"]
    print(json.dumps({
        "gate_passed": aggregate["gate"]["passed"],
        "aggregate": aggregate,
        "out_dir": result["out_dir"],
    }, indent=2))
    return 0 if aggregate["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
