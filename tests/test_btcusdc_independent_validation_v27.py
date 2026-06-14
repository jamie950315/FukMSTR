from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    BTCUSDCCandidate,
    aggregate_btcusdc_aggtrades_to_bars,
    audit_candidate_selection_gap,
    audit_fixed_family_transfer,
    audit_hourly_gate_transfer,
    audit_quantile_band_selector,
    audit_prequential_family_selector,
    audit_prequential_meta_selector,
    audit_prequential_selector_policies,
    audit_topk_portfolio_selector,
    build_delayed_candidate_trade_ledger,
    build_candidate_trade_ledger,
    audit_prequential_hour_exclusion_gate,
    build_delayed_candidate_trade_ledger_grid,
    evaluate_candidate_grid,
    select_design_hour_exclusion_gate,
    summarize_cost_delay_surface,
    summarize_delay_monthly_cooldown_grid,
    summarize_holdout_failure_attribution,
    summarize_bucket_transfer_stability,
    apply_prequential_bucket_guard,
    summarize_route_closure_decision,
    summarize_route_inventory_decision,
    summarize_fixed_family_viability,
    summarize_signal_inversion_viability,
    summarize_cost_edge_viability,
    summarize_static_bucket_viability,
    summarize_rescue_hypothesis_closure,
    summarize_short_term_candidate_validation,
    summarize_short_term_repair_candidates,
    summarize_last_two_year_stability,
    summarize_two_year_stability_repair_candidates,
    summarize_forward_monitoring_window,
    select_delay_monthly_cooldown_policy,
    summarize_hour_exclusion_combination_null,
    summarize_delay_stress_grid,
    summarize_fixed_policy_stability,
    summarize_monthly_loss_cooldown,
    run_btcusdc_rolling_forward_validation,
    run_btcusdc_independent_validation,
    run_btcusdc_nested_recency_validation,
    select_candidate_by_metric_prefix,
    select_candidate_from_calibration,
)


def _klines(minutes: int = 20) -> pd.DataFrame:
    ts = pd.date_range("2026-01-01T00:00:00Z", periods=minutes, freq="min")
    open_px = [100.0 + i for i in range(minutes)]
    close_px = [x + 0.1 for x in open_px]
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_px,
            "high": [x + 0.5 for x in open_px],
            "low": [x - 0.5 for x in open_px],
            "close": close_px,
            "volume": [10.0 + i for i in range(minutes)],
        }
    )


def test_build_candidate_trade_ledger_keeps_trades_non_overlapping() -> None:
    candidate = BTCUSDCCandidate(
        lookback_minutes=1,
        horizon_minutes=3,
        direction="long",
        filter_feature="abs_return_bps",
        threshold=0.0,
        fee_bps=0.0,
    )

    trades = build_candidate_trade_ledger(_klines(), candidate)

    assert len(trades) > 1
    gaps = pd.to_datetime(trades["timestamp"], utc=True).diff().dropna().dt.total_seconds() / 60.0
    assert float(gaps.min()) >= 3.0


def test_build_delayed_candidate_trade_ledger_grid_keeps_each_requested_delay() -> None:
    candidate = BTCUSDCCandidate(
        lookback_minutes=1,
        horizon_minutes=3,
        direction="long",
        filter_feature="abs_return_bps",
        threshold=0.0,
        fee_bps=0.0,
    )

    ledgers = build_delayed_candidate_trade_ledger_grid(_klines(30), candidate, entry_delay_minutes=[0, 2, 5])

    assert sorted(ledgers["entry_delay_minutes"].unique().tolist()) == [0, 2, 5]
    assert (ledgers.groupby("entry_delay_minutes").size() > 0).all()


def test_summarize_delay_stress_grid_flags_negative_delay_total() -> None:
    trades = pd.DataFrame(
        [
            {"entry_delay_minutes": 0, "fold": 1, "net_pnl_bps": 10.0},
            {"entry_delay_minutes": 0, "fold": 2, "net_pnl_bps": 5.0},
            {"entry_delay_minutes": 5, "fold": 1, "net_pnl_bps": 8.0},
            {"entry_delay_minutes": 5, "fold": 2, "net_pnl_bps": -20.0},
        ]
    )

    result = summarize_delay_stress_grid(
        trades,
        delay_col="entry_delay_minutes",
        fold_col="fold",
        min_positive_delay_rate=1.0,
        min_worst_delay_total_net_pnl_bps=0.0,
    )

    summary = pd.DataFrame(result["delays"])
    assert result["aggregate"]["passed"] is False
    assert result["aggregate"]["positive_delay_rate"] == 0.5
    assert result["aggregate"]["worst_delay_total_net_pnl_bps"] == -12.0
    assert summary.loc[summary["entry_delay_minutes"] == 5, "positive"].iloc[0] == False


def test_summarize_cost_delay_surface_subtracts_extra_cost_per_trade() -> None:
    trades = pd.DataFrame(
        [
            {"entry_delay_minutes": 0, "net_pnl_bps": 10.0},
            {"entry_delay_minutes": 0, "net_pnl_bps": 5.0},
            {"entry_delay_minutes": 1, "net_pnl_bps": 4.0},
            {"entry_delay_minutes": 1, "net_pnl_bps": 4.0},
        ]
    )

    result = summarize_cost_delay_surface(
        trades,
        extra_cost_bps=[0.0, 5.0],
        max_delay_minutes=[0, 1],
        min_positive_delay_rate=1.0,
        min_worst_delay_total_net_pnl_bps=0.0,
    )

    rows = pd.DataFrame(result["rows"])
    cost5_delay1 = rows.loc[(rows["extra_cost_bps"] == 5.0) & (rows["max_delay_minutes"] == 1)].iloc[0]
    assert cost5_delay1["worst_delay_total_net_pnl_bps"] == -2.0
    assert cost5_delay1["positive_delay_rate"] == 0.5
    assert cost5_delay1["passed"] == False
    assert result["aggregate"]["best_passed_extra_cost_bps"] == 0.0
    assert result["aggregate"]["best_passed_max_delay_minutes"] == 1


def test_summarize_monthly_loss_cooldown_skips_only_after_realized_loss() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-05T00:00:00Z", "net_pnl_bps": -10.0},
            {"timestamp": "2026-02-05T00:00:00Z", "net_pnl_bps": 100.0},
            {"timestamp": "2026-03-05T00:00:00Z", "net_pnl_bps": 20.0},
        ]
    )

    result = summarize_monthly_loss_cooldown(trades, trigger_negative_months=1, cooldown_months=1)

    months = pd.DataFrame(result["months"])
    assert months.loc[months["month"] == "2026-01", "risk_off"].iloc[0] == False
    assert months.loc[months["month"] == "2026-02", "risk_off"].iloc[0] == True
    assert months.loc[months["month"] == "2026-03", "risk_off"].iloc[0] == False
    assert result["aggregate"]["total_net_pnl_bps"] == 10.0
    assert result["aggregate"]["skipped_trades"] == 1


def test_summarize_delay_monthly_cooldown_grid_applies_cost_and_policy_per_delay() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-05T00:00:00Z", "entry_delay_minutes": 0, "fold": 1, "net_pnl_bps": -10.0},
            {"timestamp": "2026-02-05T00:00:00Z", "entry_delay_minutes": 0, "fold": 1, "net_pnl_bps": 100.0},
            {"timestamp": "2026-03-05T00:00:00Z", "entry_delay_minutes": 0, "fold": 2, "net_pnl_bps": 20.0},
            {"timestamp": "2026-01-05T00:00:00Z", "entry_delay_minutes": 1, "fold": 1, "net_pnl_bps": 10.0},
            {"timestamp": "2026-02-05T00:00:00Z", "entry_delay_minutes": 1, "fold": 2, "net_pnl_bps": 10.0},
        ]
    )

    result = summarize_delay_monthly_cooldown_grid(
        trades,
        extra_cost_bps=5.0,
        max_delay_minutes=1,
        trigger_negative_months=1,
        cooldown_months=1,
        holdout_folds=[2],
    )

    rows = pd.DataFrame(result["delays"])
    delay0 = rows.loc[rows["entry_delay_minutes"] == 0].iloc[0]
    delay1 = rows.loc[rows["entry_delay_minutes"] == 1].iloc[0]
    assert delay0["total_net_pnl_bps"] == 0.0
    assert delay0["skipped_trades"] == 1
    assert delay0["holdout_total_net_pnl_bps"] == 15.0
    assert delay1["total_net_pnl_bps"] == 10.0
    assert result["aggregate"]["positive_delay_rate"] == 0.5


def test_select_delay_monthly_cooldown_policy_uses_design_metrics_only() -> None:
    rows = [
        {
            "trigger_negative_months": 1,
            "cooldown_months": 1,
            "design_positive_delay_rate": 1.0,
            "design_worst_delay_total_net_pnl_bps": 5.0,
            "design_total_net_pnl_bps": 10.0,
            "holdout_total_net_pnl_bps": -999.0,
        },
        {
            "trigger_negative_months": 2,
            "cooldown_months": 1,
            "design_positive_delay_rate": 0.5,
            "design_worst_delay_total_net_pnl_bps": -1.0,
            "design_total_net_pnl_bps": 100.0,
            "holdout_total_net_pnl_bps": 999.0,
        },
    ]

    selected = select_delay_monthly_cooldown_policy(pd.DataFrame(rows))

    assert int(selected["trigger_negative_months"]) == 1
    assert int(selected["cooldown_months"]) == 1


def test_summarize_holdout_failure_attribution_breaks_out_loss_sources() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-05T01:00:00Z", "entry_delay_minutes": 0, "fold": 4, "net_pnl_bps": 100.0},
            {"timestamp": "2026-01-05T01:00:00Z", "entry_delay_minutes": 0, "fold": 5, "net_pnl_bps": -20.0},
            {"timestamp": "2026-01-06T01:00:00Z", "entry_delay_minutes": 1, "fold": 5, "net_pnl_bps": -30.0},
            {"timestamp": "2026-02-05T02:00:00Z", "entry_delay_minutes": 1, "fold": 6, "net_pnl_bps": 10.0},
            {"timestamp": "2026-02-06T02:00:00Z", "entry_delay_minutes": 2, "fold": 6, "net_pnl_bps": -60.0},
            {"timestamp": "2026-03-05T03:00:00Z", "entry_delay_minutes": 2, "fold": 7, "net_pnl_bps": 40.0},
        ]
    )

    result = summarize_holdout_failure_attribution(trades, holdout_folds=[5, 6, 7])

    assert result["aggregate"]["holdout_trades"] == 5
    assert result["aggregate"]["holdout_total_net_pnl_bps"] == -60.0
    assert result["aggregate"]["negative_fold_count"] == 2
    folds = pd.DataFrame(result["by_fold"])
    fold5 = folds.loc[folds["fold"] == 5].iloc[0]
    assert fold5["total_net_pnl_bps"] == -50.0
    assert fold5["negative_loss_share"] == 0.5
    months = pd.DataFrame(result["by_month"])
    assert months.loc[months["month"] == "2026-01", "total_net_pnl_bps"].iloc[0] == -50.0
    hours = pd.DataFrame(result["by_hour"])
    assert hours.loc[hours["hour"] == 2, "total_net_pnl_bps"].iloc[0] == -50.0
    delays = pd.DataFrame(result["by_delay"])
    assert delays.loc[delays["entry_delay_minutes"] == 1, "total_net_pnl_bps"].iloc[0] == -20.0


def test_summarize_bucket_transfer_stability_compares_design_and_holdout_signs() -> None:
    trades = pd.DataFrame(
        [
            {"bucket": "a", "fold": 1, "net_pnl_bps": 10.0},
            {"bucket": "a", "fold": 5, "net_pnl_bps": -5.0},
            {"bucket": "b", "fold": 1, "net_pnl_bps": -2.0},
            {"bucket": "b", "fold": 5, "net_pnl_bps": -3.0},
            {"bucket": "c", "fold": 2, "net_pnl_bps": 4.0},
            {"bucket": "c", "fold": 6, "net_pnl_bps": 8.0},
        ]
    )

    result = summarize_bucket_transfer_stability(
        trades,
        bucket_col="bucket",
        design_folds=[1, 2],
        holdout_folds=[5, 6],
    )

    agg = result["aggregate"]
    assert agg["bucket_count"] == 3
    assert agg["sign_agreement_rate"] == 2 / 3
    assert agg["design_positive_holdout_positive_rate"] == 0.5
    assert agg["design_negative_holdout_negative_rate"] == 1.0
    rows = pd.DataFrame(result["buckets"])
    bucket_a = rows.loc[rows["bucket"] == "a"].iloc[0]
    assert bucket_a["design_total_net_pnl_bps"] == 10.0
    assert bucket_a["holdout_total_net_pnl_bps"] == -5.0
    assert bucket_a["sign_agrees"] == False


def test_apply_prequential_bucket_guard_uses_only_prior_kept_bucket_results() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "entry_delay_minutes": 0, "bucket": "a", "net_pnl_bps": -10.0},
            {"timestamp": "2026-01-01T00:01:00Z", "entry_delay_minutes": 0, "bucket": "a", "net_pnl_bps": 100.0},
            {"timestamp": "2026-01-01T00:02:00Z", "entry_delay_minutes": 0, "bucket": "a", "net_pnl_bps": 5.0},
            {"timestamp": "2026-01-01T00:00:00Z", "entry_delay_minutes": 0, "bucket": "b", "net_pnl_bps": 10.0},
            {"timestamp": "2026-01-01T00:01:00Z", "entry_delay_minutes": 0, "bucket": "b", "net_pnl_bps": -5.0},
            {"timestamp": "2026-01-01T00:00:00Z", "entry_delay_minutes": 1, "bucket": "a", "net_pnl_bps": 7.0},
        ]
    )

    guarded = apply_prequential_bucket_guard(
        trades,
        bucket_col="bucket",
        group_cols=["entry_delay_minutes"],
        min_history_trades=1,
        min_cumulative_pnl_bps=0.0,
    ).sort_values(["entry_delay_minutes", "bucket", "timestamp"]).reset_index(drop=True)

    delay0_a = guarded.loc[(guarded["entry_delay_minutes"] == 0) & (guarded["bucket"] == "a")]
    assert delay0_a["guard_keep"].tolist() == [True, False, False]
    assert delay0_a["guard_prior_pnl_bps"].tolist() == [0.0, -10.0, -10.0]
    delay0_b = guarded.loc[(guarded["entry_delay_minutes"] == 0) & (guarded["bucket"] == "b")]
    assert delay0_b["guard_keep"].tolist() == [True, True]
    delay1_a = guarded.loc[(guarded["entry_delay_minutes"] == 1) & (guarded["bucket"] == "a")]
    assert delay1_a["guard_keep"].tolist() == [True]


def test_summarize_route_closure_decision_blocks_promotion_on_required_failure() -> None:
    evidence = [
        {"gate": "base_candidate", "passed": True, "required": True},
        {"gate": "holdout_contract", "passed": False, "required": True},
        {"gate": "diagnostic", "passed": False, "required": False},
    ]

    decision = summarize_route_closure_decision(evidence)

    assert decision["promote_route"] is False
    assert decision["route_closed"] is True
    assert decision["failed_required_gates"] == ["holdout_contract"]
    assert decision["failed_optional_gates"] == ["diagnostic"]


def test_summarize_route_closure_decision_promotes_when_required_gates_pass() -> None:
    evidence = [
        {"gate": "base_candidate", "passed": True, "required": True},
        {"gate": "holdout_contract", "passed": True, "required": True},
        {"gate": "diagnostic", "passed": False, "required": False},
    ]

    decision = summarize_route_closure_decision(evidence)

    assert decision["promote_route"] is True
    assert decision["route_closed"] is False
    assert decision["failed_required_gates"] == []


def test_summarize_route_inventory_decision_only_advances_promoted_routes() -> None:
    routes = [
        {"route": "a", "status": "closed", "promoted": False},
        {"route": "b", "status": "needs_validation", "promoted": False},
        {"route": "c", "status": "promoted", "promoted": True},
    ]

    decision = summarize_route_inventory_decision(routes)

    assert decision["promoted_routes"] == ["c"]
    assert decision["needs_validation_routes"] == ["b"]
    assert decision["closed_routes"] == ["a"]
    assert decision["next_action"] == "advance_promoted_route"


def test_summarize_route_inventory_decision_requests_new_hypothesis_when_none_promoted() -> None:
    routes = [
        {"route": "a", "status": "closed", "promoted": False},
        {"route": "b", "status": "needs_validation", "promoted": False},
    ]

    decision = summarize_route_inventory_decision(routes)

    assert decision["promoted_routes"] == []
    assert decision["next_action"] == "validate_or_create_new_hypothesis"


def test_select_candidate_from_calibration_ignores_validation_performance() -> None:
    evaluations = pd.DataFrame(
        [
            {"candidate_id": 1, "calibration_trades": 20, "calibration_total_net_pnl_bps": 10.0, "calibration_day_positive_rate": 0.6, "validation_total_net_pnl_bps": 1000.0},
            {"candidate_id": 2, "calibration_trades": 20, "calibration_total_net_pnl_bps": 50.0, "calibration_day_positive_rate": 0.6, "validation_total_net_pnl_bps": -500.0},
        ]
    )

    selected = select_candidate_from_calibration(evaluations, min_calibration_trades=10, min_calibration_day_positive_rate=0.5)

    assert int(selected["candidate_id"]) == 2


def test_evaluate_candidate_grid_adds_path_shape_metrics() -> None:
    rows = []
    for day in pd.date_range("2026-01-01", periods=4, freq="D"):
        for minute in range(24):
            ts = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=minute)
            px = 100.0 + minute + (day.day * 0.1)
            rows.append(
                {
                    "timestamp": ts,
                    "open": px,
                    "high": px + 0.5,
                    "low": px - 0.5,
                    "close": px + 0.1,
                    "volume": 10.0 + minute,
                    "replay_date": ts.date().isoformat(),
                }
            )
    frame = pd.DataFrame(rows)
    candidate = BTCUSDCCandidate(
        lookback_minutes=1,
        horizon_minutes=3,
        direction="long",
        filter_feature="abs_return_bps",
        threshold=0.0,
        fee_bps=0.0,
    )

    evaluations = evaluate_candidate_grid(frame.iloc[:48], frame.iloc[48:], [candidate], leverage=8.0)

    row = evaluations.iloc[0]
    assert row["calibration_active_day_count"] == 2
    assert "calibration_last_day_net_pnl_bps" in evaluations.columns
    assert "calibration_day_net_pnl_trend_bps" in evaluations.columns
    assert "calibration_max_drawdown_bps" in evaluations.columns
    assert "validation_profit_factor" in evaluations.columns
    assert row["validation_profit_factor"] != float("inf")


