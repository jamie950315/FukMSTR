from __future__ import annotations

import json
from pathlib import Path

from lob_microprice_lab.real_fee_lock import RealFeeLockGate, RealFeeSpec, run_real_fee_lock_certificate


def main() -> None:
    result = run_real_fee_lock_certificate(
        v17_run_dir=Path("runs/research_v17_execution_profit_lock_alpha0125_tp40"),
        out_dir=Path("runs/research_v19_real_fee_lock_taker0040_maker0000"),
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        horizon_sec=90.0,
        latency_sec=0.5,
        take_profit_bps=40.0,
        stop_loss_bps=0.0,
        max_filter_count=2,
        shift_null_runs=1000,
        gate=RealFeeLockGate(
            min_trades=10,
            min_hit_rate=0.75,
            min_mean_net_pnl_bps=8.0,
            min_total_net_pnl_bps=100.0,
            max_family_addone_p=0.01,
            max_stress_fee_side_bps=7.5,
            max_stress_latency_sec=5.0,
            missed_trade_gate_probability=0.50,
            extra_cost_gate_bps=10.0,
        ),
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result["aggregate"]["gate"]["passed"],
        "aggregate": result["aggregate"],
        "out_dir": result["out_dir"],
    }, indent=2))


if __name__ == "__main__":
    main()
