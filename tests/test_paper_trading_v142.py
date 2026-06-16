from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from lob_microprice_lab.paper_trading import (
    BinancePublicTickerSource,
    CsvPriceSource,
    CsvSignalProvider,
    MarketSnapshot,
    PaperBroker,
    PaperSignal,
    PaperTradingConfig,
    V142LeveragePolicy,
    run_v142_paper_trading,
)


class _FailOncePriceSource:
    def __init__(self) -> None:
        self.calls = 0

    def next_snapshot(self) -> MarketSnapshot | None:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("temporary price outage")
        if self.calls == 2:
            return MarketSnapshot(
                timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
                symbol="BTCUSDC",
                price=100.0,
                source="test",
            )
        return None


def test_paper_trade_v142_cli_runs_synthetic_demo(tmp_path: Path) -> None:
    from lob_microprice_lab.cli import main

    out_dir = tmp_path / "cli-paper"

    rc = main(
        [
            "paper-trade-v142",
            "--out",
            str(out_dir),
            "--source",
            "synthetic",
            "--ticks",
            "3",
            "--interval-sec",
            "60",
            "--clean",
            "--no-sleep",
        ]
    )

    assert rc == 0
    assert (out_dir / "dashboard.html").exists()
    assert (out_dir / "balance.csv").exists()
    assert (out_dir / "paper_events.jsonl").exists()
    assert (out_dir / "trades.csv").exists()


def test_real_trade_btcusdc_cli_blocks_when_v206_preflight_is_not_ready(tmp_path: Path) -> None:
    from lob_microprice_lab.cli import main

    out_dir = tmp_path / "real-money"

    rc = main(
        [
            "real-trade-btcusdc",
            "--out",
            str(out_dir),
            "--arm-real-money-token",
            "I_UNDERSTAND_THIS_USES_REAL_MONEY",
        ]
    )

    assert rc == 2
    summary = json.loads((out_dir / "real_money_launch_preflight_summary.json").read_text(encoding="utf-8"))
    assert summary["decision"]["allow_real_money_launch"] is False
    assert "readiness_gate_passed" in summary["decision"]["failed_checks"]
    assert summary["config"]["places_live_orders"] is False