def test_run_btcusdc_independent_validation_uses_date_split(tmp_path: Path) -> None:
    rows = []
    for day in pd.date_range("2026-01-01", periods=4, freq="D"):
        for minute in range(12):
            ts = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=minute)
            px = 100.0 + minute
            rows.append(
                {
                    "timestamp": ts,
                    "open": px,
                    "high": px + 0.5,
                    "low": px - 0.5,
                    "close": px + 0.1,
                    "volume": 10.0 + minute,
                }
            )
    kline_path = tmp_path / "BTCUSDC-1m-sample.csv"
    pd.DataFrame(rows).to_csv(kline_path, index=False)

    result = run_btcusdc_independent_validation(
        kline_paths=[kline_path],
        out_dir=tmp_path / "out",
        calibration_end="2026-01-02",
        validation_start="2026-01-03",
        lookbacks=(1,),
        horizons=(3,),
        directions=("long",),
        filter_features=("abs_return_bps",),
        quantiles=(0.0,),
        min_calibration_trades=2,
        min_calibration_day_positive_rate=0.0,
        leverage=8.0,
        fee_bps=0.0,
    )

    assert result["aggregate"]["calibration_start"] == "2026-01-01"
    assert result["aggregate"]["calibration_end"] == "2026-01-02"
    assert result["aggregate"]["validation_start"] == "2026-01-03"
    assert result["aggregate"]["validation_end"] == "2026-01-04"
    assert result["aggregate"]["selected_candidate"]["lookback_minutes"] == 1
    assert result["aggregate"]["validation_trades"] > 0
    assert (tmp_path / "out" / "btcusdc_v27_validation_trades.csv").exists()


def test_run_btcusdc_rolling_forward_validation_writes_fold_metrics(tmp_path: Path) -> None:
    rows = []
    for day in pd.date_range("2026-01-01", periods=6, freq="D"):
        for minute in range(24):
            ts = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=minute)
            px = 100.0 + minute + (day.day * 0.1)
            rows.append(
                {
                    "timestamp": ts,
                    "open": px,
                    "high": px + 0.5,
                    "low": px - 0.5,
                    "close": px + 0.1,
                    "volume": 10.0 + minute,
                }
            )
    kline_path = tmp_path / "BTCUSDC-1m-rolling.csv"
    pd.DataFrame(rows).to_csv(kline_path, index=False)

    result = run_btcusdc_rolling_forward_validation(
        kline_paths=[kline_path],
        out_dir=tmp_path / "rolling",
        start_date="2026-01-01",
        end_date="2026-01-06",
        calibration_days=2,
        validation_days=2,
        step_days=2,
        lookbacks=(1,),
        horizons=(3,),
        directions=("long",),
        filter_features=("abs_return_bps",),
        quantiles=(0.0,),
        min_calibration_trades=2,
        min_calibration_day_positive_rate=0.0,
        leverage=8.0,
        fee_bps=0.0,
        target_account_return_pct=0.0,
    )

    agg = result["aggregate"]
    assert agg["folds"] == 2
    assert agg["validation_windows_passed"] == 2
    assert agg["all_validation_windows_target_passed"] is True
    folds = pd.read_csv(tmp_path / "rolling" / "btcusdc_v28_fold_metrics.csv")
    assert list(folds["fold"]) == [1, 2]
    assert (folds["validation_trades"] > 0).all()
    assert (tmp_path / "rolling" / "btcusdc_v28_validation_trades.csv").exists()


def test_run_btcusdc_rolling_forward_validation_records_failed_candidate_windows(tmp_path: Path) -> None:
    rows = []
    for day in pd.date_range("2026-01-01", periods=4, freq="D"):
        for minute in range(12):
            ts = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=minute)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0 + minute,
                    "high": 100.5 + minute,
                    "low": 99.5 + minute,
                    "close": 100.1 + minute,
                    "volume": 10.0 + minute,
                }
            )
    kline_path = tmp_path / "BTCUSDC-1m-no-pass.csv"
    pd.DataFrame(rows).to_csv(kline_path, index=False)

    result = run_btcusdc_rolling_forward_validation(
        kline_paths=[kline_path],
        out_dir=tmp_path / "rolling_failed",
        start_date="2026-01-01",
        end_date="2026-01-04",
        calibration_days=2,
        validation_days=2,
        step_days=2,
        lookbacks=(1,),
        horizons=(3,),
        directions=("long",),
        filter_features=("abs_return_bps",),
        quantiles=(0.0,),
        min_calibration_trades=999,
        min_calibration_day_positive_rate=0.0,
        target_account_return_pct=0.0,
    )

    assert result["aggregate"]["folds"] == 1
    assert result["aggregate"]["risk_off_windows"] == 1
    folds = pd.read_csv(tmp_path / "rolling_failed" / "btcusdc_v28_fold_metrics.csv")
    assert folds.loc[0, "risk_off"] == True
    assert folds.loc[0, "failure_reason"] == "no candidate passed calibration requirements"


def test_run_btcusdc_rolling_forward_validation_can_risk_off_weak_calibration(tmp_path: Path) -> None:
    rows = []
    for day in pd.date_range("2026-01-01", periods=4, freq="D"):
        for minute in range(12):
            ts = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=minute)
            rows.append(
                {
                    "timestamp": ts,
                    "open": 100.0 + minute,
                    "high": 100.5 + minute,
                    "low": 99.5 + minute,
                    "close": 100.1 + minute,
                    "volume": 10.0 + minute,
                }
            )
    kline_path = tmp_path / "BTCUSDC-1m-risk-off.csv"
    pd.DataFrame(rows).to_csv(kline_path, index=False)

    result = run_btcusdc_rolling_forward_validation(
        kline_paths=[kline_path],
        out_dir=tmp_path / "rolling_risk_off",
        start_date="2026-01-01",
        end_date="2026-01-04",
        calibration_days=2,
        validation_days=2,
        step_days=2,
        lookbacks=(1,),
        horizons=(3,),
        directions=("long",),
        filter_features=("abs_return_bps",),
        quantiles=(0.0,),
        min_calibration_trades=2,
        min_calibration_day_positive_rate=0.0,
        min_calibration_account_return_pct=999.0,
        target_account_return_pct=0.0,
    )

    assert result["aggregate"]["risk_off_windows"] == 1
    assert result["aggregate"]["active_validation_windows"] == 0
    folds = pd.read_csv(tmp_path / "rolling_risk_off" / "btcusdc_v28_fold_metrics.csv")
    assert folds.loc[0, "risk_off"] == True
    assert folds.loc[0, "validation_trades"] == 0


def test_run_btcusdc_nested_recency_validation_writes_fold_metrics(tmp_path: Path) -> None:
    rows = []
    for day in pd.date_range("2026-01-01", periods=6, freq="D"):
        for minute in range(24):
            ts = pd.Timestamp(day, tz="UTC") + pd.Timedelta(minutes=minute)
            px = 100.0 + minute + (day.day * 0.1)
            rows.append(
                {
                    "timestamp": ts,
                    "open": px,
                    "high": px + 0.5,
                    "low": px - 0.5,
                    "close": px + 0.1,
                    "volume": 10.0 + minute,
                }
            )
    kline_path = tmp_path / "BTCUSDC-1m-nested.csv"
    pd.DataFrame(rows).to_csv(kline_path, index=False)

    result = run_btcusdc_nested_recency_validation(
        kline_paths=[kline_path],
        out_dir=tmp_path / "nested",
        start_date="2026-01-01",
        end_date="2026-01-06",
        calibration_days=4,
        selector_days=2,
        validation_days=2,
        step_days=2,
        lookbacks=(1,),
        horizons=(3,),
        directions=("long",),
        filter_features=("abs_return_bps",),
        quantiles=(0.0,),
        min_selector_trades=2,
        min_selector_day_positive_rate=0.0,
        leverage=8.0,
        fee_bps=0.0,
        target_account_return_pct=0.0,
    )

    agg = result["aggregate"]
    assert agg["folds"] == 1
    assert agg["active_validation_windows"] == 1
    folds = pd.read_csv(tmp_path / "nested" / "btcusdc_v43_fold_metrics.csv")
    assert folds.loc[0, "generator_start"] == "2026-01-01"
    assert folds.loc[0, "selector_start"] == "2026-01-03"
    assert folds.loc[0, "validation_trades"] > 0
    assert (tmp_path / "nested" / "btcusdc_v43_validation_trades.csv").exists()


def test_audit_candidate_selection_gap_reports_oracle_and_selector() -> None:
    evaluations = pd.DataFrame(
        [
            {"fold": 1, "candidate_id": 1, "calibration_account_return_pct": 10.0, "calibration_day_positive_rate": 0.6, "calibration_trades": 20, "validation_account_return_pct": 80.0},
            {"fold": 1, "candidate_id": 2, "calibration_account_return_pct": 20.0, "calibration_day_positive_rate": 0.6, "calibration_trades": 20, "validation_account_return_pct": -10.0},
            {"fold": 2, "candidate_id": 3, "calibration_account_return_pct": 5.0, "calibration_day_positive_rate": 0.6, "calibration_trades": 20, "validation_account_return_pct": 55.0},
            {"fold": 2, "candidate_id": 4, "calibration_account_return_pct": 30.0, "calibration_day_positive_rate": 0.6, "calibration_trades": 20, "validation_account_return_pct": -5.0},
        ]
    )

    result = audit_candidate_selection_gap(evaluations, target_account_return_pct=50.0)

    assert result["aggregate"]["oracle_windows_passed"] == 2
    assert result["aggregate"]["calibration_selector_windows_passed"] == 0
    assert result["aggregate"]["oracle_minus_selector_pass_gap"] == 2


def test_audit_fixed_family_transfer_selects_on_train_folds_only() -> None:
    evaluations = pd.DataFrame(
        [
            {"fold": 1, "candidate_id": 1, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "selector_account_return_pct": 20.0, "validation_account_return_pct": 80.0},
            {"fold": 1, "candidate_id": 2, "direction": "reversal", "filter_feature": "range_bps", "quantile": 0.8, "selector_account_return_pct": 10.0, "validation_account_return_pct": -5.0},
            {"fold": 2, "candidate_id": 3, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "selector_account_return_pct": 30.0, "validation_account_return_pct": 70.0},
            {"fold": 2, "candidate_id": 4, "direction": "reversal", "filter_feature": "range_bps", "quantile": 0.8, "selector_account_return_pct": 15.0, "validation_account_return_pct": -10.0},
            {"fold": 3, "candidate_id": 5, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "selector_account_return_pct": 40.0, "validation_account_return_pct": 60.0},
            {"fold": 3, "candidate_id": 6, "direction": "reversal", "filter_feature": "range_bps", "quantile": 0.8, "selector_account_return_pct": 100.0, "validation_account_return_pct": 100.0},
            {"fold": 4, "candidate_id": 7, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "selector_account_return_pct": 50.0, "validation_account_return_pct": 55.0},
            {"fold": 4, "candidate_id": 8, "direction": "reversal", "filter_feature": "range_bps", "quantile": 0.8, "selector_account_return_pct": 100.0, "validation_account_return_pct": 100.0},
        ]
    )

    result = audit_fixed_family_transfer(
        evaluations,
        group_columns=("direction", "filter_feature", "quantile"),
        train_folds=(1, 2),
        validation_folds=(3, 4),
        current_selection_score="selector_account_return_pct",
        target_account_return_pct=50.0,
    )

    aggregate = result["aggregate"]
    assert aggregate["selected_family"]["direction"] == "momentum"
    assert aggregate["validation_windows_passed"] == 2
    assert aggregate["validation_total_account_return_pct"] == 115.0


def test_audit_hourly_gate_transfer_selects_hours_from_selector_only() -> None:
    selector_trades = pd.DataFrame(
        [
            {"fold": 1, "timestamp": "2026-01-01T01:00:00Z", "net_pnl_bps": 100.0},
            {"fold": 1, "timestamp": "2026-01-01T02:00:00Z", "net_pnl_bps": -10.0},
            {"fold": 2, "timestamp": "2026-01-02T03:00:00Z", "net_pnl_bps": 50.0},
            {"fold": 2, "timestamp": "2026-01-02T04:00:00Z", "net_pnl_bps": -5.0},
        ]
    )
    validation_trades = pd.DataFrame(
        [
            {"fold": 1, "timestamp": "2026-01-11T01:00:00Z", "net_pnl_bps": 20.0},
            {"fold": 1, "timestamp": "2026-01-11T02:00:00Z", "net_pnl_bps": 999.0},
            {"fold": 2, "timestamp": "2026-01-12T03:00:00Z", "net_pnl_bps": 30.0},
            {"fold": 2, "timestamp": "2026-01-12T04:00:00Z", "net_pnl_bps": 999.0},
        ]
    )

    result = audit_hourly_gate_transfer(
        selector_trades,
        validation_trades,
        top_n_values=(1,),
        leverage=1.0,
        target_account_return_pct=0.0,
    )

    folds = pd.DataFrame(result["folds"])
    assert folds.loc[0, "selected_hours"] == "1"
    assert folds.loc[1, "selected_hours"] == "3"
    assert result["summary"][0]["validation_total_account_return_pct"] == 0.5


def test_audit_prequential_selector_policies_uses_only_prior_folds() -> None:
    rows = []
    for fold, values in {
        1: {"a": 70.0, "b": -10.0},
        2: {"a": -20.0, "b": 80.0},
        3: {"a": 10.0, "b": 90.0},
    }.items():
        rows.append(
            {
                "fold": fold,
                "candidate_id": 1,
                "direction": "momentum",
                "filter_feature": "range_bps",
                "quantile": 0.9,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.6,
                "calibration_account_return_pct": 10.0,
                "calibration_mean_net_pnl_bps": 1.0,
                "calibration_win_rate": 0.6,
                "validation_account_return_pct": values["a"],
            }
        )
        rows.append(
            {
                "fold": fold,
                "candidate_id": 2,
                "direction": "reversal",
                "filter_feature": "range_bps",
                "quantile": 0.9,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.6,
                "calibration_account_return_pct": 5.0,
                "calibration_mean_net_pnl_bps": 0.5,
                "calibration_win_rate": 0.5,
                "validation_account_return_pct": values["b"],
            }
        )

    result = audit_prequential_selector_policies(
        pd.DataFrame(rows),
        policy_scores=("calibration_account_return_pct",),
        direction_filters=("*", "momentum", "reversal"),
        filter_feature_filters=("range_bps",),
        quantile_max_values=(0.9,),
        warmup_folds=1,
        ranking_rule="prior_pass_total",
        target_account_return_pct=50.0,
    )

    folds = pd.DataFrame(result["folds"])
    assert folds.loc[0, "risk_off"] == True
    assert folds.loc[1, "policy_id"] == 1
    assert folds.loc[2, "policy_id"] == 2
    assert result["aggregate"]["prequential_windows_passed"] == 1


def test_audit_prequential_meta_selector_trains_only_on_prior_folds() -> None:
    evaluations = pd.DataFrame(
        [
            {"fold": 1, "candidate_id": 1, "lookback_minutes": 5, "horizon_minutes": 60, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "threshold": 1.0, "selector_trades": 20, "selector_day_positive_rate": 0.6, "selector_account_return_pct": 10.0, "validation_account_return_pct": -10.0},
            {"fold": 1, "candidate_id": 2, "lookback_minutes": 5, "horizon_minutes": 60, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "threshold": 2.0, "selector_trades": 20, "selector_day_positive_rate": 0.6, "selector_account_return_pct": 100.0, "validation_account_return_pct": 80.0},
            {"fold": 2, "candidate_id": 1, "lookback_minutes": 5, "horizon_minutes": 60, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "threshold": 1.0, "selector_trades": 20, "selector_day_positive_rate": 0.6, "selector_account_return_pct": 20.0, "validation_account_return_pct": -5.0},
            {"fold": 2, "candidate_id": 2, "lookback_minutes": 5, "horizon_minutes": 60, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "threshold": 2.0, "selector_trades": 20, "selector_day_positive_rate": 0.6, "selector_account_return_pct": 110.0, "validation_account_return_pct": 90.0},
            {"fold": 3, "candidate_id": 1, "lookback_minutes": 5, "horizon_minutes": 60, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "threshold": 1.0, "selector_trades": 20, "selector_day_positive_rate": 0.6, "selector_account_return_pct": 30.0, "validation_account_return_pct": -20.0},
            {"fold": 3, "candidate_id": 2, "lookback_minutes": 5, "horizon_minutes": 60, "direction": "momentum", "filter_feature": "range_bps", "quantile": 0.8, "threshold": 2.0, "selector_trades": 20, "selector_day_positive_rate": 0.6, "selector_account_return_pct": 120.0, "validation_account_return_pct": 70.0},
        ]
    )

    result = audit_prequential_meta_selector(
        evaluations,
        feature_columns=("selector_account_return_pct", "threshold", "direction"),
        warmup_folds=2,
        min_selector_trades=20,
        min_selector_day_positive_rate=0.5,
        model_type="ridge",
        target_account_return_pct=50.0,
    )

    folds = pd.DataFrame(result["folds"])
    assert folds.loc[0, "risk_off"] == True
    selected = folds.loc[folds["fold"] == 3].iloc[0]
    assert int(selected["candidate_id"]) == 2
    assert bool(selected["target_passed"]) is True


def test_aggregate_btcusdc_aggtrades_to_bars_computes_taker_flow() -> None:
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00.100Z",
                    "2026-01-01T00:00:10.000Z",
                    "2026-01-01T00:01:00.000Z",
                ],
                utc=True,
            ),
            "price": [100.0, 101.0, 102.0],
            "quantity": [2.0, 1.0, 3.0],
            "is_buyer_maker": [False, True, False],
        }
    )

    bars = aggregate_btcusdc_aggtrades_to_bars(trades, freq="1min")

    assert len(bars) == 2
    assert bars.loc[0, "open"] == 100.0
    assert bars.loc[0, "close"] == 101.0
    assert bars.loc[0, "taker_buy_volume"] == 2.0
    assert bars.loc[0, "taker_sell_volume"] == 1.0
    assert abs(float(bars.loc[0, "signed_taker_imbalance"]) - (1.0 / 3.0)) < 1e-9


def test_flow_momentum_candidate_uses_prior_taker_imbalance() -> None:
    bars = _klines(20)
    bars["signed_taker_imbalance"] = [0.0, 0.0, 1.0, 1.0, 1.0] + [0.5] * 15
    candidate = BTCUSDCCandidate(
        lookback_minutes=2,
        horizon_minutes=3,
        direction="flow_momentum",
        filter_feature="abs_flow_imbalance",
        threshold=0.1,
        fee_bps=0.0,
    )

    trades = build_candidate_trade_ledger(bars, candidate)

    assert not trades.empty
    assert set(trades["signal"]) == {1}
    assert (trades["abs_flow_imbalance"] >= 0.1).all()


