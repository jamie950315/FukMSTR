from __future__ import annotations

import json
from pathlib import Path

from lob_microprice_lab.btc_profit_target_lock import BTCProfitTargetGate, run_btc_profit_target_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = run_btc_profit_target_lock(
        v17_run_dir=root / "runs" / "research_v17_execution_profit_lock_alpha0125_tp40",
        out_dir=root / "runs" / "research_v21_btc_profit_target_lock_tp45",
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        take_profit_bps=45.0,
        stop_loss_bps=0.0,
        horizon_sec=90.0,
        latency_sec=0.5,
        exit_take_profit_candidates=[0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60],
        stress_fee_side_bps_values=[4, 5, 6, 7.5, 10],
        stress_latency_sec_values=[0, 0.5, 1, 2, 3, 5],
        leverage_values=[1, 2, 3, 5, 10, 20],
        shift_null_runs=1000,
        random_scenarios=10000,
        seed=21021,
        gate=BTCProfitTargetGate(
            min_trades=10,
            min_hit_rate=1.0,
            min_total_net_pnl_bps=130.0,
            min_mean_net_pnl_bps=13.0,
            max_side_exit_family_addone_p=0.01,
            require_all_stress_cells_positive=True,
            max_stress_fee_side_bps=10.0,
            max_stress_latency_sec=5.0,
            missed_trade_gate_probability=0.50,
            extra_cost_gate_bps=12.0,
            promoted_leverage_cap=3.0,
            shock_buffer_bps=250.0,
            maintenance_margin_bps=50.0,
        ),
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result["aggregate"]["gate"]["passed"],
        "aggregate": result["aggregate"],
        "out_dir": result["out_dir"],
    }, indent=2))
