from __future__ import annotations

import csv
import json
from pathlib import Path

from lob_microprice_lab.btc_leverage_lock import BTCLeverageGate, run_btc_contract_leverage_lock
from lob_microprice_lab.profit_lock import _jsonable
from lob_microprice_lab.real_fee_lock import RealFeeSpec

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out_dir = ROOT / "runs" / "research_v20_btc_contract_leverage_lock"
    result = run_btc_contract_leverage_lock(
        v17_run_dir=ROOT / "runs" / "research_v17_execution_profit_lock_alpha0125_tp40",
        v19_run_dir=ROOT / "runs" / "research_v19_real_fee_lock_taker0040_maker0000",
        out_dir=out_dir,
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        horizon_sec=90.0,
        latency_sec=0.5,
        take_profit_bps=40.0,
        stop_loss_bps=0.0,
        stress_fee_side_bps_values=[4.0, 5.0, 6.0, 7.5, 10.0],
        stress_latency_sec_values=[0.0, 0.5, 1.0, 2.0, 3.0, 5.0],
        leverage_values=[1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 30.0, 50.0],
        shift_null_runs=1000,
        random_scenarios=10000,
        seed=20020,
        gate=BTCLeverageGate(
            min_trades=10,
            min_hit_rate=0.95,
            min_total_net_pnl_bps=120.0,
            min_fold_total_net_pnl_bps=0.0,
            min_fold_mean_net_pnl_bps=0.0,
            min_bootstrap_mean_p05_bps=0.0,
            max_side_guard_addone_p=0.01,
            max_stress_fee_side_bps=7.5,
            max_stress_latency_sec=5.0,
            missed_trade_gate_probability=0.50,
            missed_trade_min_p05_total_bps=0.0,
            extra_cost_gate_bps=10.0,
            extra_cost_min_total_bps=0.0,
            promoted_leverage_cap=3.0,
            shock_buffer_bps=250.0,
            maintenance_margin_bps=50.0,
        ),
        write_data_plan=True,
        clean=True,
    )
    summary = {
        "version": "v20_btc_contract_leverage",
        "status": {
            "btc_data_search_completed": True,
            "v19_fee_policy_used_as_base": True,
            "btc_side_guard_added": True,
            "independent_multi_day_training": "data pipeline prepared; not run inside offline sandbox",
        },
        "result": result,
    }
    (ROOT / "runs" / "research_v20_summary.json").write_text(json.dumps(_jsonable(summary), indent=2), encoding="utf-8")
    agg = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    with (ROOT / "runs" / "research_v20_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value"])
        writer.writeheader()
        for k in [
            "gate",
            "trades",
            "hit_rate",
            "mean_net_pnl_bps",
            "total_net_pnl_bps",
            "fold_min_total_net_pnl_bps",
            "bootstrap_mean_p05_bps",
            "stress_gate_min_total_net_pnl_bps",
            "side_guard_family_addone_p_mean",
            "leverage_promoted_cap",
        ]:
            val = agg.get(k)
            if k == "gate" and isinstance(val, dict):
                val = val.get("passed")
            writer.writerow({"metric": k, "value": val})
    print(json.dumps({
        "v20_gate_passed": (agg.get("gate") or {}).get("passed") if isinstance(agg.get("gate"), dict) else None,
        "aggregate": agg,
        "out_dir": str(out_dir),
    }, indent=2))


if __name__ == "__main__":
    main()