def test_build_delayed_candidate_trade_ledger_reprices_entry_and_exit() -> None:
    bars = _klines(12)
    bars["signed_taker_imbalance"] = [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    candidate = BTCUSDCCandidate(
        lookback_minutes=2,
        horizon_minutes=3,
        direction="flow_momentum",
        filter_feature="abs_flow_imbalance",
        threshold=0.1,
        fee_bps=0.0,
    )

    delayed = build_delayed_candidate_trade_ledger(bars, candidate, entry_delay_minutes=2)

    assert not delayed.empty
    first = delayed.iloc[0]
    assert first["signal_timestamp"] < first["timestamp"]
    assert first["entry_delay_minutes"] == 2
    assert first["entry_px"] == 105.0
    assert first["exit_px"] == 108.0
    assert first["gross_pnl_bps"] == (108.0 / 105.0 - 1.0) * 10000.0


def test_summarize_fixed_policy_stability_requires_positive_delay_and_fold() -> None:
    base = pd.DataFrame(
        {
            "net_pnl_bps": [120.0, -40.0, 80.0, 30.0],
            "fold": [1, 1, 2, 2],
        }
    )
    delays = pd.DataFrame(
        {
            "entry_delay_minutes": [0, 1, 2],
            "total_net_pnl_bps": [190.0, 125.0, 10.0],
        }
    )
    extra = pd.DataFrame(
        {
            "extra_cost_bps": [0.0, 4.0, 8.0],
            "total_net_pnl_bps": [190.0, 174.0, 158.0],
        }
    )

    out = summarize_fixed_policy_stability(
        base,
        fold_col="fold",
        delay_summary=delays,
        extra_cost_summary=extra,
        min_trades=4,
        min_active_folds=2,
        min_positive_fold_rate=1.0,
        min_worst_fold_net_pnl_bps=0.0,
        require_delay_total_positive=True,
        required_positive_extra_cost_bps=4.0,
    )

    assert out["passed"] is True
    assert out["trade_count"] == 4
    assert out["positive_fold_rate"] == 1.0
    assert out["worst_delay_total_net_pnl_bps"] == 10.0
    assert out["failed_checks"] == []


def test_select_design_hour_exclusion_gate_uses_design_folds_only() -> None:
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T01:00:00Z",
                    "2026-01-01T02:00:00Z",
                    "2026-01-02T01:00:00Z",
                    "2026-01-02T02:00:00Z",
                    "2026-01-03T01:00:00Z",
                    "2026-01-03T02:00:00Z",
                ],
                utc=True,
            ),
            "fold": [1, 1, 2, 2, 3, 3],
            "net_pnl_bps": [20.0, -200.0, 30.0, -100.0, -500.0, 500.0],
        }
    )

    gate = select_design_hour_exclusion_gate(
        trades,
        design_folds=[1, 2],
        max_excluded_hours=2,
        min_design_positive_fold_rate=1.0,
        min_design_worst_fold_net_pnl_bps=0.0,
    )

    assert gate["excluded_hours"] == [2]
    assert gate["selected_exclusion_count"] == 1
    assert gate["design_total_net_pnl_bps"] == 50.0


def test_audit_prequential_hour_exclusion_gate_uses_prior_folds_only() -> None:
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T01:00:00Z",
                    "2026-01-01T02:00:00Z",
                    "2026-01-02T01:00:00Z",
                    "2026-01-02T02:00:00Z",
                    "2026-01-03T01:00:00Z",
                    "2026-01-03T02:00:00Z",
                ],
                utc=True,
            ),
            "fold": [1, 1, 2, 2, 3, 3],
            "net_pnl_bps": [30.0, -200.0, 40.0, -100.0, 10.0, -500.0],
        }
    )

    out = audit_prequential_hour_exclusion_gate(
        trades,
        evaluation_folds=[3],
        min_history_folds=2,
        max_excluded_hours=2,
        min_design_positive_fold_rate=1.0,
        min_design_worst_fold_net_pnl_bps=0.0,
    )

    row = out["folds"][0]
    assert row["excluded_hours"] == [2]
    assert row["fold"] == 3
    assert row["total_net_pnl_bps"] == 10.0
    assert out["aggregate"]["passed"] is True


def test_summarize_hour_exclusion_combination_null_ranks_selected_combo() -> None:
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T01:00:00Z",
                    "2026-01-01T02:00:00Z",
                    "2026-01-01T03:00:00Z",
                ],
                utc=True,
            ),
            "fold": [1, 1, 2, 2],
            "net_pnl_bps": [100.0, -50.0, 80.0, -30.0],
        }
    )

    out = summarize_hour_exclusion_combination_null(trades, selected_excluded_hours=[1])

    assert out["combination_count"] == 24
    assert out["selected_total_net_pnl_bps"] == 150.0
    assert out["share_combinations_total_ge_selected"] == 1.0 / 24.0


def test_audit_prequential_family_selector_uses_prior_fold_family_performance() -> None:
    rows = []
    for fold, family_a, family_b in [(1, 70.0, -20.0), (2, -100.0, 80.0), (3, 5.0, 90.0)]:
        rows.append(
            {
                "fold": fold,
                "candidate_id": fold * 10 + 1,
                "lookback_minutes": 5,
                "horizon_minutes": 60,
                "direction": "momentum",
                "filter_feature": "range_bps",
                "quantile": 0.8,
                "calibration_account_return_pct": 10.0,
                "calibration_min_day_net_pnl_bps": -5.0,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.5,
                "validation_account_return_pct": family_a,
            }
        )
        rows.append(
            {
                "fold": fold,
                "candidate_id": fold * 10 + 2,
                "lookback_minutes": 5,
                "horizon_minutes": 60,
                "direction": "reversal",
                "filter_feature": "range_bps",
                "quantile": 0.8,
                "calibration_account_return_pct": 8.0,
                "calibration_min_day_net_pnl_bps": -4.0,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.5,
                "validation_account_return_pct": family_b,
            }
        )

    result = audit_prequential_family_selector(
        pd.DataFrame(rows),
        group_columns=("direction", "filter_feature"),
        warmup_folds=1,
        ranking_rule="prior_pass_total",
        current_selection_score="calibration_min_day_net_pnl_bps",
        target_account_return_pct=50.0,
    )

    folds = pd.DataFrame(result["folds"])
    assert folds.loc[0, "risk_off"] == True
    assert folds.loc[1, "direction"] == "momentum"
    assert folds.loc[2, "direction"] == "reversal"
    assert result["aggregate"]["prequential_windows_passed"] == 1


def test_audit_prequential_family_selector_collapses_family_by_calibration_score() -> None:
    evaluations = pd.DataFrame(
        [
            {
                "fold": 1,
                "candidate_id": 1,
                "direction": "momentum",
                "filter_feature": "range_bps",
                "quantile": 0.8,
                "calibration_account_return_pct": 1.0,
                "calibration_min_day_net_pnl_bps": -100.0,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.5,
                "validation_account_return_pct": 200.0,
            },
            {
                "fold": 1,
                "candidate_id": 2,
                "direction": "momentum",
                "filter_feature": "range_bps",
                "quantile": 0.8,
                "calibration_account_return_pct": 2.0,
                "calibration_min_day_net_pnl_bps": 0.0,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.5,
                "validation_account_return_pct": -50.0,
            },
            {
                "fold": 1,
                "candidate_id": 3,
                "direction": "reversal",
                "filter_feature": "range_bps",
                "quantile": 0.8,
                "calibration_account_return_pct": 3.0,
                "calibration_min_day_net_pnl_bps": -1.0,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.5,
                "validation_account_return_pct": 60.0,
            },
            {
                "fold": 2,
                "candidate_id": 4,
                "direction": "momentum",
                "filter_feature": "range_bps",
                "quantile": 0.8,
                "calibration_account_return_pct": 1.0,
                "calibration_min_day_net_pnl_bps": 0.0,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.5,
                "validation_account_return_pct": -10.0,
            },
            {
                "fold": 2,
                "candidate_id": 5,
                "direction": "reversal",
                "filter_feature": "range_bps",
                "quantile": 0.8,
                "calibration_account_return_pct": 1.0,
                "calibration_min_day_net_pnl_bps": 0.0,
                "calibration_trades": 20,
                "calibration_day_positive_rate": 0.5,
                "validation_account_return_pct": 70.0,
            },
        ]
    )

    result = audit_prequential_family_selector(
        evaluations,
        group_columns=("direction", "filter_feature", "quantile"),
        warmup_folds=1,
        ranking_rule="prior_pass_total",
        current_selection_score="calibration_min_day_net_pnl_bps",
        target_account_return_pct=50.0,
    )

    folds = pd.DataFrame(result["folds"])
    assert folds.loc[1, "direction"] == "reversal"
    assert result["aggregate"]["best_static_family_passed_windows"] <= 2


def test_audit_topk_portfolio_selector_averages_selected_validation_returns() -> None:
    evaluations = pd.DataFrame(
        [
            {"fold": 1, "candidate_id": 1, "calibration_min_day_net_pnl_bps": 3.0, "calibration_trades": 20, "calibration_day_positive_rate": 0.5, "validation_account_return_pct": 100.0, "validation_trades": 10},
            {"fold": 1, "candidate_id": 2, "calibration_min_day_net_pnl_bps": 2.0, "calibration_trades": 20, "calibration_day_positive_rate": 0.5, "validation_account_return_pct": -20.0, "validation_trades": 10},
            {"fold": 1, "candidate_id": 3, "calibration_min_day_net_pnl_bps": 1.0, "calibration_trades": 20, "calibration_day_positive_rate": 0.5, "validation_account_return_pct": 300.0, "validation_trades": 10},
            {"fold": 2, "candidate_id": 4, "calibration_min_day_net_pnl_bps": 1.0, "calibration_trades": 10, "calibration_day_positive_rate": 0.5, "validation_account_return_pct": 999.0, "validation_trades": 10},
        ]
    )

    result = audit_topk_portfolio_selector(
        evaluations,
        score_columns=("calibration_min_day_net_pnl_bps",),
        topk_values=(2,),
        min_calibration_trades=20,
        min_calibration_day_positive_rate=0.0,
        target_account_return_pct=50.0,
    )

    folds = pd.DataFrame(result["folds"])
    assert len(folds) == 2
    assert folds.loc[0, "portfolio_validation_account_return_pct"] == 40.0
    assert folds.loc[0, "selected_candidate_ids"] == "1;2"
    assert folds.loc[1, "risk_off"] == True
    assert result["aggregate"]["best_passed_windows"] == 0


def test_audit_quantile_band_selector_selects_within_calibration_rank_band() -> None:
    evaluations = pd.DataFrame(
        [
            {"fold": 1, "candidate_id": 1, "calibration_trades": 20, "calibration_day_positive_rate": 0.5, "calibration_account_return_pct": 1.0, "calibration_win_rate": 0.1, "validation_account_return_pct": -10.0},
            {"fold": 1, "candidate_id": 2, "calibration_trades": 20, "calibration_day_positive_rate": 0.5, "calibration_account_return_pct": 2.0, "calibration_win_rate": 0.9, "validation_account_return_pct": 80.0},
            {"fold": 1, "candidate_id": 3, "calibration_trades": 20, "calibration_day_positive_rate": 0.5, "calibration_account_return_pct": 3.0, "calibration_win_rate": 1.0, "validation_account_return_pct": -50.0},
        ]
    )

    result = audit_quantile_band_selector(
        evaluations,
        band_columns=("calibration_account_return_pct",),
        score_columns=("calibration_win_rate",),
        bands=((0.4, 0.8),),
        min_calibration_trades=20,
        min_calibration_day_positive_rate=0.0,
        target_account_return_pct=50.0,
    )

    folds = pd.DataFrame(result["folds"])
    assert folds.loc[0, "selected_candidate_id"] == 2
    assert folds.loc[0, "validation_account_return_pct"] == 80.0
    assert result["aggregate"]["best_passed_windows"] == 1


def test_select_candidate_by_metric_prefix_ignores_true_validation_columns() -> None:
    evaluations = pd.DataFrame(
        [
            {
                "candidate_id": 1,
                "selector_trades": 20,
                "selector_total_net_pnl_bps": 10.0,
                "selector_day_positive_rate": 0.6,
                "selector_mean_net_pnl_bps": 0.5,
                "validation_account_return_pct": 999.0,
            },
            {
                "candidate_id": 2,
                "selector_trades": 20,
                "selector_total_net_pnl_bps": 50.0,
                "selector_day_positive_rate": 0.6,
                "selector_mean_net_pnl_bps": 2.5,
                "validation_account_return_pct": -100.0,
            },
        ]
    )

    selected = select_candidate_by_metric_prefix(evaluations, prefix="selector", min_trades=10, min_day_positive_rate=0.5)

    assert int(selected["candidate_id"]) == 2


def test_summarize_fixed_family_viability_rejects_unstable_positive_total() -> None:
    evaluations = pd.DataFrame(
        [
            {
                "fold": 1,
                "lookback_minutes": 60,
                "horizon_minutes": 120,
                "direction": "reversal",
                "filter_feature": "range_bps",
                "quantile": 0.98,
                "validation_trades": 10,
                "validation_total_net_pnl_bps": 100.0,
                "validation_account_return_pct": 8.0,
            },
            {
                "fold": 2,
                "lookback_minutes": 60,
                "horizon_minutes": 120,
                "direction": "reversal",
                "filter_feature": "range_bps",
                "quantile": 0.98,
                "validation_trades": 10,
                "validation_total_net_pnl_bps": -20.0,
                "validation_account_return_pct": -1.6,
            },
            {
                "fold": 3,
                "lookback_minutes": 60,
                "horizon_minutes": 120,
                "direction": "reversal",
                "filter_feature": "range_bps",
                "quantile": 0.98,
                "validation_trades": 10,
                "validation_total_net_pnl_bps": 50.0,
                "validation_account_return_pct": 4.0,
            },
            {
                "fold": 1,
                "lookback_minutes": 15,
                "horizon_minutes": 240,
                "direction": "momentum",
                "filter_feature": "range_bps",
                "quantile": 0.94,
                "validation_trades": 20,
                "validation_total_net_pnl_bps": 20.0,
                "validation_account_return_pct": 1.6,
            },
        ]
    )

    result = summarize_fixed_family_viability(
        evaluations,
        min_active_folds=3,
        min_positive_fold_rate=1.0,
        min_total_account_return_pct=0.0,
        min_worst_fold_account_return_pct=0.0,
    )

    assert result["aggregate"]["promote_fixed_family"] is False
    assert result["aggregate"]["passed_family_count"] == 0
    assert result["aggregate"]["best_positive_fold_rate"] == 2 / 3
    assert result["aggregate"]["failed_checks"] == ["no_family_passed"]


def test_summarize_signal_inversion_viability_charges_costs_after_flip() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "fold": 1, "gross_pnl_bps": -20.0, "cost_bps": 8.0, "net_pnl_bps": -28.0},
            {"timestamp": "2026-01-02T00:00:00Z", "fold": 1, "gross_pnl_bps": -10.0, "cost_bps": 8.0, "net_pnl_bps": -18.0},
            {"timestamp": "2026-01-03T00:00:00Z", "fold": 2, "gross_pnl_bps": 5.0, "cost_bps": 8.0, "net_pnl_bps": -3.0},
        ]
    )

    result = summarize_signal_inversion_viability(
        trades,
        min_total_net_pnl_bps=0.0,
        min_positive_fold_rate=1.0,
        min_positive_month_rate=1.0,
        min_win_rate=0.5,
    )

    assert result["original"]["total_net_pnl_bps"] == -49.0
    assert result["inverted"]["total_net_pnl_bps"] == 1.0
    assert result["inverted"]["win_rate"] == 2 / 3
    assert result["inverted"]["positive_fold_rate"] == 0.5
    assert result["aggregate"]["promote_inverted_signal"] is False
    assert result["aggregate"]["failed_checks"] == ["positive_fold_rate"]


def test_summarize_cost_edge_viability_finds_max_passing_cost() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "fold": 1, "gross_pnl_bps": 10.0},
            {"timestamp": "2026-01-02T00:00:00Z", "fold": 2, "gross_pnl_bps": 12.0},
        ]
    )

    result = summarize_cost_edge_viability(
        trades,
        cost_bps_values=[0.0, 5.0, 11.0],
        variants=("original",),
        min_total_net_pnl_bps=0.0,
        min_positive_fold_rate=1.0,
        min_positive_month_rate=1.0,
        min_win_rate=1.0,
    )

    scenarios = pd.DataFrame(result["scenarios"])
    cost5 = scenarios.loc[scenarios["cost_bps"] == 5.0].iloc[0]
    cost11 = scenarios.loc[scenarios["cost_bps"] == 11.0].iloc[0]
    assert cost5["passed"] == True
    assert cost5["total_net_pnl_bps"] == 12.0
    assert cost11["passed"] == False
    assert result["aggregate"]["has_passing_cost"] is True
    assert result["aggregate"]["best_passing_cost_bps"] == 5.0


def test_summarize_static_bucket_viability_separates_outcome_from_pretrade() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "fold": 1, "exit_reason": "take_profit", "lane": "core", "net_pnl_bps": 20.0},
            {"timestamp": "2026-02-01T00:00:00Z", "fold": 2, "exit_reason": "take_profit", "lane": "core", "net_pnl_bps": 20.0},
            {"timestamp": "2026-01-02T00:00:00Z", "fold": 1, "exit_reason": "horizon", "lane": "core", "net_pnl_bps": -30.0},
            {"timestamp": "2026-02-02T00:00:00Z", "fold": 2, "exit_reason": "horizon", "lane": "rescue", "net_pnl_bps": -30.0},
        ]
    )

    result = summarize_static_bucket_viability(
        trades,
        bucket_columns=("exit_reason", "lane"),
        outcome_columns=("exit_reason",),
        min_trades=2,
        min_total_net_pnl_bps=0.0,
        min_positive_fold_rate=1.0,
        min_positive_month_rate=1.0,
        min_win_rate=1.0,
    )

    rows = pd.DataFrame(result["buckets"])
    take_profit = rows.loc[(rows["bucket_column"] == "exit_reason") & (rows["bucket_value"] == "take_profit")].iloc[0]
    core = rows.loc[(rows["bucket_column"] == "lane") & (rows["bucket_value"] == "core")].iloc[0]
    assert take_profit["passed"] == True
    assert take_profit["bucket_type"] == "outcome"
    assert core["passed"] == False
    assert result["aggregate"]["passed_outcome_bucket_count"] == 1
    assert result["aggregate"]["passed_pretrade_bucket_count"] == 0
    assert result["aggregate"]["promote_pretrade_bucket"] is False


def test_summarize_rescue_hypothesis_closure_requires_all_required_closed() -> None:
    evidence = [
        {"hypothesis": "route_inventory", "closed": True, "required": True},
        {"hypothesis": "signal_inversion", "closed": True, "required": True},
        {"hypothesis": "cost_edge", "closed": False, "required": True},
        {"hypothesis": "outcome_only_tp", "closed": True, "required": False},
    ]

    result = summarize_rescue_hypothesis_closure(evidence)

    assert result["all_required_rescue_hypotheses_closed"] is False
    assert result["open_required_hypotheses"] == ["cost_edge"]
    assert result["next_action"] == "continue_required_rescue_validation"

    closed = summarize_rescue_hypothesis_closure([{**row, "closed": True} for row in evidence])
    assert closed["all_required_rescue_hypotheses_closed"] is True
    assert closed["next_action"] == "new_hypothesis_required"


