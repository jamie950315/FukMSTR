from __future__ import annotations

import json
from pathlib import Path

from lob_microprice_lab.btc_leverage_lock import BTCLeverageGate, run_btc_contract_leverage_lock
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def main() -> int:
    result = run_btc_contract_leverage_lock(
        v17_run_dir=Path("runs/research_v17_execution_profit_lock_alpha0125_tp40"),
        v19_run_dir=Path("runs/research_v19_real_fee_lock_taker0040_maker0000"),
        out_dir=Path("runs/research_v20_btc_contract_leverage_lock"),
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        shift_null_runs=1000,
        random_scenarios=10000,
        gate=BTCLeverageGate(
            min_trades=10,
            min_hit_rate=0.95,
            min_total_net_pnl_bps=120.0,
            promoted_leverage_cap=3.0,
            shock_buffer_bps=250.0,
            maintenance_margin_bps=50.0,
        ),
        clean=True,
    )
    print(json.dumps({
        "gate_passed": result.get("aggregate", {}).get("gate", {}).get("passed"),
        "aggregate": result.get("aggregate"),
        "out_dir": result.get("out_dir"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
