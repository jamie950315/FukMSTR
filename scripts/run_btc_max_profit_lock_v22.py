from __future__ import annotations

import json

from lob_microprice_lab.btc_max_profit_lock import BTCMaxProfitGate, run_btc_max_profit_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def main() -> int:
    result = run_btc_max_profit_lock(
        v17_run_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        out_dir="runs/research_v22_btc_max_profit_lock",
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        take_profit_bps=50.0,
        stop_loss_bps=0.0,
        horizon_sec=90.0,
        latency_sec=0.5,
        exit_take_profit_candidates=[0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60],
        stress_fee_side_bps_values=[4, 5, 6, 7.5, 10],
        stress_latency_sec_values=[0, 0.5, 1, 2, 3, 5],
        leverage_values=[1, 2, 3, 5, 10, 20],
        shift_null_runs=1000,
        random_scenarios=10000,
        seed=22022,
        gate=BTCMaxProfitGate(
            min_trades=11,
            min_hit_rate=1.0,
            min_total_net_pnl_bps=180.0,
            min_mean_net_pnl_bps=16.0,
            max_full_family_addone_p=0.01,
            max_stress_fee_side_bps=10.0,
            max_stress_latency_sec=5.0,
            missed_trade_gate_probability=0.50,
            extra_cost_gate_bps=15.0,
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