def test_summarize_short_term_candidate_validation_keeps_recent_edge_separate() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "fold": 1, "net_pnl_bps": 120.0, "lookback_minutes": 1440, "horizon_minutes": 720},
            {"timestamp": "2026-02-01T00:00:00Z", "fold": 2, "net_pnl_bps": 130.0, "lookback_minutes": 1440, "horizon_minutes": 720},
            {"timestamp": "2026-03-01T00:00:00Z", "fold": 3, "net_pnl_bps": 140.0, "lookback_minutes": 1440, "horizon_minutes": 720},
            {"timestamp": "2026-04-01T00:00:00Z", "fold": 4, "net_pnl_bps": 150.0, "lookback_minutes": 1440, "horizon_minutes": 720},
            {"timestamp": "2026-05-01T00:00:00Z", "fold": 5, "net_pnl_bps": 160.0, "lookback_minutes": 1440, "horizon_minutes": 720},
            {"timestamp": "2026-06-01T00:00:00Z", "fold": 6, "net_pnl_bps": -10.0, "lookback_minutes": 1440, "horizon_minutes": 720},
            {"timestamp": "2026-07-01T00:00:00Z", "fold": 7, "net_pnl_bps": -20.0, "lookback_minutes": 1440, "horizon_minutes": 720},
            {"timestamp": "2026-08-01T00:00:00Z", "fold": 7, "net_pnl_bps": -30.0, "lookback_minutes": 1440, "horizon_minutes": 720},
        ]
    )
    delay_summary = pd.DataFrame(
        [
            {"entry_delay_minutes": 0, "total_net_pnl_bps": 640.0},
            {"entry_delay_minutes": 5, "total_net_pnl_bps": 600.0},
        ]
    )
    extra_cost_summary = pd.DataFrame(
        [
            {"extra_cost_bps": 0.0, "total_net_pnl_bps": 640.0},
            {"extra_cost_bps": 16.0, "total_net_pnl_bps": 512.0},
        ]
    )

    result = summarize_short_term_candidate_validation(
        trades,
        delay_summary=delay_summary,
        extra_cost_summary=extra_cost_summary,
        holdout_folds=[1, 2, 3, 4, 5],
        min_trades=8,
        min_positive_fold_rate=0.70,
        min_worst_fold_net_pnl_bps=-100.0,
        recent_months=6,
        recent_tail_active_months=3,
        min_recent_tail_positive_month_rate=0.67,
    )

    assert result["short_term"]["passed"] is True
    assert result["recent"]["passed"] is False
    assert result["recent"]["tail_active_positive_month_rate"] == 0.0
    assert result["decision"]["promote_short_term_candidate"] is False
    assert result["decision"]["next_action"] == "refresh_recent_data_or_wait"


def test_summarize_short_term_repair_candidates_selects_recent_fix_without_breaking_base_gate() -> None:
    baseline = {
        "short_term": {"passed": True, "total_net_pnl_bps": 100.0, "holdout_total_net_pnl_bps": 40.0},
        "recent": {"passed": False, "recent_total_net_pnl_bps": -20.0},
    }
    candidates = [
        {
            "policy": "recent_only_fit",
            "short_term": {"passed": False, "total_net_pnl_bps": 80.0, "holdout_total_net_pnl_bps": -5.0},
            "recent": {"passed": True, "recent_total_net_pnl_bps": 50.0},
        },
        {
            "policy": "oversold_short_veto",
            "short_term": {"passed": True, "total_net_pnl_bps": 150.0, "holdout_total_net_pnl_bps": 55.0},
            "recent": {"passed": True, "recent_total_net_pnl_bps": 10.0},
        },
    ]

    result = summarize_short_term_repair_candidates(
        baseline,
        candidates,
        min_total_improvement_bps=0.0,
        min_recent_total_improvement_bps=0.0,
    )

    rows = pd.DataFrame(result["candidates"])
    bad = rows.loc[rows["policy"] == "recent_only_fit"].iloc[0]
    assert bad["passed"] == False
    assert result["aggregate"]["promote_repair_candidate"] is True
    assert result["aggregate"]["selected_policy"] == "oversold_short_veto"
    assert result["aggregate"]["selected_total_improvement_bps"] == 50.0
    assert result["aggregate"]["selected_recent_total_improvement_bps"] == 30.0


def test_summarize_last_two_year_stability_rejects_positive_but_choppy_months() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "net_pnl_bps": 100.0},
            {"timestamp": "2026-02-01T00:00:00Z", "net_pnl_bps": -10.0},
            {"timestamp": "2026-03-01T00:00:00Z", "net_pnl_bps": 100.0},
            {"timestamp": "2026-04-01T00:00:00Z", "net_pnl_bps": -10.0},
            {"timestamp": "2026-05-01T00:00:00Z", "net_pnl_bps": 100.0},
            {"timestamp": "2026-06-01T00:00:00Z", "net_pnl_bps": -10.0},
        ]
    )
    delay_summary = pd.DataFrame(
        [
            {"entry_delay_minutes": 0, "total_net_pnl_bps": 270.0},
            {"entry_delay_minutes": 5, "total_net_pnl_bps": 250.0},
        ]
    )
    extra_cost_summary = pd.DataFrame(
        [
            {"extra_cost_bps": 0.0, "total_net_pnl_bps": 270.0},
            {"extra_cost_bps": 16.0, "total_net_pnl_bps": 174.0},
        ]
    )

    result = summarize_last_two_year_stability(
        trades,
        delay_summary=delay_summary,
        extra_cost_summary=extra_cost_summary,
        start_timestamp="2026-01-01T00:00:00Z",
        end_timestamp="2026-06-30T00:00:00Z",
        min_trades=6,
        min_active_month_positive_rate=0.67,
        min_calendar_month_positive_rate=0.50,
        min_quarter_positive_rate=1.0,
        min_rolling_3m_positive_rate=1.0,
        min_rolling_6m_positive_rate=1.0,
    )

    assert result["aggregate"]["total_net_pnl_bps"] == 270.0
    assert result["months"]["active_positive_month_rate"] == 0.5
    assert result["decision"]["stable_enough"] is False
    assert "active_month_positive_rate" in result["decision"]["failed_checks"]


def test_summarize_two_year_stability_repair_candidates_requires_stability_and_improvement() -> None:
    baseline = {
        "aggregate": {
            "trade_count": 127,
            "total_net_pnl_bps": 3600.0,
            "max_drawdown_bps": 1500.0,
            "required_extra_cost_total_net_pnl_bps": 1600.0,
            "worst_delay_total_net_pnl_bps": 3300.0,
        },
        "decision": {
            "stable_enough": False,
            "failed_checks": ["rolling_3m_positive_rate"],
        },
    }
    candidates = [
        {
            "policy": "profit_only",
            "description": "Higher total but still unstable.",
            "stability": {
                "aggregate": {
                    "trade_count": 130,
                    "total_net_pnl_bps": 3900.0,
                    "max_drawdown_bps": 1400.0,
                    "required_extra_cost_total_net_pnl_bps": 1700.0,
                    "worst_delay_total_net_pnl_bps": 3200.0,
                },
                "decision": {"stable_enough": False, "failed_checks": ["rolling_6m_positive_rate"]},
            },
        },
        {
            "policy": "stricter_oversold_short_veto",
            "description": "Tighten the same risk veto.",
            "stability": {
                "aggregate": {
                    "trade_count": 112,
                    "total_net_pnl_bps": 4530.0,
                    "max_drawdown_bps": 1400.0,
                    "required_extra_cost_total_net_pnl_bps": 2700.0,
                    "worst_delay_total_net_pnl_bps": 4100.0,
                },
                "decision": {"stable_enough": True, "failed_checks": []},
            },
        },
    ]

    result = summarize_two_year_stability_repair_candidates(
        baseline,
        candidates,
        min_total_improvement_bps=100.0,
        min_trades=100,
    )

    rows = pd.DataFrame(result["candidates"])
    rejected = rows.loc[rows["policy"] == "profit_only"].iloc[0]
    selected = rows.loc[rows["policy"] == "stricter_oversold_short_veto"].iloc[0]
    assert rejected["passed"] == False
    assert selected["passed"] == True
    assert result["aggregate"]["promote_stability_repair"] is True
    assert result["aggregate"]["selected_policy"] == "stricter_oversold_short_veto"
    assert result["aggregate"]["selected_total_improvement_bps"] == 930.0


def test_summarize_forward_monitoring_window_treats_no_signal_as_monitoring_not_loss() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-06-01T00:00:00Z", "signal_timestamp": "2026-06-01T00:00:00Z", "net_pnl_bps": -50.0},
        ]
    )

    result = summarize_forward_monitoring_window(
        trades,
        start_timestamp="2026-06-06T04:10:00Z",
        end_timestamp="2026-06-12T23:59:00Z",
        signal_timestamp_col="signal_timestamp",
    )

    assert result["decision"]["status"] == "no_signal"
    assert result["decision"]["monitoring_ok"] is True
    assert result["aggregate"]["trade_count"] == 0
    assert result["decision"]["next_action"] == "continue_monitoring"


def test_summarize_forward_monitoring_window_flags_negative_forward_trade() -> None:
    trades = pd.DataFrame(
        [
            {"timestamp": "2026-06-07T00:00:00Z", "signal_timestamp": "2026-06-07T00:00:00Z", "net_pnl_bps": -20.0},
        ]
    )

    result = summarize_forward_monitoring_window(
        trades,
        start_timestamp="2026-06-06T04:10:00Z",
        end_timestamp="2026-06-12T23:59:00Z",
        signal_timestamp_col="signal_timestamp",
    )

    assert result["decision"]["status"] == "failed"
    assert result["decision"]["monitoring_ok"] is False
    assert "total_net_pnl_nonnegative" in result["decision"]["failed_checks"]


def test_v90_mechanical_policy_preserves_v87_short_veto() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v90_forward_monitoring.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v90_forward_monitoring", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        [
            {"hour": 10, "signal": -1, "lookback_return_bps": -700.0},
            {"hour": 10, "signal": -1, "lookback_return_bps": -600.0},
            {"hour": 2, "signal": 1, "lookback_return_bps": 100.0},
        ]
    )

    mask = module._policy_mask("v89_mechanical_remove_hours_0_2_3_4", frame, excluded_hours=[])

    assert mask.tolist() == [False, True, False]


def test_eth_v90_runner_builds_symbol_specific_monthly_and_daily_paths() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_ethusdc_v90_transfer_test.py"
    spec = importlib.util.spec_from_file_location("run_ethusdc_v90_transfer_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monthly = module._binance_aggtrade_path("ETHUSDC", "monthly", "2026-05")
    daily = module._binance_aggtrade_path("ETHUSDC", "daily", "2026-06-12")

    assert monthly.name == "ETHUSDC-aggTrades-2026-05.zip"
    assert "/monthly/aggTrades/ETHUSDC/" in module._binance_aggtrade_url("ETHUSDC", "monthly", "2026-05")
    assert daily.name == "ETHUSDC-aggTrades-2026-06-12.zip"
    assert "/daily/aggTrades/ETHUSDC/" in module._binance_aggtrade_url("ETHUSDC", "daily", "2026-06-12")


def test_btcusdc_v92_runner_uses_full_available_bar_window() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v92_earliest_to_latest_window.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v92_earliest_to_latest_window", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bars = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-04T12:31:00Z",
                    "2025-06-01T00:00:00Z",
                    "2026-06-12T23:59:00Z",
                ],
                utc=True,
            )
        }
    )

    start_ts, end_ts = module._full_available_window(bars)

    assert start_ts.isoformat() == "2024-01-04T12:31:00+00:00"
    assert end_ts.isoformat() == "2026-06-12T23:59:00+00:00"


def test_btcusdc_v93_side_summary_splits_long_and_short_metrics() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v93_short_side_audit.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v93_short_side_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        [
            {"timestamp": "2026-01-01T00:00:00Z", "signal": 1, "net_pnl_bps": 10.0},
            {"timestamp": "2026-01-01T12:00:00Z", "signal": 1, "net_pnl_bps": -5.0},
            {"timestamp": "2026-01-02T00:00:00Z", "signal": -1, "net_pnl_bps": 20.0},
            {"timestamp": "2026-01-02T12:00:00Z", "signal": -1, "net_pnl_bps": -30.0},
        ]
    )

    summary = module._side_summary(trades)

    long_row = summary.loc[summary["side"] == "long"].iloc[0]
    short_row = summary.loc[summary["side"] == "short"].iloc[0]
    assert long_row["trades"] == 2
    assert long_row["total_net_pnl_bps"] == 5.0
    assert long_row["win_rate"] == 0.5
    assert short_row["trades"] == 2
    assert short_row["total_net_pnl_bps"] == -10.0
    assert short_row["win_rate"] == 0.5


def test_btcusdc_v94_high_frequency_gate_requires_daily_frequency_and_holdout_profit() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v94_high_frequency_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v94_high_frequency_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "full_total_net_pnl_bps": 120.0,
        "full_win_rate": 0.56,
        "full_avg_trades_per_calendar_day": 1.1,
        "full_calendar_positive_month_rate": 0.7,
        "holdout_total_net_pnl_bps": 50.0,
        "holdout_win_rate": 0.57,
        "holdout_avg_trades_per_calendar_day": 1.2,
        "holdout_calendar_positive_month_rate": 0.6,
    }
    too_sparse = {**passing, "full_avg_trades_per_calendar_day": 0.9}
    weak_holdout = {**passing, "holdout_total_net_pnl_bps": -1.0}

    assert module._passes_high_frequency_gate(passing) is True
    assert module._passes_high_frequency_gate(too_sparse) is False
    assert module._passes_high_frequency_gate(weak_holdout) is False


def test_btcusdc_v94_daily_frequency_summary_counts_calendar_days() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v94_high_frequency_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v94_high_frequency_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T12:00:00Z",
                    "2026-01-03T00:00:00Z",
                ],
                utc=True,
            ),
            "net_pnl_bps": [10.0, -2.0, 5.0],
        }
    )

    summary = module._trade_summary(
        trades,
        start_ts=pd.Timestamp("2026-01-01T00:00:00Z"),
        end_ts=pd.Timestamp("2026-01-03T23:59:00Z"),
    )

    assert summary["trade_count"] == 3
    assert summary["calendar_day_count"] == 3
    assert summary["active_day_count"] == 2
    assert summary["avg_trades_per_calendar_day"] == 1.0
    assert summary["active_day_rate"] == 2 / 3


def test_btcusdc_v94_spaced_indices_matches_greedy_non_overlap() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v94_high_frequency_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v94_high_frequency_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    mask = pd.Series([False, True, True, False, True, True, True, False, True])

    assert module._spaced_indices(mask, horizon=3).tolist() == [1, 4, 8]


def test_btcusdc_v95_barrier_ledger_uses_conservative_same_bar_stop() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v95_tp_sl_high_frequency_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v95_tp_sl_high_frequency_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="min"),
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 101.0, 100.1, 100.1],
            "low": [100.0, 99.0, 99.9, 99.9],
        }
    )

    ledger = module._barrier_ledger(
        frame,
        entry_idx=pd.Index([0]),
        signal_values=pd.Series([1], index=[0]),
        horizon_minutes=3,
        take_profit_bps=50.0,
        stop_loss_bps=50.0,
        fee_bps=0.0,
    )

    assert len(ledger) == 1
    assert ledger.iloc[0]["exit_reason"] == "stop_loss"
    assert ledger.iloc[0]["net_pnl_bps"] == -50.0


def test_btcusdc_v95_barrier_ledger_handles_short_take_profit() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v95_tp_sl_high_frequency_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v95_tp_sl_high_frequency_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="min"),
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 100.1, 100.1, 100.1],
            "low": [100.0, 99.0, 99.8, 99.8],
        }
    )

    ledger = module._barrier_ledger(
        frame,
        entry_idx=pd.Index([0]),
        signal_values=pd.Series([-1], index=[0]),
        horizon_minutes=3,
        take_profit_bps=50.0,
        stop_loss_bps=80.0,
        fee_bps=4.0,
    )

    assert len(ledger) == 1
    assert ledger.iloc[0]["exit_reason"] == "take_profit"
    assert ledger.iloc[0]["net_pnl_bps"] == 46.0


def test_btcusdc_v95_gate_requires_win_frequency_and_holdout_profit() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v95_tp_sl_high_frequency_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v95_tp_sl_high_frequency_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "full_total_net_pnl_bps": 100.0,
        "full_win_rate": 0.56,
        "full_avg_trades_per_calendar_day": 1.1,
        "full_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }

    assert module._passes_tp_sl_gate(passing) is True
    assert module._passes_tp_sl_gate({**passing, "holdout_win_rate": 0.55}) is False
    assert module._passes_tp_sl_gate({**passing, "full_avg_trades_per_calendar_day": 0.99}) is False
    assert module._passes_tp_sl_gate({**passing, "holdout_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v96_labels_fee_adjusted_up_down_and_flat() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v96_ml_probability_gate.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v96_ml_probability_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    labels = module._labels_from_future_return(pd.Series([12.0, -15.0, 3.0]), fee_bps=8.5)

    assert labels.tolist() == [1, -1, 0]


def test_btcusdc_v96_prediction_ledger_uses_probability_side_and_spacing() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v96_ml_probability_gate.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v96_ml_probability_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    predictions = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=5, freq="min"),
            "future_return_bps": [20.0, 30.0, -25.0, -30.0, 50.0],
            "prob_up": [0.70, 0.80, 0.10, 0.20, 0.90],
            "prob_down": [0.10, 0.20, 0.75, 0.80, 0.05],
        }
    )

    ledger = module._prediction_ledger(predictions, probability_threshold=0.65, horizon_minutes=2, fee_bps=5.0)

    assert ledger["signal"].tolist() == [1, -1, 1]
    assert ledger["net_pnl_bps"].tolist() == [15.0, 20.0, 45.0]


def test_btcusdc_v96_gate_requires_selector_and_holdout_quality() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v96_ml_probability_gate.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v96_ml_probability_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "selector_total_net_pnl_bps": 20.0,
        "selector_win_rate": 0.56,
        "selector_avg_trades_per_calendar_day": 1.2,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }

    assert module._passes_ml_gate(passing) is True
    assert module._passes_ml_gate({**passing, "selector_win_rate": 0.55}) is False
    assert module._passes_ml_gate({**passing, "holdout_avg_trades_per_calendar_day": 0.99}) is False
    assert module._passes_ml_gate({**passing, "holdout_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v97_regime_mask_uses_selector_quantiles_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v97_hgb_regime_gate.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v97_hgb_regime_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    selector = pd.DataFrame(
        {
            "range_mean_60": [10.0, 20.0, 30.0],
            "abs_flow_mean_60": [0.1, 0.2, 0.3],
        }
    )
    holdout = pd.DataFrame(
        {
            "range_mean_60": [19.0, 20.0, 25.0, 1000.0],
            "abs_flow_mean_60": [0.19, 0.2, 0.25, 0.01],
        }
    )

    mask = module._regime_mask(holdout, selector, range_quantile=0.5, flow_quantile=0.5)

    assert mask.tolist() == [False, True, True, False]


def test_btcusdc_v97_gate_requires_selector_and_holdout_quality() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v97_hgb_regime_gate.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v97_hgb_regime_gate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "selector_total_net_pnl_bps": 20.0,
        "selector_win_rate": 0.56,
        "selector_avg_trades_per_calendar_day": 1.2,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }

    assert module._passes_tree_gate(passing) is True
    assert module._passes_tree_gate({**passing, "selector_win_rate": 0.55}) is False
    assert module._passes_tree_gate({**passing, "holdout_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v98_adjusts_fee_from_gross_without_changing_trades() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v98_cost_sensitivity.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v98_cost_sensitivity", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    ledger = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"], utc=True),
            "signal": [1, -1],
            "gross_pnl_bps": [10.0, -5.0],
            "net_pnl_bps": [1.5, -13.5],
        }
    )

    adjusted = module._ledger_with_fee(ledger, fee_bps=4.0)

    assert adjusted["signal"].tolist() == [1, -1]
    assert adjusted["net_pnl_bps"].tolist() == [6.0, -9.0]


