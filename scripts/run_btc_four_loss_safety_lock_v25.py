from __future__ import annotations

import json
from pathlib import Path

from lob_microprice_lab.btc_four_loss_safety_lock import BTCFourLossSafetyGate, run_btc_four_loss_safety_lock


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = run_btc_four_loss_safety_lock(
        v24_run_dir=root / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=root / "runs" / "research_v25_btc_four_loss_safety_lock",
        gate=BTCFourLossSafetyGate(
            normal_leverage_required=5.0,
            synthetic_loss_bps=-40.0,
            promoted_loss_count=4,
            warning_loss_count=5,
            min_no_loss_account_return_pct=9.5,
            min_four_loss_account_return_pct=0.0,
            min_four_loss_p05_account_return_pct=0.0,
            min_four_loss_max_drawdown_pct=-5.25,
            min_extreme_stress_account_return_pct=1.5,
            min_missed_trade_p05_account_return_pct=1.25,
            min_extra_cost_account_return_pct=0.5,
        ),
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result["aggregate"]["gate"]["passed"],
        "aggregate": result["aggregate"],
        "selected_risk_policy": result["selected_risk_policy"],
        "out_dir": result["out_dir"],
    }, indent=2))
