from pathlib import Path

from lob_microprice_lab.btc_four_loss_safety_lock import BTCFourLossSafetyGate, run_btc_four_loss_safety_lock


def test_v25_four_loss_safety_gate_passes(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    result = run_btc_four_loss_safety_lock(
        v24_run_dir=root / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=tmp_path / "v25",
        gate=BTCFourLossSafetyGate(),
        clean=True,
    )
    agg = result["aggregate"]
    assert agg["gate"]["passed"] is True
    assert agg["selected_trade_win_rate"] == 1.0
    assert agg["normal_leverage"] == 5.0
    assert agg["four_loss_min_account_return_pct"] > 0.0
    assert agg["four_loss_p05_account_return_pct"] > 0.0
    assert agg["four_loss_worst_drawdown_pct"] >= -5.25


def test_v25_is_trade_rule_frozen(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    result = run_btc_four_loss_safety_lock(
        v24_run_dir=root / "runs" / "research_v24_btc_adaptive_exit_safety_lock",
        out_dir=tmp_path / "v25_frozen",
        clean=True,
    )
    policy = result["frozen_trade_policy"]
    assert policy["entry_changed"] is False
    assert policy["exit_changed"] is False
    assert policy["fee_changed"] is False
    assert result["aggregate"]["trades"] == 11
