from __future__ import annotations

import pandas as pd

from lob_microprice_lab.btc_adaptive_exit_lock import (
    BTCAdaptiveExitGate,
    assign_adaptive_take_profit_bps,
    default_v23_adaptive_exit_spec,
    run_btc_adaptive_exit_lock,
)
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def test_adaptive_take_profit_assignment_rules() -> None:
    frame = pd.DataFrame({
        "kline_15s_signal": [-0.5, 0.5, -0.1, -0.45],
        "prob_edge": [0.1, -0.4, 0.3, 0.18],
    })
    signal = [1, -1, -1, 1]
    tps = assign_adaptive_take_profit_bps(frame, signal, default_v23_adaptive_exit_spec())
    assert list(tps) == [20.0, 25.0, 45.0, 20.0]


def test_v24_smoke_gate_passes_with_small_null(tmp_path) -> None:
    out = tmp_path / "v24"
    result = run_btc_adaptive_exit_lock(
        v17_run_dir="runs/research_v17_execution_profit_lock_alpha0125_tp40",
        out_dir=out,
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        shift_null_runs=20,
        random_scenarios=500,
        seed=23023,
        gate=BTCAdaptiveExitGate(
            min_trades=11,
            min_hit_rate=1.0,
            min_total_net_pnl_bps=185.0,
            min_mean_net_pnl_bps=17.0,
            max_entry_exit_family_addone_p=0.10,
            require_all_stress_cells_positive=True,
            max_stress_fee_side_bps=10.0,
            max_stress_latency_sec=5.0,
            missed_trade_gate_probability=0.50,
            extra_cost_gate_bps=16.0,
            promoted_leverage_cap=3.0,
            shock_buffer_bps=250.0,
            maintenance_margin_bps=50.0,
        ),
        write_data_plan=False,
        clean=True,
    )
    agg = result["aggregate"]
    assert agg["gate"]["passed"] is True
    assert agg["trades"] == 11
    assert agg["hit_rate"] == 1.0
    assert agg["total_net_pnl_bps"] > 190.0
