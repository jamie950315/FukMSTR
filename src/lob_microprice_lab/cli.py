from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .adaptive import run_adaptive_walk_forward
from .backtest import backtest_predictions, backtest_predictions_non_overlapping, save_backtest_report, sweep_edge_thresholds
from .baselines import evaluate_rule_baselines
from .binance_ws import collect_binance_spot_local_book
from .diagnostics import feature_correlation_report, feature_forward_scan, profile_market_data, run_feature_diagnostics
from .data_schema import read_csv
from .edge_calibration import run_calibrated_edge_audit
from .ensemble import run_ensemble_walk_forward
from .kline_blend import run_kline_blend_ensemble
from .kline_features import parse_candle_path_specs, write_kline_cache
from .kline_guard import KlineGuardGateConfig, KlineGuardSpec, run_kline_guard_audit
from .kline_weighting import KlineWeightGateConfig, run_kline_weight_audit
from .profit_stability import KlineStabilityGateConfig, run_kline_stability_lock_audit
from .profit_success_fast import ProfitSuccessFastGate, run_profit_success_fast
from .profit_lock import ProfitLockGate, run_profit_lock_certificate
from .exit_lock import ExitLockSpec
from .profit_execution_lock import ExecutionProfitLockGate, run_execution_profit_lock_certificate
from .deployment_lock import DeploymentLockGate, run_deployment_lock_certificate
from .real_fee_lock import FeeGuardFilterSpec, RealFeeLockGate, RealFeeSpec, run_real_fee_lock_certificate
from .btc_leverage_lock import BTCLeverageGate, run_btc_contract_leverage_lock
from .btc_profit_target_lock import BTCProfitTargetGate, run_btc_profit_target_lock
from .btc_rescue_profit_lock import BTCRescueProfitGate, run_btc_rescue_profit_lock
from .btc_adaptive_exit_lock import BTCAdaptiveExitGate, run_btc_adaptive_exit_lock
from .btc_contract_data import write_btc_contract_data_plan, download_manifest_files
from .execution import backtest_taker_bidask_non_overlapping, robust_profit_gate, sweep_taker_bidask
from .fixed_template import FixedTemplateGateConfig, run_fixed_template_audit
from .family_adaptive import FamilySpec, run_family_adaptive_audit
from .long_horizon import LongWindowGateConfig, parse_model_sets, run_long_horizon_sweep, summarize_completed_long_runs
from .pipeline import run_train
from .paper_trading import (
    BinancePublicTickerSource,
    CsvPriceSource,
    CsvSignalProvider,
    NoSignalProvider,
    PaperTradingConfig,
    SyntheticPriceSource,
    run_v142_paper_trading,
)
from .portfolio import combine_fixed_backtest_ledgers
from .trade_replay import write_trade_replay_page
from .real_data import (
    TARDIS_DERIBIT_L2_SAMPLE_URL,
    convert_tardis_incremental_l2_to_book_csv,
    fetch_binance_spot_depth_snapshots,
    fetch_tardis_sample_book,
)
from .research import run_feature_ablation
from .rule_taker import run_rule_taker_walk_forward
from .sample_data import generate_sample_data
from .selection_bias import FamilyNullGateConfig, run_template_family_null_audit
from .sequential_selection import SequentialGateConfig, run_sequential_template_audit
from .slot_veto import SlotVetoGateConfig, SlotVetoSpec, run_slot_veto_audit
from .selective import run_selective_from_ensemble_dir
from .stress import run_stress_report
from .template_transfer import run_template_transfer_audit
from .trade_audit import audit_trade_backtest
from .tuning import parse_float_list, parse_str_list, run_tuning
from .validation import run_walk_forward


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lob-microprice-lab")
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("generate-sample", help="Generate synthetic book and trade CSV files.")
    sample.add_argument("--out", required=True)
    sample.add_argument("--rows", type=int, default=4000)
    sample.add_argument("--depth", type=int, default=10)
    sample.add_argument("--seed", type=int, default=42)

    fetch_tardis = sub.add_parser("fetch-tardis-sample", help="Download a public Tardis L2 sample and convert it to book CSV.")
    fetch_tardis.add_argument("--out", required=True)
    fetch_tardis.add_argument("--url", default=TARDIS_DERIBIT_L2_SAMPLE_URL)
    fetch_tardis.add_argument("--depth", type=int, default=10)
    fetch_tardis.add_argument("--sample-ms", type=int, default=500)
    fetch_tardis.add_argument("--max-input-rows", type=int, default=None)
    fetch_tardis.add_argument("--max-snapshots", type=int, default=None)
    fetch_tardis.add_argument("--overwrite", action="store_true")

    convert_tardis = sub.add_parser("convert-tardis-l2", help="Convert Tardis incremental_book_L2 CSV/CSV.GZ to book CSV.")
    convert_tardis.add_argument("--input", required=True)
    convert_tardis.add_argument("--out", required=True)
    convert_tardis.add_argument("--depth", type=int, default=10)
    convert_tardis.add_argument("--sample-ms", type=int, default=500)
    convert_tardis.add_argument("--max-input-rows", type=int, default=None)
    convert_tardis.add_argument("--max-snapshots", type=int, default=None)

    fetch_binance = sub.add_parser("fetch-binance-depth", help="Poll Binance public spot depth snapshots into book CSV.")
    fetch_binance.add_argument("--out", required=True)
    fetch_binance.add_argument("--symbol", default="BTCUSDT")
    fetch_binance.add_argument("--depth", type=int, default=20)
    fetch_binance.add_argument("--interval-sec", type=float, default=1.0)
    fetch_binance.add_argument("--samples", type=int, default=120)

    ws = sub.add_parser("collect-binance-ws", help="Collect a gap-checked Binance spot local book via REST snapshot plus WebSocket diff-depth.")
    ws.add_argument("--out", required=True)
    ws.add_argument("--symbol", default="BTCUSDT")
    ws.add_argument("--depth", type=int, default=20)
    ws.add_argument("--sample-ms", type=int, default=1000)
    ws.add_argument("--seconds", type=float, default=120.0)
    ws.add_argument("--rest-limit", type=int, default=1000)

    profile = sub.add_parser("profile", help="Profile book data quality and microstructure statistics.")
    profile.add_argument("--book", required=True)
    profile.add_argument("--trades", default=None)
    profile.add_argument("--config", default=None)
    profile.add_argument("--out", required=True)

    scan = sub.add_parser("feature-scan", help="Rank features by forward-return correlation across horizons.")
    scan.add_argument("--book", required=True)
    scan.add_argument("--trades", default=None)
    scan.add_argument("--config", default=None)
    scan.add_argument("--out", required=True)
    scan.add_argument("--horizons-sec", default="1,5,10")
    scan.add_argument("--threshold-bps", type=float, default=1.0)
    scan.add_argument("--top-n", type=int, default=40)

    diag = sub.add_parser("diagnostics", help="Build profile plus feature-scan diagnostics.")
    diag.add_argument("--book", required=True)
    diag.add_argument("--trades", default=None)
    diag.add_argument("--config", default=None)
    diag.add_argument("--out", required=True)
    diag.add_argument("--top-n", type=int, default=60)
    diag.add_argument("--clean", action="store_true")

    corr = sub.add_parser("correlations", help="Rank train/validation feature correlations using config horizon.")
    corr.add_argument("--book", required=True)
    corr.add_argument("--trades", default=None)
    corr.add_argument("--config", default=None)
    corr.add_argument("--out", required=True)
    corr.add_argument("--top-n", type=int, default=40)
    corr.add_argument("--clean", action="store_true")

    train = sub.add_parser("train", help="Train a short-horizon classifier from CSV files.")
    train.add_argument("--book", required=True)
    train.add_argument("--trades", default=None)
    train.add_argument("--config", default=None)
    train.add_argument("--out", required=True)

    tune = sub.add_parser("tune", help="Grid-search horizon, threshold, model, and signal edge on chronological validation.")
    tune.add_argument("--book", required=True)
    tune.add_argument("--trades", default=None)
    tune.add_argument("--config", default=None)
    tune.add_argument("--out", required=True)
    tune.add_argument("--horizons-sec", default="0.5,1,2,5")
    tune.add_argument("--thresholds-bps", default="0.1,0.25,0.5")
    tune.add_argument("--models", default="logistic")
    tune.add_argument("--edge-thresholds", default="0.05,0.10")
    tune.add_argument("--clean", action="store_true")

    wf = sub.add_parser("walk-forward", help="Run embargoed chronological walk-forward validation and edge sweep.")
    wf.add_argument("--book", required=True)
    wf.add_argument("--trades", default=None)
    wf.add_argument("--config", default=None)
    wf.add_argument("--out", required=True)
    wf.add_argument("--horizon-sec", type=float, default=10.0)
    wf.add_argument("--threshold-bps", type=float, default=1.0)
    wf.add_argument("--model", default="logistic")
    wf.add_argument("--edge-threshold", type=float, default=0.5)
    wf.add_argument("--edge-thresholds", default="0.05,0.10,0.20,0.30,0.50,0.70,0.90")
    wf.add_argument("--folds", type=int, default=3)
    wf.add_argument("--min-train-ratio", type=float, default=0.50)
    wf.add_argument("--valid-ratio", type=float, default=0.15)
    wf.add_argument("--embargo-sec", type=float, default=None)
    wf.add_argument("--no-null", action="store_true")
    wf.add_argument("--clean", action="store_true")


    awf = sub.add_parser("adaptive-walk-forward", help="Select edge on a past calibration window, then evaluate future folds with latency-aware non-overlap backtest.")
    awf.add_argument("--book", required=True)
    awf.add_argument("--trades", default=None)
    awf.add_argument("--config", default=None)
    awf.add_argument("--out", required=True)
    awf.add_argument("--horizon-sec", type=float, default=10.0)
    awf.add_argument("--threshold-bps", type=float, default=1.0)
    awf.add_argument("--model", default="logistic")
    awf.add_argument("--candidate-edges", default="0.1,0.2,0.3,0.5,0.7,0.9")
    awf.add_argument("--cost-bps", type=float, default=1.5)
    awf.add_argument("--latency-sec", type=float, default=0.5)
    awf.add_argument("--folds", type=int, default=2)
    awf.add_argument("--min-train-ratio", type=float, default=0.5)
    awf.add_argument("--valid-ratio", type=float, default=0.15)
    awf.add_argument("--calibration-ratio", type=float, default=0.2)
    awf.add_argument("--embargo-sec", type=float, default=None)
    awf.add_argument("--min-calibration-trades", type=int, default=5)
    awf.add_argument("--clean", action="store_true")

    rules = sub.add_parser("rule-baselines", help="Evaluate deterministic signed-feature rule baselines.")
    rules.add_argument("--book", required=True)
    rules.add_argument("--trades", default=None)
    rules.add_argument("--config", default=None)
    rules.add_argument("--out", required=True)
    rules.add_argument("--signal-thresholds", default="0,0.05,0.10,0.20,0.30,0.50,0.70")
    rules.add_argument("--clean", action="store_true")

    ablate = sub.add_parser("ablate-features", help="Run feature-family ablation experiments.")
    ablate.add_argument("--book", required=True)
    ablate.add_argument("--trades", default=None)
    ablate.add_argument("--config", default=None)
    ablate.add_argument("--out", required=True)
    ablate.add_argument("--horizon-sec", type=float, default=10.0)
    ablate.add_argument("--threshold-bps", type=float, default=1.0)
    ablate.add_argument("--model", default="logistic")
    ablate.add_argument("--edge-threshold", type=float, default=0.5)
    ablate.add_argument("--clean", action="store_true")

    sweep = sub.add_parser("sweep-edge", help="Sweep signal edge thresholds from an existing predictions CSV.")
    sweep.add_argument("--predictions", required=True)
    sweep.add_argument("--cost-bps", type=float, default=1.5)
    sweep.add_argument("--thresholds", default="0.05,0.10,0.20,0.30,0.50,0.70,0.90")
    sweep.add_argument("--horizon-sec", type=float, default=None)
    sweep.add_argument("--out", required=True)


    stress = sub.add_parser("stress", help="Run latency/cost stress tests and conservative profit gate on a predictions CSV.")
    stress.add_argument("--predictions", required=True)
    stress.add_argument("--out", required=True)
    stress.add_argument("--horizon-sec", type=float, required=True)
    stress.add_argument("--edge-thresholds", default="0.1,0.2,0.3,0.5,0.7,0.9")
    stress.add_argument("--cost-bps-values", default="0.5,1.5,3.0")
    stress.add_argument("--latency-sec-values", default="0,0.25,0.5,1.0")
    stress.add_argument("--gate-edge-threshold", type=float, default=None)
    stress.add_argument("--gate-cost-bps", type=float, default=None)
    stress.add_argument("--gate-latency-sec", type=float, default=None)
    stress.add_argument("--clean", action="store_true")

    ewf = sub.add_parser("ensemble-walk-forward", help="Run calibration-selected ensemble walk-forward with taker bid/ask execution.")
    ewf.add_argument("--book", required=True)
    ewf.add_argument("--trades", default=None)
    ewf.add_argument("--config", default=None)
    ewf.add_argument("--out", required=True)
    ewf.add_argument("--horizon-sec", type=float, default=10.0)
    ewf.add_argument("--threshold-bps", type=float, default=1.0)
    ewf.add_argument("--models", default="logistic,hgb,et")
    ewf.add_argument("--candidate-edges", default="0.1,0.2,0.3,0.5,0.7,0.9")
    ewf.add_argument("--cost-bps", type=float, default=1.5)
    ewf.add_argument("--latency-sec", type=float, default=0.5)
    ewf.add_argument("--stress-cost-bps-values", default="1.5,3.0")
    ewf.add_argument("--stress-latency-sec-values", default="0,0.5,1.0")
    ewf.add_argument("--folds", type=int, default=2)
    ewf.add_argument("--min-train-ratio", type=float, default=0.5)
    ewf.add_argument("--valid-ratio", type=float, default=0.15)
    ewf.add_argument("--calibration-ratio", type=float, default=0.2)
    ewf.add_argument("--embargo-sec", type=float, default=None)
    ewf.add_argument("--top-k-features", type=int, default=0)
    ewf.add_argument("--min-calibration-trades", type=int, default=10)
    ewf.add_argument("--stationary-only", action="store_true", help="Drop raw absolute price-level features before feature selection.")
    ewf.add_argument("--kline-timeframes", default="", help="Comma-separated leakage-safe candle timeframes, e.g. 1s,5s,15s,1m,5m.")
    ewf.add_argument("--kline-candle", action="append", default=[], help="External candle spec timeframe:path or timeframe:path1,path2. Can be repeated.")
    ewf.add_argument("--kline-decision-lag-sec", type=float, default=0.0, help="Only use candles with close_ts <= event_ts - lag.")
    ewf.add_argument("--kline-lookbacks", default="1,3,6,12,24", help="Candle lookback counts used for K-line features.")
    ewf.add_argument("--clean", action="store_true")

    kcache = sub.add_parser("build-kline-cache", help="Build leakage-safe multi-timeframe K-line features aligned to book/event timestamps.")
    kcache.add_argument("--book", required=True)
    kcache.add_argument("--events", default="", help="Optional event CSV containing timestamps. Defaults to --book timestamps.")
    kcache.add_argument("--out", required=True)
    kcache.add_argument("--timeframes", default="1s,5s,15s,1m,5m")
    kcache.add_argument("--candle", action="append", default=[], help="External candle spec timeframe:path or timeframe:path1,path2. Can be repeated.")
    kcache.add_argument("--decision-lag-sec", type=float, default=0.0)
    kcache.add_argument("--lookbacks", default="1,3,6,12,24")

    kwa = sub.add_parser("kline-weight-audit", help="Learn calibration-only weights for base edge plus multi-timeframe K-line signals.")
    kwa.add_argument("--ensemble-dir", required=True)
    kwa.add_argument("--out", required=True)
    kwa.add_argument("--horizon-sec", type=float, required=True)
    kwa.add_argument("--cost-bps", type=float, default=1.5)
    kwa.add_argument("--latency-sec", type=float, default=0.5)
    kwa.add_argument("--edge-thresholds", default="0.05,0.1,0.2,0.3,0.5")
    kwa.add_argument("--base-weight-values", default="0,0.25,0.5,0.75,1.0")
    kwa.add_argument("--kline-signs", default="-1,1")
    kwa.add_argument("--min-calibration-trades", type=int, default=4)
    kwa.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    kwa.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    kwa.add_argument("--shift-null-runs", type=int, default=80)
    kwa.add_argument("--gate-min-oof-trades", type=int, default=20)
    kwa.add_argument("--gate-min-folds-with-trades", type=int, default=5)
    kwa.add_argument("--gate-min-fold-mean-net-bps", type=float, default=0.0)
    kwa.add_argument("--gate-max-shift-null-p-total", type=float, default=0.10)
    kwa.add_argument("--gate-max-shift-null-p-mean", type=float, default=0.10)
    kwa.add_argument("--clean", action="store_true")

    kblend = sub.add_parser("kline-blend-ensemble", help="Blend a v12 base ensemble with a K-line-augmented ensemble using a fixed alpha.")
    kblend.add_argument("--base-ensemble-dir", required=True)
    kblend.add_argument("--kline-ensemble-dir", required=True)
    kblend.add_argument("--out", required=True)
    kblend.add_argument("--kline-alpha", type=float, default=0.1)
    kblend.add_argument("--drop-kline-feature-columns", action="store_true", help="Keep blended probabilities but drop raw K-line feature columns for faster downstream audits.")
    kblend.add_argument("--clean", action="store_true")

    rtwf = sub.add_parser("rule-taker-walk-forward", help="Select deterministic LOB rule on calibration data, then validate with taker bid/ask execution.")
    rtwf.add_argument("--book", required=True)
    rtwf.add_argument("--trades", default=None)
    rtwf.add_argument("--config", default=None)
    rtwf.add_argument("--out", required=True)
    rtwf.add_argument("--horizon-sec", type=float, default=10.0)
    rtwf.add_argument("--threshold-bps", type=float, default=1.0)
    rtwf.add_argument("--rule-features", default="")
    rtwf.add_argument("--signal-thresholds", default="0,0.05,0.1,0.2,0.3,0.5,0.7")
    rtwf.add_argument("--candidate-edges", default="0.5")
    rtwf.add_argument("--cost-bps", type=float, default=1.5)
    rtwf.add_argument("--latency-sec", type=float, default=0.5)
    rtwf.add_argument("--stress-cost-bps-values", default="1.5,3.0")
    rtwf.add_argument("--stress-latency-sec-values", default="0,0.5,1.0")
    rtwf.add_argument("--folds", type=int, default=2)
    rtwf.add_argument("--min-train-ratio", type=float, default=0.5)
    rtwf.add_argument("--valid-ratio", type=float, default=0.15)
    rtwf.add_argument("--calibration-ratio", type=float, default=0.2)
    rtwf.add_argument("--embargo-sec", type=float, default=None)
    rtwf.add_argument("--min-calibration-trades", type=int, default=10)
    rtwf.add_argument("--clean", action="store_true")

    execbt = sub.add_parser("backtest-taker", help="Run taker bid/ask non-overlap backtest on an existing predictions CSV.")
    execbt.add_argument("--predictions", required=True)
    execbt.add_argument("--out", required=True)
    execbt.add_argument("--horizon-sec", type=float, required=True)
    execbt.add_argument("--cost-bps", type=float, default=1.5)
    execbt.add_argument("--latency-sec", type=float, default=0.0)
    execbt.add_argument("--edge-threshold", type=float, default=0.5)

    execsweep = sub.add_parser("sweep-taker", help="Sweep cost/latency/edge with taker bid/ask execution on predictions CSV.")
    execsweep.add_argument("--predictions", required=True)
    execsweep.add_argument("--out", required=True)
    execsweep.add_argument("--horizon-sec", type=float, required=True)
    execsweep.add_argument("--cost-bps-values", default="1.5,3.0")
    execsweep.add_argument("--latency-sec-values", default="0,0.5,1.0")
    execsweep.add_argument("--edge-thresholds", default="0.1,0.2,0.3,0.5,0.7,0.9")

    sel = sub.add_parser("selective-from-ensemble", help="Post-process an ensemble walk-forward run with calibration-only selective filters.")
    sel.add_argument("--ensemble-dir", required=True)
    sel.add_argument("--out", required=True)
    sel.add_argument("--horizon-sec", type=float, required=True)
    sel.add_argument("--cost-bps", type=float, default=1.5)
    sel.add_argument("--latency-sec", type=float, default=0.5)
    sel.add_argument("--edge-thresholds", default="0.1,0.2,0.3,0.5,0.7")
    sel.add_argument("--min-calibration-trades", type=int, default=8)
    sel.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    sel.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    sel.add_argument("--signed-columns", default="")
    sel.add_argument("--spread-quantiles", default="1.0,0.75,0.5")
    sel.add_argument("--vol-modes", default="none,low,high,band")
    sel.add_argument("--clean", action="store_true")

    lhs = sub.add_parser("long-horizon-sweep", help="Run a 30s+ ensemble grid and rank candidates with the v06 long-window gate.")
    lhs.add_argument("--book", required=True)
    lhs.add_argument("--trades", default=None)
    lhs.add_argument("--config", default=None)
    lhs.add_argument("--out", required=True)
    lhs.add_argument("--horizons-sec", default="30,45,60")
    lhs.add_argument("--thresholds-bps", default="1")
    lhs.add_argument("--model-sets", default="logistic;logistic,hgb")
    lhs.add_argument("--top-k-features", default="80")
    lhs.add_argument("--candidate-edges", default="0.1,0.2,0.3,0.5,0.7")
    lhs.add_argument("--cost-bps", type=float, default=1.5)
    lhs.add_argument("--latency-sec", type=float, default=0.5)
    lhs.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    lhs.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    lhs.add_argument("--folds", type=int, default=3)
    lhs.add_argument("--min-train-ratio", type=float, default=0.45)
    lhs.add_argument("--valid-ratio", type=float, default=0.12)
    lhs.add_argument("--calibration-ratio", type=float, default=0.2)
    lhs.add_argument("--min-calibration-trades", type=int, default=8)
    lhs.add_argument("--stationary-only", action="store_true", help="Drop raw absolute price-level features in each ensemble run.")
    lhs.add_argument("--gate-min-fold-trades", type=int, default=10)
    lhs.add_argument("--gate-min-oof-trades", type=int, default=30)
    lhs.add_argument("--gate-min-oof-hit-rate", type=float, default=0.55)
    lhs.add_argument("--clean", action="store_true")
    lhs.add_argument("--no-skip-existing", action="store_true")

    lsum = sub.add_parser("summarize-long-runs", help="Summarize existing ensemble run directories with the v06 long-window gate.")
    lsum.add_argument("--runs", nargs="+", required=True)
    lsum.add_argument("--out", required=True)
    lsum.add_argument("--gate-min-fold-trades", type=int, default=10)
    lsum.add_argument("--gate-min-oof-trades", type=int, default=30)
    lsum.add_argument("--gate-min-oof-hit-rate", type=float, default=0.55)

    fta = sub.add_parser("fixed-template-audit", help="Freeze selective candidates before validation and audit a fixed long-window template.")
    fta.add_argument("--ensemble-dir", required=True)
    fta.add_argument("--out", required=True)
    fta.add_argument("--horizon-sec", type=float, required=True)
    fta.add_argument("--cost-bps", type=float, default=1.5)
    fta.add_argument("--latency-sec", type=float, default=0.5)
    fta.add_argument("--edge-thresholds", default="0.1,0.2,0.3,0.5,0.7")
    fta.add_argument("--signed-columns", default="")
    fta.add_argument("--spread-quantiles", default="1.0")
    fta.add_argument("--vol-modes", default="none")
    fta.add_argument("--template-source", choices=["first_fold", "all_calibrations"], default="first_fold")
    fta.add_argument("--selection-policy", choices=["source_rank", "validation_rank"], default="source_rank")
    fta.add_argument("--min-source-trades", type=int, default=8)
    fta.add_argument("--top-k-templates", type=int, default=50)
    fta.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    fta.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    fta.add_argument("--gate-min-folds-with-trades", type=int, default=2)
    fta.add_argument("--gate-min-oof-trades", type=int, default=20)
    fta.add_argument("--gate-min-fold-trades", type=int, default=3)
    fta.add_argument("--gate-max-shift-null-p", type=float, default=0.10)
    fta.add_argument("--clean", action="store_true")

    fam = sub.add_parser("family-adaptive-audit", help="Freeze a selective rule family, adapt thresholds on calibration only, then validate.")
    fam.add_argument("--ensemble-dir", required=True)
    fam.add_argument("--out", required=True)
    fam.add_argument("--horizon-sec", type=float, required=True)
    fam.add_argument("--cost-bps", type=float, default=1.5)
    fam.add_argument("--latency-sec", type=float, default=0.5)
    fam.add_argument("--edge-thresholds", default="0.1,0.2,0.3,0.5,0.7")
    fam.add_argument("--signed-abs-quantiles", default="0,0.5,0.75")
    fam.add_argument("--spread-quantiles", default="1.0")
    fam.add_argument("--vol-modes", default="none")
    fam.add_argument("--min-calibration-trades", type=int, default=8)
    fam.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    fam.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    fam.add_argument("--family-json", default="", help="Path to selected_candidate.json, summary.json, or a family JSON file.")
    fam.add_argument("--family-direction-mode", default="any", choices=["any", "normal", "invert"])
    fam.add_argument("--family-signed-col", default="")
    fam.add_argument("--family-signed-mode", default="any", choices=["any", "none", "agree", "disagree"])
    fam.add_argument("--shift-null-runs", type=int, default=80)
    fam.add_argument("--clean", action="store_true")

    cal = sub.add_parser("calibrated-edge-audit", help="Learn a calibration-only edge mapping, then run selective long-window trading.")
    cal.add_argument("--ensemble-dir", required=True)
    cal.add_argument("--out", required=True)
    cal.add_argument("--horizon-sec", type=float, required=True)
    cal.add_argument("--cost-bps", type=float, default=1.5)
    cal.add_argument("--latency-sec", type=float, default=0.5)
    cal.add_argument("--calibrator", choices=["logistic", "ridge"], default="logistic")
    cal.add_argument("--calibrator-features", default="prob_edge_raw,prob_confidence,spread_bps,imbalance_l3,imbalance_l5,microprice_dev_bps_l3,microprice_dev_bps_l5,ofi_sum_l3_norm,ofi_sum_l5_norm,mid_ret_60r_bps,mid_vol_60r_bps")
    cal.add_argument("--edge-thresholds", default="0.05,0.1,0.2,0.3,0.5")
    cal.add_argument("--signed-columns", default="imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps")
    cal.add_argument("--spread-quantiles", default="1.0")
    cal.add_argument("--vol-modes", default="none")
    cal.add_argument("--min-calibration-trades", type=int, default=8)
    cal.add_argument("--min-train-labels", type=int, default=50)
    cal.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    cal.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    cal.add_argument("--shift-null-runs", type=int, default=80)
    cal.add_argument("--clean", action="store_true")

    transfer = sub.add_parser("template-transfer-audit", help="Rank templates on past validation folds, then test the selected template on the next fold.")
    transfer.add_argument("--ensemble-dir", required=True)
    transfer.add_argument("--out", required=True)
    transfer.add_argument("--horizon-sec", type=float, required=True)
    transfer.add_argument("--cost-bps", type=float, default=1.5)
    transfer.add_argument("--latency-sec", type=float, default=0.5)
    transfer.add_argument("--edge-thresholds", default="0.1,0.2,0.3,0.5,0.7")
    transfer.add_argument("--signed-columns", default="imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps")
    transfer.add_argument("--spread-quantiles", default="1.0")
    transfer.add_argument("--vol-modes", default="none")
    transfer.add_argument("--min-source-trades", type=int, default=4)
    transfer.add_argument("--top-k-templates", type=int, default=80)
    transfer.add_argument("--warmup-folds", type=int, default=1)
    transfer.add_argument("--min-history-trades", type=int, default=3)
    transfer.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    transfer.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    transfer.add_argument("--shift-null-runs", type=int, default=80)
    transfer.add_argument("--clean", action="store_true")


    famnull = sub.add_parser("template-family-null-audit", help="Correct long-window template search for family-wise shifted-signal nulls.")
    famnull.add_argument("--ensemble-dir", required=True)
    famnull.add_argument("--out", required=True)
    famnull.add_argument("--horizon-sec", type=float, required=True)
    famnull.add_argument("--cost-bps", type=float, default=1.5)
    famnull.add_argument("--latency-sec", type=float, default=0.5)
    famnull.add_argument("--edge-thresholds", default="0.1,0.2,0.3,0.5,0.7")
    famnull.add_argument("--signed-columns", default="imbalance_l3,microprice_dev_bps_l3,mid_ret_60r_bps")
    famnull.add_argument("--spread-quantiles", default="1.0")
    famnull.add_argument("--vol-modes", default="none")
    famnull.add_argument("--template-source", choices=["first_fold", "all_calibrations"], default="first_fold")
    famnull.add_argument("--min-source-trades", type=int, default=4)
    famnull.add_argument("--top-k-templates", type=int, default=80)
    famnull.add_argument("--shift-runs", type=int, default=80)
    famnull.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    famnull.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    famnull.add_argument("--gate-min-oof-trades", type=int, default=100)
    famnull.add_argument("--gate-min-fold-trades", type=int, default=8)
    famnull.add_argument("--gate-max-familywise-p", type=float, default=0.05)
    famnull.add_argument("--clean", action="store_true")

    seq = sub.add_parser("sequential-template-audit", help="Select fixed templates online using only earlier validation periods.")
    seq.add_argument("--ensemble-dir", required=True)
    seq.add_argument("--out", required=True)
    seq.add_argument("--horizon-sec", type=float, required=True)
    seq.add_argument("--cost-bps", type=float, default=1.5)
    seq.add_argument("--latency-sec", type=float, default=0.5)
    seq.add_argument("--edge-thresholds", default="0.1,0.2,0.3,0.5,0.7")
    seq.add_argument("--signed-columns", default="")
    seq.add_argument("--spread-quantiles", default="1.0")
    seq.add_argument("--vol-modes", default="none")
    seq.add_argument("--template-source", choices=["first_fold", "all_calibrations"], default="first_fold")
    seq.add_argument("--min-source-trades", type=int, default=4)
    seq.add_argument("--top-k-templates", type=int, default=80)
    seq.add_argument("--period-sec", type=float, default=0.0, help="0 means one period per validation fold.")
    seq.add_argument("--ranking-policy", choices=["source_rank", "past_total", "past_mean", "past_rank_score", "past_lower_bound"], default="past_lower_bound")
    seq.add_argument("--cold-start-policy", choices=["source_rank", "no_trade"], default="source_rank")
    seq.add_argument("--warmup-periods", type=int, default=1)
    seq.add_argument("--min-history-trades", type=int, default=4)
    seq.add_argument("--min-history-periods", type=int, default=1)
    seq.add_argument("--lower-bound-z", type=float, default=1.645)
    seq.add_argument("--min-lower-bound-bps", type=float, default=0.0)
    seq.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    seq.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    seq.add_argument("--shift-null-runs", type=int, default=80)
    seq.add_argument("--gate-min-oof-trades", type=int, default=20)
    seq.add_argument("--gate-min-periods-with-trades", type=int, default=3)
    seq.add_argument("--gate-min-period-mean-net-bps", type=float, default=0.0)
    seq.add_argument("--gate-max-shift-null-p", type=float, default=0.10)
    seq.add_argument("--clean", action="store_true")

    audit = sub.add_parser("audit-trades", help="Audit an existing taker/selective backtest ledger with concentration and path diagnostics.")
    audit.add_argument("--backtest", required=True)
    audit.add_argument("--out", required=True)
    audit.add_argument("--horizon-sec", type=float, default=None)
    audit.add_argument("--latency-sec", type=float, default=None)
    audit.add_argument("--clean", action="store_true")

    port = sub.add_parser("combine-fixed-backtests", help="Combine fixed-template trade ledgers with portfolio-level non-overlap.")
    port.add_argument("--backtests", nargs="+", required=True)
    port.add_argument("--horizons-sec", required=True)
    port.add_argument("--strategy-names", default="")
    port.add_argument("--out", required=True)
    port.add_argument("--clean", action="store_true")

    bt = sub.add_parser("backtest", help="Backtest an existing predictions CSV file.")
    bt.add_argument("--predictions", required=True)
    bt.add_argument("--cost-bps", type=float, default=1.5)
    bt.add_argument("--edge-threshold", type=float, default=0.10)
    bt.add_argument("--horizon-sec", type=float, default=None)
    bt.add_argument("--out", required=True)


    kstab = sub.add_parser("kline-stability-lock-audit", help="Audit a fixed K-line alpha overlay with alpha/OFI family null controls and stability blocks.")
    kstab.add_argument("--base-ensemble-dir", required=True)
    kstab.add_argument("--kline-ensemble-dir", required=True)
    kstab.add_argument("--out", required=True)
    kstab.add_argument("--horizon-sec", type=float, required=True)
    kstab.add_argument("--cost-bps", type=float, default=1.5)
    kstab.add_argument("--latency-sec", type=float, default=0.5)
    kstab.add_argument("--selected-alpha", type=float, default=0.125)
    kstab.add_argument("--alpha-grid", default="0,0.025,0.05,0.075,0.1,0.125,0.15")
    kstab.add_argument("--edge-threshold", type=float, default=0.1)
    kstab.add_argument("--filter-col", default="ofi_sum_l5_norm")
    kstab.add_argument("--filter-operator", choices=["<=", ">="], default="<=")
    kstab.add_argument("--filter-quantile", type=float, default=0.9)
    kstab.add_argument("--family-filter-cols", default="ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm")
    kstab.add_argument("--family-quantiles", default="0.5,0.6,0.7,0.8,0.9")
    kstab.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    kstab.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    kstab.add_argument("--shift-null-runs", type=int, default=80)
    kstab.add_argument("--gate-min-oof-trades", type=int, default=20)
    kstab.add_argument("--gate-min-folds-with-trades", type=int, default=5)
    kstab.add_argument("--gate-min-equal-trade-blocks", type=int, default=6)
    kstab.add_argument("--gate-max-family-p", type=float, default=0.05)
    kstab.add_argument("--write-selected-blend-dir", default="")
    kstab.add_argument("--clean", action="store_true")

    kguard = sub.add_parser("kline-guard-audit", help="Apply fixed K-line probability blend, v12 OFI slot-veto, then a slot-preserving K-line support guard.")
    kguard.add_argument("--base-ensemble-dir", required=True)
    kguard.add_argument("--kline-ensemble-dir", required=True)
    kguard.add_argument("--out", required=True)
    kguard.add_argument("--horizon-sec", type=float, required=True)
    kguard.add_argument("--cost-bps", type=float, default=1.5)
    kguard.add_argument("--latency-sec", type=float, default=0.5)
    kguard.add_argument("--edge-threshold", type=float, default=0.1)
    kguard.add_argument("--kline-alpha", type=float, default=0.125)
    kguard.add_argument("--ofi-col", default="ofi_sum_l5_norm")
    kguard.add_argument("--ofi-quantile", type=float, default=0.9)
    kguard.add_argument("--kline-col", default="kline_15s_rv_6_bps")
    kguard.add_argument("--kline-quantile", type=float, default=0.0)
    kguard.add_argument("--kline-operator", choices=[">=", "<="], default=">=")
    kguard.add_argument("--directional", action="store_true", default=True)
    kguard.add_argument("--non-directional", dest="directional", action="store_false")
    kguard.add_argument("--family-kline-cols", default="kline_15s_rv_6_bps,kline_15s_rv_12_bps,kline_1m_rv_3_bps,kline_1m_range_z_6,kline_1s_rv_1_bps,kline_15m_ret_3_bps,kline_15s_signal")
    kguard.add_argument("--family-kline-quantiles", default="0.0,0.05,0.10,0.20,0.30")
    kguard.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    kguard.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    kguard.add_argument("--shift-null-runs", type=int, default=80)
    kguard.add_argument("--family-shift-runs", type=int, default=80)
    kguard.add_argument("--gate-min-oof-trades", type=int, default=20)
    kguard.add_argument("--gate-min-periods-with-trades", type=int, default=5)
    kguard.add_argument("--gate-min-period-mean-net-bps", type=float, default=0.0)
    kguard.add_argument("--gate-max-family-null-p-total", type=float, default=0.05)
    kguard.add_argument("--gate-max-family-null-p-mean", type=float, default=0.10)
    kguard.add_argument("--clean", action="store_true")

    psf = sub.add_parser("profit-success-fast", help="V15 fast triple-family profit success audit: alpha + OFI + K-line guard families.")
    psf.add_argument("--base-ensemble-dir", required=True)
    psf.add_argument("--kline-ensemble-dir", required=True)
    psf.add_argument("--out", required=True)
    psf.add_argument("--horizon-sec", type=float, default=90.0)
    psf.add_argument("--cost-bps", type=float, default=1.5)
    psf.add_argument("--latency-sec", type=float, default=0.5)
    psf.add_argument("--edge-threshold", type=float, default=0.1)
    psf.add_argument("--kline-alpha", type=float, default=0.125)
    psf.add_argument("--ofi-col", default="ofi_sum_l5_norm")
    psf.add_argument("--ofi-quantile", type=float, default=0.9)
    psf.add_argument("--kline-col", default="kline_15s_rv_6_bps")
    psf.add_argument("--kline-quantile", type=float, default=0.0)
    psf.add_argument("--kline-operator", choices=[">=", "<="], default=">=")
    psf.add_argument("--directional", action="store_true", default=True)
    psf.add_argument("--non-directional", dest="directional", action="store_false")
    psf.add_argument("--alpha-grid", default="0,0.025,0.05,0.075,0.1,0.125,0.15")
    psf.add_argument("--ofi-cols", default="ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm")
    psf.add_argument("--ofi-quantiles", default="0.5,0.6,0.7,0.8,0.9")
    psf.add_argument("--kline-cols", default="kline_15s_rv_6_bps,kline_15s_rv_12_bps,kline_1m_rv_3_bps,kline_1m_range_z_6,kline_1s_rv_1_bps,kline_15m_ret_3_bps,kline_15s_signal")
    psf.add_argument("--kline-quantiles", default="0.0")
    psf.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    psf.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    psf.add_argument("--shift-null-runs", type=int, default=40)
    psf.add_argument("--gate-min-oof-trades", type=int, default=20)
    psf.add_argument("--gate-min-folds-with-trades", type=int, default=5)
    psf.add_argument("--gate-min-fold-mean-net-bps", type=float, default=0.0)
    psf.add_argument("--gate-min-fold-total-net-bps", type=float, default=0.0)
    psf.add_argument("--gate-min-bootstrap-mean-p05-bps", type=float, default=0.0)
    psf.add_argument("--gate-max-family-p", type=float, default=0.05)
    psf.add_argument("--clean", action="store_true")

    plock = sub.add_parser("profit-lock-certificate", help="V16 frozen-policy profit-lock certificate with sparse 1000-shift family nulls and extended stress.")
    plock.add_argument("--base-ensemble-dir", required=True)
    plock.add_argument("--kline-ensemble-dir", required=True)
    plock.add_argument("--out", required=True)
    plock.add_argument("--horizon-sec", type=float, default=90.0)
    plock.add_argument("--cost-bps", type=float, default=1.5)
    plock.add_argument("--latency-sec", type=float, default=0.5)
    plock.add_argument("--edge-threshold", type=float, default=0.1)
    plock.add_argument("--kline-alpha", type=float, default=0.125)
    plock.add_argument("--ofi-col", default="ofi_sum_l5_norm")
    plock.add_argument("--ofi-quantile", type=float, default=0.9)
    plock.add_argument("--kline-col", default="kline_15s_rv_6_bps")
    plock.add_argument("--kline-quantile", type=float, default=0.0)
    plock.add_argument("--kline-operator", choices=[">=", "<="], default=">=")
    plock.add_argument("--directional", action="store_true", default=True)
    plock.add_argument("--non-directional", dest="directional", action="store_false")
    plock.add_argument("--alpha-grid", default="0,0.025,0.05,0.075,0.1,0.125,0.15")
    plock.add_argument("--ofi-cols", default="ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm")
    plock.add_argument("--ofi-quantiles", default="0.5,0.6,0.7,0.8,0.9")
    plock.add_argument("--kline-cols", default="kline_15s_rv_6_bps,kline_15s_rv_12_bps,kline_1m_rv_3_bps,kline_1m_range_z_6,kline_1s_rv_1_bps,kline_15m_ret_3_bps,kline_15s_signal")
    plock.add_argument("--kline-quantiles", default="0.0")
    plock.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0,7.5,10.0")
    plock.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0,3.0,5.0")
    plock.add_argument("--shift-null-runs", type=int, default=1000)
    plock.add_argument("--gate-min-oof-trades", type=int, default=20)
    plock.add_argument("--gate-min-folds-with-trades", type=int, default=5)
    plock.add_argument("--gate-min-fold-mean-net-bps", type=float, default=0.0)
    plock.add_argument("--gate-min-fold-total-net-bps", type=float, default=0.0)
    plock.add_argument("--gate-min-bootstrap-mean-p05-bps", type=float, default=0.0)
    plock.add_argument("--gate-max-addone-family-p", type=float, default=0.01)
    plock.add_argument("--gate-min-top-winner-removal-k", type=int, default=5)
    plock.add_argument("--gate-min-top-winner-removed-total-bps", type=float, default=0.0)
    plock.add_argument("--gate-max-primary-stress-cost-bps", type=float, default=7.5)
    plock.add_argument("--gate-max-primary-stress-latency-sec", type=float, default=5.0)
    plock.add_argument("--gate-max-secondary-stress-cost-bps", type=float, default=10.0)
    plock.add_argument("--gate-max-secondary-stress-latency-sec", type=float, default=3.0)
    plock.add_argument("--gate-min-stress-mean-net-bps", type=float, default=0.0)
    plock.add_argument("--clean", action="store_true")



    eplock = sub.add_parser("execution-profit-lock-certificate", help="V17 frozen entry plus slot-preserving take-profit exit-lock certificate with 1000-shift add-one family nulls and full severe stress.")
    eplock.add_argument("--base-ensemble-dir", required=True)
    eplock.add_argument("--kline-ensemble-dir", required=True)
    eplock.add_argument("--out", required=True)
    eplock.add_argument("--horizon-sec", type=float, default=90.0)
    eplock.add_argument("--cost-bps", type=float, default=1.5)
    eplock.add_argument("--latency-sec", type=float, default=0.5)
    eplock.add_argument("--edge-threshold", type=float, default=0.1)
    eplock.add_argument("--kline-alpha", type=float, default=0.125)
    eplock.add_argument("--ofi-col", default="ofi_sum_l5_norm")
    eplock.add_argument("--ofi-quantile", type=float, default=0.9)
    eplock.add_argument("--kline-col", default="kline_15s_rv_6_bps")
    eplock.add_argument("--kline-quantile", type=float, default=0.0)
    eplock.add_argument("--kline-operator", choices=[">=", "<="], default=">=")
    eplock.add_argument("--directional", action="store_true", default=True)
    eplock.add_argument("--non-directional", dest="directional", action="store_false")
    eplock.add_argument("--take-profit-bps", type=float, default=40.0)
    eplock.add_argument("--stop-loss-bps", type=float, default=0.0)
    eplock.add_argument("--exit-take-profit-bps-values", default="0,20,30,40,60,90")
    eplock.add_argument("--exit-stop-loss-bps-values", default="0")
    eplock.add_argument("--alpha-grid", default="0,0.025,0.05,0.075,0.1,0.125,0.15")
    eplock.add_argument("--ofi-cols", default="ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm")
    eplock.add_argument("--ofi-quantiles", default="0.5,0.6,0.7,0.8,0.9")
    eplock.add_argument("--kline-cols", default="kline_15s_rv_6_bps,kline_15s_rv_12_bps,kline_1m_rv_3_bps,kline_1m_range_z_6,kline_1s_rv_1_bps,kline_15m_ret_3_bps,kline_15s_signal")
    eplock.add_argument("--kline-quantiles", default="0.0")
    eplock.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0,7.5,10.0")
    eplock.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0,3.0,5.0")
    eplock.add_argument("--shift-null-runs", type=int, default=1000)
    eplock.add_argument("--gate-min-oof-trades", type=int, default=20)
    eplock.add_argument("--gate-min-folds-with-trades", type=int, default=5)
    eplock.add_argument("--gate-min-fold-mean-net-bps", type=float, default=0.0)
    eplock.add_argument("--gate-min-fold-total-net-bps", type=float, default=0.0)
    eplock.add_argument("--gate-min-bootstrap-mean-p05-bps", type=float, default=0.0)
    eplock.add_argument("--gate-max-addone-family-p", type=float, default=0.01)
    eplock.add_argument("--gate-min-top-winner-removal-k", type=int, default=5)
    eplock.add_argument("--gate-min-top-winner-removed-total-bps", type=float, default=0.0)
    eplock.add_argument("--gate-min-full-stress-mean-net-bps", type=float, default=0.0)
    eplock.add_argument("--gate-min-full-stress-total-net-bps", type=float, default=0.0)
    eplock.add_argument("--clean", action="store_true")

    dlock = sub.add_parser("deployment-lock-certificate", help="V18 frozen V17 deployment-readiness certificate: missed trades, extra fees, clock-time blocks, and combined failure stress.")
    dlock.add_argument("--v17-run-dir", required=True)
    dlock.add_argument("--out", required=True)
    dlock.add_argument("--horizon-sec", type=float, default=90.0)
    dlock.add_argument("--miss-probabilities", default="0.05,0.10,0.20,0.30,0.40,0.50")
    dlock.add_argument("--extra-cost-bps-values", default="0,1,2,3,5,7.5,10")
    dlock.add_argument("--combined-miss-probabilities", default="0.10,0.20,0.30,0.40,0.50")
    dlock.add_argument("--combined-extra-cost-bps-values", default="1,2,3,5")
    dlock.add_argument("--clock-block-counts", default="3,4,5,6,8,10,12")
    dlock.add_argument("--random-scenarios", type=int, default=10000)
    dlock.add_argument("--seed", type=int, default=18018)
    dlock.add_argument("--gate-min-trades", type=int, default=20)
    dlock.add_argument("--gate-min-clock-block-count", type=int, default=10)
    dlock.add_argument("--gate-miss-trade-probability", type=float, default=0.50)
    dlock.add_argument("--gate-combined-miss-probability", type=float, default=0.50)
    dlock.add_argument("--gate-combined-extra-cost-bps", type=float, default=3.0)
    dlock.add_argument("--gate-extra-cost-bps", type=float, default=10.0)
    dlock.add_argument("--clean", action="store_true")

    rflock = sub.add_parser("real-fee-lock-certificate", help="V19 fee-aware certificate using user real fees: 0.0400%% taker and 0.0000%% maker, plus a frozen high-fee guard.")
    rflock.add_argument("--v17-run-dir", required=True)
    rflock.add_argument("--out", required=True)
    rflock.add_argument("--taker-fee-percent", type=float, default=0.0400)
    rflock.add_argument("--maker-fee-percent", type=float, default=0.0000)
    rflock.add_argument("--horizon-sec", type=float, default=90.0)
    rflock.add_argument("--latency-sec", type=float, default=0.5)
    rflock.add_argument("--take-profit-bps", type=float, default=40.0)
    rflock.add_argument("--stop-loss-bps", type=float, default=0.0)
    rflock.add_argument("--candidate-quantiles", default="0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9")
    rflock.add_argument("--max-filter-count", type=int, default=2)
    rflock.add_argument("--shift-null-runs", type=int, default=1000)
    rflock.add_argument("--stress-fee-side-bps-values", default="4,5,6,7.5,10")
    rflock.add_argument("--stress-latency-sec-values", default="0,0.5,1,2,3,5")
    rflock.add_argument("--random-scenarios", type=int, default=10000)
    rflock.add_argument("--seed", type=int, default=19019)
    rflock.add_argument("--gate-min-trades", type=int, default=10)
    rflock.add_argument("--gate-min-hit-rate", type=float, default=0.75)
    rflock.add_argument("--gate-min-mean-net-bps", type=float, default=8.0)
    rflock.add_argument("--gate-min-total-net-bps", type=float, default=100.0)
    rflock.add_argument("--gate-max-family-addone-p", type=float, default=0.01)
    rflock.add_argument("--gate-max-stress-fee-side-bps", type=float, default=7.5)
    rflock.add_argument("--gate-max-stress-latency-sec", type=float, default=5.0)
    rflock.add_argument("--gate-missed-trade-probability", type=float, default=0.50)
    rflock.add_argument("--gate-extra-cost-bps", type=float, default=10.0)
    rflock.add_argument("--clean", action="store_true")

    btcplan = sub.add_parser("btc-contract-data-plan", help="Write a BTCUSDT perpetual contract data-source manifest for Binance Vision and REST tasks.")
    btcplan.add_argument("--out", required=True)
    btcplan.add_argument("--start-date", default="2024-01-01")
    btcplan.add_argument("--end-date", default="2026-06-10")
    btcplan.add_argument("--symbol", default="BTCUSDT")

    dlmanifest = sub.add_parser("download-contract-manifest", help="Download URLs from a contract data manifest. Intended for local use outside the sandbox.")
    dlmanifest.add_argument("--manifest", required=True)
    dlmanifest.add_argument("--out", required=True)
    dlmanifest.add_argument("--max-files", type=int, default=0)

    btclock = sub.add_parser("btc-contract-leverage-lock", help="V20 BTC contract leverage lock: V19 real-fee rule plus BTC side guard and leverage scenarios.")
    btclock.add_argument("--v17-run-dir", required=True)
    btclock.add_argument("--v19-run-dir", default="")
    btclock.add_argument("--out", required=True)
    btclock.add_argument("--taker-fee-percent", type=float, default=0.0400)
    btclock.add_argument("--maker-fee-percent", type=float, default=0.0000)
    btclock.add_argument("--horizon-sec", type=float, default=90.0)
    btclock.add_argument("--latency-sec", type=float, default=0.5)
    btclock.add_argument("--take-profit-bps", type=float, default=40.0)
    btclock.add_argument("--stop-loss-bps", type=float, default=0.0)
    btclock.add_argument("--stress-fee-side-bps-values", default="4,5,6,7.5,10")
    btclock.add_argument("--stress-latency-sec-values", default="0,0.5,1,2,3,5")
    btclock.add_argument("--leverage-values", default="1,2,3,5,10,20")
    btclock.add_argument("--shift-null-runs", type=int, default=1000)
    btclock.add_argument("--random-scenarios", type=int, default=10000)
    btclock.add_argument("--seed", type=int, default=20020)
    btclock.add_argument("--gate-min-trades", type=int, default=10)
    btclock.add_argument("--gate-min-hit-rate", type=float, default=0.95)
    btclock.add_argument("--gate-min-total-net-bps", type=float, default=120.0)
    btclock.add_argument("--gate-max-side-guard-p", type=float, default=0.01)
    btclock.add_argument("--gate-max-stress-fee-side-bps", type=float, default=7.5)
    btclock.add_argument("--gate-max-stress-latency-sec", type=float, default=5.0)
    btclock.add_argument("--gate-missed-trade-probability", type=float, default=0.50)
    btclock.add_argument("--gate-extra-cost-bps", type=float, default=10.0)
    btclock.add_argument("--promoted-leverage-cap", type=float, default=3.0)
    btclock.add_argument("--shock-buffer-bps", type=float, default=250.0)
    btclock.add_argument("--maintenance-margin-bps", type=float, default=50.0)
    btclock.add_argument("--no-data-plan", action="store_true")
    btclock.add_argument("--clean", action="store_true")

    btctarget = sub.add_parser("btc-profit-target-lock", help="V21 BTC profit target lock: V20 BTC entry rule with audited 45 bps take-profit target.")
    btctarget.add_argument("--v17-run-dir", required=True)
    btctarget.add_argument("--out", required=True)
    btctarget.add_argument("--taker-fee-percent", type=float, default=0.0400)
    btctarget.add_argument("--maker-fee-percent", type=float, default=0.0000)
    btctarget.add_argument("--horizon-sec", type=float, default=90.0)
    btctarget.add_argument("--latency-sec", type=float, default=0.5)
    btctarget.add_argument("--take-profit-bps", type=float, default=45.0)
    btctarget.add_argument("--stop-loss-bps", type=float, default=0.0)
    btctarget.add_argument("--exit-take-profit-candidates", default="0,10,15,20,25,30,35,40,45,50,55,60")
    btctarget.add_argument("--stress-fee-side-bps-values", default="4,5,6,7.5,10")
    btctarget.add_argument("--stress-latency-sec-values", default="0,0.5,1,2,3,5")
    btctarget.add_argument("--leverage-values", default="1,2,3,5,10,20")
    btctarget.add_argument("--shift-null-runs", type=int, default=1000)
    btctarget.add_argument("--random-scenarios", type=int, default=10000)
    btctarget.add_argument("--seed", type=int, default=21021)
    btctarget.add_argument("--gate-min-trades", type=int, default=10)
    btctarget.add_argument("--gate-min-hit-rate", type=float, default=1.0)
    btctarget.add_argument("--gate-min-total-net-bps", type=float, default=130.0)
    btctarget.add_argument("--gate-min-mean-net-bps", type=float, default=13.0)
    btctarget.add_argument("--gate-max-family-addone-p", type=float, default=0.01)
    btctarget.add_argument("--gate-max-stress-fee-side-bps", type=float, default=10.0)
    btctarget.add_argument("--gate-max-stress-latency-sec", type=float, default=5.0)
    btctarget.add_argument("--gate-missed-trade-probability", type=float, default=0.50)
    btctarget.add_argument("--gate-extra-cost-bps", type=float, default=12.0)
    btctarget.add_argument("--promoted-leverage-cap", type=float, default=3.0)
    btctarget.add_argument("--shock-buffer-bps", type=float, default=250.0)
    btctarget.add_argument("--maintenance-margin-bps", type=float, default=50.0)
    btctarget.add_argument("--allow-negative-stress-cells", action="store_true")
    btctarget.add_argument("--no-data-plan", action="store_true")
    btctarget.add_argument("--clean", action="store_true")


    btcrescue = sub.add_parser("btc-rescue-profit-lock", help="V22 BTC rescue profit lock: V20/V21 BTC rule plus slot-preserving long rescue lane and 52 bps take-profit target.")
    btcrescue.add_argument("--v17-run-dir", required=True)
    btcrescue.add_argument("--out", required=True)
    btcrescue.add_argument("--taker-fee-percent", type=float, default=0.0400)
    btcrescue.add_argument("--maker-fee-percent", type=float, default=0.0000)
    btcrescue.add_argument("--horizon-sec", type=float, default=90.0)
    btcrescue.add_argument("--latency-sec", type=float, default=0.5)
    btcrescue.add_argument("--take-profit-bps", type=float, default=52.0)
    btcrescue.add_argument("--stop-loss-bps", type=float, default=0.0)
    btcrescue.add_argument("--exit-take-profit-candidates", default="0,10,15,20,25,30,35,40,45,50,52,55,60")
    btcrescue.add_argument("--stress-fee-side-bps-values", default="4,5,6,7.5,10")
    btcrescue.add_argument("--stress-latency-sec-values", default="0,0.5,1,2,3,5")
    btcrescue.add_argument("--leverage-values", default="1,2,3,5,10,20")
    btcrescue.add_argument("--shift-null-runs", type=int, default=1000)
    btcrescue.add_argument("--random-scenarios", type=int, default=10000)
    btcrescue.add_argument("--seed", type=int, default=22022)
    btcrescue.add_argument("--gate-min-trades", type=int, default=11)
    btcrescue.add_argument("--gate-min-hit-rate", type=float, default=1.0)
    btcrescue.add_argument("--gate-min-total-net-bps", type=float, default=180.0)
    btcrescue.add_argument("--gate-min-mean-net-bps", type=float, default=16.0)
    btcrescue.add_argument("--gate-max-family-addone-p", type=float, default=0.01)
    btcrescue.add_argument("--gate-max-stress-fee-side-bps", type=float, default=10.0)
    btcrescue.add_argument("--gate-max-stress-latency-sec", type=float, default=5.0)
    btcrescue.add_argument("--gate-missed-trade-probability", type=float, default=0.50)
    btcrescue.add_argument("--gate-extra-cost-bps", type=float, default=16.0)
    btcrescue.add_argument("--promoted-leverage-cap", type=float, default=3.0)
    btcrescue.add_argument("--shock-buffer-bps", type=float, default=250.0)
    btcrescue.add_argument("--maintenance-margin-bps", type=float, default=50.0)
    btcrescue.add_argument("--allow-negative-stress-cells", action="store_true")
    btcrescue.add_argument("--no-data-plan", action="store_true")
    btcrescue.add_argument("--clean", action="store_true")

    btcadaptive = sub.add_parser("btc-adaptive-exit-lock", help="V24 BTC adaptive exit lock: V22 BTC entries plus slot-preserving asymmetric take-profit ladder.")
    btcadaptive.add_argument("--v17-run-dir", required=True)
    btcadaptive.add_argument("--out", required=True)
    btcadaptive.add_argument("--taker-fee-percent", type=float, default=0.0400)
    btcadaptive.add_argument("--maker-fee-percent", type=float, default=0.0000)
    btcadaptive.add_argument("--horizon-sec", type=float, default=90.0)
    btcadaptive.add_argument("--latency-sec", type=float, default=0.5)
    btcadaptive.add_argument("--stress-fee-side-bps-values", default="4,5,6,7.5,10")
    btcadaptive.add_argument("--stress-latency-sec-values", default="0,0.5,1,2,3,5")
    btcadaptive.add_argument("--leverage-values", default="1,2,3,5,10,20")
    btcadaptive.add_argument("--shift-null-runs", type=int, default=1000)
    btcadaptive.add_argument("--random-scenarios", type=int, default=10000)
    btcadaptive.add_argument("--seed", type=int, default=23023)
    btcadaptive.add_argument("--gate-min-trades", type=int, default=11)
    btcadaptive.add_argument("--gate-min-hit-rate", type=float, default=1.0)
    btcadaptive.add_argument("--gate-min-total-net-bps", type=float, default=185.0)
    btcadaptive.add_argument("--gate-min-mean-net-bps", type=float, default=17.0)
    btcadaptive.add_argument("--gate-max-family-addone-p", type=float, default=0.01)
    btcadaptive.add_argument("--gate-max-stress-fee-side-bps", type=float, default=10.0)
    btcadaptive.add_argument("--gate-max-stress-latency-sec", type=float, default=5.0)
    btcadaptive.add_argument("--gate-missed-trade-probability", type=float, default=0.50)
    btcadaptive.add_argument("--gate-extra-cost-bps", type=float, default=16.0)
    btcadaptive.add_argument("--promoted-leverage-cap", type=float, default=3.0)
    btcadaptive.add_argument("--shock-buffer-bps", type=float, default=250.0)
    btcadaptive.add_argument("--maintenance-margin-bps", type=float, default=50.0)
    btcadaptive.add_argument("--allow-negative-stress-cells", action="store_true")
    btcadaptive.add_argument("--no-data-plan", action="store_true")
    btcadaptive.add_argument("--clean", action="store_true")

    sv = sub.add_parser("slot-veto-audit", help="Audit a conservative slot-preserving OFI veto on an ensemble walk-forward run.")
    sv.add_argument("--ensemble-dir", required=True)
    sv.add_argument("--out", required=True)
    sv.add_argument("--horizon-sec", type=float, required=True)
    sv.add_argument("--cost-bps", type=float, default=1.5)
    sv.add_argument("--latency-sec", type=float, default=0.5)
    sv.add_argument("--edge-threshold", type=float, default=0.1)
    sv.add_argument("--filter-col", default="ofi_sum_l5_norm")
    sv.add_argument("--filter-operator", choices=["<=", ">="], default="<=")
    sv.add_argument("--filter-quantile", type=float, default=0.9)
    sv.add_argument("--family-filter-cols", default="ofi_sum_l3_norm,ofi_sum_l5_norm,ofi_sum_l10_norm")
    sv.add_argument("--family-quantiles", default="0.5,0.6,0.7,0.8,0.9")
    sv.add_argument("--stress-cost-bps-values", default="1.5,3.0,5.0")
    sv.add_argument("--stress-latency-sec-values", default="0,0.5,1.0,2.0")
    sv.add_argument("--shift-null-runs", type=int, default=80)
    sv.add_argument("--family-shift-runs", type=int, default=80)
    sv.add_argument("--gate-min-oof-trades", type=int, default=20)
    sv.add_argument("--gate-min-periods-with-trades", type=int, default=5)
    sv.add_argument("--gate-min-period-mean-net-bps", type=float, default=0.0)
    sv.add_argument("--gate-max-family-null-p-total", type=float, default=0.05)
    sv.add_argument("--gate-max-family-null-p-mean", type=float, default=0.10)
    sv.add_argument("--clean", action="store_true")

    paper = sub.add_parser("paper-trade-v142", help="Run V142 paper trading with live-updating logs and balance dashboard.")
    paper.add_argument("--out", required=True)
    paper.add_argument("--symbol", default="BTCUSDC")
    paper.add_argument("--source", choices=["synthetic", "csv", "binance-public"], default="binance-public")
    paper.add_argument("--market", choices=["spot", "um-futures"], default="spot")
    paper.add_argument("--price-csv", default=None)
    paper.add_argument("--signal-csv", default=None)
    paper.add_argument("--ticks", type=int, default=0, help="Number of price updates to process. Use 0 for continuous mode.")
    paper.add_argument("--interval-sec", type=float, default=60.0)
    paper.add_argument("--initial-balance-usdc", type=float, default=10_000.0)
    paper.add_argument("--fee-bps-per-side", type=float, default=4.0)
    paper.add_argument("--clean", action="store_true")
    paper.add_argument("--no-sleep", action="store_true")

    replay = sub.add_parser("trade-replay-v142", help="Build an interactive V142 historical trading replay page.")
    replay.add_argument(
        "--account-path",
        default="runs/research_v142_high_confidence_rescue_5x/v142_selected_account_path.csv",
    )
    replay.add_argument("--out", required=True)
    replay.add_argument("--start", default="2024-07-01")
    replay.add_argument("--end", default="2026-06-12")
    replay.add_argument("--initial-balance-usdc", type=float, default=10_000.0)
    replay.add_argument("--title", default="BTCUSDC V142 Trading Replay")
    replay.add_argument(
        "--signal-reference",
        default=None,
        help="CSV with timestamp and signal columns used to fill missing historical side values.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)


    if args.command == "trade-replay-v142":
        result = write_trade_replay_page(
            account_path=args.account_path,
            out=args.out,
            start=args.start,
            end=args.end,
            initial_balance_usdc=args.initial_balance_usdc,
            title=args.title,
            signal_reference=args.signal_reference,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "paper-trade-v142":
        config = PaperTradingConfig(
            symbol=args.symbol.upper(),
            initial_balance_usdc=args.initial_balance_usdc,
            fee_bps_per_side=args.fee_bps_per_side,
        )
        if args.source == "csv":
            if not args.price_csv:
                parser.error("--price-csv is required when --source csv")
            market_source = CsvPriceSource(args.price_csv, symbol=args.symbol)
        elif args.source == "synthetic":
            market_source = SyntheticPriceSource(symbol=args.symbol, interval_sec=args.interval_sec)
        else:
            market_source = BinancePublicTickerSource(symbol=args.symbol, market=args.market)
        signal_provider = (
            CsvSignalProvider(args.signal_csv, default_symbol=args.symbol, default_horizon_minutes=config.default_horizon_minutes)
            if args.signal_csv
            else NoSignalProvider()
        )
        result = run_v142_paper_trading(
            out_dir=args.out,
            market_source=market_source,
            signal_provider=signal_provider,
            config=config,
            ticks=args.ticks,
            interval_sec=args.interval_sec,
            clean=args.clean,
            sleep=not args.no_sleep,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "build-kline-cache":
        book = read_csv(args.book)
        events = read_csv(args.events) if getattr(args, "events", "").strip() else book[["timestamp"]].copy()
        result = write_kline_cache(
            events=events,
            out_path=args.out,
            book=book,
            candle_paths_by_timeframe=parse_candle_path_specs(args.candle),
            timeframes=parse_str_list(args.timeframes),
            timestamp_col="timestamp",
            decision_lag_sec=args.decision_lag_sec,
            lookbacks=[int(x) for x in parse_float_list(args.lookbacks)],
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "kline-blend-ensemble":
        result = run_kline_blend_ensemble(
            base_ensemble_dir=args.base_ensemble_dir,
            kline_ensemble_dir=args.kline_ensemble_dir,
            out_dir=args.out,
            kline_alpha=args.kline_alpha,
            keep_kline_feature_columns=not args.drop_kline_feature_columns,
            clean=args.clean,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "kline-weight-audit":
        result = run_kline_weight_audit(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            base_weight_values=parse_float_list(args.base_weight_values),
            kline_signs=[int(x) for x in parse_float_list(args.kline_signs)],
            min_calibration_trades=args.min_calibration_trades,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            gate_config=KlineWeightGateConfig(
                min_oof_trades=args.gate_min_oof_trades,
                min_folds_with_trades=args.gate_min_folds_with_trades,
                min_fold_mean_net_bps=args.gate_min_fold_mean_net_bps,
                max_shift_null_p_total=args.gate_max_shift_null_p_total,
                max_shift_null_p_mean=args.gate_max_shift_null_p_mean,
            ),
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0


    if args.command == "kline-stability-lock-audit":
        result = run_kline_stability_lock_audit(
            base_ensemble_dir=args.base_ensemble_dir,
            kline_ensemble_dir=args.kline_ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            selected_alpha=args.selected_alpha,
            alpha_grid=parse_float_list(args.alpha_grid),
            selected_spec=SlotVetoSpec(
                edge_threshold=args.edge_threshold,
                filter_col=args.filter_col,
                filter_operator=args.filter_operator,
                filter_quantile=args.filter_quantile,
            ),
            family_filter_cols=parse_str_list(args.family_filter_cols),
            family_quantiles=parse_float_list(args.family_quantiles),
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            gate_config=KlineStabilityGateConfig(
                min_oof_trades=args.gate_min_oof_trades,
                min_folds_with_trades=args.gate_min_folds_with_trades,
                min_equal_trade_blocks=args.gate_min_equal_trade_blocks,
                max_selected_shift_p_total=args.gate_max_family_p,
                max_selected_shift_p_mean=args.gate_max_family_p,
                max_alpha_family_p_total=args.gate_max_family_p,
                max_alpha_family_p_mean=args.gate_max_family_p,
                max_ofi_family_p_total=args.gate_max_family_p,
                max_ofi_family_p_mean=args.gate_max_family_p,
                max_union_family_p_total=args.gate_max_family_p,
                max_union_family_p_mean=args.gate_max_family_p,
            ),
            write_selected_blend_dir=args.write_selected_blend_dir.strip() or None,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0


    if args.command == "kline-guard-audit":
        result = run_kline_guard_audit(
            base_ensemble_dir=args.base_ensemble_dir,
            kline_ensemble_dir=args.kline_ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            spec=KlineGuardSpec(
                edge_threshold=args.edge_threshold,
                kline_alpha=args.kline_alpha,
                ofi_col=args.ofi_col,
                ofi_quantile=args.ofi_quantile,
                kline_col=args.kline_col,
                kline_quantile=args.kline_quantile,
                kline_operator=args.kline_operator,
                directional=args.directional,
            ),
            family_kline_cols=parse_str_list(args.family_kline_cols),
            family_kline_quantiles=parse_float_list(args.family_kline_quantiles),
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            family_shift_runs=args.family_shift_runs,
            gate_config=KlineGuardGateConfig(
                min_oof_trades=args.gate_min_oof_trades,
                min_periods_with_trades=args.gate_min_periods_with_trades,
                min_period_mean_net_bps=args.gate_min_period_mean_net_bps,
                max_family_null_p_total=args.gate_max_family_null_p_total,
                max_family_null_p_mean=args.gate_max_family_null_p_mean,
            ),
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0



    if args.command == "profit-success-fast":
        result = run_profit_success_fast(
            base_ensemble_dir=args.base_ensemble_dir,
            kline_ensemble_dir=args.kline_ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            selected_spec=KlineGuardSpec(
                edge_threshold=args.edge_threshold,
                kline_alpha=args.kline_alpha,
                ofi_col=args.ofi_col,
                ofi_quantile=args.ofi_quantile,
                kline_col=args.kline_col,
                kline_quantile=args.kline_quantile,
                kline_operator=args.kline_operator,
                directional=args.directional,
            ),
            alpha_grid=parse_float_list(args.alpha_grid),
            ofi_cols=parse_str_list(args.ofi_cols),
            ofi_quantiles=parse_float_list(args.ofi_quantiles),
            kline_cols=parse_str_list(args.kline_cols),
            kline_quantiles=parse_float_list(args.kline_quantiles),
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            gate=ProfitSuccessFastGate(
                min_oof_trades=args.gate_min_oof_trades,
                min_folds_with_trades=args.gate_min_folds_with_trades,
                min_fold_mean_net_bps=args.gate_min_fold_mean_net_bps,
                min_fold_total_net_bps=args.gate_min_fold_total_net_bps,
                min_bootstrap_mean_p05_bps=args.gate_min_bootstrap_mean_p05_bps,
                max_family_p=args.gate_max_family_p,
            ),
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0





    if args.command == "btc-contract-data-plan":
        result = write_btc_contract_data_plan(out_dir=args.out, start_date=args.start_date, end_date=args.end_date, symbol=args.symbol)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "download-contract-manifest":
        result = download_manifest_files(args.manifest, args.out, max_files=args.max_files)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "btc-contract-leverage-lock":
        result = run_btc_contract_leverage_lock(
            v17_run_dir=args.v17_run_dir,
            v19_run_dir=args.v19_run_dir or None,
            out_dir=args.out,
            fee_spec=RealFeeSpec(taker_fee_percent=args.taker_fee_percent, maker_fee_percent=args.maker_fee_percent),
            horizon_sec=args.horizon_sec,
            latency_sec=args.latency_sec,
            take_profit_bps=args.take_profit_bps,
            stop_loss_bps=args.stop_loss_bps,
            stress_fee_side_bps_values=parse_float_list(args.stress_fee_side_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            leverage_values=parse_float_list(args.leverage_values),
            shift_null_runs=args.shift_null_runs,
            random_scenarios=args.random_scenarios,
            seed=args.seed,
            gate=BTCLeverageGate(
                min_trades=args.gate_min_trades,
                min_hit_rate=args.gate_min_hit_rate,
                min_total_net_pnl_bps=args.gate_min_total_net_bps,
                max_side_guard_addone_p=args.gate_max_side_guard_p,
                max_stress_fee_side_bps=args.gate_max_stress_fee_side_bps,
                max_stress_latency_sec=args.gate_max_stress_latency_sec,
                missed_trade_gate_probability=args.gate_missed_trade_probability,
                extra_cost_gate_bps=args.gate_extra_cost_bps,
                promoted_leverage_cap=args.promoted_leverage_cap,
                shock_buffer_bps=args.shock_buffer_bps,
                maintenance_margin_bps=args.maintenance_margin_bps,
            ),
            write_data_plan=not args.no_data_plan,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "btc-profit-target-lock":
        result = run_btc_profit_target_lock(
            v17_run_dir=args.v17_run_dir,
            out_dir=args.out,
            fee_spec=RealFeeSpec(taker_fee_percent=args.taker_fee_percent, maker_fee_percent=args.maker_fee_percent),
            horizon_sec=args.horizon_sec,
            latency_sec=args.latency_sec,
            take_profit_bps=args.take_profit_bps,
            stop_loss_bps=args.stop_loss_bps,
            exit_take_profit_candidates=parse_float_list(args.exit_take_profit_candidates),
            stress_fee_side_bps_values=parse_float_list(args.stress_fee_side_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            leverage_values=parse_float_list(args.leverage_values),
            shift_null_runs=args.shift_null_runs,
            random_scenarios=args.random_scenarios,
            seed=args.seed,
            gate=BTCProfitTargetGate(
                min_trades=args.gate_min_trades,
                min_hit_rate=args.gate_min_hit_rate,
                min_total_net_pnl_bps=args.gate_min_total_net_bps,
                min_mean_net_pnl_bps=args.gate_min_mean_net_bps,
                max_side_exit_family_addone_p=args.gate_max_family_addone_p,
                require_all_stress_cells_positive=not args.allow_negative_stress_cells,
                max_stress_fee_side_bps=args.gate_max_stress_fee_side_bps,
                max_stress_latency_sec=args.gate_max_stress_latency_sec,
                missed_trade_gate_probability=args.gate_missed_trade_probability,
                extra_cost_gate_bps=args.gate_extra_cost_bps,
                promoted_leverage_cap=args.promoted_leverage_cap,
                shock_buffer_bps=args.shock_buffer_bps,
                maintenance_margin_bps=args.maintenance_margin_bps,
            ),
            write_data_plan=not args.no_data_plan,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0


    if args.command == "btc-rescue-profit-lock":
        result = run_btc_rescue_profit_lock(
            v17_run_dir=args.v17_run_dir,
            out_dir=args.out,
            fee_spec=RealFeeSpec(taker_fee_percent=args.taker_fee_percent, maker_fee_percent=args.maker_fee_percent),
            horizon_sec=args.horizon_sec,
            latency_sec=args.latency_sec,
            take_profit_bps=args.take_profit_bps,
            stop_loss_bps=args.stop_loss_bps,
            exit_take_profit_candidates=parse_float_list(args.exit_take_profit_candidates),
            stress_fee_side_bps_values=parse_float_list(args.stress_fee_side_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            leverage_values=parse_float_list(args.leverage_values),
            shift_null_runs=args.shift_null_runs,
            random_scenarios=args.random_scenarios,
            seed=args.seed,
            gate=BTCRescueProfitGate(
                min_trades=args.gate_min_trades,
                min_hit_rate=args.gate_min_hit_rate,
                min_total_net_pnl_bps=args.gate_min_total_net_bps,
                min_mean_net_pnl_bps=args.gate_min_mean_net_bps,
                max_entry_exit_family_addone_p=args.gate_max_family_addone_p,
                require_all_stress_cells_positive=not args.allow_negative_stress_cells,
                max_stress_fee_side_bps=args.gate_max_stress_fee_side_bps,
                max_stress_latency_sec=args.gate_max_stress_latency_sec,
                missed_trade_gate_probability=args.gate_missed_trade_probability,
                extra_cost_gate_bps=args.gate_extra_cost_bps,
                promoted_leverage_cap=args.promoted_leverage_cap,
                shock_buffer_bps=args.shock_buffer_bps,
                maintenance_margin_bps=args.maintenance_margin_bps,
            ),
            write_data_plan=not args.no_data_plan,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "btc-adaptive-exit-lock":
        result = run_btc_adaptive_exit_lock(
            v17_run_dir=args.v17_run_dir,
            out_dir=args.out,
            fee_spec=RealFeeSpec(taker_fee_percent=args.taker_fee_percent, maker_fee_percent=args.maker_fee_percent),
            horizon_sec=args.horizon_sec,
            latency_sec=args.latency_sec,
            stress_fee_side_bps_values=parse_float_list(args.stress_fee_side_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            leverage_values=parse_float_list(args.leverage_values),
            shift_null_runs=args.shift_null_runs,
            random_scenarios=args.random_scenarios,
            seed=args.seed,
            gate=BTCAdaptiveExitGate(
                min_trades=args.gate_min_trades,
                min_hit_rate=args.gate_min_hit_rate,
                min_total_net_pnl_bps=args.gate_min_total_net_bps,
                min_mean_net_pnl_bps=args.gate_min_mean_net_bps,
                max_entry_exit_family_addone_p=args.gate_max_family_addone_p,
                require_all_stress_cells_positive=not args.allow_negative_stress_cells,
                max_stress_fee_side_bps=args.gate_max_stress_fee_side_bps,
                max_stress_latency_sec=args.gate_max_stress_latency_sec,
                missed_trade_gate_probability=args.gate_missed_trade_probability,
                extra_cost_gate_bps=args.gate_extra_cost_bps,
                promoted_leverage_cap=args.promoted_leverage_cap,
                shock_buffer_bps=args.shock_buffer_bps,
                maintenance_margin_bps=args.maintenance_margin_bps,
            ),
            write_data_plan=not args.no_data_plan,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "real-fee-lock-certificate":
        result = run_real_fee_lock_certificate(
            v17_run_dir=args.v17_run_dir,
            out_dir=args.out,
            fee_spec=RealFeeSpec(taker_fee_percent=args.taker_fee_percent, maker_fee_percent=args.maker_fee_percent),
            horizon_sec=args.horizon_sec,
            latency_sec=args.latency_sec,
            take_profit_bps=args.take_profit_bps,
            stop_loss_bps=args.stop_loss_bps,
            candidate_quantiles=parse_float_list(args.candidate_quantiles),
            max_filter_count=args.max_filter_count,
            shift_null_runs=args.shift_null_runs,
            stress_fee_side_bps_values=parse_float_list(args.stress_fee_side_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            random_scenarios=args.random_scenarios,
            seed=args.seed,
            gate=RealFeeLockGate(
                min_trades=args.gate_min_trades,
                min_hit_rate=args.gate_min_hit_rate,
                min_mean_net_pnl_bps=args.gate_min_mean_net_bps,
                min_total_net_pnl_bps=args.gate_min_total_net_bps,
                max_family_addone_p=args.gate_max_family_addone_p,
                max_stress_fee_side_bps=args.gate_max_stress_fee_side_bps,
                max_stress_latency_sec=args.gate_max_stress_latency_sec,
                missed_trade_gate_probability=args.gate_missed_trade_probability,
                extra_cost_gate_bps=args.gate_extra_cost_bps,
            ),
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "deployment-lock-certificate":
        result = run_deployment_lock_certificate(
            v17_run_dir=args.v17_run_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            miss_probabilities=parse_float_list(args.miss_probabilities),
            extra_cost_bps_values=parse_float_list(args.extra_cost_bps_values),
            combined_miss_probabilities=parse_float_list(args.combined_miss_probabilities),
            combined_extra_cost_bps_values=parse_float_list(args.combined_extra_cost_bps_values),
            clock_block_counts=[int(x) for x in parse_float_list(args.clock_block_counts)],
            random_scenarios=args.random_scenarios,
            seed=args.seed,
            gate=DeploymentLockGate(
                min_trades=args.gate_min_trades,
                horizon_sec=args.horizon_sec,
                min_clock_block_count=args.gate_min_clock_block_count,
                miss_trade_gate_probability=args.gate_miss_trade_probability,
                combined_miss_probability=args.gate_combined_miss_probability,
                combined_extra_cost_bps=args.gate_combined_extra_cost_bps,
                extra_cost_gate_bps=args.gate_extra_cost_bps,
            ),
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "execution-profit-lock-certificate":
        result = run_execution_profit_lock_certificate(
            base_ensemble_dir=args.base_ensemble_dir,
            kline_ensemble_dir=args.kline_ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            selected_signal_spec=KlineGuardSpec(
                edge_threshold=args.edge_threshold,
                kline_alpha=args.kline_alpha,
                ofi_col=args.ofi_col,
                ofi_quantile=args.ofi_quantile,
                kline_col=args.kline_col,
                kline_quantile=args.kline_quantile,
                kline_operator=args.kline_operator,
                directional=args.directional,
            ),
            selected_exit_spec=ExitLockSpec(take_profit_bps=args.take_profit_bps, stop_loss_bps=args.stop_loss_bps, reserve_horizon=True),
            alpha_grid=parse_float_list(args.alpha_grid),
            ofi_cols=parse_str_list(args.ofi_cols),
            ofi_quantiles=parse_float_list(args.ofi_quantiles),
            kline_cols=parse_str_list(args.kline_cols),
            kline_quantiles=parse_float_list(args.kline_quantiles),
            exit_take_profit_bps_values=parse_float_list(args.exit_take_profit_bps_values),
            exit_stop_loss_bps_values=parse_float_list(args.exit_stop_loss_bps_values),
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            gate=ExecutionProfitLockGate(
                min_oof_trades=args.gate_min_oof_trades,
                min_folds_with_trades=args.gate_min_folds_with_trades,
                min_fold_mean_net_bps=args.gate_min_fold_mean_net_bps,
                min_fold_total_net_bps=args.gate_min_fold_total_net_bps,
                min_bootstrap_mean_p05_bps=args.gate_min_bootstrap_mean_p05_bps,
                max_addone_family_p=args.gate_max_addone_family_p,
                min_top_winner_removal_k=args.gate_min_top_winner_removal_k,
                min_top_winner_removed_total_bps=args.gate_min_top_winner_removed_total_bps,
                min_full_stress_mean_net_bps=args.gate_min_full_stress_mean_net_bps,
                min_full_stress_total_net_bps=args.gate_min_full_stress_total_net_bps,
            ),
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "profit-lock-certificate":
        result = run_profit_lock_certificate(
            base_ensemble_dir=args.base_ensemble_dir,
            kline_ensemble_dir=args.kline_ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            selected_spec=KlineGuardSpec(
                edge_threshold=args.edge_threshold,
                kline_alpha=args.kline_alpha,
                ofi_col=args.ofi_col,
                ofi_quantile=args.ofi_quantile,
                kline_col=args.kline_col,
                kline_quantile=args.kline_quantile,
                kline_operator=args.kline_operator,
                directional=args.directional,
            ),
            alpha_grid=parse_float_list(args.alpha_grid),
            ofi_cols=parse_str_list(args.ofi_cols),
            ofi_quantiles=parse_float_list(args.ofi_quantiles),
            kline_cols=parse_str_list(args.kline_cols),
            kline_quantiles=parse_float_list(args.kline_quantiles),
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            gate=ProfitLockGate(
                min_oof_trades=args.gate_min_oof_trades,
                min_folds_with_trades=args.gate_min_folds_with_trades,
                min_fold_mean_net_bps=args.gate_min_fold_mean_net_bps,
                min_fold_total_net_bps=args.gate_min_fold_total_net_bps,
                min_bootstrap_mean_p05_bps=args.gate_min_bootstrap_mean_p05_bps,
                max_addone_family_p=args.gate_max_addone_family_p,
                min_top_winner_removal_k=args.gate_min_top_winner_removal_k,
                min_top_winner_removed_total_bps=args.gate_min_top_winner_removed_total_bps,
                max_primary_stress_cost_bps=args.gate_max_primary_stress_cost_bps,
                max_primary_stress_latency_sec=args.gate_max_primary_stress_latency_sec,
                max_secondary_stress_cost_bps=args.gate_max_secondary_stress_cost_bps,
                max_secondary_stress_latency_sec=args.gate_max_secondary_stress_latency_sec,
                min_stress_mean_net_bps=args.gate_min_stress_mean_net_bps,
            ),
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0


    if args.command == "slot-veto-audit":
        result = run_slot_veto_audit(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            spec=SlotVetoSpec(
                edge_threshold=args.edge_threshold,
                filter_col=args.filter_col,
                filter_operator=args.filter_operator,
                filter_quantile=args.filter_quantile,
            ),
            family_filter_cols=parse_str_list(args.family_filter_cols),
            family_quantiles=parse_float_list(args.family_quantiles),
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            family_shift_runs=args.family_shift_runs,
            gate_config=SlotVetoGateConfig(
                min_oof_trades=args.gate_min_oof_trades,
                min_periods_with_trades=args.gate_min_periods_with_trades,
                min_period_mean_net_bps=args.gate_min_period_mean_net_bps,
                max_family_null_p_total=args.gate_max_family_null_p_total,
                max_family_null_p_mean=args.gate_max_family_null_p_mean,
            ),
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("aggregate") or {}).get("gate", {}).get("passed") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "generate-sample":
        book_path, trades_path = generate_sample_data(args.out, rows=args.rows, depth=args.depth, seed=args.seed)
        print(json.dumps({"book": str(book_path), "trades": str(trades_path)}, indent=2))
        return 0

    if args.command == "fetch-tardis-sample":
        manifest = fetch_tardis_sample_book(
            args.out,
            url=args.url,
            depth=args.depth,
            sample_ms=args.sample_ms,
            max_input_rows=args.max_input_rows,
            max_snapshots=args.max_snapshots,
            overwrite=args.overwrite,
        )
        print(json.dumps(manifest, indent=2))
        return 0

    if args.command == "convert-tardis-l2":
        stats = convert_tardis_incremental_l2_to_book_csv(
            args.input,
            args.out,
            depth=args.depth,
            sample_ms=args.sample_ms,
            max_input_rows=args.max_input_rows,
            max_snapshots=args.max_snapshots,
        )
        print(json.dumps(stats.to_dict(), indent=2))
        return 0

    if args.command == "fetch-binance-depth":
        path = fetch_binance_spot_depth_snapshots(args.out, symbol=args.symbol, depth=args.depth, interval_sec=args.interval_sec, samples=args.samples)
        print(json.dumps({"book": str(path)}, indent=2))
        return 0

    if args.command == "collect-binance-ws":
        path = collect_binance_spot_local_book(args.out, symbol=args.symbol, depth=args.depth, sample_ms=args.sample_ms, seconds=args.seconds, rest_limit=args.rest_limit)
        print(json.dumps({"book": str(path)}, indent=2))
        return 0

    if args.command == "profile":
        result = profile_market_data(book_path=args.book, trades_path=args.trades, config_path=args.config, out_dir=args.out)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "feature-scan":
        result = feature_forward_scan(
            book_path=args.book,
            trades_path=args.trades,
            config_path=args.config,
            out_dir=args.out,
            horizons_sec=parse_float_list(args.horizons_sec),
            threshold_bps=args.threshold_bps,
            top_n=args.top_n,
        )
        print(json.dumps({"rows_features": result.get("rows_features"), "feature_count": result.get("feature_count"), "out_dir": args.out}, indent=2))
        return 0

    if args.command == "diagnostics":
        result = run_feature_diagnostics(book_path=args.book, trades_path=args.trades, config_path=args.config, out_dir=args.out, top_n=args.top_n, clean=args.clean)
        print(json.dumps({"rows_dataset": result.get("rows_dataset"), "feature_count": result.get("feature_count"), "out_dir": args.out}, indent=2))
        return 0

    if args.command == "correlations":
        result = feature_correlation_report(book_path=args.book, trades_path=args.trades, config_path=args.config, out_dir=args.out, top_n=args.top_n, clean=args.clean)
        print(json.dumps({"rows_dataset": result.get("rows_dataset"), "feature_count": result.get("feature_count"), "out_dir": args.out}, indent=2))
        return 0

    if args.command == "train":
        summary = run_train(book_path=args.book, trades_path=args.trades, config_path=args.config, out_dir=args.out)
        print(json.dumps(_compact_summary(summary), indent=2))
        return 0

    if args.command == "tune":
        result = run_tuning(
            book_path=args.book,
            trades_path=args.trades,
            base_config_path=args.config,
            out_dir=args.out,
            horizons_sec=parse_float_list(args.horizons_sec),
            thresholds_bps=parse_float_list(args.thresholds_bps),
            models=parse_str_list(args.models),
            edge_thresholds=parse_float_list(args.edge_thresholds),
            clean=args.clean,
        )
        print(json.dumps(_compact_tuning_summary(result), indent=2))
        return 0

    if args.command == "walk-forward":
        result = run_walk_forward(
            book_path=args.book,
            trades_path=args.trades,
            base_config_path=args.config,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            threshold_bps=args.threshold_bps,
            model_type=args.model,
            edge_threshold=args.edge_threshold,
            folds=args.folds,
            min_train_ratio=args.min_train_ratio,
            valid_ratio=args.valid_ratio,
            embargo_sec=args.embargo_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            run_null=not args.no_null,
            clean=args.clean,
        )
        print(json.dumps(_compact_walk_forward_summary(result), indent=2))
        return 0


    if args.command == "adaptive-walk-forward":
        result = run_adaptive_walk_forward(
            book_path=args.book,
            trades_path=args.trades,
            base_config_path=args.config,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            threshold_bps=args.threshold_bps,
            model_type=args.model,
            candidate_edges=parse_float_list(args.candidate_edges),
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            folds=args.folds,
            min_train_ratio=args.min_train_ratio,
            valid_ratio=args.valid_ratio,
            calibration_ratio=args.calibration_ratio,
            embargo_sec=args.embargo_sec,
            min_calibration_trades=args.min_calibration_trades,
            clean=args.clean,
        )
        print(json.dumps({
            "strict_research_pass": (result.get("aggregate") or {}).get("strict_research_pass") if isinstance(result.get("aggregate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "rule-baselines":
        result = evaluate_rule_baselines(
            book_path=args.book,
            trades_path=args.trades,
            config_path=args.config,
            out_dir=args.out,
            signal_thresholds=parse_float_list(args.signal_thresholds),
            clean=args.clean,
        )
        print(json.dumps({"rules_tested": result.get("rules_tested"), "best": result.get("best"), "out_dir": args.out}, indent=2))
        return 0

    if args.command == "ablate-features":
        result = run_feature_ablation(
            book_path=args.book,
            trades_path=args.trades,
            base_config_path=args.config,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            threshold_bps=args.threshold_bps,
            model_type=args.model,
            edge_threshold=args.edge_threshold,
            clean=args.clean,
        )
        print(json.dumps({"variants_completed": result.get("variants_completed"), "best": result.get("best"), "out_dir": args.out}, indent=2))
        return 0

    if args.command == "sweep-edge":
        predictions = pd.read_csv(args.predictions)
        sweep = sweep_edge_thresholds(predictions, cost_bps=args.cost_bps, thresholds=parse_float_list(args.thresholds), horizon_sec=args.horizon_sec)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        sweep.to_csv(args.out, index=False)
        print(json.dumps({"rows": len(sweep), "out": args.out, "best": sweep.head(1).to_dict(orient="records")}, indent=2))
        return 0


    if args.command == "stress":
        result = run_stress_report(
            predictions_path=args.predictions,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            cost_bps_values=parse_float_list(args.cost_bps_values),
            latency_sec_values=parse_float_list(args.latency_sec_values),
            gate_edge_threshold=args.gate_edge_threshold,
            gate_cost_bps=args.gate_cost_bps,
            gate_latency_sec=args.gate_latency_sec,
            clean=args.clean,
        )
        compact = {
            "best_stress_row": result.get("best_stress_row"),
            "robust_grid_gate_passed": (result.get("robust_grid_gate") or {}).get("passed") if isinstance(result.get("robust_grid_gate"), dict) else None,
            "point_gate_passed": (result.get("gate_result") or {}).get("passed") if isinstance(result.get("gate_result"), dict) else None,
            "out_dir": args.out,
        }
        print(json.dumps(compact, indent=2))
        return 0

    if args.command == "ensemble-walk-forward":
        result = run_ensemble_walk_forward(
            book_path=args.book,
            trades_path=args.trades,
            base_config_path=args.config,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            threshold_bps=args.threshold_bps,
            model_types=parse_str_list(args.models),
            candidate_edges=parse_float_list(args.candidate_edges),
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            folds=args.folds,
            min_train_ratio=args.min_train_ratio,
            valid_ratio=args.valid_ratio,
            calibration_ratio=args.calibration_ratio,
            embargo_sec=args.embargo_sec,
            top_k_features=args.top_k_features,
            min_calibration_trades=args.min_calibration_trades,
            stationary_only=args.stationary_only,
            kline_timeframes=parse_str_list(args.kline_timeframes) if getattr(args, "kline_timeframes", "").strip() else None,
            kline_candle_paths=parse_candle_path_specs(getattr(args, "kline_candle", [])),
            kline_decision_lag_sec=getattr(args, "kline_decision_lag_sec", 0.0),
            kline_lookbacks=[int(x) for x in parse_float_list(getattr(args, "kline_lookbacks", "1,3,6,12,24"))],
            clean=args.clean,
        )
        print(json.dumps({
            "strict_research_pass": (result.get("aggregate") or {}).get("strict_research_pass") if isinstance(result.get("aggregate"), dict) else None,
            "robust_profit_gate_passed": (result.get("profit_gate") or {}).get("passed") if isinstance(result.get("profit_gate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "rule-taker-walk-forward":
        rule_features = parse_str_list(args.rule_features) if args.rule_features.strip() else None
        result = run_rule_taker_walk_forward(
            book_path=args.book,
            trades_path=args.trades,
            base_config_path=args.config,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            threshold_bps=args.threshold_bps,
            rule_features=rule_features,
            signal_thresholds=parse_float_list(args.signal_thresholds),
            candidate_edges=parse_float_list(args.candidate_edges),
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            folds=args.folds,
            min_train_ratio=args.min_train_ratio,
            valid_ratio=args.valid_ratio,
            calibration_ratio=args.calibration_ratio,
            embargo_sec=args.embargo_sec,
            min_calibration_trades=args.min_calibration_trades,
            clean=args.clean,
        )
        print(json.dumps({
            "strict_research_pass": (result.get("aggregate") or {}).get("strict_research_pass") if isinstance(result.get("aggregate"), dict) else None,
            "robust_profit_gate_passed": (result.get("profit_gate") or {}).get("passed") if isinstance(result.get("profit_gate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "backtest-taker":
        predictions = pd.read_csv(args.predictions)
        frame, metrics = backtest_taker_bidask_non_overlapping(
            predictions,
            cost_bps=args.cost_bps,
            edge_threshold=args.edge_threshold,
            horizon_sec=args.horizon_sec,
            latency_sec=args.latency_sec,
        )
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.out, index=False)
        print(json.dumps(metrics, indent=2))
        return 0

    if args.command == "sweep-taker":
        predictions = pd.read_csv(args.predictions)
        sweep = sweep_taker_bidask(
            predictions,
            horizon_sec=args.horizon_sec,
            cost_bps_values=parse_float_list(args.cost_bps_values),
            latency_sec_values=parse_float_list(args.latency_sec_values),
            edge_thresholds=parse_float_list(args.edge_thresholds),
        )
        gate = robust_profit_gate(sweep)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        sweep.to_csv(args.out, index=False)
        print(json.dumps({"rows": len(sweep), "best": sweep.head(1).to_dict(orient="records"), "gate": gate}, indent=2))
        return 0

    if args.command == "selective-from-ensemble":
        signed_columns = parse_str_list(args.signed_columns) if args.signed_columns.strip() else None
        result = run_selective_from_ensemble_dir(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            min_calibration_trades=args.min_calibration_trades,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            signed_columns=signed_columns,
            spread_quantiles=parse_float_list(args.spread_quantiles),
            vol_modes=parse_str_list(args.vol_modes),
            clean=args.clean,
        )
        print(json.dumps({
            "strict_selective_pass": (result.get("aggregate") or {}).get("strict_selective_pass") if isinstance(result.get("aggregate"), dict) else None,
            "robust_profit_gate_passed": (result.get("profit_gate") or {}).get("passed") if isinstance(result.get("profit_gate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "long-horizon-sweep":
        gate_cfg = LongWindowGateConfig(
            min_fold_trades=args.gate_min_fold_trades,
            min_oof_trades=args.gate_min_oof_trades,
            min_oof_hit_rate=args.gate_min_oof_hit_rate,
        )
        result = run_long_horizon_sweep(
            book_path=args.book,
            trades_path=args.trades,
            base_config_path=args.config,
            out_dir=args.out,
            horizons_sec=parse_float_list(args.horizons_sec),
            threshold_bps_values=parse_float_list(args.thresholds_bps),
            model_sets=parse_model_sets(args.model_sets),
            top_k_features_values=[int(x) for x in parse_float_list(args.top_k_features)],
            candidate_edges=parse_float_list(args.candidate_edges),
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            folds=args.folds,
            min_train_ratio=args.min_train_ratio,
            valid_ratio=args.valid_ratio,
            calibration_ratio=args.calibration_ratio,
            min_calibration_trades=args.min_calibration_trades,
            stationary_only=args.stationary_only,
            gate_config=gate_cfg,
            clean=args.clean,
            skip_existing=not args.no_skip_existing,
        )
        print(json.dumps({"completed_runs": result.get("completed_runs"), "best": result.get("best"), "out_dir": args.out}, indent=2))
        return 0

    if args.command == "summarize-long-runs":
        gate_cfg = LongWindowGateConfig(
            min_fold_trades=args.gate_min_fold_trades,
            min_oof_trades=args.gate_min_oof_trades,
            min_oof_hit_rate=args.gate_min_oof_hit_rate,
        )
        frame = summarize_completed_long_runs(args.runs, gate_config=gate_cfg)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.out, index=False)
        print(json.dumps({"rows": len(frame), "best": frame.head(1).to_dict(orient="records") if not frame.empty else []}, indent=2))
        return 0

    if args.command == "fixed-template-audit":
        signed_columns = parse_str_list(args.signed_columns) if args.signed_columns.strip() else None
        gate_cfg = FixedTemplateGateConfig(
            min_folds_with_trades=args.gate_min_folds_with_trades,
            min_oof_trades=args.gate_min_oof_trades,
            min_fold_trades=args.gate_min_fold_trades,
            max_shift_null_p_mean=args.gate_max_shift_null_p,
            max_shift_null_p_total=args.gate_max_shift_null_p,
        )
        result = run_fixed_template_audit(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            signed_columns=signed_columns,
            spread_quantiles=parse_float_list(args.spread_quantiles),
            vol_modes=parse_str_list(args.vol_modes),
            template_source=args.template_source,
            selection_policy=args.selection_policy,
            min_source_trades=args.min_source_trades,
            top_k_templates=args.top_k_templates,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            gate_config=gate_cfg,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("gate") or {}).get("passed") if isinstance(result.get("gate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "failed_checks": (result.get("gate") or {}).get("failed_checks") if isinstance(result.get("gate"), dict) else None,
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "family-adaptive-audit":
        if args.family_json.strip():
            family = FamilySpec.from_json_file(args.family_json)
        else:
            family = FamilySpec(
                direction_mode=args.family_direction_mode,
                signed_col=args.family_signed_col.strip() or None,
                signed_mode=args.family_signed_mode,
            )
        result = run_family_adaptive_audit(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            family=family,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            signed_abs_quantiles=parse_float_list(args.signed_abs_quantiles),
            spread_quantiles=parse_float_list(args.spread_quantiles),
            vol_modes=parse_str_list(args.vol_modes),
            min_calibration_trades=args.min_calibration_trades,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("gate") or {}).get("passed") if isinstance(result.get("gate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "failed_checks": (result.get("gate") or {}).get("failed_checks") if isinstance(result.get("gate"), dict) else None,
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "calibrated-edge-audit":
        signed_columns = parse_str_list(args.signed_columns) if args.signed_columns.strip() else None
        result = run_calibrated_edge_audit(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            calibrator=args.calibrator,
            calibrator_features=parse_str_list(args.calibrator_features),
            edge_thresholds=parse_float_list(args.edge_thresholds),
            signed_columns=signed_columns,
            spread_quantiles=parse_float_list(args.spread_quantiles),
            vol_modes=parse_str_list(args.vol_modes),
            min_calibration_trades=args.min_calibration_trades,
            min_train_labels=args.min_train_labels,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("gate") or {}).get("passed") if isinstance(result.get("gate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "failed_checks": (result.get("gate") or {}).get("failed_checks") if isinstance(result.get("gate"), dict) else None,
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "template-transfer-audit":
        signed_columns = parse_str_list(args.signed_columns) if args.signed_columns.strip() else None
        result = run_template_transfer_audit(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            signed_columns=signed_columns,
            spread_quantiles=parse_float_list(args.spread_quantiles),
            vol_modes=parse_str_list(args.vol_modes),
            min_source_trades=args.min_source_trades,
            top_k_templates=args.top_k_templates,
            warmup_folds=args.warmup_folds,
            min_history_trades=args.min_history_trades,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("gate") or {}).get("passed") if isinstance(result.get("gate"), dict) else None,
            "aggregate": result.get("aggregate"),
            "failed_checks": (result.get("gate") or {}).get("failed_checks") if isinstance(result.get("gate"), dict) else None,
            "out_dir": args.out,
        }, indent=2))
        return 0


    if args.command == "template-family-null-audit":
        signed_columns = parse_str_list(args.signed_columns) if args.signed_columns.strip() else None
        gate_cfg = FamilyNullGateConfig(
            min_oof_trades=args.gate_min_oof_trades,
            min_fold_trades=args.gate_min_fold_trades,
            max_familywise_p_mean=args.gate_max_familywise_p,
            max_familywise_p_total=args.gate_max_familywise_p,
        )
        result = run_template_family_null_audit(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            signed_columns=signed_columns,
            spread_quantiles=parse_float_list(args.spread_quantiles),
            vol_modes=parse_str_list(args.vol_modes),
            template_source=args.template_source,
            min_source_trades=args.min_source_trades,
            top_k_templates=args.top_k_templates,
            shift_runs=args.shift_runs,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            gate_config=gate_cfg,
            clean=args.clean,
        )
        print(json.dumps({
            "selected_oracle_gate_passed": (result.get("selected_oracle_gate") or {}).get("passed") if isinstance(result.get("selected_oracle_gate"), dict) else None,
            "source_rank1_gate_passed": (result.get("source_rank1_gate") or {}).get("passed") if isinstance(result.get("source_rank1_gate"), dict) else None,
            "selected_oracle": result.get("selected_oracle"),
            "source_rank1": result.get("source_rank1"),
            "familywise_null": result.get("familywise_null"),
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "sequential-template-audit":
        signed_columns = parse_str_list(args.signed_columns) if args.signed_columns.strip() else None
        gate_cfg = SequentialGateConfig(
            min_oof_trades=args.gate_min_oof_trades,
            min_periods_with_trades=args.gate_min_periods_with_trades,
            min_period_mean_net_bps=args.gate_min_period_mean_net_bps,
            max_shift_null_p_mean=args.gate_max_shift_null_p,
            max_shift_null_p_total=args.gate_max_shift_null_p,
        )
        result = run_sequential_template_audit(
            ensemble_dir=args.ensemble_dir,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            cost_bps=args.cost_bps,
            latency_sec=args.latency_sec,
            edge_thresholds=parse_float_list(args.edge_thresholds),
            signed_columns=signed_columns,
            spread_quantiles=parse_float_list(args.spread_quantiles),
            vol_modes=parse_str_list(args.vol_modes),
            template_source=args.template_source,
            min_source_trades=args.min_source_trades,
            top_k_templates=args.top_k_templates,
            period_sec=args.period_sec,
            ranking_policy=args.ranking_policy,
            cold_start_policy=args.cold_start_policy,
            warmup_periods=args.warmup_periods,
            min_history_trades=args.min_history_trades,
            min_history_periods=args.min_history_periods,
            lower_bound_z=args.lower_bound_z,
            min_lower_bound_bps=args.min_lower_bound_bps,
            stress_cost_bps_values=parse_float_list(args.stress_cost_bps_values),
            stress_latency_sec_values=parse_float_list(args.stress_latency_sec_values),
            shift_null_runs=args.shift_null_runs,
            gate_config=gate_cfg,
            clean=args.clean,
        )
        print(json.dumps({
            "gate_passed": (result.get("gate") or {}).get("passed") if isinstance(result.get("gate"), dict) else None,
            "selected_online": result.get("selected_online"),
            "source_rank1": result.get("source_rank1"),
            "period_oracle": result.get("period_oracle"),
            "regret": result.get("regret"),
            "failed_checks": (result.get("gate") or {}).get("failed_checks") if isinstance(result.get("gate"), dict) else None,
            "out_dir": args.out,
        }, indent=2))
        return 0

    if args.command == "audit-trades":
        result = audit_trade_backtest(
            backtest_csv=args.backtest,
            out_dir=args.out,
            horizon_sec=args.horizon_sec,
            latency_sec=args.latency_sec,
            clean=args.clean,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "combine-fixed-backtests":
        names = parse_str_list(args.strategy_names) if args.strategy_names.strip() else None
        result = combine_fixed_backtest_ledgers(
            backtest_paths=args.backtests,
            horizon_secs=parse_float_list(args.horizons_sec),
            strategy_names=names,
            out_dir=args.out,
            clean=args.clean,
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "backtest":
        predictions = pd.read_csv(args.predictions)
        if args.horizon_sec is None:
            _, metrics = backtest_predictions(predictions, cost_bps=args.cost_bps, edge_threshold=args.edge_threshold)
        else:
            _, metrics = backtest_predictions_non_overlapping(predictions, cost_bps=args.cost_bps, edge_threshold=args.edge_threshold, horizon_sec=args.horizon_sec)
        save_backtest_report(metrics, Path(args.out))
        print(json.dumps(metrics, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _compact_summary(summary: dict[str, object]) -> dict[str, object]:
    metrics = summary.get("metrics", {})
    backtest = summary.get("backtest", {})
    strict = summary.get("backtest_non_overlap", {})
    return {
        "rows_total": summary.get("rows_total"),
        "rows_train": summary.get("rows_train"),
        "rows_valid": summary.get("rows_valid"),
        "feature_count": summary.get("feature_count"),
        "accuracy": metrics.get("accuracy") if isinstance(metrics, dict) else None,
        "balanced_accuracy": metrics.get("balanced_accuracy") if isinstance(metrics, dict) else None,
        "macro_f1": metrics.get("macro_f1") if isinstance(metrics, dict) else None,
        "majority_accuracy_valid": metrics.get("majority_accuracy_valid") if isinstance(metrics, dict) else None,
        "accuracy_lift_vs_majority": metrics.get("accuracy_lift_vs_majority") if isinstance(metrics, dict) else None,
        "event_trades": backtest.get("trades") if isinstance(backtest, dict) else None,
        "event_mean_net_pnl_bps": backtest.get("mean_net_pnl_bps") if isinstance(backtest, dict) else None,
        "event_total_net_pnl_bps": backtest.get("total_net_pnl_bps") if isinstance(backtest, dict) else None,
        "strict_trades": strict.get("trades") if isinstance(strict, dict) else None,
        "strict_mean_net_pnl_bps": strict.get("mean_net_pnl_bps") if isinstance(strict, dict) else None,
        "strict_total_net_pnl_bps": strict.get("total_net_pnl_bps") if isinstance(strict, dict) else None,
        "out_dir": summary.get("out_dir"),
    }


def _compact_tuning_summary(result: dict[str, object]) -> dict[str, object]:
    best = result.get("best")
    if isinstance(best, dict):
        best = {
            "rank": best.get("rank"),
            "horizon_sec": best.get("horizon_sec"),
            "threshold_bps": best.get("threshold_bps"),
            "model_type": best.get("model_type"),
            "edge_threshold": best.get("edge_threshold"),
            "accuracy": best.get("accuracy"),
            "balanced_accuracy": best.get("balanced_accuracy"),
            "macro_f1": best.get("macro_f1"),
            "mean_net_pnl_bps": best.get("mean_net_pnl_bps"),
            "run_dir": best.get("run_dir"),
        }
    return {
        "trials_requested": result.get("trials_requested"),
        "trials_completed": result.get("trials_completed"),
        "trials_failed": result.get("trials_failed"),
        "leaderboard_path": result.get("leaderboard_path"),
        "best": best,
    }


def _compact_walk_forward_summary(result: dict[str, object]) -> dict[str, object]:
    aggregate = result.get("aggregate", {}) if isinstance(result.get("aggregate"), dict) else {}
    return {
        "rows_dataset": result.get("rows_dataset"),
        "feature_count": result.get("feature_count"),
        "median_step_sec": result.get("median_step_sec"),
        "embargo_rows": result.get("embargo_rows"),
        "balanced_accuracy_mean": aggregate.get("balanced_accuracy_mean"),
        "macro_f1_mean": aggregate.get("macro_f1_mean"),
        "signal_lift_vs_null_balanced_accuracy": aggregate.get("signal_lift_vs_null_balanced_accuracy"),
        "best_event_edge": aggregate.get("best_event_edge"),
        "best_non_overlap_edge": aggregate.get("best_non_overlap_edge"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
