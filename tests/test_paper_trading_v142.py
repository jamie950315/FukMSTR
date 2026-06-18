from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import base64
import hashlib
import threading

import pandas as pd
import pytest

from lob_microprice_lab.paper_trading import (
    BinancePublicTickerSource,
    BookCsvPriceSource,
    CsvPriceSource,
    CsvSignalProvider,
    MarketSnapshot,
    PaperBroker,
    PaperSignal,
    PaperTradingConfig,
    V142LeveragePolicy,
    run_v142_paper_trading,
)
from lob_microprice_lab.paper_dashboard import (
    build_dashboard_state,
    make_dashboard_server,
    request_kill_switch,
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


class _RequestKillSwitchAfterFirstSnapshotSource:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.index = 0
        self.snapshots = [
            MarketSnapshot(
                timestamp=pd.Timestamp("2026-01-01T00:00:00Z"),
                symbol="BTCUSDC",
                price=100.0,
                source="test",
            ),
            MarketSnapshot(
                timestamp=pd.Timestamp("2026-01-01T00:01:00Z"),
                symbol="BTCUSDC",
                price=101.0,
                source="test",
            ),
            MarketSnapshot(
                timestamp=pd.Timestamp("2026-01-01T00:02:00Z"),
                symbol="BTCUSDC",
                price=102.0,
                source="test",
            ),
        ]

    def next_snapshot(self) -> MarketSnapshot | None:
        if self.index >= len(self.snapshots):
            return None
        snapshot = self.snapshots[self.index]
        self.index += 1
        if self.index == 2:
            request_kill_switch(self.out_dir, reason="operator_test")
        return snapshot


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


def test_book_csv_price_source_uses_mid_price_from_l1_book(tmp_path: Path) -> None:
    book_csv = tmp_path / "book.csv"
    book_csv.write_text(
        "\n".join(
            [
                "timestamp,bid_px_1,bid_sz_1,ask_px_1,ask_sz_1",
                "2026-06-18T00:00:00Z,100.0,2.0,100.2,3.0",
                "2026-06-18T00:01:00Z,101.0,2.5,101.4,3.5",
            ]
        ),
        encoding="utf-8",
    )

    source = BookCsvPriceSource(book_csv, symbol="btcusdc")

    first = source.next_snapshot()
    second = source.next_snapshot()

    assert first is not None
    assert first.symbol == "BTCUSDC"
    assert first.source == "book-csv"
    assert first.price == pytest.approx(100.1)
    assert second is not None
    assert second.price == pytest.approx(101.2)
    assert source.next_snapshot() is None


def test_book_csv_price_source_parses_numeric_microsecond_timestamps(tmp_path: Path) -> None:
    book_csv = tmp_path / "book_us.csv"
    book_csv.write_text(
        "\n".join(
            [
                "timestamp,bid_px_1,bid_sz_1,ask_px_1,ask_sz_1",
                "1781718009688854,100.0,2.0,100.2,3.0",
            ]
        ),
        encoding="utf-8",
    )

    source = BookCsvPriceSource(book_csv, symbol="BTCUSDC")
    snapshot = source.next_snapshot()

    assert snapshot is not None
    assert snapshot.timestamp.year == 2026


def test_paper_trade_v142_cli_runs_from_realtime_book_csv(tmp_path: Path) -> None:
    from lob_microprice_lab.cli import main

    book_csv = tmp_path / "book.csv"
    book_csv.write_text(
        "\n".join(
            [
                "timestamp,bid_px_1,bid_sz_1,ask_px_1,ask_sz_1",
                "2026-06-18T00:00:00Z,100.0,2.0,100.2,3.0",
                "2026-06-18T00:01:00Z,100.1,2.0,100.3,3.0",
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli-paper-book"

    rc = main(
        [
            "paper-trade-v142",
            "--out",
            str(out_dir),
            "--source",
            "book-csv",
            "--book-csv",
            str(book_csv),
            "--ticks",
            "2",
            "--clean",
            "--no-sleep",
        ]
    )

    assert rc == 0
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["events"] == 2
    balance = pd.read_csv(out_dir / "balance.csv")
    assert list(balance["source"]) == ["book-csv", "book-csv"]
    assert list(balance["price"]) == pytest.approx([100.1, 100.2])


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


def test_real_trade_preflight_blocks_ready_summary_without_v216_execution_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lob_microprice_lab.real_money_launch as launch

    monkeypatch.setattr(launch, "_dirty_runtime_paths_from_git", lambda: [])
    readiness_summary = tmp_path / "ready_without_v216.json"
    readiness_summary.write_text(
        json.dumps(
            {
                "config": {
                    "requires_forward_freshness": True,
                    "requires_public_data_availability": True,
                },
                "checks": {
                    "forward_freshness_clean": True,
                    "public_data_available": True,
                },
                "evidence": {
                    "forward_freshness_status": "forward_freshness_passed",
                    "forward_data_current": True,
                    "fresh_forward_evidence_available": True,
                    "public_data_status": "public_data_availability_passed",
                    "public_data_available": True,
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

    payload = launch.real_money_launch_preflight(
        out_dir=tmp_path / "real-money",
        arm_token=launch.REQUIRED_ARM_TOKEN,
        readiness_summary=readiness_summary,
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_execution_provenance_clean" in payload["decision"]["failed_checks"]


def test_real_trade_preflight_blocks_ready_summary_without_v220_recent_execution_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lob_microprice_lab.real_money_launch as launch

    monkeypatch.setattr(launch, "_dirty_runtime_paths_from_git", lambda: [])
    readiness_summary = tmp_path / "ready_without_v220.json"
    readiness_summary.write_text(
        json.dumps(
            {
                "config": {
                    "min_execution_fills": 30,
                    "requires_forward_freshness": True,
                    "requires_public_data_availability": True,
                    "requires_execution_validation": True,
                    "requires_execution_provenance": True,
                    "requires_signal_provenance": True,
                },
                "checks": {
                    "forward_freshness_clean": True,
                    "public_data_available": True,
                    "execution_validation_passed": True,
                    "execution_fill_evidence_available": True,
                    "filled_status_clean": True,
                    "execution_provenance_clean": True,
                    "signal_provenance_clean": True,
                    "execution_slippage_p95_clean": True,
                    "execution_kill_switch_tested": True,
                    "execution_secrets_absent_from_repo": True,
                },
                "evidence": {
                    "forward_freshness_status": "forward_freshness_passed",
                    "forward_data_current": True,
                    "fresh_forward_evidence_available": True,
                    "public_data_status": "public_data_availability_passed",
                    "public_data_available": True,
                    "execution_validation_passed": True,
                    "execution_fill_count": 30,
                    "execution_fill_evidence_available": True,
                    "filled_status_clean": True,
                    "execution_provenance_clean": True,
                    "signal_provenance_clean": True,
                    "execution_slippage_p95_clean": True,
                    "execution_kill_switch_tested": True,
                    "execution_secrets_absent_from_repo": True,
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

    payload = launch.real_money_launch_preflight(
        out_dir=tmp_path / "real-money",
        arm_token=launch.REQUIRED_ARM_TOKEN,
        readiness_summary=readiness_summary,
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_execution_provenance_clean" in payload["decision"]["failed_checks"]


def test_real_trade_preflight_blocks_ready_summary_from_different_source_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lob_microprice_lab.real_money_launch as launch

    monkeypatch.setattr(launch, "_dirty_runtime_paths_from_git", lambda: [])
    monkeypatch.setattr(launch, "_current_git_commit", lambda: "current-source-commit")
    readiness_summary = tmp_path / "ready_from_old_commit.json"
    readiness_summary.write_text(
        json.dumps(
            {
                "config": {
                    "min_execution_fills": 30,
                    "requires_forward_freshness": True,
                    "requires_public_data_availability": True,
                    "requires_execution_validation": True,
                    "requires_execution_provenance": True,
                    "requires_signal_provenance": True,
                    "requires_readiness_source_provenance": True,
                },
                "checks": {
                    "forward_freshness_clean": True,
                    "public_data_available": True,
                    "execution_validation_passed": True,
                    "execution_fill_evidence_available": True,
                    "filled_status_clean": True,
                    "execution_provenance_clean": True,
                    "signal_provenance_clean": True,
                    "execution_slippage_p95_clean": True,
                    "execution_kill_switch_tested": True,
                    "execution_secrets_absent_from_repo": True,
                    "readiness_source_provenance_clean": True,
                },
                "evidence": {
                    "forward_freshness_status": "forward_freshness_passed",
                    "forward_data_current": True,
                    "fresh_forward_evidence_available": True,
                    "public_data_status": "public_data_availability_passed",
                    "public_data_available": True,
                    "execution_validation_passed": True,
                    "execution_fill_count": 30,
                    "execution_fill_evidence_available": True,
                    "filled_status_clean": True,
                    "execution_provenance_clean": True,
                    "signal_provenance_clean": True,
                    "execution_slippage_p95_clean": True,
                    "execution_kill_switch_tested": True,
                    "execution_secrets_absent_from_repo": True,
                    "readiness_source_commit": "old-source-commit",
                    "readiness_runtime_source_clean": True,
                    "readiness_dirty_runtime_path_count": 0,
                    "readiness_dirty_runtime_paths": [],
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

    payload = launch.real_money_launch_preflight(
        out_dir=tmp_path / "real-money",
        arm_token=launch.REQUIRED_ARM_TOKEN,
        readiness_summary=readiness_summary,
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_source_provenance_clean" in payload["decision"]["failed_checks"]


def test_real_trade_preflight_blocks_ready_summary_when_input_hash_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lob_microprice_lab.real_money_launch as launch

    input_file = tmp_path / "input.json"
    input_file.write_text('{"status":"current"}', encoding="utf-8")
    monkeypatch.setattr(launch, "_dirty_runtime_paths_from_git", lambda: [])
    monkeypatch.setattr(launch, "_current_git_commit", lambda: "current-source-commit")
    readiness_summary = tmp_path / "ready_with_old_input_hash.json"
    readiness_summary.write_text(
        json.dumps(
            {
                "config": {
                    "min_execution_fills": 30,
                    "requires_forward_freshness": True,
                    "requires_public_data_availability": True,
                    "requires_execution_validation": True,
                    "requires_execution_provenance": True,
                    "requires_signal_provenance": True,
                    "requires_readiness_source_provenance": True,
                    "requires_readiness_input_hashes": True,
                },
                "inputs": {
                    "test_input": str(input_file),
                },
                "checks": {
                    "forward_freshness_clean": True,
                    "public_data_available": True,
                    "execution_validation_passed": True,
                    "execution_fill_evidence_available": True,
                    "filled_status_clean": True,
                    "execution_provenance_clean": True,
                    "signal_provenance_clean": True,
                    "execution_slippage_p95_clean": True,
                    "execution_kill_switch_tested": True,
                    "execution_secrets_absent_from_repo": True,
                    "readiness_source_provenance_clean": True,
                    "readiness_input_hashes_clean": True,
                },
                "evidence": {
                    "forward_freshness_status": "forward_freshness_passed",
                    "forward_data_current": True,
                    "fresh_forward_evidence_available": True,
                    "public_data_status": "public_data_availability_passed",
                    "public_data_available": True,
                    "execution_validation_passed": True,
                    "execution_fill_count": 30,
                    "execution_fill_evidence_available": True,
                    "filled_status_clean": True,
                    "execution_provenance_clean": True,
                    "signal_provenance_clean": True,
                    "execution_slippage_p95_clean": True,
                    "execution_kill_switch_tested": True,
                    "execution_secrets_absent_from_repo": True,
                    "readiness_source_commit": "current-source-commit",
                    "readiness_runtime_source_clean": True,
                    "readiness_dirty_runtime_path_count": 0,
                    "readiness_dirty_runtime_paths": [],
                    "readiness_input_hashes": {
                        "test_input": "old-input-hash",
                    },
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

    payload = launch.real_money_launch_preflight(
        out_dir=tmp_path / "real-money",
        arm_token=launch.REQUIRED_ARM_TOKEN,
        readiness_summary=readiness_summary,
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_input_hashes_clean" in payload["decision"]["failed_checks"]


def test_real_trade_preflight_blocks_ready_summary_without_strategy_manifest_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lob_microprice_lab.real_money_launch as launch

    input_file = tmp_path / "input.json"
    input_file.write_text('{"status":"current"}', encoding="utf-8")
    input_hash = hashlib.sha256(input_file.read_bytes()).hexdigest()
    monkeypatch.setattr(launch, "_dirty_runtime_paths_from_git", lambda: [])
    monkeypatch.setattr(launch, "_current_git_commit", lambda: "current-source-commit")
    monkeypatch.setattr(launch, "_runtime_source_hash_from_git", lambda: "runtime-source-hash")
    readiness_summary = tmp_path / "ready_without_strategy_manifest.json"
    readiness_summary.write_text(
        json.dumps(
            {
                "config": {
                    "min_execution_fills": 30,
                    "requires_forward_freshness": True,
                    "requires_public_data_availability": True,
                    "requires_execution_validation": True,
                    "requires_execution_provenance": True,
                    "requires_signal_provenance": True,
                    "requires_recent_execution_evidence": True,
                    "requires_paper_shadow_capture_summary": True,
                    "requires_readiness_source_provenance": True,
                    "requires_readiness_runtime_source_hash": True,
                    "requires_readiness_input_hashes": True,
                },
                "inputs": {
                    "test_input": str(input_file),
                },
                "checks": {
                    "forward_freshness_clean": True,
                    "public_data_available": True,
                    "execution_validation_passed": True,
                    "execution_fill_evidence_available": True,
                    "filled_status_clean": True,
                    "execution_provenance_clean": True,
                    "signal_provenance_clean": True,
                    "execution_slippage_p95_clean": True,
                    "recent_execution_evidence_clean": True,
                    "paper_shadow_capture_summary_clean": True,
                    "execution_kill_switch_tested": True,
                    "execution_secrets_absent_from_repo": True,
                    "readiness_source_provenance_clean": True,
                    "readiness_runtime_source_hash_clean": True,
                    "readiness_input_hashes_clean": True,
                },
                "evidence": {
                    "forward_freshness_status": "forward_freshness_passed",
                    "forward_data_current": True,
                    "fresh_forward_evidence_available": True,
                    "public_data_status": "public_data_availability_passed",
                    "public_data_available": True,
                    "execution_validation_passed": True,
                    "execution_fill_count": 30,
                    "execution_fill_evidence_available": True,
                    "filled_status_clean": True,
                    "execution_provenance_clean": True,
                    "signal_provenance_clean": True,
                    "execution_slippage_p95_clean": True,
                    "recent_execution_evidence_clean": True,
                    "paper_shadow_capture_summary_clean": True,
                    "execution_kill_switch_tested": True,
                    "execution_secrets_absent_from_repo": True,
                    "readiness_source_commit": "current-source-commit",
                    "readiness_runtime_source_hash": "runtime-source-hash",
                    "readiness_runtime_source_clean": True,
                    "readiness_dirty_runtime_path_count": 0,
                    "readiness_dirty_runtime_paths": [],
                    "readiness_input_hashes": {
                        "test_input": input_hash,
                    },
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

    payload = launch.real_money_launch_preflight(
        out_dir=tmp_path / "real-money",
        arm_token=launch.REQUIRED_ARM_TOKEN,
        readiness_summary=readiness_summary,
    )

    assert payload["decision"]["allow_real_money_launch"] is False
    assert "readiness_strategy_manifest_clean" in payload["decision"]["failed_checks"]


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


def test_v142_paper_runner_writes_dashboard_state_files(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    price_csv.write_text(
        "\n".join(
            [
                "timestamp,price",
                "2026-01-01T00:00:00Z,100",
                "2026-01-01T00:01:00Z,100.5",
            ]
        ),
        encoding="utf-8",
    )
    signal_csv.write_text(
        "\n".join(
            [
                "timestamp,signal_id,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,live-long,1,base,0.61,30",
                "2026-01-01T00:00:00Z,bad-side,0,base,0.42,30",
            ]
        ),
        encoding="utf-8",
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=CsvPriceSource(price_csv, symbol="BTCUSDC"),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        config=PaperTradingConfig(initial_balance_usdc=10_000.0),
        clean=True,
        sleep=False,
    )

    assert summary["open_positions"] == 1
    positions = pd.read_csv(out_dir / "positions.csv")
    orders = pd.read_csv(out_dir / "order_events.csv")
    decisions = pd.read_csv(out_dir / "decisions.csv")
    assert positions["signal_id"].tolist() == ["live-long"]
    assert orders.loc[orders["signal_id"] == "live-long", "status"].iloc[0] == "filled"
    assert orders.loc[orders["signal_id"] == "bad-side", "status"].iloc[0] == "rejected"
    assert set(decisions["decision"].tolist()) >= {"accepted", "rejected", "no_signal"}


def test_v142_paper_runner_kill_switch_closes_open_positions(tmp_path: Path) -> None:
    signal_csv = tmp_path / "signals.csv"
    out_dir = tmp_path / "paper"
    signal_csv.write_text(
        "\n".join(
            [
                "timestamp,signal_id,side,leg,direction_probability,horizon_minutes",
                "2026-01-01T00:00:00Z,manual-close,1,base,0.61,30",
            ]
        ),
        encoding="utf-8",
    )

    summary = run_v142_paper_trading(
        out_dir=out_dir,
        market_source=_RequestKillSwitchAfterFirstSnapshotSource(out_dir),
        signal_provider=CsvSignalProvider(signal_csv, default_symbol="BTCUSDC"),
        config=PaperTradingConfig(initial_balance_usdc=10_000.0),
        clean=False,
        sleep=False,
    )

    assert summary["open_positions"] == 0
    trades = pd.read_csv(out_dir / "trades.csv")
    orders = pd.read_csv(out_dir / "order_events.csv")
    decisions = pd.read_csv(out_dir / "decisions.csv")
    assert "kill_switch_close" in trades["event_type"].tolist()
    assert "closed_by_kill_switch" in orders["status"].tolist()
    assert "kill_switch_active" in decisions["decision"].tolist()


def test_dashboard_state_includes_market_orders_positions_and_decisions(tmp_path: Path) -> None:
    run_dir = tmp_path / "paper"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps({"open_positions": 1, "final_equity_usdc": 10025.0, "trades": 1}),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "event_type": "snapshot",
                "symbol": "BTCUSDC",
                "price": 100.5,
                "equity_usdc": 10025.0,
                "drawdown_pct": -0.1,
                "open_positions": 1,
            }
        ]
    ).to_csv(run_dir / "balance.csv", index=False)
    pd.DataFrame(
        [{"signal_id": "p1", "symbol": "BTCUSDC", "side": 1, "unrealized_pnl_usdc": 25.0}]
    ).to_csv(run_dir / "positions.csv", index=False)
    pd.DataFrame(
        [{"timestamp": "2026-01-01T00:00:00Z", "signal_id": "p1", "status": "filled", "reason": "accepted"}]
    ).to_csv(run_dir / "order_events.csv", index=False)
    pd.DataFrame(
        [{"timestamp": "2026-01-01T00:00:00Z", "signal_id": "p1", "decision": "accepted", "reason": "passed_realtime_safe_checks"}]
    ).to_csv(run_dir / "decisions.csv", index=False)
    book_csv = tmp_path / "book.csv"
    book_csv.write_text(
        "\n".join(
            [
                "timestamp,bid_px_1,bid_sz_1,ask_px_1,ask_sz_1",
                "2026-01-01T00:00:00Z,100.0,2.0,101.0,3.0",
            ]
        ),
        encoding="utf-8",
    )

    state = build_dashboard_state(run_dir=run_dir, book_csv=book_csv, symbol="BTCUSDC")

    assert state["market"]["mid_price"] == 100.5
    assert state["market"]["spread_bps"] == pytest.approx(99.50248756218906)
    assert state["summary"]["open_positions"] == 1
    assert state["positions"][0]["signal_id"] == "p1"
    assert state["orders"][0]["status"] == "filled"
    assert state["decisions"][0]["decision"] == "accepted"
    assert state["kill_switch"]["active"] is False


def test_dashboard_admin_endpoints_require_authentication(tmp_path: Path) -> None:
    server = make_dashboard_server(
        run_dir=tmp_path,
        symbol="BTCUSDC",
        host="127.0.0.1",
        port=0,
        admin_user="jamie",
        admin_password="secret",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(f"{base_url}/api/kill-switch", method="POST"), timeout=5)
        assert exc.value.code == 401
        assert not (tmp_path / "kill_switch.json").exists()

        token = base64.b64encode(b"jamie:secret").decode("ascii")
        req = Request(
            f"{base_url}/api/kill-switch",
            data=b'{"reason":"test"}',
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=5) as response:
            assert response.status == 200
        assert json.loads((tmp_path / "kill_switch.json").read_text(encoding="utf-8"))["active"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_public_page_is_read_only_and_admin_page_has_controls(tmp_path: Path) -> None:
    server = make_dashboard_server(
        run_dir=tmp_path,
        symbol="BTCUSDC",
        host="127.0.0.1",
        port=0,
        admin_user="jamie",
        admin_password="secret",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        public_html = urlopen(f"{base_url}/", timeout=5).read().decode("utf-8")
        assert "Public View" in public_html
        assert "id=\"kill\"" not in public_html

        with pytest.raises(HTTPError) as exc:
            urlopen(f"{base_url}/admin", timeout=5)
        assert exc.value.code == 401

        token = base64.b64encode(b"jamie:secret").decode("ascii")
        req = Request(f"{base_url}/admin", headers={"Authorization": f"Basic {token}"})
        admin_html = urlopen(req, timeout=5).read().decode("utf-8")
        assert "Admin Panel" in admin_html
        assert "id=\"kill\"" in admin_html
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_admin_auth_accepts_password_hash(tmp_path: Path) -> None:
    server = make_dashboard_server(
        run_dir=tmp_path,
        symbol="BTCUSDC",
        host="127.0.0.1",
        port=0,
        admin_user="jamie",
        admin_password_sha256=hashlib.sha256(b"secret").hexdigest(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        token = base64.b64encode(b"jamie:secret").decode("ascii")
        req = Request(f"{base_url}/admin", headers={"Authorization": f"Basic {token}"})
        with urlopen(req, timeout=5) as response:
            body = response.read().decode("utf-8")
        assert response.status == 200
        assert "Admin Panel" in body
    finally:
        server.shutdown()
        server.server_close()


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