def test_real_trade_preflight_blocks_legacy_ready_summary_without_v212(tmp_path: Path) -> None:
    from lob_microprice_lab.real_money_launch import REQUIRED_ARM_TOKEN, real_money_launch_preflight

    readiness_summary = tmp_path / "legacy_ready.json"
    readiness_summary.write_text(
        json.dumps(
            {
                "decision": {
                    "status": "real_money_ready",
                    "promote_to_real_money": True,
                    "failed_checks": [],
                }
            }
        ),
        encoding="utf-8",
    )

    payload = real_money_launch_preflight(
        out_dir=tmp_path / "real-money",
        arm_token=REQUIRED_ARM_TOKEN,
        readiness_summary=readiness_summary,
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_forward_freshness_clean" in payload["decision"]["failed_checks"]


def test_real_trade_preflight_blocks_ready_summary_without_v214_public_data(tmp_path: Path) -> None:
    from lob_microprice_lab.real_money_launch import REQUIRED_ARM_TOKEN, real_money_launch_preflight

    readiness_summary = tmp_path / "ready_without_v214.json"
    readiness_summary.write_text(
        json.dumps(
            {
                "config": {
                    "requires_forward_freshness": True,
                },
                "checks": {
                    "forward_freshness_clean": True,
                },
                "evidence": {
                    "forward_freshness_status": "forward_freshness_passed",
                    "forward_data_current": True,
                    "fresh_forward_evidence_available": True,
                },
                "decision": {
                    "status": "real_money_ready",
                    "promote_to_real_money": True,
                    "failed_checks": [],
                },
            }
        ),
        encoding="utf-8",
    )

    payload = real_money_launch_preflight(
        out_dir=tmp_path / "real-money",
        arm_token=REQUIRED_ARM_TOKEN,
        readiness_summary=readiness_summary,
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_public_data_available" in payload["decision"]["failed_checks"]


def test_v142_leverage_policy_applies_5x_only_to_high_confidence_rescue() -> None:
    policy = V142LeveragePolicy(PaperTradingConfig(strategy_mode="research_v142"))
    signal = PaperSignal(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        signal_id="s1",
        symbol="BTCUSDC",
        side=1,
        source="test",
        leg="rescue",
        direction_probability=0.67,
    )

    leverage, high_confidence = policy.leverage_for_signal(signal, prior_drawdown_pct=0.0)

    assert leverage == 5.0
    assert high_confidence is True


def test_realtime_safe_policy_does_not_use_research_5x_rescue() -> None:
    policy = V142LeveragePolicy(PaperTradingConfig())
    signal = PaperSignal(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        signal_id="s1",
        symbol="BTCUSDC",
        side=1,
        source="test",
        leg="rescue",
        direction_probability=0.67,
    )

    leverage, high_confidence = policy.leverage_for_signal(signal, prior_drawdown_pct=0.0)

    assert leverage == 1.0
    assert high_confidence is False


def test_v142_leverage_policy_disables_5x_after_drawdown_trigger() -> None:
    policy = V142LeveragePolicy(PaperTradingConfig(strategy_mode="research_v142"))
    signal = PaperSignal(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        signal_id="s1",
        symbol="BTCUSDC",
        side=1,
        source="test",
        leg="rescue",
        direction_probability=0.67,
    )

    leverage, high_confidence = policy.leverage_for_signal(signal, prior_drawdown_pct=-6.0)

    assert leverage == 2.25
    assert high_confidence is False


def test_v142_paper_runner_writes_logs_trades_balance_and_dashboard(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    price_csv.write_text(
        "\n".join(
            [
                "timestamp,price",
                "2026-01-01T00:00:00Z,100",
                "2026-01-01T00:30:00Z,101",
                "2026-01-01T00:31:00Z,101",
            ]
        ),
        encoding="utf-8",
    )
    signal_csv.write_text(
        "\n".join(
            [
                "timestamp,signal_id,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,hc1,1,rescue,0.67,30",
            ]
        ),
        encoding="utf-8",
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        config=PaperTradingConfig(initial_balance_usdc=10_000.0, strategy_mode="research_v142"),
        clean=True,
        sleep=False,
    )

    assert summary["events"] == 3
    assert summary["trades"] == 2
    assert Path(str(summary["dashboard"])).exists()
    assert (out_dir / "paper_events.jsonl").exists()
    assert (out_dir / "balance.csv").exists()
    assert (out_dir / "trades.csv").exists()
    trades = pd.read_csv(out_dir / "trades.csv")
    assert trades.loc[trades["event_type"] == "open", "leverage"].iloc[0] == 5.0
    assert bool(trades.loc[trades["event_type"] == "open", "high_confidence_rescue_5x"].iloc[0]) is True
    summary_json = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary_json["final_balance_usdc"] > 10_000.0


def test_paper_broker_close_drawdown_does_not_count_closed_position_twice() -> None:
    broker = PaperBroker(PaperTradingConfig(initial_balance_usdc=10_000.0, fee_bps_per_side=0.0))
    open_snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        symbol="BTCUSDC",
        price=100.0,
        source="test",
    )
    close_snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2026-01-01T00:30:00Z"),
        symbol="BTCUSDC",
        price=90.0,
        source="test",
    )
    signal = PaperSignal(
        timestamp=open_snapshot.timestamp,
        signal_id="s1",
        symbol="BTCUSDC",
        side=1,
        source="test",
        leg="base",
        horizon_minutes=30,
    )

    broker.on_snapshot(open_snapshot, [signal])
    broker.on_snapshot(close_snapshot, [])

    close_row = [row for row in broker.trades if row["event_type"] == "close"][0]
    assert close_row["balance_usdc"] == 9000.0
    assert close_row["equity_usdc"] == 9000.0
    assert close_row["drawdown_pct"] == pytest.approx(-10.0)


def test_paper_broker_caps_total_open_notional_to_policy_leverage() -> None:
    broker = PaperBroker(
        PaperTradingConfig(initial_balance_usdc=10_000.0, fee_bps_per_side=0.0, strategy_mode="research_v142")
    )
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        symbol="BTCUSDC",
        price=100.0,
        source="test",
    )
    signals = [
        PaperSignal(
            timestamp=snapshot.timestamp,
            signal_id="s1",
            symbol="BTCUSDC",
            side=1,
            source="test",
            leg="base",
        ),
        PaperSignal(
            timestamp=snapshot.timestamp,
            signal_id="s2",
            symbol="BTCUSDC",
            side=-1,
            source="test",
            leg="base",
        ),
    ]

    event = broker.on_snapshot(snapshot, signals)

    assert event["opened"] == 1
    assert sum(position.notional_usdc for position in broker.open_positions) == 35_000.0


