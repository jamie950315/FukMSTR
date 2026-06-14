from __future__ import annotations

import json
import os
import sys

from lob_microprice_lab.exit_lock import ExitLockSpec
from lob_microprice_lab.kline_guard import KlineGuardSpec
from lob_microprice_lab.profit_execution_lock import ExecutionProfitLockGate, run_execution_profit_lock_certificate


def main() -> int:
    result = run_execution_profit_lock_certificate(
        base_ensemble_dir="runs/research_v09_ensemble_h90_5fold_stationary",
        kline_ensemble_dir="runs/research_v13_kline_h90_5fold_stationary_v12folds",
        out_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        horizon_sec=90.0,
        cost_bps=1.5,
        latency_sec=0.5,
        selected_signal_spec=KlineGuardSpec(
            edge_threshold=0.1,
            kline_alpha=0.125,
            ofi_col="ofi_sum_l5_norm",
            ofi_quantile=0.9,
            kline_col="kline_15s_rv_6_bps",
            kline_quantile=0.0,
            kline_operator=">=",
            directional=True,
        ),
        selected_exit_spec=ExitLockSpec(take_profit_bps=40.0, stop_loss_bps=0.0, reserve_horizon=True),
        exit_take_profit_bps_values=[0.0, 20.0, 30.0, 40.0, 60.0, 90.0],
        exit_stop_loss_bps_values=[0.0],
        stress_cost_bps_values=[1.5, 3.0, 5.0, 7.5, 10.0],
        stress_latency_sec_values=[0.0, 0.5, 1.0, 2.0, 3.0, 5.0],
        shift_null_runs=1000,
        gate=ExecutionProfitLockGate(
            max_addone_family_p=0.01,
            min_top_winner_removal_k=5,
            min_full_stress_mean_net_bps=0.0,
            min_full_stress_total_net_bps=0.0,
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
