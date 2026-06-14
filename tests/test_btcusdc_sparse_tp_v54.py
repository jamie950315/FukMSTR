from __future__ import annotations

import pandas as pd

from lob_microprice_lab.btcusdc_sparse_tp import (
    SparseTakeProfitPolicy,
    annotate_sparse_tp_delay_outcomes,
    apply_take_profit_exit,
    build_direction_flip_entries,
    build_sparse_abs_return_entries,
    decide_sparse_tp_promotion,
    sparse_tp_to_contract_source_ledger,
    sample_null_sparse_entries,
    shift_sparse_entries_to_delay,
    summarize_boolean_runs,
    summarize_sparse_delay_scan,
    summarize_sparse_delay_signal_fragility,
    summarize_sparse_tp_price_path,
    summarize_sparse_tp_by_fold_sets,
    summarize_sparse_tp_outcomes,
)


def test_apply_take_profit_exit_handles_long_and_short_hits() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:01:00Z",
                    "2026-01-01T00:02:00Z",
                ],
                utc=True,
            ),
            "open": [100.0, 100.1, 99.9],
            "high": [100.0, 100.9, 100.2],
            "low": [100.0, 99.1, 99.0],
        }
    )
    entries = pd.DataFrame(
        {
            "fold": [1, 1],
            "idx": [0, 0],
            "timestamp": [bars.loc[0, "timestamp"], bars.loc[0, "timestamp"]],
            "replay_date": ["2026-01-01", "2026-01-01"],
            "signal": [1, -1],
            "entry_px": [100.0, 100.0],
            "threshold": [10.0, 10.0],
        }
    )

    out = apply_take_profit_exit(entries, bars, SparseTakeProfitPolicy(take_profit_bps=80.0, horizon_minutes=2), bars_prepared=True)

    assert out["exit_reason"].tolist() == ["take_profit", "take_profit"]
    assert out["exit_idx"].tolist() == [1, 1]
    assert out["gross_pnl_bps"].tolist() == [80.0, 80.0]
    assert out["cost_bps"].tolist() == [8.0, 8.0]
    assert out["net_pnl_bps"].tolist() == [72.0, 72.0]


def test_apply_take_profit_exit_falls_back_to_horizon_open() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:01:00Z",
                    "2026-01-01T00:02:00Z",
                ],
                utc=True,
            ),
            "open": [100.0, 100.1, 101.0],
            "high": [100.0, 100.2, 101.2],
            "low": [100.0, 99.9, 100.8],
        }
    )
    entries = pd.DataFrame(
        {
            "fold": [1],
            "idx": [0],
            "timestamp": [bars.loc[0, "timestamp"]],
            "replay_date": ["2026-01-01"],
            "signal": [1],
            "entry_px": [100.0],
            "threshold": [10.0],
        }
    )

    out = apply_take_profit_exit(entries, bars, SparseTakeProfitPolicy(take_profit_bps=150.0, horizon_minutes=2))

    assert out.loc[0, "exit_reason"] == "horizon"
    assert out.loc[0, "exit_idx"] == 2
    assert abs(float(out.loc[0, "gross_pnl_bps"]) - 100.0) < 1e-9
    assert abs(float(out.loc[0, "net_pnl_bps"]) - 92.0) < 1e-9


def test_build_sparse_abs_return_entries_uses_fold_calibration_and_delayed_entry() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=9, freq="min"),
            "open": [100.0, 101.0, 103.0, 100.0, 112.0, 111.0, 110.0, 109.0, 108.0],
            "high": [100.0, 101.2, 103.2, 100.2, 112.2, 111.2, 110.2, 109.2, 108.2],
            "low": [99.8, 100.8, 102.8, 99.8, 111.8, 110.8, 109.8, 108.8, 107.8],
            "close": [100.0, 101.0, 103.0, 100.0, 112.0, 111.0, 110.0, 109.0, 108.0],
            "volume": [1.0] * 9,
        }
    )
    folds = ((1, "2026-01-01T00:01:00Z", "2026-01-01T00:04:00Z", "2026-01-01T00:04:00Z", "2026-01-01T00:08:00Z"),)

    out = build_sparse_abs_return_entries(
        bars,
        folds=folds,
        entry_delay_minutes=1,
        lookback_minutes=1,
        horizon_minutes=2,
        quantile=1.0,
    )

    assert len(out) == 1
    row = out.iloc[0]
    assert int(row["fold"]) == 1
    assert int(row["signal_idx"]) == 4
    assert int(row["idx"]) == 5
    assert row["signal_timestamp"] == pd.Timestamp("2026-01-01T00:04:00Z")
    assert row["timestamp"] == pd.Timestamp("2026-01-01T00:05:00Z")
    assert float(row["entry_px"]) == 111.0
    assert int(row["signal"]) == -1
    assert abs(float(row["threshold"]) - 291.26213592232995) < 1e-9


