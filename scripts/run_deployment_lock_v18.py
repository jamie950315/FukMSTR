from __future__ import annotations

import json
import os
import sys

from lob_microprice_lab.deployment_lock import DeploymentLockGate, run_deployment_lock_certificate


def main() -> int:
    result = run_deployment_lock_certificate(
        v17_run_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        out_dir="runs/research_v18_deployment_lock_certificate",
        horizon_sec=90.0,
        miss_probabilities=[0.05, 0.10, 0.20, 0.30, 0.40, 0.50],
        extra_cost_bps_values=[0.0, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0],
        combined_miss_probabilities=[0.10, 0.20, 0.30, 0.40, 0.50],
        combined_extra_cost_bps_values=[1.0, 2.0, 3.0, 5.0],
        clock_block_counts=[3, 4, 5, 6, 8, 10, 12],
        random_scenarios=10000,
        seed=18018,
        gate=DeploymentLockGate(
            min_trades=20,
            horizon_sec=90.0,
            min_clock_block_count=10,
            miss_trade_gate_probability=0.50,
            miss_trade_min_p01_total_bps=0.0,
            miss_trade_min_p05_total_bps=0.0,
            combined_miss_probability=0.50,
            combined_extra_cost_bps=3.0,
            combined_min_p05_total_bps=0.0,
            extra_cost_gate_bps=10.0,
            extra_cost_min_total_bps=0.0,
        ),
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result["aggregate"]["gate"]["passed"],
        "aggregate": result["aggregate"],
        "out_dir": result["out_dir"],
    }, indent=2))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    os._exit(main())