def test_btcusdc_v98_cost_gate_requires_frequency_win_and_profit() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v98_cost_sensitivity.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v98_cost_sensitivity", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "selector_total_net_pnl_bps": 20.0,
        "selector_win_rate": 0.56,
        "selector_avg_trades_per_calendar_day": 1.2,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }

    assert module._passes_cost_gate(passing) is True
    assert module._passes_cost_gate({**passing, "holdout_win_rate": 0.55}) is False
    assert module._passes_cost_gate({**passing, "holdout_avg_trades_per_calendar_day": 0.99}) is False
    assert module._passes_cost_gate({**passing, "selector_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v98_decision_does_not_treat_zero_fee_only_as_realistic_completion() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v98_cost_sensitivity.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v98_cost_sensitivity", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passed = pd.DataFrame(
        [
            {"policy_id": "zero_fee_candidate", "fee_bps": 0.0},
        ]
    )

    decision = module._decision_from_passed(passed)

    assert decision["passing_candidate_count"] == 1
    assert decision["passing_nonzero_fee_candidate_count"] == 0
    assert decision["zero_fee_only_candidate_count"] == 1
    assert decision["selected_policy"] is None
    assert decision["zero_fee_research_policy"] == "zero_fee_candidate"
    assert decision["goal_satisfied_by_scan"] is False


def test_btcusdc_v99_policy_headroom_uses_max_passing_fee() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v99_low_cost_headroom.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v99_low_cost_headroom", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    candidates = pd.DataFrame(
        [
            {"base_policy_id": "policy_a", "policy_id": "policy_a_fee0", "fee_bps": 0.0, "passed_low_cost_gate": True, "holdout_total_net_pnl_bps": 30.0},
            {"base_policy_id": "policy_a", "policy_id": "policy_a_fee0.25", "fee_bps": 0.25, "passed_low_cost_gate": True, "holdout_total_net_pnl_bps": 25.0},
            {"base_policy_id": "policy_a", "policy_id": "policy_a_fee0.5", "fee_bps": 0.5, "passed_low_cost_gate": False, "holdout_total_net_pnl_bps": 20.0},
            {"base_policy_id": "policy_b", "policy_id": "policy_b_fee0", "fee_bps": 0.0, "passed_low_cost_gate": True, "holdout_total_net_pnl_bps": 10.0},
        ]
    )

    headroom = module._policy_headroom(candidates)

    policy_a = headroom.loc[headroom["base_policy_id"] == "policy_a"].iloc[0]
    policy_b = headroom.loc[headroom["base_policy_id"] == "policy_b"].iloc[0]
    assert policy_a["passing_fee_count"] == 2
    assert policy_a["max_passing_fee_bps"] == 0.25
    assert policy_a["max_passing_nonzero_fee_bps"] == 0.25
    assert policy_a["zero_fee_only"] is False
    assert policy_b["max_passing_fee_bps"] == 0.0
    assert pd.isna(policy_b["max_passing_nonzero_fee_bps"])
    assert policy_b["zero_fee_only"] is True


def test_btcusdc_v99_decision_requires_nonzero_fee_headroom() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v99_low_cost_headroom.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v99_low_cost_headroom", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    zero_only = pd.DataFrame(
        [
            {"base_policy_id": "policy_zero", "max_passing_fee_bps": 0.0, "max_passing_nonzero_fee_bps": float("nan"), "zero_fee_only": True},
        ]
    )
    zero_decision = module._decision_from_headroom(zero_only)

    assert zero_decision["selected_policy"] is None
    assert zero_decision["zero_fee_research_policy"] == "policy_zero"
    assert zero_decision["max_passing_nonzero_fee_bps"] is None
    assert zero_decision["goal_satisfied_by_scan"] is False

    nonzero = pd.DataFrame(
        [
            {"base_policy_id": "policy_nonzero", "max_passing_fee_bps": 0.25, "max_passing_nonzero_fee_bps": 0.25, "zero_fee_only": False},
            {"base_policy_id": "policy_zero", "max_passing_fee_bps": 0.0, "max_passing_nonzero_fee_bps": float("nan"), "zero_fee_only": True},
        ]
    )
    nonzero_decision = module._decision_from_headroom(nonzero)

    assert nonzero_decision["selected_policy"] == "policy_nonzero"
    assert nonzero_decision["max_passing_nonzero_fee_bps"] == 0.25
    assert nonzero_decision["goal_satisfied_by_scan"] is True


def test_btcusdc_v100_adverse_fill_keeps_worst_trades_and_extra_cost() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v100_maker_fill_risk.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v100_maker_fill_risk", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    ledger = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="h"),
            "net_pnl_bps": [10.0, -5.0, 20.0, -1.0],
            "gross_pnl_bps": [10.0, -5.0, 20.0, -1.0],
            "window": ["holdout"] * 4,
        }
    )

    stressed = module._stress_ledger(
        ledger,
        fill_model="adverse_selection",
        fill_rate=0.5,
        extra_adverse_bps=0.25,
    )

    assert stressed["timestamp"].tolist() == [ledger.iloc[1]["timestamp"], ledger.iloc[3]["timestamp"]]
    assert stressed["net_pnl_bps"].tolist() == [-5.25, -1.25]
    assert stressed["fill_model"].tolist() == ["adverse_selection", "adverse_selection"]
    assert stressed["fill_rate"].tolist() == [0.5, 0.5]


def test_btcusdc_v100_decision_requires_all_required_stresses_to_pass() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v100_maker_fill_risk.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v100_maker_fill_risk", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stress = pd.DataFrame(
        [
            {
                "base_policy_id": "policy_a",
                "fill_model": "time_stride",
                "fill_rate": 0.9,
                "extra_adverse_bps": 0.25,
                "required_stress": True,
                "passed_maker_stress_gate": True,
                "holdout_total_net_pnl_bps": 10.0,
            },
            {
                "base_policy_id": "policy_a",
                "fill_model": "adverse_selection",
                "fill_rate": 0.9,
                "extra_adverse_bps": 0.25,
                "required_stress": True,
                "passed_maker_stress_gate": False,
                "holdout_total_net_pnl_bps": -1.0,
            },
            {
                "base_policy_id": "policy_b",
                "fill_model": "time_stride",
                "fill_rate": 0.9,
                "extra_adverse_bps": 0.25,
                "required_stress": True,
                "passed_maker_stress_gate": True,
                "holdout_total_net_pnl_bps": 20.0,
            },
            {
                "base_policy_id": "policy_b",
                "fill_model": "adverse_selection",
                "fill_rate": 0.9,
                "extra_adverse_bps": 0.25,
                "required_stress": True,
                "passed_maker_stress_gate": True,
                "holdout_total_net_pnl_bps": 15.0,
            },
        ]
    )

    decision = module._decision_from_stress(stress)

    assert decision["selected_policy"] == "policy_b"
    assert decision["maker_execution_viable"] is True
    assert decision["candidate_count_passing_required_stress"] == 1


def test_btcusdc_v101_edge_prediction_ledger_uses_signed_edge_and_spacing() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v101_thick_edge_regression.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v101_thick_edge_regression", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    predictions = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=6, freq="min"),
            "future_return_bps": [30.0, 40.0, -25.0, -30.0, 5.0, -50.0],
            "predicted_return_bps": [15.0, 14.0, -20.0, -5.0, 30.0, -40.0],
        }
    )

    ledger = module._edge_prediction_ledger(
        predictions,
        edge_threshold_bps=10.0,
        horizon_minutes=2,
        fee_bps=8.5,
    )

    assert ledger["signal"].tolist() == [1, -1, 1]
    assert ledger["timestamp"].tolist() == [
        predictions.iloc[0]["timestamp"],
        predictions.iloc[2]["timestamp"],
        predictions.iloc[4]["timestamp"],
    ]
    assert ledger["net_pnl_bps"].round(6).tolist() == [21.5, 16.5, -3.5]


def test_btcusdc_v101_gate_requires_profit_win_frequency_and_months() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v101_thick_edge_regression.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v101_thick_edge_regression", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "selector_total_net_pnl_bps": 20.0,
        "selector_win_rate": 0.56,
        "selector_avg_trades_per_calendar_day": 1.2,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }

    assert module._passes_thick_edge_gate(passing) is True
    assert module._passes_thick_edge_gate({**passing, "holdout_win_rate": 0.55}) is False
    assert module._passes_thick_edge_gate({**passing, "holdout_avg_trades_per_calendar_day": 0.99}) is False
    assert module._passes_thick_edge_gate({**passing, "selector_calendar_positive_month_rate": 0.49}) is False
    assert module._passes_thick_edge_gate({**passing, "selector_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v102_ma_features_use_prior_close_without_lookahead() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v102_ma_feature_regression.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v102_ma_feature_regression", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=110, freq="min"),
            "open": [float(x) for x in range(100, 210)],
            "close": [float(x) for x in range(100, 210)],
        }
    )

    out = module._add_ma_features(frame)
    row = out.iloc[99]

    assert row["ma7"] == sum(range(192, 199)) / 7
    assert row["ma25"] == sum(range(174, 199)) / 25
    assert row["ma99"] == sum(range(100, 199)) / 99
    assert row["ma_stack_long"] == 1.0
    assert row["ma_stack_short"] == 0.0


def test_btcusdc_v102_feature_frame_includes_ma_columns() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v102_ma_feature_regression.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v102_ma_feature_regression", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=180, freq="min"),
            "open": np.linspace(100.0, 120.0, 180),
            "high": np.linspace(101.0, 121.0, 180),
            "low": np.linspace(99.0, 119.0, 180),
            "close": np.linspace(100.5, 120.5, 180),
            "volume": np.linspace(10.0, 20.0, 180),
            "signed_taker_imbalance": np.linspace(-0.1, 0.1, 180),
        }
    )

    _, feature_cols = module._ma_feature_frame(bars, horizon_minutes=15)

    for column in [
        "ma7_dist_bps",
        "ma25_dist_bps",
        "ma99_dist_bps",
        "ma7_ma25_spread_bps",
        "ma25_ma99_spread_bps",
        "ma7_slope_5_bps",
        "ma25_slope_5_bps",
        "ma99_slope_5_bps",
        "ma_stack_long",
        "ma_stack_short",
    ]:
        assert column in feature_cols


def test_btcusdc_v103_daily_topk_ledger_selects_ranked_non_overlapping_predictions() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v103_daily_topk_ma_regression.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v103_daily_topk_ma_regression", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    predictions = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:05:00Z",
                    "2026-01-01T00:20:00Z",
                    "2026-01-02T00:00:00Z",
                    "2026-01-02T00:05:00Z",
                    "2026-01-02T00:20:00Z",
                ]
            ),
            "future_return_bps": [12.0, 30.0, -40.0, -20.0, 60.0, 25.0],
            "predicted_return_bps": [20.0, 50.0, -45.0, -30.0, 80.0, 10.0],
        }
    )

    ledger = module._daily_topk_prediction_ledger(
        predictions,
        daily_top_k=2,
        min_edge_bps=0.0,
        horizon_minutes=15,
        fee_bps=8.5,
    )

    assert ledger["timestamp"].tolist() == [
        predictions.iloc[1]["timestamp"],
        predictions.iloc[2]["timestamp"],
        predictions.iloc[4]["timestamp"],
        predictions.iloc[5]["timestamp"],
    ]
    assert ledger["signal"].tolist() == [1, -1, 1, 1]
    assert ledger["net_pnl_bps"].round(6).tolist() == [21.5, 31.5, 51.5, 16.5]
    assert ledger["daily_top_k"].tolist() == [2, 2, 2, 2]


def test_btcusdc_v103_gate_requires_profit_win_frequency_and_months() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v103_daily_topk_ma_regression.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v103_daily_topk_ma_regression", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "selector_total_net_pnl_bps": 20.0,
        "selector_win_rate": 0.56,
        "selector_avg_trades_per_calendar_day": 1.2,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }

    assert module._passes_daily_topk_gate(passing) is True
    assert module._passes_daily_topk_gate({**passing, "selector_win_rate": 0.55}) is False
    assert module._passes_daily_topk_gate({**passing, "holdout_avg_trades_per_calendar_day": 0.99}) is False
    assert module._passes_daily_topk_gate({**passing, "holdout_calendar_positive_month_rate": 0.49}) is False
    assert module._passes_daily_topk_gate({**passing, "holdout_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v104_daily_topk_probability_ledger_selects_confident_non_overlapping_predictions() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v104_ma_hgb_daily_topk_classifier.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v104_ma_hgb_daily_topk_classifier", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    predictions = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:05:00Z",
                    "2026-01-01T00:20:00Z",
                    "2026-01-02T00:00:00Z",
                    "2026-01-02T00:05:00Z",
                    "2026-01-02T00:20:00Z",
                ]
            ),
            "future_return_bps": [12.0, 30.0, -40.0, -20.0, 60.0, 25.0],
            "prob_down": [0.10, 0.20, 0.70, 0.58, 0.10, 0.20],
            "prob_flat": [0.20, 0.10, 0.10, 0.20, 0.20, 0.24],
            "prob_up": [0.70, 0.70, 0.20, 0.22, 0.70, 0.56],
        }
    )

    ledger = module._daily_topk_probability_ledger(
        predictions,
        daily_top_k=2,
        probability_floor=0.55,
        horizon_minutes=15,
        fee_bps=8.5,
    )

    assert ledger["timestamp"].tolist() == [
        predictions.iloc[0]["timestamp"],
        predictions.iloc[2]["timestamp"],
        predictions.iloc[4]["timestamp"],
        predictions.iloc[5]["timestamp"],
    ]
    assert ledger["signal"].tolist() == [1, -1, 1, 1]
    assert ledger["direction_probability"].round(6).tolist() == [0.7, 0.7, 0.7, 0.56]
    assert ledger["net_pnl_bps"].round(6).tolist() == [3.5, 31.5, 51.5, 16.5]


def test_btcusdc_v104_gate_requires_profit_win_frequency_and_months() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v104_ma_hgb_daily_topk_classifier.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v104_ma_hgb_daily_topk_classifier", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "selector_total_net_pnl_bps": 20.0,
        "selector_win_rate": 0.56,
        "selector_avg_trades_per_calendar_day": 1.2,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }

    assert module._passes_daily_classifier_gate(passing) is True
    assert module._passes_daily_classifier_gate({**passing, "selector_win_rate": 0.55}) is False
    assert module._passes_daily_classifier_gate({**passing, "selector_avg_trades_per_calendar_day": 0.99}) is False
    assert module._passes_daily_classifier_gate({**passing, "selector_calendar_positive_month_rate": 0.49}) is False
    assert module._passes_daily_classifier_gate({**passing, "selector_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v105_selector_gate_uses_selector_fields_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v105_selector_locked_v104_audit.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v105_selector_locked_v104_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    row = {
        "selector_total_net_pnl_bps": 20.0,
        "selector_win_rate": 0.56,
        "selector_avg_trades_per_calendar_day": 1.2,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": -999.0,
        "holdout_win_rate": 0.0,
        "holdout_avg_trades_per_calendar_day": 0.0,
        "holdout_calendar_positive_month_rate": 0.0,
    }

    assert module._passes_selector_gate(row) is True
    assert module._passes_selector_gate({**row, "selector_win_rate": 0.55}) is False
    assert module._passes_selector_gate({**row, "selector_avg_trades_per_calendar_day": 0.99}) is False
    assert module._passes_selector_gate({**row, "selector_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v105_selector_locked_decision_ignores_holdout_ranking() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v105_selector_locked_v104_audit.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v105_selector_locked_v104_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    candidates = pd.DataFrame(
        [
            {
                "policy_id": "holdout_star",
                "selector_total_net_pnl_bps": 100.0,
                "selector_win_rate": 0.60,
                "selector_avg_trades_per_calendar_day": 1.1,
                "selector_calendar_positive_month_rate": 0.6,
                "holdout_total_net_pnl_bps": 10000.0,
                "holdout_win_rate": 0.90,
                "holdout_avg_trades_per_calendar_day": 2.0,
                "holdout_calendar_positive_month_rate": 1.0,
            },
            {
                "policy_id": "selector_star",
                "selector_total_net_pnl_bps": 200.0,
                "selector_win_rate": 0.58,
                "selector_avg_trades_per_calendar_day": 1.0,
                "selector_calendar_positive_month_rate": 0.8,
                "holdout_total_net_pnl_bps": 50.0,
                "holdout_win_rate": 0.56,
                "holdout_avg_trades_per_calendar_day": 1.0,
                "holdout_calendar_positive_month_rate": 0.5,
            },
        ]
    )

    decision = module._selector_locked_decision(candidates)

    assert decision["selected_policy"] == "selector_star"
    assert decision["selector_locked_holdout_passed"] is True
    assert decision["goal_satisfied_by_selector_locked_selection"] is True


def test_btcusdc_v106_exact_daily_gate_requires_every_calendar_day() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v106_exact_daily_coverage_classifier.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v106_exact_daily_coverage_classifier", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "selector_total_net_pnl_bps": 20.0,
        "selector_win_rate": 0.56,
        "selector_active_day_count": 10,
        "selector_calendar_day_count": 10,
        "selector_avg_trades_per_calendar_day": 1.2,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_active_day_count": 30,
        "holdout_calendar_day_count": 30,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }

    assert module._passes_exact_daily_gate(passing) is True
    assert module._passes_exact_daily_gate({**passing, "holdout_active_day_count": 29}) is False
    assert module._passes_exact_daily_gate({**passing, "selector_active_day_count": 9}) is False
    assert module._passes_exact_daily_gate({**passing, "holdout_win_rate": 0.55}) is False
    assert module._passes_exact_daily_gate({**passing, "selector_total_net_pnl_bps": -1.0}) is False


def test_btcusdc_v106_selector_locked_exact_daily_decision_uses_selector_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v106_exact_daily_coverage_classifier.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v106_exact_daily_coverage_classifier", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    base = {
        "selector_win_rate": 0.56,
        "selector_active_day_count": 10,
        "selector_calendar_day_count": 10,
        "selector_avg_trades_per_calendar_day": 1.0,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_active_day_count": 30,
        "holdout_calendar_day_count": 30,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }
    candidates = pd.DataFrame(
        [
            {**base, "policy_id": "holdout_star", "probability_floor": 0.0, "selector_total_net_pnl_bps": 100.0, "holdout_total_net_pnl_bps": 999.0},
            {**base, "policy_id": "future_gap_risk", "probability_floor": 0.35, "selector_total_net_pnl_bps": 300.0, "holdout_total_net_pnl_bps": 9999.0},
            {**base, "policy_id": "selector_star", "probability_floor": 0.0, "selector_total_net_pnl_bps": 200.0, "holdout_total_net_pnl_bps": 30.0},
        ]
    )

    decision = module._selector_locked_exact_daily_decision(candidates)

    assert decision["selected_policy"] == "selector_star"
    assert decision["selector_locked_holdout_passed"] is True
    assert decision["goal_satisfied_by_selector_locked_exact_daily_selection"] is True