def test_build_sparse_abs_return_entries_supports_direction_modes() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=9, freq="min"),
            "open": [100.0, 101.0, 103.0, 100.0, 112.0, 111.0, 110.0, 109.0, 108.0],
            "high": [100.0, 101.2, 103.2, 100.2, 112.2, 111.2, 110.2, 109.2, 108.2],
            "low": [99.8, 100.8, 102.8, 99.8, 111.8, 110.8, 109.8, 108.8, 107.8],
            "close": [100.0, 101.0, 103.0, 100.0, 112.0, 111.0, 110.0, 109.0, 108.0],
            "volume": [1.0] * 9,
        }
    )
    folds = ((1, "2026-01-01T00:01:00Z", "2026-01-01T00:04:00Z", "2026-01-01T00:04:00Z", "2026-01-01T00:08:00Z"),)

    momentum = build_sparse_abs_return_entries(
        bars,
        folds=folds,
        entry_delay_minutes=1,
        lookback_minutes=1,
        horizon_minutes=2,
        quantile=1.0,
        direction="momentum",
    )
    reversal = build_sparse_abs_return_entries(
        bars,
        folds=folds,
        entry_delay_minutes=1,
        lookback_minutes=1,
        horizon_minutes=2,
        quantile=1.0,
        direction="reversal",
    )

    assert momentum["signal"].tolist() == [1]
    assert reversal["signal"].tolist() == [-1]
    assert momentum["direction"].tolist() == ["momentum"]


def test_shift_sparse_entries_to_delay_reprices_and_keeps_validation_window() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=7, freq="min"),
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "high": [100.2, 101.2, 102.2, 103.2, 104.2, 105.2, 106.2],
            "low": [99.8, 100.8, 101.8, 102.8, 103.8, 104.8, 105.8],
        }
    )
    entries = pd.DataFrame(
        {
            "fold": [1, 1],
            "signal_idx": [1, 4],
            "idx": [1, 4],
            "entry_delay_min": [0, 0],
            "signal_timestamp": [bars.loc[1, "timestamp"], bars.loc[4, "timestamp"]],
            "timestamp": [bars.loc[1, "timestamp"], bars.loc[4, "timestamp"]],
            "replay_date": ["2026-01-01", "2026-01-01"],
            "signal": [1, -1],
            "entry_px": [101.0, 104.0],
            "threshold": [10.0, 10.0],
        }
    )
    folds = ((1, "2025-12-31", "2026-01-01T00:01:00Z", "2026-01-01T00:01:00Z", "2026-01-01T00:06:00Z"),)

    out = shift_sparse_entries_to_delay(entries, bars, folds=folds, entry_delay_minutes=2, bars_prepared=True)

    assert len(out) == 1
    assert int(out.loc[0, "signal_idx"]) == 1
    assert int(out.loc[0, "idx"]) == 3
    assert int(out.loc[0, "entry_delay_min"]) == 2
    assert out.loc[0, "timestamp"] == pd.Timestamp("2026-01-01T00:03:00Z")
    assert float(out.loc[0, "entry_px"]) == 103.0


def test_summarize_boolean_runs_groups_contiguous_delay_ranges() -> None:
    scan = pd.DataFrame(
        {
            "entry_delay_min": [0, 1, 2, 3, 4, 5],
            "basic_gate_screen": [True, True, False, False, True, False],
        }
    )

    out = summarize_boolean_runs(scan, value_col="basic_gate_screen", index_col="entry_delay_min")

    assert out.to_dict("records") == [
        {"value": True, "start": 0, "end": 1, "count": 2},
        {"value": False, "start": 2, "end": 3, "count": 2},
        {"value": True, "start": 4, "end": 4, "count": 1},
        {"value": False, "start": 5, "end": 5, "count": 1},
    ]