def test_paper_broker_rejects_invalid_market_price_without_opening_position() -> None:
    broker = PaperBroker(PaperTradingConfig(initial_balance_usdc=10_000.0, fee_bps_per_side=0.0))
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        symbol="BTCUSDC",
        price=0.0,
        source="test",
    )
    signal = PaperSignal(
        timestamp=snapshot.timestamp,
        signal_id="s1",
        symbol="BTCUSDC",
        side=1,
        source="test",
        leg="base",
    )

    event = broker.on_snapshot(snapshot, [signal])

    assert event["event_type"] == "market_data_error"
    assert event["opened"] == 0
    assert event["closed"] == 0
    assert event["open_positions"] == 0
    assert event["error"] == "invalid market price: 0.0"
    assert broker.open_positions == []
    assert broker.trades == []


def test_paper_runner_logs_invalid_market_prices_without_consuming_signals(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    _write_text(
        price_csv,
        "\n".join(
            [
                "timestamp,price",
                "2026-01-01T00:00:00Z,0",
                "2026-01-01T00:01:00Z,100",
            ]
        ),
    )
    _write_text(
        signal_csv,
        "\n".join(
            [
                "timestamp,signal_id,symbol,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,valid-after-bad-price,BTCUSDC,1,base,0.60,30",
            ]
        ),
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        clean=True,
        sleep=False,
    )

    events = pd.read_csv(out_dir / "balance.csv")
    trades = pd.read_csv(out_dir / "trades.csv")
    assert summary["market_data_errors"] == 1
    assert events.loc[0, "event_type"] == "market_data_error"
    assert events.loc[0, "error"] == "invalid market price: 0.0"
    assert events.loc[1, "opened"] == 1
    assert trades.loc[0, "signal_id"] == "valid-after-bad-price"


def test_paper_runner_does_not_use_invalid_market_price_for_final_equity(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    _write_text(
        price_csv,
        "\n".join(
            [
                "timestamp,price",
                "2026-01-01T00:00:00Z,100",
                "2026-01-01T00:30:00Z,0",
            ]
        ),
    )
    _write_text(
        signal_csv,
        "\n".join(
            [
                "timestamp,signal_id,symbol,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,open-before-bad-price,BTCUSDC,1,base,0.60,30",
            ]
        ),
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        clean=True,
        sleep=False,
    )

    assert summary["market_data_errors"] == 1
    assert summary["open_positions"] == 1
    assert summary["trades"] == 1
    assert summary["final_equity_usdc"] == pytest.approx(9996.0)


def test_cli_paper_trade_defaults_to_realtime_safe_strategy(tmp_path: Path) -> None:
    from lob_microprice_lab.cli import main

    out_dir = tmp_path / "cli-paper"

    rc = main(
        [
            "paper-trade-v142",
            "--out",
            str(out_dir),
            "--source",
            "synthetic",
            "--ticks",
            "1",
            "--interval-sec",
            "60",
            "--clean",
            "--no-sleep",
        ]
    )

    assert rc == 0
    config = json.loads((out_dir / "paper_config.json").read_text(encoding="utf-8"))
    assert config["strategy_mode"] == "realtime_safe"


def test_realtime_safe_rejects_stale_signal_without_opening_position() -> None:
    broker = PaperBroker(PaperTradingConfig(initial_balance_usdc=10_000.0, fee_bps_per_side=0.0))
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2026-01-01T00:10:00Z"),
        symbol="BTCUSDC",
        price=100.0,
        source="test",
    )
    stale_signal = PaperSignal(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        signal_id="stale",
        symbol="BTCUSDC",
        side=1,
        source="test",
        leg="base",
    )

    event = broker.on_snapshot(snapshot, [stale_signal])

    assert event["opened"] == 0
    assert event["rejected_signal_count"] == 1
    assert broker.open_positions == []
    assert broker.rejected_signals[0]["reason"] == "stale_signal"


def test_realtime_safe_rejects_signal_before_available_at_without_opening_position() -> None:
    broker = PaperBroker(PaperTradingConfig(initial_balance_usdc=10_000.0, fee_bps_per_side=0.0))
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2026-01-01T00:01:00Z"),
        symbol="BTCUSDC",
        price=100.0,
        source="test",
    )
    not_yet_available = PaperSignal(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        signal_id="future-availability",
        symbol="BTCUSDC",
        side=1,
        source="test",
        leg="base",
        available_at=pd.Timestamp("2026-01-01T00:02:00Z"),
    )

    event = broker.on_snapshot(snapshot, [not_yet_available])

    assert event["opened"] == 0
    assert event["rejected_signal_count"] == 1
    assert broker.open_positions == []
    assert broker.rejected_signals[0]["reason"] == "future_available_at"
    assert broker.rejected_signals[0]["available_at"] == "2026-01-01T00:02:00+00:00"


