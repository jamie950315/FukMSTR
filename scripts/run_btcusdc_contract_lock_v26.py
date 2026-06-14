from __future__ import annotations

import json
from pathlib import Path

from lob_microprice_lab.btcusdc_contract_lock import (
    BTCUSDCContractGate,
    BTCUSDCContractPolicy,
    run_btcusdc_contract_lock,
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = run_btcusdc_contract_lock(
        v24_run_dir=root / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=root / "runs" / "research_v26_btcusdc_contract_lock",
        policy=BTCUSDCContractPolicy(
            symbol="BTCUSDC",
            source_symbol="BTCUSDT/BTC bundled transfer proxy",
            taker_fee_bps_per_side=4.0,
            maker_fee_bps_per_side=0.0,
            route="taker_entry_taker_exit",
            quote_transfer_surcharge_bps=0.50,
            normal_leverage=8.0,
            emergency_leverage=6.5,
            emergency_trades=12,
            loss_trigger_bps=-20.0,
            horizon_sec=90.0,
            latency_sec=0.5,
        ),
        gate=BTCUSDCContractGate(
            min_trades=11,
            min_win_rate=0.90,
            min_total_net_pnl_bps=175.0,
            min_mean_net_pnl_bps=15.0,
            min_no_loss_account_return_pct=14.0,
            min_extreme_10bps_5s_account_return_pct=2.5,
            missed_trade_probability=0.50,
            min_missed_trade_p05_account_return_pct=1.5,
            extra_cost_gate_bps=16.0,
            min_extra_cost_account_return_pct=0.5,
            synthetic_loss_bps=-40.0,
            promoted_synthetic_loss_count=4,
            min_promoted_loss_return_pct=0.75,
            min_promoted_loss_drawdown_pct=-10.0,
            shock_buffer_bps=1000.0,
            maintenance_margin_bps=50.0,
            max_promoted_leverage=8.0,
            require_data_manifest=True,
        ),
        data_start="2024-01-01",
        data_end="2026-06-10",
        max_loss_count=5,
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result["aggregate"]["gate"]["passed"],
        "aggregate": result["aggregate"],
        "out_dir": result["out_dir"],
    }, indent=2))