def test_summarize_sparse_delay_signal_fragility_reports_loss_ranges() -> None:
    ledger = pd.DataFrame(
        {
            "scan_entry_delay_min": [0, 1, 2, 0, 1, 2],
            "fold": [5, 5, 5, 6, 6, 6],
            "signal_idx": [10, 10, 10, 20, 20, 20],
            "signal_timestamp": pd.to_datetime(["2026-01-01T00:10:00Z"] * 3 + ["2026-01-02T00:20:00Z"] * 3),
            "signal": [1, 1, 1, -1, -1, -1],
            "exit_reason": ["take_profit", "horizon", "horizon", "take_profit", "take_profit", "take_profit"],
            "net_pnl_bps": [72.0, -2.0, -5.0, 72.0, 72.0, 72.0],
        }
    )

    out = summarize_sparse_delay_signal_fragility(ledger, quote_surcharge_bps=0.5)

    assert out.loc[0, "signal_idx"] == 10
    assert out.loc[0, "loss_delay_count"] == 2
    assert out.loc[0, "loss_delay_ranges"] == "1-2"
    assert out.loc[0, "worst_delay"] == 2
    assert out.loc[0, "worst_final_net_pnl_bps"] == -5.5
    assert out.loc[1, "signal_idx"] == 20
    assert out.loc[1, "loss_delay_count"] == 0
    assert out.loc[1, "loss_delay_ranges"] == ""


def test_summarize_sparse_delay_scan_reports_pass_counts_and_worst_delay() -> None:
    scan = pd.DataFrame(
        {
            "entry_delay_min": [0, 1, 2, 3],
            "screen_passed": [True, False, True, False],
            "total_net_pnl_bps": [100.0, -20.0, 50.0, -5.0],
            "min_trade_net_pnl_bps": [10.0, -30.0, 5.0, -10.0],
        }
    )

    out = summarize_sparse_delay_scan(
        scan,
        pass_col="screen_passed",
        total_col="total_net_pnl_bps",
        min_trade_col="min_trade_net_pnl_bps",
    )

    assert out["delay_count"] == 4
    assert out["pass_count"] == 2
    assert out["fail_count"] == 2
    assert out["pass_rate"] == 0.5
    assert out["fail_delay_ranges"] == "1,3"
    assert out["worst_delay"] == 1
    assert out["min_total_net_pnl_bps"] == -20.0
    assert out["min_trade_net_pnl_bps"] == -30.0


def test_decide_sparse_tp_promotion_rejects_failed_replay_and_dense_holdout() -> None:
    out = decide_sparse_tp_promotion(
        true_replay_gate_passed=False,
        v60_holdout_dense_pass_count=111,
        v60_holdout_dense_delay_count=121,
        design_robust_holdout_pass_count=0,
        design_robust_holdout_delay_count=121,
    )

    assert out["promote_sparse_tp"] is False
    assert out["status"] == "reject"
    assert out["primary_reasons"] == [
        "true_btcusdc_replay_failed",
        "v60_dense_holdout_not_fully_robust",
        "design_robust_selector_failed_holdout",
    ]


def test_summarize_sparse_tp_outcomes_subtracts_quote_surcharge() -> None:
    ledger = pd.DataFrame(
        {
            "net_pnl_bps": [72.0, -10.0],
            "exit_reason": ["take_profit", "horizon"],
            "hold_sec": [60.0, 120.0],
        }
    )

    out = summarize_sparse_tp_outcomes(ledger, quote_surcharge_bps=0.5)

    assert out["trades"] == 2
    assert out["wins"] == 1
    assert out["win_rate"] == 0.5
    assert out["take_profit_rate"] == 0.5
    assert out["total_net_pnl_bps"] == 61.0
    assert out["mean_net_pnl_bps"] == 30.5
    assert out["min_trade_net_pnl_bps"] == -10.5
    assert out["max_hold_sec"] == 120.0


