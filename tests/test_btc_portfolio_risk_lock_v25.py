from __future__ import annotations

import json

import pandas as pd

from lob_microprice_lab.btc_adaptive_safety_lock import _loss_injection_table
from lob_microprice_lab.btc_portfolio_risk_lock import (
    BTCPortfolioRiskGate,
    BTCPortfolioRiskPolicy,
    run_btc_portfolio_risk_lock,
)


def _sample_trades() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="90s", tz="UTC"),
        "fold": [1, 1, 2, 2],
        "signal": [1, -1, 1, -1],
        "net_pnl_bps": [30.0, 20.0, 12.0, 8.0],
        "take_profit_bps": [40.0, 40.0, 20.0, 20.0],
        "exit_reason": ["take_profit", "take_profit", "horizon", "horizon"],
    })


def test_policy_conversion_defaults_to_v25_survivor_mode() -> None:
    p = BTCPortfolioRiskPolicy()
    ap = p.to_adaptive_policy()
    assert ap.normal_leverage == 8.0
    assert ap.risk_off_leverage == 6.75
    assert ap.risk_off_trades == 10


def test_loss_injection_table_contains_promoted_loss_count() -> None:
    trades = _sample_trades()
    p = BTCPortfolioRiskPolicy(normal_leverage=8, emergency_leverage=6, emergency_trades=3)
    gate = BTCPortfolioRiskGate(promoted_synthetic_loss_count=2, synthetic_loss_bps=-40)
    inj = _loss_injection_table(trades, policy=p.to_adaptive_policy(), gate=gate, max_loss_count=2)
    assert set(inj["loss_count"].astype(int)) == {0, 1, 2}
    assert float(inj.loc[inj["loss_count"] == 0, "min_total_account_return_pct"].iloc[0]) > 0


def test_run_btc_portfolio_risk_lock(tmp_path) -> None:
    v24 = tmp_path / "v24"
    v24.mkdir()
    trades = _sample_trades()
    trades.to_csv(v24 / "btc_adaptive_exit_trade_ledger.csv", index=False)
    pd.DataFrame([{"taker_fee_bps_per_side": 10.0, "latency_sec": 5.0, "total_net_pnl_bps": 20.0}]).to_csv(v24 / "btc_adaptive_fee_latency_stress.csv", index=False)
    pd.DataFrame([{"miss_probability": 0.5, "p05_total_bps": 10.0}]).to_csv(v24 / "btc_adaptive_missed_trade_stress.csv", index=False)
    pd.DataFrame([{"extra_cost_bps_per_trade": 16.0, "total_net_pnl_bps": 8.0}]).to_csv(v24 / "btc_adaptive_extra_cost_reserve.csv", index=False)
    summary = {
        "aggregate": {
            "gate": {"passed": True},
            "selected_trade_win_rate": 1.0,
            "notional_total_net_pnl_bps": 70.0,
            "notional_mean_net_pnl_bps": 17.5,
            "entry_exit_family_addone_p_total": 0.001,
            "entry_exit_family_addone_p_mean": 0.001,
        }
    }
    (v24 / "summary_v24.json").write_text(json.dumps(summary), encoding="utf-8")
    result = run_btc_portfolio_risk_lock(
        v24_run_dir=v24,
        out_dir=tmp_path / "out",
        policy=BTCPortfolioRiskPolicy(normal_leverage=4, emergency_leverage=3, emergency_trades=2),
        gate=BTCPortfolioRiskGate(
            min_trades=4,
            min_no_loss_account_return_pct=2.0,
            max_promoted_leverage=4.0,
            promoted_synthetic_loss_count=1,
            min_promoted_loss_return_pct=-10.0,
            min_promoted_loss_drawdown_pct=-10.0,
            min_extreme_stress_account_return_pct=0.5,
            min_missed_trade_p05_account_return_pct=0.2,
            min_extra_cost_account_return_pct=0.1,
            shock_buffer_bps=100.0,
        ),
        max_loss_count=1,
        clean=True,
    )
    assert result["aggregate"]["gate"]["passed"] is True
    assert (tmp_path / "out" / "REPORT_V25.md").exists()
