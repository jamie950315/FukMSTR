from __future__ import annotations

import json
from pathlib import Path

from lob_microprice_lab.btc_portfolio_risk_lock import (
    BTCPortfolioRiskGate,
    BTCPortfolioRiskPolicy,
    run_btc_portfolio_risk_lock,
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = run_btc_portfolio_risk_lock(
        v24_run_dir=root / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=root / "runs" / "research_v25_btc_portfolio_risk_lock",
        policy=BTCPortfolioRiskPolicy(
            normal_leverage=8.0,
            emergency_leverage=6.75,
            emergency_trades=10,
            loss_trigger_bps=-20.0,
            session_stop_drawdown_pct=-10.0,
        ),
        gate=BTCPortfolioRiskGate(
            min_trades=11,
            min_win_rate=1.0,
            min_no_loss_account_return_pct=15.0,
            max_promoted_leverage=8.0,
            promoted_synthetic_loss_count=4,
            synthetic_loss_bps=-40.0,
            min_promoted_loss_return_pct=1.25,
            min_promoted_loss_drawdown_pct=-10.0,
            min_extreme_stress_account_return_pct=3.0,
            min_missed_trade_p05_account_return_pct=2.0,
            min_extra_cost_account_return_pct=1.0,
            shock_buffer_bps=1000.0,
            maintenance_margin_bps=50.0,
            max_entry_exit_family_addone_p=0.01,
        ),
        max_loss_count=5,
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result["aggregate"]["gate"]["passed"],
        "aggregate": result["aggregate"],
        "out_dir": result["out_dir"],
    }, indent=2))