def test_summarize_sparse_tp_by_fold_sets_reports_design_and_holdout() -> None:
    ledger = pd.DataFrame(
        {
            "fold": [1, 2, 5],
            "net_pnl_bps": [72.0, -10.0, 72.0],
            "exit_reason": ["take_profit", "horizon", "take_profit"],
            "hold_sec": [60.0, 120.0, 180.0],
        }
    )

    out = summarize_sparse_tp_by_fold_sets(ledger, design_folds={1, 2, 3, 4}, holdout_folds={5, 6, 7}, quote_surcharge_bps=0.5)

    assert out["design_trades"] == 2
    assert out["design_wins"] == 1
    assert out["design_total_net_pnl_bps"] == 61.0
    assert out["holdout_trades"] == 1
    assert out["holdout_wins"] == 1
    assert out["holdout_total_net_pnl_bps"] == 71.5


def test_annotate_sparse_tp_delay_outcomes_flags_target_and_final_net() -> None:
    delay_1 = pd.DataFrame(
        {
            "fold": [6],
            "signal_idx": [100],
            "signal_timestamp": pd.to_datetime(["2026-01-01T00:00:00Z"]),
            "idx": [101],
            "timestamp": pd.to_datetime(["2026-01-01T00:01:00Z"]),
            "signal": [-1],
            "entry_px": [100.0],
            "tp_bps": [80.0],
            "exit_reason": ["take_profit"],
            "net_pnl_bps": [72.0],
        }
    )
    delay_5 = pd.DataFrame(
        {
            "fold": [6],
            "signal_idx": [100],
            "signal_timestamp": pd.to_datetime(["2026-01-01T00:00:00Z"]),
            "idx": [105],
            "timestamp": pd.to_datetime(["2026-01-01T00:05:00Z"]),
            "signal": [-1],
            "entry_px": [99.0],
            "tp_bps": [80.0],
            "exit_reason": ["horizon"],
            "net_pnl_bps": [-12.0],
        }
    )

    out = annotate_sparse_tp_delay_outcomes({1: delay_1, 5: delay_5}, quote_surcharge_bps=0.5)

    assert out["entry_delay_min"].tolist() == [1, 5]
    assert out["tp_hit"].tolist() == [True, False]
    assert out["is_loss_after_surcharge"].tolist() == [False, True]
    assert out["final_net_pnl_bps"].tolist() == [71.5, -12.5]
    assert out["tp_target_px"].tolist() == [99.2, 98.208]


def test_summarize_sparse_tp_price_path_reports_short_target_miss() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="min"),
            "open": [100.0, 99.8, 99.7, 101.0],
            "high": [100.0, 100.2, 100.3, 101.1],
            "low": [100.0, 99.1, 99.3, 100.9],
        }
    )

    out = summarize_sparse_tp_price_path(
        bars,
        entry_idx=0,
        horizon_minutes=3,
        signal=-1,
        entry_px=100.0,
        take_profit_bps=100.0,
    )

    assert out["target_hit"] is False
    assert out["best_touch_idx"] == 1
    assert out["best_touch_px"] == 99.1
    assert out["tp_target_px"] == 99.0
    assert abs(out["target_miss_bps"] - 10.101010101010166) < 1e-9
    assert abs(out["horizon_gross_pnl_bps"] - -100.0) < 1e-9


def test_summarize_sparse_tp_price_path_reports_first_short_hit() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="min"),
            "open": [100.0, 100.2, 99.5, 99.0],
            "high": [100.0, 100.3, 99.7, 99.2],
            "low": [100.0, 99.3, 98.9, 98.7],
        }
    )

    out = summarize_sparse_tp_price_path(
        bars,
        entry_idx=0,
        horizon_minutes=3,
        signal=-1,
        entry_px=100.0,
        take_profit_bps=100.0,
    )

    assert out["target_hit"] is True
    assert out["first_hit_idx"] == 2
    assert out["first_hit_timestamp"] == pd.Timestamp("2026-01-01T00:02:00Z")
    assert out["first_hit_px"] == 98.9


