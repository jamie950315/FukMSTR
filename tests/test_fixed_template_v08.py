import pandas as pd

from lob_microprice_lab.fixed_template import (
    FixedTemplateGateConfig,
    candidate_from_signature,
    candidate_signature,
    evaluate_fixed_template_gate,
    rank_fixed_template_leaderboard,
    summarize_fixed_template_candidate,
)
from lob_microprice_lab.selective import SelectiveCandidate


def test_candidate_signature_round_trip():
    candidate = SelectiveCandidate(
        edge_threshold=0.2,
        direction_mode="invert",
        signed_col="imbalance_l3",
        signed_mode="disagree",
        signed_abs_threshold=0.123456789,
    )
    restored = candidate_from_signature(candidate_signature(candidate))
    assert restored.direction_mode == "invert"
    assert restored.signed_col == "imbalance_l3"
    assert abs(restored.signed_abs_threshold - 0.12345679) < 1e-9


def test_rank_fixed_template_leaderboard_prefers_fold_stability():
    frame = pd.DataFrame(
        [
            {"template_signature": "a", "fold_mean_net_pnl_bps_min": -1.0, "oof_mean_net_pnl_bps": 4.0, "oof_total_net_pnl_bps": 80.0, "bootstrap_mean_p05_bps_min": -2.0, "folds_with_trades": 3, "oof_trades": 20},
            {"template_signature": "b", "fold_mean_net_pnl_bps_min": 0.5, "oof_mean_net_pnl_bps": 1.0, "oof_total_net_pnl_bps": 25.0, "bootstrap_mean_p05_bps_min": 0.1, "folds_with_trades": 3, "oof_trades": 20},
        ]
    )
    ranked = rank_fixed_template_leaderboard(frame)
    assert ranked.iloc[0]["template_signature"] == "b"


def test_summarize_fixed_template_candidate_counts_sides_and_pnl():
    folds = pd.DataFrame(
        [
            {"fold": 1, "trades": 2, "mean_net_pnl_bps": 1.0, "total_net_pnl_bps": 2.0, "bootstrap_mean_p05_bps": 0.1},
            {"fold": 2, "trades": 1, "mean_net_pnl_bps": -0.5, "total_net_pnl_bps": -0.5, "bootstrap_mean_p05_bps": -1.0},
        ]
    )
    oof = pd.DataFrame(
        {
            "traded": [1, 1, 0, 1],
            "signal": [1, -1, 0, 1],
            "net_pnl_bps": [2.0, -1.0, 0.0, 3.0],
        }
    )
    summary = summarize_fixed_template_candidate(folds, oof)
    assert summary["oof_trades"] == 3
    assert summary["oof_long_trades"] == 2
    assert summary["oof_short_trades"] == 1
    assert summary["fold_mean_net_pnl_bps_min"] == -0.5


def test_fixed_template_gate_reports_failed_checks():
    gate = evaluate_fixed_template_gate(
        aggregate={"folds_with_trades": 1, "oof_trades": 10, "fold_trades_min": 0, "oof_mean_net_pnl_bps": -1.0, "fold_mean_net_pnl_bps_min": -2.0, "fold_bootstrap_mean_p05_bps_min": -3.0},
        stress_gate={"passed": False},
        shift_summary={"p_null_mean_ge_actual": 0.5, "p_null_total_ge_actual": 0.5},
        gate_config=FixedTemplateGateConfig(),
    )
    assert gate["passed"] is False
    assert "positive_oof_mean" in gate["failed_checks"]
    assert "stress_gate_ok" in gate["failed_checks"]