def test_btcusdc_v107_price_context_features_use_prior_high_low_without_lookahead() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v107_price_context_exact_daily_classifier.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v107_price_context_exact_daily_classifier", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=8, freq="min"),
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "high": [101.0, 102.0, 103.0, 999.0, 105.0, 106.0, 107.0, 108.0],
            "low": [99.0, 98.0, 97.0, 1.0, 95.0, 94.0, 93.0, 92.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5],
            "volume": [10.0, 11.0, 12.0, 1000.0, 14.0, 15.0, 16.0, 17.0],
        }
    )

    out = module._add_price_context_features(frame, windows=(3,), volume_windows=(3,))
    row = out.iloc[3]

    assert row["prior_high_3"] == 103.0
    assert row["prior_low_3"] == 97.0
    assert round(row["range_pos_3"], 6) == 1.0
    assert round(row["prior_high_3_dist_bps"], 6) == round((103.0 / 103.0 - 1.0) * 10000.0, 6)
    assert round(row["prior_low_3_dist_bps"], 6) == round((103.0 / 97.0 - 1.0) * 10000.0, 6)


def test_btcusdc_v107_feature_frame_includes_price_context_columns() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v107_price_context_exact_daily_classifier.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v107_price_context_exact_daily_classifier", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=300, freq="min"),
            "open": np.linspace(100.0, 130.0, 300),
            "high": np.linspace(101.0, 131.0, 300),
            "low": np.linspace(99.0, 129.0, 300),
            "close": np.linspace(100.5, 130.5, 300),
            "volume": np.linspace(10.0, 20.0, 300),
            "signed_taker_imbalance": np.linspace(-0.1, 0.1, 300),
        }
    )

    _, feature_cols = module._price_context_feature_frame(bars, horizon_minutes=15)

    for column in [
        "prior_high_15_dist_bps",
        "prior_low_15_dist_bps",
        "range_pos_15",
        "range_width_15_bps",
        "realized_vol_15_bps",
        "volume_z_30",
    ]:
        assert column in feature_cols


def test_btcusdc_v108_technical_indicators_use_prior_bars_without_lookahead() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v108_technical_indicator_exact_daily_classifier.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v108_technical_indicator_exact_daily_classifier", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=40, freq="min"),
            "open": [100.0 + i for i in range(40)],
            "high": [101.0 + i for i in range(40)],
            "low": [99.0 + i for i in range(40)],
            "close": [100.5 + i for i in range(40)],
            "volume": [10.0 + i for i in range(40)],
        }
    )
    frame.loc[20, "close"] = 9999.0
    frame.loc[20, "high"] = 10000.0
    frame.loc[20, "low"] = 1.0

    out = module._add_technical_indicator_features(
        frame,
        rsi_windows=(3,),
        bollinger_windows=(3,),
        atr_windows=(3,),
        stochastic_windows=(3,),
    )
    row = out.iloc[20]

    assert round(row["bollinger_mid_3"], 6) == round((117.5 + 118.5 + 119.5) / 3.0, 6)
    assert row["stoch_pos_3"] == 1.0
    assert row["rsi_3"] == 100.0
    assert row["atr_3_bps"] < 500.0


def test_btcusdc_v108_feature_frame_includes_technical_indicator_columns() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v108_technical_indicator_exact_daily_classifier.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v108_technical_indicator_exact_daily_classifier", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=300, freq="min"),
            "open": np.linspace(100.0, 130.0, 300),
            "high": np.linspace(101.0, 131.0, 300),
            "low": np.linspace(99.0, 129.0, 300),
            "close": np.linspace(100.5, 130.5, 300),
            "volume": np.linspace(10.0, 20.0, 300),
            "signed_taker_imbalance": np.linspace(-0.1, 0.1, 300),
        }
    )

    _, feature_cols = module._technical_indicator_feature_frame(bars, horizon_minutes=15)

    for column in [
        "rsi_14",
        "macd_line_bps",
        "macd_signal_bps",
        "macd_hist_bps",
        "bollinger_z_20",
        "bollinger_width_20_bps",
        "atr_14_bps",
        "stoch_pos_14",
    ]:
        assert column in feature_cols


def test_btcusdc_v109_average_probability_frames_aligns_by_timestamp() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v109_feature_family_ensemble_exact_daily.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v109_feature_family_ensemble_exact_daily", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=2, freq="min")
    first = pd.DataFrame(
        {
            "timestamp": timestamps,
            "future_return_bps": [10.0, -20.0],
            "prob_down": [0.2, 0.6],
            "prob_flat": [0.3, 0.2],
            "prob_up": [0.5, 0.2],
        }
    )
    second = pd.DataFrame(
        {
            "timestamp": list(reversed(timestamps)),
            "future_return_bps": [-20.0, 10.0],
            "prob_down": [0.4, 0.1],
            "prob_flat": [0.3, 0.4],
            "prob_up": [0.3, 0.5],
        }
    )

    out = module._average_probability_frames([first, second])

    assert out["timestamp"].tolist() == list(timestamps)
    assert out["future_return_bps"].tolist() == [10.0, -20.0]
    assert out["prob_down"].round(6).tolist() == [0.15, 0.5]
    assert out["prob_flat"].round(6).tolist() == [0.35, 0.25]
    assert out["prob_up"].round(6).tolist() == [0.5, 0.25]


def test_btcusdc_v110_flow_sweep_regime_features_use_prior_bars_without_lookahead() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v110_flow_sweep_regime_ensemble.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v110_flow_sweep_regime_ensemble", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    rows = 320
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=rows, freq="min"),
            "open": np.linspace(100.0, 130.0, rows),
            "high": np.linspace(101.0, 131.0, rows),
            "low": np.linspace(99.0, 129.0, rows),
            "close": np.linspace(100.5, 130.5, rows),
            "volume": np.linspace(10.0, 20.0, rows),
            "trade_count": np.arange(rows) + 1,
            "taker_buy_volume": np.linspace(4.0, 12.0, rows),
            "taker_sell_volume": np.linspace(6.0, 8.0, rows),
            "taker_buy_ratio": np.linspace(0.4, 0.6, rows),
            "signed_taker_imbalance": np.linspace(-0.2, 0.2, rows),
        }
    )

    changed = frame.copy()
    changed.loc[250, "high"] = 99999.0
    changed.loc[250, "low"] = 1.0
    changed.loc[250, "close"] = 99999.0
    changed.loc[250, "volume"] = 99999.0
    changed.loc[250, "trade_count"] = 99999
    changed.loc[250, "taker_buy_volume"] = 99999.0
    changed.loc[250, "taker_sell_volume"] = 1.0
    changed.loc[250, "taker_buy_ratio"] = 1.0
    changed.loc[250, "signed_taker_imbalance"] = 1.0

    original_out = module._add_flow_sweep_regime_features(frame)
    changed_out = module._add_flow_sweep_regime_features(changed)

    pd.testing.assert_series_equal(
        original_out.loc[250, module.FLOW_SWEEP_REGIME_FEATURE_COLUMNS],
        changed_out.loc[250, module.FLOW_SWEEP_REGIME_FEATURE_COLUMNS],
        check_names=False,
    )


def test_btcusdc_v110_feature_frame_includes_flow_sweep_regime_columns() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v110_flow_sweep_regime_ensemble.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v110_flow_sweep_regime_ensemble", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=360, freq="min"),
            "open": np.linspace(100.0, 130.0, 360),
            "high": np.linspace(101.0, 131.0, 360),
            "low": np.linspace(99.0, 129.0, 360),
            "close": np.linspace(100.5, 130.5, 360),
            "volume": np.linspace(10.0, 20.0, 360),
            "trade_count": np.arange(360) + 1,
            "taker_buy_volume": np.linspace(4.0, 12.0, 360),
            "taker_sell_volume": np.linspace(6.0, 8.0, 360),
            "taker_buy_ratio": np.linspace(0.4, 0.6, 360),
            "signed_taker_imbalance": np.linspace(-0.2, 0.2, 360),
        }
    )

    _, feature_cols = module._flow_sweep_regime_feature_frame(bars, horizon_minutes=30)

    for column in [
        "signed_flow_mean_15",
        "signed_volume_ratio_60",
        "buy_ratio_z_60",
        "trade_count_z_60",
        "cvd_slope_norm_60",
        "cvd_price_divergence_60",
        "prior_high_sweep_60",
        "low_sweep_flow_fade_60",
        "realized_vol_z_60",
        "flow_vol_interaction_60",
    ]:
        assert column in feature_cols


def test_btcusdc_v110_average_probability_frames_reuses_timestamp_alignment() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v110_flow_sweep_regime_ensemble.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v110_flow_sweep_regime_ensemble", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=2, freq="min")
    first = pd.DataFrame(
        {
            "timestamp": timestamps,
            "future_return_bps": [10.0, -20.0],
            "prob_down": [0.2, 0.6],
            "prob_flat": [0.3, 0.2],
            "prob_up": [0.5, 0.2],
        }
    )
    second = pd.DataFrame(
        {
            "timestamp": list(reversed(timestamps)),
            "future_return_bps": [-20.0, 10.0],
            "prob_down": [0.4, 0.1],
            "prob_flat": [0.3, 0.4],
            "prob_up": [0.3, 0.5],
        }
    )

    out = module._average_probability_frames([first, second])

    assert out["timestamp"].tolist() == list(timestamps)
    assert out["future_return_bps"].tolist() == [10.0, -20.0]
    assert out["prob_down"].round(6).tolist() == [0.15, 0.5]
    assert out["prob_flat"].round(6).tolist() == [0.35, 0.25]
    assert out["prob_up"].round(6).tolist() == [0.5, 0.25]


def test_btcusdc_v111_daily_fallback_fills_missing_days_without_filling_to_topk() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v111_high_confidence_daily_fallback.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v111_high_confidence_daily_fallback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    predictions = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:30:00Z",
                    "2026-01-01T01:00:00Z",
                    "2026-01-02T00:00:00Z",
                    "2026-01-02T00:30:00Z",
                    "2026-01-02T01:00:00Z",
                ],
                utc=True,
            ),
            "future_return_bps": [20.0, 10.0, -5.0, 12.0, -8.0, 3.0],
            "prob_down": [0.1, 0.2, 0.2, 0.31, 0.32, 0.30],
            "prob_flat": [0.2, 0.2, 0.3, 0.34, 0.33, 0.35],
            "prob_up": [0.7, 0.6, 0.5, 0.35, 0.35, 0.35],
        }
    )

    ledger = module._daily_topk_probability_ledger_with_fallback(
        predictions,
        daily_top_k=3,
        primary_probability_floor=0.50,
        fallback_min_daily_trades=1,
        horizon_minutes=30,
        fee_bps=0.0,
    )

    assert len(ledger) == 4
    assert ledger["timestamp"].dt.normalize().nunique() == 2
    assert int(ledger["used_fallback"].sum()) == 1
    day_counts = ledger.groupby(ledger["timestamp"].dt.normalize()).size().tolist()
    assert day_counts == [3, 1]


def test_btcusdc_v111_selector_decision_allows_nonzero_floor_when_fallback_is_exact_daily() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v111_high_confidence_daily_fallback.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v111_high_confidence_daily_fallback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    base = {
        "selector_win_rate": 0.56,
        "selector_active_day_count": 10,
        "selector_calendar_day_count": 10,
        "selector_avg_trades_per_calendar_day": 1.1,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_total_net_pnl_bps": 30.0,
        "holdout_win_rate": 0.57,
        "holdout_active_day_count": 30,
        "holdout_calendar_day_count": 30,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }
    candidates = pd.DataFrame(
        [
            {**base, "policy_id": "floor_0", "primary_probability_floor": 0.0, "selector_total_net_pnl_bps": 100.0},
            {**base, "policy_id": "floor_40", "primary_probability_floor": 0.40, "selector_total_net_pnl_bps": 200.0},
        ]
    )

    decision = module._selector_locked_v111_decision(candidates)

    assert decision["selected_policy"] == "floor_40"
    assert decision["selector_locked_holdout_passed"] is True


def test_btcusdc_v112_performance_target_requires_five_percent_improvement() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v112_expanded_topk_daily_fallback.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v112_expanded_topk_daily_fallback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._meets_five_percent_target(105.0, 100.0) is True
    assert module._meets_five_percent_target(104.99, 100.0) is False
    assert module._meets_five_percent_target(105.0, 0.0) is False


def test_btcusdc_v112_selector_decision_uses_selector_only_before_target_check() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v112_expanded_topk_daily_fallback.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v112_expanded_topk_daily_fallback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    base = {
        "selector_win_rate": 0.56,
        "selector_active_day_count": 10,
        "selector_calendar_day_count": 10,
        "selector_avg_trades_per_calendar_day": 1.1,
        "selector_calendar_positive_month_rate": 0.6,
        "holdout_win_rate": 0.57,
        "holdout_active_day_count": 30,
        "holdout_calendar_day_count": 30,
        "holdout_avg_trades_per_calendar_day": 1.0,
        "holdout_calendar_positive_month_rate": 0.6,
    }
    candidates = pd.DataFrame(
        [
            {
                **base,
                "policy_id": "selector_star",
                "selector_total_net_pnl_bps": 200.0,
                "holdout_total_net_pnl_bps": 30.0,
            },
            {
                **base,
                "policy_id": "holdout_star",
                "selector_total_net_pnl_bps": 100.0,
                "holdout_total_net_pnl_bps": 9999.0,
            },
        ]
    )

    decision = module._selector_locked_v112_decision(candidates, baseline_holdout_bps=100.0)

    assert decision["selected_policy"] == "selector_star"
    assert decision["selector_locked_holdout_passed"] is True
    assert decision["five_percent_target_met"] is False


def test_btcusdc_v113_fold_windows_use_warmup_and_cover_latest_available_data() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v113_v112_earliest_walk_forward.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v113_v112_earliest_walk_forward", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    windows = module._fold_windows(
        data_start=pd.Timestamp("2024-01-04T12:31:00Z"),
        data_end=pd.Timestamp("2024-08-15T23:59:00Z"),
        train_days=180,
        test_days=60,
    )

    assert windows[0]["test_start"] == pd.Timestamp("2024-07-03T00:00:00Z")
    assert windows[0]["train_end_exclusive"] == pd.Timestamp("2024-07-02T23:30:00Z")
    assert windows[-1]["test_end_exclusive"] == pd.Timestamp("2024-08-16T00:00:00Z")


def test_btcusdc_v114_candidate_summary_requires_target_improvement_and_other_month_guard() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v114_v112_guard_sweep.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v114_v112_guard_sweep", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "month": ["2026-03", "2026-03", "2026-04", "2026-04", "2026-05", "2026-05"],
            "net_pnl_bps": [50.0, 50.0, -40.0, -10.0, 100.0, 100.0],
        }
    )
    baseline = module._monthly_pnl(frame)
    passing = pd.Series([True, True, False, True, True, True])
    failing = pd.Series([False, True, False, True, True, True])

    passing_summary = module._candidate_summary("passing", frame, passing, baseline)
    failing_summary = module._candidate_summary("failing", frame, failing, baseline)

    assert passing_summary["target_month_improved"] is True
    assert passing_summary["other_month_guard_passed"] is True
    assert passing_summary["selected_gate_passed"] is True
    assert failing_summary["target_month_improved"] is True
    assert failing_summary["other_month_guard_passed"] is False
    assert failing_summary["selected_gate_passed"] is False


def test_btcusdc_v115_contrarian_sizing_downweights_trend_following_signals() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v115_v112_contrarian_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v115_v112_contrarian_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    signal = pd.Series([1, 1, -1, -1])
    prior_ret = pd.Series([400.0, -400.0, -400.0, 400.0])

    aligned = module._aligned_prior_return_bps(signal, prior_ret)
    weights = module._contrarian_position_weights(signal, prior_ret, amp=0.5, scale_bps=800.0)

    assert aligned.tolist() == [400.0, -400.0, 400.0, -400.0]
    assert weights.iloc[0] < weights.iloc[1]
    assert weights.iloc[2] < weights.iloc[3]


def test_btcusdc_v115_sizing_summary_requires_five_percent_and_month_guard() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v115_v112_contrarian_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v115_v112_contrarian_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    baseline_monthly = pd.Series([100.0, 100.0], index=pd.Index(["2026-01", "2026-02"], name="month"))
    passing = pd.DataFrame(
        {
            "month": ["2026-01", "2026-02"],
            "weighted_net_pnl_bps": [110.0, 101.0],
            "position_weight": [1.0, 1.0],
        }
    )
    failing_total = pd.DataFrame(
        {
            "month": ["2026-01", "2026-02"],
            "weighted_net_pnl_bps": [104.0, 105.0],
            "position_weight": [1.0, 1.0],
        }
    )
    failing_month = pd.DataFrame(
        {
            "month": ["2026-01", "2026-02"],
            "weighted_net_pnl_bps": [120.0, 94.0],
            "position_weight": [1.0, 1.0],
        }
    )

    assert module._sizing_summary(passing, baseline_monthly)["selected_gate_passed"] is True
    assert module._sizing_summary(failing_total, baseline_monthly)["five_percent_target_met"] is False
    assert module._sizing_summary(failing_month, baseline_monthly)["month_guard_passed"] is False


def test_btcusdc_v116_monitoring_decision_separates_no_data_from_no_signal() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v116_v115_forward_monitoring.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v116_v115_forward_monitoring", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    no_data = module._monitoring_decision(
        has_new_complete_day=False,
        data_end=pd.Timestamp("2026-06-12T23:59:00Z"),
        v115_trade_end=pd.Timestamp("2026-06-12T17:25:00Z"),
    )
    new_data = module._monitoring_decision(
        has_new_complete_day=True,
        data_end=pd.Timestamp("2026-06-13T23:59:00Z"),
        v115_trade_end=pd.Timestamp("2026-06-12T17:25:00Z"),
    )

    assert no_data["status"] == "no_new_complete_public_file"
    assert no_data["forward_trade_proof"] is False
    assert no_data["new_signal_count"] == 0
    assert no_data["next_action"] == "wait_for_next_complete_binance_public_day"
    assert new_data["status"] == "new_data_available_rerun_required"
    assert new_data["next_action"] == "rebuild_v113_then_apply_v114_and_v115_to_new_rows"


def test_btcusdc_v118_live_non_overlapping_indices_are_chronological() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v118_live_executable_feasibility.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v118_live_executable_feasibility", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:05:00Z",
                "2026-01-01T00:30:00Z",
                "2026-01-01T00:35:00Z",
                "2026-01-01T01:00:00Z",
            ],
            utc=True,
        )
    )
    eligible = pd.Series([True, True, True, True, True])

    keep = module._live_non_overlapping_indices(timestamps, eligible, horizon_minutes=30)

    assert keep == [0, 2, 4]


def test_btcusdc_v118_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v118_live_executable_feasibility.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v118_live_executable_feasibility", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v119_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v119_live_entry_model_audit.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v119_live_entry_model_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v120_live_non_overlapping_indices_are_chronological() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v120_live_peak_trigger_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v120_live_peak_trigger_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:05:00Z",
                "2026-01-01T00:30:00Z",
                "2026-01-01T00:35:00Z",
                "2026-01-01T01:00:00Z",
            ],
            utc=True,
        )
    )
    eligible = pd.Series([True, True, True, True, True])

    keep = module._live_non_overlapping_indices(timestamps, eligible, horizon_minutes=30)

    assert keep == [0, 2, 4]