def test_research_mode_keeps_historical_stale_signal_replay() -> None:
    broker = PaperBroker(
        PaperTradingConfig(initial_balance_usdc=10_000.0, fee_bps_per_side=0.0, strategy_mode="research_v142")
    )
    snapshot = MarketSnapshot(
        timestamp=pd.Timestamp("2026-01-01T00:10:00Z"),
        symbol="BTCUSDC",
        price=100.0,
        source="test",
    )
    historical_signal = PaperSignal(
        timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
        signal_id="historical",
        symbol="BTCUSDC",
        side=1,
        source="test",
        leg="base",
    )

    event = broker.on_snapshot(snapshot, [historical_signal])

    assert event["opened"] == 1
    assert event["rejected_signal_count"] == 0
    assert len(broker.open_positions) == 1


def test_research_mode_does_not_open_invalid_or_wrong_symbol_csv_signals(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    _write_text(price_csv, "timestamp,price\n2026-01-01T00:10:00Z,100\n")
    _write_text(
        signal_csv,
        "\n".join(
            [
                "timestamp,signal_id,symbol,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,wrong-symbol,ETHUSDC,1,base,0.60,30",
                "2026-01-01T00:00:00Z,zero-side,BTCUSDC,0,base,0.60,30",
                "2026-01-01T00:00:00Z,bad-side,BTCUSDC,2,base,0.60,30",
                "2026-01-01T00:00:00Z,valid-stale,BTCUSDC,1,base,0.60,30",
            ]
        ),
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        config=PaperTradingConfig(strategy_mode="research_v142"),
        clean=True,
        sleep=False,
    )

    trades = pd.read_csv(out_dir / "trades.csv")
    rejected = pd.read_csv(out_dir / "rejected_signals.csv")
    assert summary["trades"] == 1
    assert trades.loc[0, "signal_id"] == "valid-stale"
    assert summary["rejected_signals"] == 0
    assert rejected.empty


def test_paper_runner_writes_rejected_signal_reason_log(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    _write_text(price_csv, "timestamp,price\n2026-01-01T00:10:00Z,100\n")
    _write_text(
        signal_csv,
        "\n".join(
            [
                "timestamp,signal_id,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,old1,1,base,0.60,30",
            ]
        ),
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        clean=True,
        sleep=False,
    )

    rejected = pd.read_csv(out_dir / "rejected_signals.csv")
    assert summary["rejected_signals"] == 1
    assert rejected.loc[0, "signal_id"] == "old1"
    assert rejected.loc[0, "reason"] == "stale_signal"
    assert rejected.loc[0, "snapshot_symbol"] == "BTCUSDC"


def test_csv_signal_provider_exposes_invalid_rows_for_realtime_rejection_log(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    _write_text(price_csv, "timestamp,price\n2026-01-01T00:00:00Z,100\n")
    _write_text(
        signal_csv,
        "\n".join(
            [
                "timestamp,signal_id,symbol,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,wrong-symbol,ETHUSDC,1,base,0.60,30",
                "2026-01-01T00:00:00Z,zero-side,BTCUSDC,0,base,0.60,30",
                "2026-01-01T00:00:00Z,bad-side,BTCUSDC,2,base,0.60,30",
                "2026-01-01T00:00:00Z,decimal-side,BTCUSDC,1.5,base,0.60,30",
                "2026-01-01T00:00:00Z,valid,BTCUSDC,1,base,0.60,30",
            ]
        ),
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        clean=True,
        sleep=False,
    )

    rejected = pd.read_csv(out_dir / "rejected_signals.csv")
    trades = pd.read_csv(out_dir / "trades.csv")
    assert summary["trades"] == 1
    assert trades.loc[0, "signal_id"] == "valid"
    assert summary["rejected_signals"] == 4
    assert rejected[["signal_id", "reason"]].to_dict("records") == [
        {"signal_id": "wrong-symbol", "reason": "wrong_symbol"},
        {"signal_id": "zero-side", "reason": "invalid_side"},
        {"signal_id": "bad-side", "reason": "invalid_side"},
        {"signal_id": "decimal-side", "reason": "invalid_side"},
    ]


def test_csv_signal_provider_waits_for_available_at_before_emitting(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    _write_text(
        price_csv,
        "\n".join(
            [
                "timestamp,price",
                "2026-01-01T00:00:00Z,100",
                "2026-01-01T00:02:00Z,101",
            ]
        ),
    )
    _write_text(
        signal_csv,
        "\n".join(
            [
                "timestamp,available_at,signal_id,symbol,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,2026-01-01T00:02:00Z,late-ready,BTCUSDC,1,base,0.60,30",
            ]
        ),
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        clean=True,
        sleep=False,
    )

    events = pd.read_csv(out_dir / "balance.csv")
    trades = pd.read_csv(out_dir / "trades.csv")
    assert summary["trades"] == 1
    assert summary["rejected_signals"] == 0
    assert events.loc[0, "opened"] == 0
    assert events.loc[1, "opened"] == 1
    assert trades.loc[0, "signal_id"] == "late-ready"
    assert trades.loc[0, "timestamp"] == "2026-01-01T00:02:00+00:00"


def test_csv_signal_provider_accepts_generated_at_as_available_at_alias(tmp_path: Path) -> None:
    signal_csv = tmp_path / "signals.csv"
    _write_text(
        signal_csv,
        "\n".join(
            [
                "timestamp,generated_at,signal_id,symbol,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,2026-01-01T00:02:00Z,generated-ready,BTCUSDC,1,base,0.60,30",
            ]
        ),
    )
    provider = CsvSignalProvider(signal_csv, default_symbol="BTCUSDC")

    early = provider.signals_for_snapshot(
        MarketSnapshot(
            timestamp=pd.Timestamp("2026-01-01T00:01:00Z"),
            symbol="BTCUSDC",
            price=100.0,
            source="test",
        )
    )
    ready = provider.signals_for_snapshot(
        MarketSnapshot(
            timestamp=pd.Timestamp("2026-01-01T00:02:00Z"),
            symbol="BTCUSDC",
            price=100.0,
            source="test",
        )
    )

    assert early == []
    assert len(ready) == 1
    assert ready[0].signal_id == "generated-ready"
    assert ready[0].available_at == pd.Timestamp("2026-01-01T00:02:00Z")


def test_paper_runner_summarizes_rejected_signal_reasons(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    _write_text(price_csv, "timestamp,price\n2026-01-01T00:10:00Z,100\n")
    _write_text(
        signal_csv,
        "\n".join(
            [
                "timestamp,signal_id,symbol,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:10:00Z,wrong-symbol,ETHUSDC,1,base,0.60,30",
                "2026-01-01T00:10:00Z,bad-side,BTCUSDC,2,base,0.60,30",
                "2026-01-01T00:00:00Z,old-signal,BTCUSDC,1,base,0.60,30",
            ]
        ),
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        clean=True,
        sleep=False,
    )

    summary_json = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    dashboard = (out_dir / "dashboard.html").read_text(encoding="utf-8")
    expected = {"invalid_side": 1, "stale_signal": 1, "wrong_symbol": 1}
    assert summary["rejected_signal_reasons"] == expected
    assert summary_json["rejected_signal_reasons"] == expected
    assert "Rejected Signal Reasons" in dashboard
    assert "invalid_side" in dashboard
    assert "stale_signal" in dashboard
    assert "wrong_symbol" in dashboard


def test_paper_runner_sleeps_between_bounded_live_ticks(tmp_path: Path, monkeypatch) -> None:
    sleep_calls: list[float] = []
    monkeypatch.setattr("lob_microprice_lab.paper_trading.time.sleep", sleep_calls.append)

    summary = run_v142_paper_trading(
        out_dir=tmp_path / "paper",
        market_source=CsvPriceSource(
            _write_text(
                tmp_path / "prices.csv",
                "timestamp,price\n2026-01-01T00:00:00Z,100\n2026-01-01T00:01:00Z,101\n",
            ),
            symbol="BTCUSDC",
        ),
        ticks=2,
        interval_sec=60.0,
        clean=True,
        sleep=True,
    )

    assert summary["events"] == 2
    assert sleep_calls == [60.0]


def test_paper_runner_starts_new_output_files_without_clean(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    _write_text(price_csv, "timestamp,price\n2026-01-01T00:00:00Z,100\n")
    out_dir = tmp_path / "paper"

    for _ in range(2):
        run_v142_paper_trading(
            out_dir=out_dir,
            market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
            ticks=1,
            interval_sec=0.0,
            clean=False,
            sleep=False,
        )

    assert len((out_dir / "paper_events.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_paper_runner_logs_transient_price_errors_and_continues(tmp_path: Path) -> None:
    summary = run_v142_paper_trading(
        out_dir=tmp_path / "paper",
        market_source=_FailOncePriceSource(),
        ticks=2,
        interval_sec=0.0,
        clean=True,
        sleep=False,
    )

    events = [json.loads(line) for line in (tmp_path / "paper" / "paper_events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert summary["events"] == 2
    assert events[0]["event_type"] == "error"
    assert events[1]["event_type"] == "snapshot"


def test_binance_public_ticker_source_uses_public_read_only_urls() -> None:
    spot = BinancePublicTickerSource(symbol="btcusdc", market="spot")
    futures = BinancePublicTickerSource(symbol="BTCUSDC", market="um-futures")

    assert spot._url() == "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDC"
    assert futures._url() == "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDC"


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path