def test_sparse_tp_to_contract_source_ledger_writes_gate_columns_and_equity() -> None:
    ledger = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"]),
            "entry_px": [100.0, 101.0],
            "exit_px": [100.8, 100.192],
            "signal": [1, -1],
            "fold": [5, 6],
            "entry_delay_min": [1, 1],
            "gross_pnl_bps": [80.0, 80.0],
            "cost_bps": [8.0, 8.0],
            "net_pnl_bps": [72.0, 72.0],
            "exit_reason": ["take_profit", "take_profit"],
            "hold_sec": [60.0, 120.0],
            "tp_bps": [80.0, 80.0],
            "replay_date": ["2026-01-01", "2026-01-01"],
            "threshold": [10.0, 11.0],
            "lookback_minutes": [1440, 1440],
            "horizon_minutes": [1440, 1440],
            "filter_feature": ["abs_return_bps", "abs_return_bps"],
            "quantile": [0.995, 0.995],
        }
    )

    out = sparse_tp_to_contract_source_ledger(ledger)

    assert out["best_bid"].tolist() == [100.0, 101.0]
    assert out["best_ask"].tolist() == [100.0, 101.0]
    assert out["latency_sec"].tolist() == [60.0, 60.0]
    assert out["raw_selective_signal"].tolist() == [1, -1]
    assert out["traded"].tolist() == [1, 1]
    assert out["equity_bps"].tolist() == [72.0, 144.0]


def test_build_direction_flip_entries_preserves_entry_fields_and_flips_signal() -> None:
    entries = pd.DataFrame(
        {
            "fold": [1, 1],
            "idx": [4, 8],
            "signal": [1, -1],
            "timestamp": pd.to_datetime(["2026-01-01T00:04:00Z", "2026-01-01T00:08:00Z"]),
            "entry_px": [100.0, 101.0],
            "direction": ["reversal", "reversal"],
        }
    )

    out = build_direction_flip_entries(entries)

    assert out["idx"].tolist() == [4, 8]
    assert out["entry_px"].tolist() == [100.0, 101.0]
    assert out["signal"].tolist() == [-1, 1]
    assert out["direction"].tolist() == ["reversal_direction_flip", "reversal_direction_flip"]


def test_sample_null_sparse_entries_preserves_fold_counts_directions_and_windows() -> None:
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=12, freq="min"),
            "open": [100.0 + i for i in range(12)],
            "high": [100.2 + i for i in range(12)],
            "low": [99.8 + i for i in range(12)],
            "close": [100.0 + i for i in range(12)],
            "volume": [1.0] * 12,
        }
    )
    entries = pd.DataFrame(
        {
            "fold": [1, 1, 2],
            "signal": [1, -1, -1],
            "entry_delay_min": [1, 1, 1],
            "lookback_minutes": [2, 2, 2],
            "horizon_minutes": [1, 1, 1],
            "threshold": [99.0, 99.0, 88.0],
            "filter_feature": ["abs_return_bps", "abs_return_bps", "abs_return_bps"],
            "quantile": [0.995, 0.995, 0.995],
        }
    )
    folds = (
        (1, "2025-12-31T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:02:00Z", "2026-01-01T00:07:00Z"),
        (2, "2025-12-31T00:00:00Z", "2026-01-01T00:00:00Z", "2026-01-01T00:07:00Z", "2026-01-01T00:11:00Z"),
    )

    out = sample_null_sparse_entries(entries, bars, folds=folds, seed=7, run_id=3)

    assert out.groupby("fold").size().to_dict() == {1: 2, 2: 1}
    assert sorted(out.loc[out["fold"] == 1, "signal"].tolist()) == [-1, 1]
    assert out.loc[out["fold"] == 2, "signal"].tolist() == [-1]
    assert out["null_run"].tolist() == [3, 3, 3]
    assert out.loc[out["fold"] == 1, "timestamp"].between(pd.Timestamp("2026-01-01T00:02:00Z"), pd.Timestamp("2026-01-01T00:06:00Z")).all()
    assert out.loc[out["fold"] == 2, "timestamp"].between(pd.Timestamp("2026-01-01T00:07:00Z"), pd.Timestamp("2026-01-01T00:10:00Z")).all()