def test_btcusdc_v120_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v120_live_peak_trigger_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v120_live_peak_trigger_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v121_live_native_target_uses_current_trade_pnl_threshold() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v121_live_native_entry_model.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v121_live_native_entry_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    pnl = pd.Series([25.0, 10.0, 9.999, -5.0])

    target = module._make_live_native_target(pnl, min_net_pnl_bps=10.0)

    assert target.tolist() == [1, 1, 0, 0]


def test_btcusdc_v121_prior_fold_training_indices_use_no_current_or_future_rows() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v121_live_native_entry_model.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v121_live_native_entry_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    folds = pd.Series([1, 1, 2, 2, 3, 3, 4])

    cold_start = module._prior_fold_train_indices(folds, test_fold=2, min_train_folds=2)
    warm = module._prior_fold_train_indices(folds, test_fold=4, min_train_folds=2)

    assert cold_start == []
    assert warm == [0, 1, 2, 3, 4, 5]


def test_btcusdc_v121_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v121_live_native_entry_model.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v121_live_native_entry_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v122_drought_fallback_waits_for_no_recent_trade() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v122_live_drought_fallback.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v122_live_drought_fallback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:30:00Z",
                "2026-01-02T00:00:00Z",
                "2026-01-09T00:00:00Z",
                "2026-01-09T00:30:00Z",
            ],
            utc=True,
        )
    )
    primary = pd.Series([True, False, False, False, True])
    fallback = pd.Series([False, True, True, True, True])

    keep = module._live_drought_fallback_indices(
        timestamps,
        primary,
        fallback,
        cooldown_minutes=30,
        drought_days=7,
    )

    assert keep == [0, 3, 4]


def test_btcusdc_v122_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v122_live_drought_fallback.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v122_live_drought_fallback", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v123_group_thresholds_use_prior_folds_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v123_live_hourly_threshold_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v123_live_hourly_threshold_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "fold": [1, 1, 2, 2, 3, 3, 4],
            "hour": [0, 0, 0, 1, 0, 1, 0],
            "dow": [1, 1, 1, 1, 1, 1, 1],
            "score": [0.10, 0.30, 0.50, 0.70, 0.90, 0.95, 0.99],
        }
    )

    thresholds = module._prior_fold_group_thresholds(
        frame,
        test_fold=3,
        group_cols=["hour"],
        quantile=0.50,
        min_train_folds=2,
    )

    assert thresholds.tolist() == [0.30, 0.70]


def test_btcusdc_v123_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v123_live_hourly_threshold_scan.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v123_live_hourly_threshold_scan", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v124_priority_ensemble_prefers_higher_priority_same_time() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v124_live_family_ensemble.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v124_live_family_ensemble", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:10:00Z",
                    "2026-01-01T00:30:00Z",
                ],
                utc=True,
            ),
            "source": ["low", "high", "later_blocked", "next"],
            "priority": [2, 1, 1, 2],
            "net_pnl_bps": [1.0, 2.0, 3.0, 4.0],
        }
    )

    selected = module._priority_non_overlapping_events(events, cooldown_minutes=30)

    assert selected["source"].tolist() == ["high", "next"]


def test_btcusdc_v124_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v124_live_family_ensemble.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v124_live_family_ensemble", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v125_daily_cutoff_uses_prior_days_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v125_live_prior_day_topk_cutoff.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v125_live_prior_day_topk_cutoff", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "date": ["2026-01-01"] * 3 + ["2026-01-02"] * 3 + ["2026-01-03"] * 2,
            "score": [0.10, 0.50, 0.90, 0.20, 0.60, 0.80, 0.99, 1.00],
        }
    )

    cutoffs = module._prior_day_topk_cutoffs(frame, top_k=2, lookback_days=2, min_history_days=2)

    assert pd.isna(cutoffs.iloc[0])
    assert pd.isna(cutoffs.iloc[3])
    assert cutoffs.iloc[6] == 0.60
    assert cutoffs.iloc[7] == 0.60


def test_btcusdc_v125_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v125_live_prior_day_topk_cutoff.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v125_live_prior_day_topk_cutoff", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v126_prior_day_cutoff_source_uses_only_prior_days() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:05:00Z",
                    "2026-01-01T00:10:00Z",
                    "2026-01-02T00:00:00Z",
                    "2026-01-02T00:05:00Z",
                    "2026-01-02T00:10:00Z",
                    "2026-01-03T00:00:00Z",
                    "2026-01-03T00:05:00Z",
                ],
                utc=True,
            ),
            "date": ["2026-01-01"] * 3 + ["2026-01-02"] * 3 + ["2026-01-03"] * 2,
            "month": ["2026-01"] * 8,
            "score": [0.10, 0.50, 0.90, 0.20, 0.60, 0.80, 0.65, 0.59],
            "margin": [0.2] * 8,
            "aligned_prior_ret_720_bps": [-400.0] * 8,
            "net_pnl_bps": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        }
    )

    events = module._v125_prior_day_cutoff_events(
        frame,
        source="v125_top2_lb2",
        priority=5,
        top_k=2,
        lookback_days=2,
        offset=0.0,
        margin_min=0.1,
        prior_ret_max=-300.0,
        cooldown_minutes=30,
        min_history_days=2,
    )

    assert events["timestamp"].tolist() == [pd.Timestamp("2026-01-03T00:00:00Z")]
    assert events["source"].tolist() == ["v125_top2_lb2"]
    assert events["priority"].tolist() == [5]


def test_btcusdc_v126_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v126_live_family_ensemble_with_prior_day_cutoff", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v127_source_adaptive_sizing_uses_prior_source_outcomes_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v127_live_source_adaptive_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v127_live_source_adaptive_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:30:00Z",
                    "2026-01-01T01:00:00Z",
                    "2026-01-01T01:30:00Z",
                ],
                utc=True,
            ),
            "source": ["a", "a", "b", "b"],
            "net_pnl_bps": [100.0, 50.0, -100.0, 200.0],
        }
    )

    sized = module._apply_source_adaptive_sizing(
        trades,
        amp=2.0,
        scale_bps=50.0,
        min_weight=0.1,
        max_weight=5.0,
    )

    assert sized["prior_source_count"].tolist() == [0, 1, 0, 1]
    assert sized["prior_source_mean_bps"].tolist() == [0.0, 100.0, 0.0, -100.0]
    assert sized.loc[0, "position_weight"] == 1.0
    assert sized.loc[1, "position_weight"] > 1.0
    assert sized.loc[3, "position_weight"] < 1.0


def test_btcusdc_v127_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v127_live_source_adaptive_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v127_live_source_adaptive_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v128_source_health_gate_uses_prior_source_outcomes_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v128_live_source_health_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v128_live_source_health_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:30:00Z",
                    "2026-01-01T01:00:00Z",
                    "2026-01-01T01:30:00Z",
                    "2026-01-01T02:00:00Z",
                ],
                utc=True,
            ),
            "source": ["a", "a", "a", "b", "b"],
            "net_pnl_bps": [100.0, -300.0, 50.0, -200.0, 500.0],
        }
    )

    gated = module._apply_source_health_gate(
        trades,
        min_source_count=1,
        prior_mean_floor_bps=-50.0,
        last_n=2,
        last_sum_floor_bps=-500.0,
    )

    assert gated["source"].tolist() == ["a", "a", "b"]
    assert gated["prior_source_count"].tolist() == [0, 1, 0]
    assert gated["prior_source_mean_bps"].tolist() == [0.0, 100.0, 0.0]


def test_btcusdc_v128_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v128_live_source_health_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v128_live_source_health_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v129_deduped_priority_events_keep_one_per_timestamp_before_cooldown() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v129_live_short_cooldown_source_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v129_live_short_cooldown_source_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:04:00Z",
                    "2026-01-01T00:05:00Z",
                ],
                utc=True,
            ),
            "source": ["low", "high", "blocked", "next"],
            "priority": [3, 1, 1, 2],
            "month": ["2026-01"] * 4,
            "net_pnl_bps": [1.0, 2.0, 3.0, 4.0],
        }
    )

    selected = module._deduped_priority_non_overlapping_events(events, cooldown_minutes=5)

    assert selected["source"].tolist() == ["high", "next"]


def test_btcusdc_v129_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v129_live_short_cooldown_source_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v129_live_short_cooldown_source_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v130_consensus_features_use_same_timestamp_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v130_live_consensus_confidence_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v130_live_consensus_confidence_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    selected = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"], utc=True),
            "source": ["a", "c"],
            "priority": [1, 1],
            "month": ["2026-01", "2026-01"],
            "net_pnl_bps": [10.0, 20.0],
        }
    )
    source_events = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:05:00Z",
                    "2026-01-01T00:10:00Z",
                ],
                utc=True,
            ),
            "source": ["b", "a", "c", "future"],
            "priority": [2, 1, 1, 1],
            "month": ["2026-01"] * 4,
            "net_pnl_bps": [10.0, 10.0, 20.0, 30.0],
        }
    )

    with_consensus = module._attach_same_timestamp_consensus(selected, source_events)

    assert with_consensus["consensus_count"].tolist() == [2, 1]
    assert with_consensus["consensus_sources"].tolist() == ["a+b", "c"]


def test_btcusdc_v130_best_trades_keeps_consensus_config_names() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v130_live_consensus_confidence_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v130_live_consensus_confidence_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"], utc=True),
            "source": ["a", "b"],
            "priority": [1, 2],
            "month": ["2026-01", "2026-01"],
            "net_pnl_bps": [10.0, 10.0],
        }
    )
    best = {
        "source_subset": "a+b",
        "cooldown_minutes": 0,
        "sizing_amp": 1.0,
        "sizing_scale_bps": 10.0,
        "sizing_min_weight": 1.0,
        "sizing_max_weight": 3.0,
        "consensus_consensus_multiplier": 2.0,
        "consensus_consensus_cap": 4.0,
    }

    best_trades = module._best_trades(events, best)

    assert best_trades["consensus_count"].tolist() == [2]
    assert "consensus_raw_multiplier" in best_trades


def test_btcusdc_v130_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v130_live_consensus_confidence_sizing.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v130_live_consensus_confidence_sizing", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v131_probability_floor_events_are_chronological_without_daily_cap() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v131_live_probability_floor_rescue.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v131_live_probability_floor_rescue", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    predictions = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:10:00Z",
                    "2026-01-01T00:40:00Z",
                    "2026-01-01T01:20:00Z",
                ],
                utc=True,
            ),
            "future_return_bps": [20.0, 30.0, -40.0, 50.0],
            "prob_down": [0.20, 0.20, 0.70, 0.20],
            "prob_flat": [0.10, 0.10, 0.10, 0.10],
            "prob_up": [0.70, 0.80, 0.20, 0.75],
        }
    )

    events = module._probability_floor_events(
        predictions,
        floor=0.60,
        cooldown_minutes=30,
        source="test_floor",
        priority=8,
        fee_bps=8.5,
    )

    assert events["timestamp"].dt.strftime("%H:%M").tolist() == ["00:00", "00:40", "01:20"]
    assert events["source"].tolist() == ["test_floor", "test_floor", "test_floor"]
    assert events["net_pnl_bps"].round(6).tolist() == [11.5, 31.5, 41.5]


def test_btcusdc_v131_probability_config_uses_named_cooldown() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v131_live_probability_floor_rescue.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v131_live_probability_floor_rescue", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    predictions = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z"], utc=True),
            "future_return_bps": [20.0],
            "prob_down": [0.20],
            "prob_flat": [0.10],
            "prob_up": [0.70],
        }
    )

    events = module._source_events_with_probability_floor(
        predictions,
        floor=0.60,
        probability_cooldown_minutes=30,
    )

    assert "v131_prob_floor_0.6_cool30" in set(events["source"])


def test_btcusdc_v131_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v131_live_probability_floor_rescue.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v131_live_probability_floor_rescue", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v132_additive_rescue_keeps_base_pnl_and_allows_same_timestamp() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v132_live_additive_rescue_hour_veto.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v132_live_additive_rescue_hour_veto", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    base = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z"], utc=True),
            "month": ["2026-01"],
            "source": ["base"],
            "weighted_net_pnl_bps": [10.0],
        }
    )
    rescue = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"], utc=True),
            "month": ["2026-01", "2026-01"],
            "source": ["rescue", "rescue"],
            "net_pnl_bps": [3.0, 4.0],
        }
    )

    combined = module._combine_base_with_additive_rescue(base, rescue, rescue_weight=2.0)

    assert combined["timestamp"].dt.strftime("%H:%M").tolist() == ["00:00", "00:00", "00:05"]
    assert combined["leg"].tolist() == ["base", "rescue", "rescue"]
    assert combined["weighted_net_pnl_bps"].tolist() == [10.0, 6.0, 8.0]


def test_btcusdc_v132_hour_veto_uses_current_timestamp_hour_only() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v132_live_additive_rescue_hour_veto.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v132_live_additive_rescue_hour_veto", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", "2026-01-01T14:00:00Z"],
                utc=True,
            ),
            "month": ["2026-01"] * 3,
            "source": ["a", "b", "c"],
            "leg": ["base", "base", "rescue"],
            "weighted_net_pnl_bps": [1.0, 2.0, 3.0],
        }
    )

    kept = module._apply_fixed_hour_veto(trades, veto_hours=(1, 14))

    assert kept["timestamp"].dt.strftime("%H:%M").tolist() == ["00:00"]


def test_btcusdc_v132_similarity_gate_requires_v115_like_performance() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v132_live_additive_rescue_hour_veto.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v132_live_additive_rescue_hour_veto", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {"vs_v115_rate": 0.80, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_profit = {"vs_v115_rate": 0.79, "positive_months": 24, "total_net_pnl_bps": 100.0}
    weak_months = {"vs_v115_rate": 0.90, "positive_months": 23, "total_net_pnl_bps": 100.0}
    losing = {"vs_v115_rate": 0.90, "positive_months": 24, "total_net_pnl_bps": -1.0}

    assert module._passes_live_similarity_gate(passing) is True
    assert module._passes_live_similarity_gate(weak_profit) is False
    assert module._passes_live_similarity_gate(weak_months) is False
    assert module._passes_live_similarity_gate(losing) is False


def test_btcusdc_v133_config_keeps_live_execution_constraints() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v133_live_rescue_weight_step.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v133_live_rescue_weight_step", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.RESCUE_WEIGHT == 2.5
    assert module.VETO_HOURS == (1, 14)
    assert module.REQUIRED_V132_IMPROVEMENT_RATE == 1.05


def test_btcusdc_v133_improvement_gate_requires_five_percent_over_v132() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v133_live_rescue_weight_step.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v133_live_rescue_weight_step", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "total_net_pnl_bps": 105.0,
        "vs_v115_rate": 0.90,
        "positive_months": 24,
    }
    weak_improvement = {
        "total_net_pnl_bps": 104.99,
        "vs_v115_rate": 0.90,
        "positive_months": 24,
    }
    weak_months = {
        "total_net_pnl_bps": 120.0,
        "vs_v115_rate": 0.90,
        "positive_months": 23,
    }

    assert module._passes_v133_gate(passing, v132_total=100.0) is True
    assert module._passes_v133_gate(weak_improvement, v132_total=100.0) is False
    assert module._passes_v133_gate(weak_months, v132_total=100.0) is False


def test_btcusdc_v133_summary_records_no_daily_cap_or_day_end_ranking() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v133_live_rescue_weight_step.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v133_live_rescue_weight_step", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False
    assert config["rescue_weight"] == 2.5


def test_btcusdc_v134_config_keeps_live_execution_constraints() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v134_live_weight_hour_step.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v134_live_weight_hour_step", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.RESCUE_WEIGHT == 3.2
    assert module.VETO_HOURS == (1, 6, 14)
    assert module.REQUIRED_V133_IMPROVEMENT_RATE == 1.10


def test_btcusdc_v134_improvement_gate_requires_ten_percent_over_v133() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v134_live_weight_hour_step.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v134_live_weight_hour_step", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "total_net_pnl_bps": 110.0,
        "vs_v115_rate": 0.90,
        "positive_months": 24,
    }
    weak_improvement = {
        "total_net_pnl_bps": 109.99,
        "vs_v115_rate": 0.90,
        "positive_months": 24,
    }
    weak_months = {
        "total_net_pnl_bps": 120.0,
        "vs_v115_rate": 0.90,
        "positive_months": 23,
    }

    assert module._passes_v134_gate(passing, v133_total=100.0) is True
    assert module._passes_v134_gate(weak_improvement, v133_total=100.0) is False
    assert module._passes_v134_gate(weak_months, v133_total=100.0) is False


def test_btcusdc_v134_summary_records_no_daily_cap_or_day_end_ranking() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v134_live_weight_hour_step.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v134_live_weight_hour_step", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False
    assert config["rescue_weight"] == 3.2


def test_btcusdc_v135_config_records_drawdown_reduction_target() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v135_live_drawdown_guard.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v135_live_drawdown_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.RESCUE_WEIGHT == 2.9
    assert module.VETO_HOURS == (1, 5, 6, 9, 14)
    assert module.DRAWDOWN_STOP_BPS == 1600.0
    assert module.REQUIRED_DRAWDOWN_REDUCTION_RATE == 0.50
    assert module.MIN_TOTAL_NET_PNL_BPS == 40000.0


def test_btcusdc_v135_drawdown_guard_pauses_until_next_utc_day_after_realized_loss() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v135_live_drawdown_guard.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v135_live_drawdown_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:10:00Z",
                    "2026-01-01T00:20:00Z",
                    "2026-01-02T00:00:00Z",
                ],
                utc=True,
            ),
            "month": ["2026-01"] * 4,
            "source": ["a", "b", "skipped", "next_day"],
            "leg": ["base"] * 4,
            "net_pnl_bps": [100.0, -170.0, 999.0, 5.0],
            "position_weight": [1.0] * 4,
            "weighted_net_pnl_bps": [100.0, -170.0, 999.0, 5.0],
        }
    )

    guarded = module._apply_drawdown_rest_of_day_guard(trades, drawdown_stop_bps=150.0)

    assert guarded["source"].tolist() == ["a", "b", "next_day"]
    assert guarded["weighted_equity_bps"].tolist() == [100.0, -70.0, -65.0]


def test_btcusdc_v135_gate_requires_half_drawdown_and_profit_floor() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v135_live_drawdown_guard.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v135_live_drawdown_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    passing = {
        "total_net_pnl_bps": 40001.0,
        "max_drawdown_bps": 50.0,
        "positive_months": 24,
    }
    weak_profit = {
        "total_net_pnl_bps": 39999.0,
        "max_drawdown_bps": 50.0,
        "positive_months": 24,
    }
    weak_drawdown = {
        "total_net_pnl_bps": 40001.0,
        "max_drawdown_bps": 50.1,
        "positive_months": 24,
    }

    assert module._passes_v135_gate(passing, baseline_drawdown_bps=100.0) is True
    assert module._passes_v135_gate(weak_profit, baseline_drawdown_bps=100.0) is False
    assert module._passes_v135_gate(weak_drawdown, baseline_drawdown_bps=100.0) is False


