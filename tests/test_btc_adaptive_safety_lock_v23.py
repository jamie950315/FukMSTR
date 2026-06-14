from __future__ import annotations

from pathlib import Path

import pandas as pd

from lob_microprice_lab.btc_adaptive_safety_lock import (
    BTCAdaptiveLeveragePolicy,
    BTCAdaptiveSafetyGate,
    _loss_injection_table,
    _policy_scan,
    run_btc_adaptive_safety_lock,
)
from lob_microprice_lab.real_fee_lock import RealFeeSpec


def _sample_trades() -> pd.DataFrame:
    return pd.DataFrame({
        "net_pnl_bps": [45.28, 45.44, 11.04, 0.74, 38.93, 3.87, 18.88, 2.28, 4.67, 11.86, 0.72],
        "fold": [1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5],
    })


def test_loss_injection_table_survives_three_losses():
    gate = BTCAdaptiveSafetyGate(synthetic_loss_bps=-40.0, synthetic_loss_count=3)
    policy = BTCAdaptiveLeveragePolicy(normal_leverage=5.0, risk_off_leverage=4.0, risk_off_trades=3)
    table = _loss_injection_table(_sample_trades(), policy=policy, gate=gate, max_loss_count=3)
    row = table.loc[table["loss_count"] == 3].iloc[0]
    assert row["min_total_account_return_pct"] > 1.0
    assert row["worst_max_drawdown_pct"] > -5.0


def test_loss_injection_table_samples_large_combination_sets():
    trades = pd.DataFrame({"net_pnl_bps": [5.0] * 40})
    gate = BTCAdaptiveSafetyGate(synthetic_loss_bps=-40.0, synthetic_loss_count=4)
    policy = BTCAdaptiveLeveragePolicy(normal_leverage=8.0, risk_off_leverage=6.5, risk_off_trades=12)

    table = _loss_injection_table(
        trades,
        policy=policy,
        gate=gate,
        max_loss_count=4,
        max_exact_combinations=10,
        sampled_scenarios=25,
        seed=123,
    )

    row = table.loc[table["loss_count"] == 4].iloc[0]
    assert row["scenarios"] == 25
    assert row["scenario_method"] == "sampled"


def test_policy_scan_selects_5x_policy():
    gate = BTCAdaptiveSafetyGate()
    scan = _policy_scan(_sample_trades(), gate=gate)
    selected = scan.loc[scan["passes_v23_policy_gate"]].iloc[0]
    assert selected["normal_leverage"] == 5.0
    assert selected["risk_off_leverage"] <= 5.0
    assert selected["gate_loss_min_account_return_pct"] > 1.0


def test_run_btc_adaptive_safety_lock_smoke(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    run_dir = root / "runs" / "research_v17_execution_profit_lock_alpha0125_tp40"
    if not run_dir.exists():
        return
    result = run_btc_adaptive_safety_lock(
        v17_run_dir=run_dir,
        out_dir=tmp_path / "v23",
        fee_spec=RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000),
        gate=BTCAdaptiveSafetyGate(max_entry_exit_family_addone_p=0.20, min_missed_trade_p05_account_return_pct=0.80),
        shift_null_runs=8,
        random_scenarios=200,
        seed=23,
        write_data_plan=False,
        clean=True,
    )
    assert result["aggregate"]["trades"] == 11
    assert result["aggregate"]["normal_leverage"] == 5.0
    assert result["aggregate"]["gate"]["passed"] is True
    assert (tmp_path / "v23" / "REPORT_V23.md").exists()