def test_btcusdc_v136_config_keeps_live_constraints_and_no_degrade_targets() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v136_live_win_rate_guard.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v136_live_win_rate_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert module.MIN_WIN_RATE == 0.62
    assert module.RESCUE_WEIGHT == 3.0
    assert module.VETO_HOURS == (1, 3, 5, 6, 9, 14)
    assert module.DRAWDOWN_STOP_BPS == 1550.0
    assert module.HOUR17_V1257_PRIOR_MEAN_FLOOR_BPS == 12.0
    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False
    assert config["uses_realized_drawdown_guard"] is True
    assert config["uses_hour17_confidence_guard"] is True


def test_btcusdc_v136_hour17_guard_keeps_consensus2_and_high_prior_v1257() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v136_live_win_rate_guard.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v136_live_win_rate_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T03:00:00Z",
                    "2026-01-01T17:00:00Z",
                    "2026-01-01T17:05:00Z",
                    "2026-01-01T17:10:00Z",
                    "2026-01-01T17:15:00Z",
                    "2026-01-01T18:00:00Z",
                ],
                utc=True,
            ),
            "month": ["2026-01"] * 6,
            "source": [
                "hour3",
                "base_consensus2",
                "v125_top7_lb14_coverage",
                "v125_top7_lb14_coverage",
                "rescue",
                "normal",
            ],
            "leg": ["base", "base", "base", "base", "rescue", "base"],
            "net_pnl_bps": [1.0] * 6,
            "position_weight": [1.0] * 6,
            "weighted_net_pnl_bps": [1.0] * 6,
            "consensus_count": [1, 2, 1, 1, 0, 1],
            "prior_source_mean_bps": [0.0, 0.0, 12.0, 11.99, 0.0, 0.0],
        }
    )

    guarded = module._apply_v136_hour_confidence_guard(trades)

    assert guarded["source"].tolist() == ["base_consensus2", "v125_top7_lb14_coverage", "rescue", "normal"]


def test_btcusdc_v136_gate_requires_win_rate_and_no_v135_degrade() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v136_live_win_rate_guard.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v136_live_win_rate_guard", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    baseline = {
        "total_net_pnl_bps": 100.0,
        "win_rate": 0.599,
        "max_drawdown_bps": 50.0,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_bps": 2.0,
    }
    passing = {
        "total_net_pnl_bps": 101.0,
        "win_rate": 0.621,
        "max_drawdown_bps": 49.0,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_bps": 2.1,
    }
    weak_win = {**passing, "win_rate": 0.62}
    weak_total = {**passing, "total_net_pnl_bps": 99.99}
    weak_drawdown = {**passing, "max_drawdown_bps": 50.01}
    weak_worst_month = {**passing, "worst_month_bps": 1.99}

    assert module._passes_v136_gate(passing, v135_selected=baseline) is True
    assert module._passes_v136_gate(weak_win, v135_selected=baseline) is False
    assert module._passes_v136_gate(weak_total, v135_selected=baseline) is False
    assert module._passes_v136_gate(weak_drawdown, v135_selected=baseline) is False
    assert module._passes_v136_gate(weak_worst_month, v135_selected=baseline) is False


def test_btcusdc_v137_config_uses_weighted_model_ensemble_without_new_limits() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v137_live_weighted_model_ensemble.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v137_live_weighted_model_ensemble", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert module.MODEL_FAMILY_WEIGHTS == {"ma": 11.0, "price_context": 8.0, "technical": 5.0}
    assert module.RESCUE_WEIGHT == 2.9
    assert module.VETO_HOURS == (1, 5, 6, 9, 14)
    assert module.DRAWDOWN_STOP_BPS == 1600.0
    assert config["uses_weighted_model_ensemble"] is True
    assert config["uses_new_trade_limitations"] is False
    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False


def test_btcusdc_v137_weighted_average_probability_frames_uses_family_weights() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v137_live_weighted_model_ensemble.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v137_live_weighted_model_ensemble", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    timestamps = pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"], utc=True)
    ma = pd.DataFrame(
        {
            "timestamp": timestamps,
            "future_return_bps": [1.0, -1.0],
            "prob_down": [0.2, 0.3],
            "prob_flat": [0.1, 0.1],
            "prob_up": [0.7, 0.6],
        }
    )
    price_context = pd.DataFrame(
        {
            "timestamp": timestamps,
            "future_return_bps": [1.0, -1.0],
            "prob_down": [0.4, 0.4],
            "prob_flat": [0.2, 0.2],
            "prob_up": [0.4, 0.4],
        }
    )
    technical = pd.DataFrame(
        {
            "timestamp": timestamps,
            "future_return_bps": [1.0, -1.0],
            "prob_down": [0.6, 0.5],
            "prob_flat": [0.3, 0.3],
            "prob_up": [0.1, 0.2],
        }
    )

    weighted = module._weighted_average_probability_frames(
        {"ma": ma, "price_context": price_context, "technical": technical},
        weights={"ma": 11.0, "price_context": 8.0, "technical": 5.0},
    )

    assert weighted["timestamp"].tolist() == list(timestamps)
    assert weighted.loc[0, "prob_up"] == (11.0 * 0.7 + 8.0 * 0.4 + 5.0 * 0.1) / 24.0
    assert weighted.loc[0, "prob_down"] == (11.0 * 0.2 + 8.0 * 0.4 + 5.0 * 0.6) / 24.0
    assert weighted.loc[1, "future_return_bps"] == -1.0


def test_btcusdc_v137_gate_requires_model_improvement_without_v135_degrade() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v137_live_weighted_model_ensemble.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v137_live_weighted_model_ensemble", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    baseline = {
        "total_net_pnl_bps": 100.0,
        "win_rate": 0.60,
        "max_drawdown_bps": 50.0,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_bps": 2.0,
    }
    passing = {
        "total_net_pnl_bps": 101.0,
        "win_rate": 0.601,
        "max_drawdown_bps": 50.0,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_bps": 2.0,
    }
    weak_total = {**passing, "total_net_pnl_bps": 100.0}
    weak_win = {**passing, "win_rate": 0.60}
    weak_drawdown = {**passing, "max_drawdown_bps": 50.01}
    weak_worst_month = {**passing, "worst_month_bps": 1.99}

    assert module._passes_v137_gate(passing, v135_selected=baseline) is True
    assert module._passes_v137_gate(weak_total, v135_selected=baseline) is False
    assert module._passes_v137_gate(weak_win, v135_selected=baseline) is False
    assert module._passes_v137_gate(weak_drawdown, v135_selected=baseline) is False
    assert module._passes_v137_gate(weak_worst_month, v135_selected=baseline) is False


def test_btcusdc_v138_config_uses_confidence_sizing_without_new_trade_limits() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v138_live_confidence_sized_model.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v138_live_confidence_sized_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert module.MODEL_FAMILY_WEIGHTS == {"ma": 11.0, "price_context": 8.0, "technical": 5.0}
    assert module.BASE_RESCUE_WEIGHT == 2.9
    assert module.HIGH_CONFIDENCE_RESCUE_WEIGHT == 4.5
    assert module.HIGH_CONFIDENCE_PROBABILITY_FLOOR == 0.66
    assert config["uses_confidence_sized_model"] is True
    assert config["uses_new_trade_limitations"] is False
    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False


def test_btcusdc_v138_confidence_sizing_changes_weight_without_filtering_events() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v138_live_confidence_sized_model.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v138_live_confidence_sized_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    events = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z", "2026-01-01T00:10:00Z"],
                utc=True,
            ),
            "month": ["2026-01"] * 3,
            "net_pnl_bps": [10.0, -5.0, 7.0],
            "source": ["x"] * 3,
            "priority": [8] * 3,
            "direction_probability": [0.60, 0.6599, 0.66],
        }
    )

    sized = module._assign_confidence_rescue_weights(events)

    assert len(sized) == len(events)
    assert sized["position_weight"].tolist() == [2.9, 2.9, 4.5]
    assert sized["weighted_net_pnl_bps"].tolist() == [29.0, -14.5, 31.5]


def test_btcusdc_v138_gate_requires_v137_profit_improvement_without_core_degrade() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v138_live_confidence_sized_model.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v138_live_confidence_sized_model", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    baseline = {
        "total_net_pnl_bps": 100.0,
        "win_rate": 0.60,
        "max_drawdown_bps": 50.0,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_bps": 2.0,
    }
    passing = {
        "total_net_pnl_bps": 101.0,
        "win_rate": 0.60,
        "max_drawdown_bps": 50.0,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_bps": 2.0,
    }
    weak_total = {**passing, "total_net_pnl_bps": 100.0}
    weak_win = {**passing, "win_rate": 0.599}
    weak_drawdown = {**passing, "max_drawdown_bps": 50.01}
    weak_worst_month = {**passing, "worst_month_bps": 1.99}

    assert module._passes_v138_gate(passing, v137_selected=baseline) is True
    assert module._passes_v138_gate(weak_total, v137_selected=baseline) is False
    assert module._passes_v138_gate(weak_win, v137_selected=baseline) is False
    assert module._passes_v138_gate(weak_drawdown, v137_selected=baseline) is False
    assert module._passes_v138_gate(weak_worst_month, v137_selected=baseline) is False


def test_btcusdc_v139_config_uses_indicator_leverage_without_filtering_trades() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v139_indicator_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v139_indicator_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert module.DEFAULT_ACCOUNT_LEVERAGE == 1.0
    assert module.INDICATOR_ACCOUNT_LEVERAGE == {
        "rescue_high_ge_0p66": 5.0,
        "v123_threshold": 1.5,
    }
    assert config["uses_indicator_leverage"] is True
    assert config["uses_new_trade_filter"] is False
    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False


def test_btcusdc_v139_indicator_keys_classify_rescue_confidence_and_base_source() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v139_indicator_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v139_indicator_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:05:00Z",
                    "2026-01-01T00:10:00Z",
                    "2026-01-01T00:15:00Z",
                ],
                utc=True,
            ),
            "month": ["2026-01"] * 4,
            "source": ["v122_drought", "rescue", "rescue", "rescue"],
            "leg": ["base", "rescue", "rescue", "rescue"],
            "net_pnl_bps": [1.0] * 4,
            "position_weight": [1.0] * 4,
            "weighted_net_pnl_bps": [1.0] * 4,
        }
    )
    rescue = pd.DataFrame(
        {
            "timestamp": trades.loc[1:, "timestamp"],
            "direction_probability": [0.619, 0.62, 0.66],
            "signal": [1, 1, -1],
            "prob_up": [0.619, 0.62, 0.20],
            "prob_down": [0.20, 0.30, 0.66],
        }
    )

    enriched = module._enrich_indicator_columns(trades, rescue)

    assert enriched["indicator_key"].tolist() == [
        "v122_drought",
        "rescue_low_0p60_0p62",
        "rescue_mid_0p62_0p66",
        "rescue_high_ge_0p66",
    ]


def test_btcusdc_v139_indicator_leverage_increases_account_pnl_without_changing_trade_count() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v139_indicator_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v139_indicator_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z", "2026-01-01T00:10:00Z"],
                utc=True,
            ),
            "month": ["2026-01"] * 3,
            "indicator_key": ["v122_drought", "rescue_high_ge_0p66", "v123_threshold"],
            "weighted_net_pnl_bps": [10.0, 20.0, -4.0],
        }
    )

    levered = module._apply_indicator_leverage(
        trades,
        leverage_map={"rescue_high_ge_0p66": 5.0, "v123_threshold": 1.5},
        default_leverage=1.0,
    )

    assert len(levered) == len(trades)
    assert levered["account_leverage"].tolist() == [1.0, 5.0, 1.5]
    assert levered["account_pnl_bps"].tolist() == [10.0, 100.0, -6.0]
    assert levered["account_return_pct"].tolist() == [0.1, 1.0, -0.06]


def test_btcusdc_v140_config_promotes_fixed_3x_performance_overlay() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v140_performance_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v140_performance_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert module.SELECTED_ACCOUNT_LEVERAGE == 3.0
    assert module.MAX_SELECTED_DRAWDOWN_PCT == -50.0
    assert config["uses_fixed_account_leverage"] is True
    assert config["uses_new_trade_filter"] is False
    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False


def test_btcusdc_v140_fixed_leverage_scales_account_path_without_changing_trades() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v140_performance_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v140_performance_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z", "2026-01-01T00:10:00Z"],
                utc=True,
            ),
            "month": ["2026-01"] * 3,
            "weighted_net_pnl_bps": [10.0, -5.0, 20.0],
        }
    )

    levered = module._apply_fixed_account_leverage(trades, leverage=3.0)

    assert len(levered) == len(trades)
    assert levered["account_leverage"].tolist() == [3.0, 3.0, 3.0]
    assert levered["account_pnl_bps"].tolist() == [30.0, -15.0, 60.0]
    assert levered["account_return_pct"].tolist() == [0.3, -0.15, 0.6]


def test_btcusdc_v140_gate_requires_significant_v139_improvement_and_drawdown_cap() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v140_performance_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v140_performance_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    baseline = {
        "total_account_return_pct": 600.0,
    }
    passing = {
        "total_account_return_pct": 1201.0,
        "max_drawdown_pct": -49.0,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_pct": 0.01,
    }
    weak_return = {**passing, "total_account_return_pct": 1199.0}
    weak_drawdown = {**passing, "max_drawdown_pct": -50.1}
    weak_month = {**passing, "positive_months": 23}

    assert module._passes_v140_gate(passing, v139_selected=baseline) is True
    assert module._passes_v140_gate(weak_return, v139_selected=baseline) is False
    assert module._passes_v140_gate(weak_drawdown, v139_selected=baseline) is False
    assert module._passes_v140_gate(weak_month, v139_selected=baseline) is False


def test_btcusdc_v141_config_uses_causal_drawdown_throttle() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v141_drawdown_throttle_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v141_drawdown_throttle_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert module.HIGH_ACCOUNT_LEVERAGE == 3.5
    assert module.MID_ACCOUNT_LEVERAGE == 2.25
    assert module.LOW_ACCOUNT_LEVERAGE == 1.25
    assert module.MID_DRAWDOWN_TRIGGER_PCT == -5.0
    assert module.LOW_DRAWDOWN_TRIGGER_PCT == -15.0
    assert config["uses_causal_drawdown_throttle"] is True
    assert config["uses_new_trade_filter"] is False
    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False


def test_btcusdc_v141_throttle_uses_prior_drawdown_before_current_trade() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v141_drawdown_throttle_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v141_drawdown_throttle_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:05:00Z",
                    "2026-01-01T00:10:00Z",
                    "2026-01-01T00:15:00Z",
                ],
                utc=True,
            ),
            "month": ["2026-01"] * 4,
            "weighted_net_pnl_bps": [100.0, -600.0, -200.0, 100.0],
        }
    )

    levered = module._apply_drawdown_throttle_leverage(
        trades,
        high_leverage=3.5,
        mid_leverage=2.25,
        low_leverage=1.25,
        mid_drawdown_trigger_pct=-5.0,
        low_drawdown_trigger_pct=-15.0,
    )

    assert levered["prior_drawdown_pct"].round(6).tolist() == [0.0, 0.0, -21.0, -23.5]
    assert levered["account_leverage"].tolist() == [3.5, 3.5, 1.25, 1.25]
    assert levered["account_pnl_bps"].tolist() == [350.0, -2100.0, -250.0, 125.0]


def test_btcusdc_v141_gate_requires_high_profit_and_lower_drawdown_than_v140() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v141_drawdown_throttle_leverage.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v141_drawdown_throttle_leverage", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    v139 = {"total_account_return_pct": 650.0}
    v140 = {"total_account_return_pct": 1350.0, "max_drawdown_pct": -48.0}
    passing = {
        "total_account_return_pct": 1195.0,
        "max_drawdown_pct": -34.5,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_pct": 0.01,
    }
    weak_profit = {**passing, "total_account_return_pct": 1090.0}
    weak_drawdown = {**passing, "max_drawdown_pct": -40.0}
    weak_month = {**passing, "positive_months": 23}

    assert module._passes_v141_gate(passing, v139_selected=v139, v140_selected=v140) is True
    assert module._passes_v141_gate(weak_profit, v139_selected=v139, v140_selected=v140) is False
    assert module._passes_v141_gate(weak_drawdown, v139_selected=v139, v140_selected=v140) is False
    assert module._passes_v141_gate(weak_month, v139_selected=v139, v140_selected=v140) is False


def test_btcusdc_v142_config_applies_5x_only_to_high_confidence_rescue() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v142_high_confidence_rescue_5x.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v142_high_confidence_rescue_5x", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    config = module._strategy_config()

    assert module.HIGH_CONFIDENCE_RESCUE_LEVERAGE == 5.0
    assert module.HIGH_CONFIDENCE_PROBABILITY_FLOOR == 0.66
    assert config["uses_high_confidence_rescue_5x"] is True
    assert config["uses_causal_drawdown_throttle"] is True
    assert config["uses_new_trade_filter"] is False
    assert config["uses_daily_trade_cap"] is False
    assert config["uses_day_end_ranking"] is False


def test_btcusdc_v142_high_confidence_5x_is_disabled_after_drawdown_trigger() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v142_high_confidence_rescue_5x.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v142_high_confidence_rescue_5x", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:05:00Z",
                    "2026-01-01T00:10:00Z",
                    "2026-01-01T00:15:00Z",
                ],
                utc=True,
            ),
            "month": ["2026-01"] * 4,
            "leg": ["rescue", "base", "rescue", "rescue"],
            "direction_probability": [0.661, np.nan, 0.662, 0.659],
            "weighted_net_pnl_bps": [100.0, -600.0, 100.0, 100.0],
        }
    )

    levered = module._apply_high_confidence_rescue_leverage(
        trades,
        high_confidence_leverage=5.0,
        high_confidence_probability_floor=0.66,
        high_leverage=3.5,
        mid_leverage=2.25,
        low_leverage=1.25,
        mid_drawdown_trigger_pct=-5.0,
        low_drawdown_trigger_pct=-15.0,
    )

    assert levered["prior_drawdown_pct"].round(6).tolist() == [0.0, 0.0, -21.0, -19.75]
    assert levered["account_leverage"].tolist() == [5.0, 3.5, 1.25, 1.25]
    assert levered["high_confidence_rescue_5x"].tolist() == [True, False, False, False]
    assert levered["account_pnl_bps"].tolist() == [500.0, -2100.0, 125.0, 125.0]


def test_btcusdc_v142_gate_requires_no_v141_drawdown_degradation_and_profit_gain() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v142_high_confidence_rescue_5x.py"
    spec = importlib.util.spec_from_file_location("run_btcusdc_v142_high_confidence_rescue_5x", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    v141 = {"total_account_return_pct": 1195.0, "max_drawdown_pct": -34.5}
    passing = {
        "total_account_return_pct": 1208.0,
        "max_drawdown_pct": -34.0,
        "positive_months": 24,
        "month_count": 24,
        "worst_month_pct": 0.01,
        "high_confidence_5x_trade_count": 2,
    }
    weak_profit = {**passing, "total_account_return_pct": 1199.0}
    weak_drawdown = {**passing, "max_drawdown_pct": -35.0}
    weak_month = {**passing, "positive_months": 23}

    assert module._passes_v142_gate(passing, v141_selected=v141) is True
    assert module._passes_v142_gate(weak_profit, v141_selected=v141) is False
    assert module._passes_v142_gate(weak_drawdown, v141_selected=v141) is False
    assert module._passes_v142_gate(weak_month, v141_selected=v141) is False
