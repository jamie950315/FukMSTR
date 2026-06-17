from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.trade_replay import build_trade_replay_payload, write_trade_replay_page


def _sample_account_path() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": "2024-07-08T00:10:00Z",
                "source": "base_a",
                "leg": "base",
                "signal": 1,
                "position_weight": 1.0,
                "account_leverage": 3.5,
                "account_pnl_bps": -200.0,
                "account_return_pct": -2.0,
                "equity_return_pct": -2.0,
                "drawdown_pct": -2.0,
                "direction_probability": "",
                "high_confidence_rescue_5x": False,
            },
            {
                "timestamp": "2024-08-02T12:00:00Z",
                "source": "rescue_a",
                "leg": "rescue",
                "signal": -1,
                "position_weight": 0.5,
                "account_leverage": 5.0,
                "account_pnl_bps": 500.0,
                "account_return_pct": 5.0,
                "equity_return_pct": 3.0,
                "drawdown_pct": 0.0,
                "direction_probability": 0.67,
                "high_confidence_rescue_5x": True,
            },
        ]
    )


def test_build_trade_replay_payload_keeps_requested_time_window_and_money_fields() -> None:
    payload = build_trade_replay_payload(
        _sample_account_path(),
        start="2024-07-01",
        end="2026-06-12",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
    )

    assert payload["period"]["start"] == "2024-07-01T00:00:00+00:00"
    assert payload["period"]["end"] == "2026-06-12T23:59:59.999999+00:00"
    assert payload["summary"]["trade_count"] == 2
    assert payload["timeline"][0]["type"] == "boundary"
    assert payload["timeline"][-1]["type"] == "boundary"
    trade = payload["trades"][1]
    assert trade["amount_usdc"] > 0
    assert trade["leverage"] == 5.0
    assert trade["profit_pct"] == 5.0
    assert trade["result"] == "win"
    assert trade["balance_usdc"] == 10_300.0
    assert payload["timeline"][0]["visible_trade_count"] == 0
    assert payload["timeline"][1]["visible_trade_count"] == 1
    assert payload["timeline"][-1]["visible_trade_count"] == 2


def test_build_trade_replay_payload_treats_date_only_end_as_full_day() -> None:
    account_path = _sample_account_path()
    account_path.loc[len(account_path)] = {
        "timestamp": "2026-06-12T18:30:00Z",
        "source": "end_day",
        "leg": "base",
        "signal": 1,
        "position_weight": 1.0,
        "account_leverage": 3.5,
        "account_pnl_bps": 100.0,
        "account_return_pct": 1.0,
        "equity_return_pct": 4.0,
        "drawdown_pct": 0.0,
        "direction_probability": "",
        "high_confidence_rescue_5x": False,
    }

    payload = build_trade_replay_payload(
        account_path,
        start="2024-07-01",
        end="2026-06-12",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
    )

    assert payload["summary"]["trade_count"] == 3
    assert payload["trades"][-1]["timestamp"] == "2026-06-12T18:30:00+00:00"
    assert payload["timeline"][-1]["timestamp"] == "2026-06-12T23:59:59.999999+00:00"


def test_build_trade_replay_payload_keeps_date_only_end_display_in_requested_month() -> None:
    account_path = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-31T22:00:00Z",
                "source": "month_end",
                "leg": "base",
                "signal": 1,
                "position_weight": 1.0,
                "account_leverage": 1.0,
                "account_pnl_bps": 100.0,
                "account_return_pct": 1.0,
                "equity_return_pct": 1.0,
                "drawdown_pct": 0.0,
            }
        ]
    )

    payload = build_trade_replay_payload(
        account_path,
        start="2026-01-01",
        end="2026-01-31",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
    )

    assert payload["summary"]["trade_count"] == 1
    assert payload["timeline"][-1]["timestamp"].startswith("2026-01-31")


def test_build_trade_replay_payload_counts_same_timestamp_trades_by_replay_step() -> None:
    account_path = _sample_account_path()
    account_path.loc[1, "timestamp"] = account_path.loc[0, "timestamp"]

    payload = build_trade_replay_payload(
        account_path,
        start="2024-07-01",
        end="2024-07-08",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
    )

    trade_points = [point for point in payload["timeline"] if point["type"] == "trade"]
    assert [point["visible_trade_count"] for point in trade_points] == [1, 2]


def test_build_trade_replay_payload_preserves_input_order_for_same_timestamp_trades() -> None:
    rows = []
    for index in range(50):
        rows.append(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "source": f"s{index}",
                "leg": "base",
                "signal": 1,
                "position_weight": 1.0,
                "account_leverage": 1.0,
                "account_pnl_bps": float(index),
                "account_return_pct": 0.01,
                "equity_return_pct": float(index) / 100.0,
                "drawdown_pct": 0.0,
            }
        )

    payload = build_trade_replay_payload(
        pd.DataFrame(rows),
        start="2026-01-01",
        end="2026-01-01",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
    )

    assert [trade["source"] for trade in payload["trades"]] == [f"s{index}" for index in range(50)]


def test_build_trade_replay_payload_fills_missing_side_from_signal_reference() -> None:
    account_path = _sample_account_path()
    account_path.loc[0, "signal"] = pd.NA
    account_path["signal_reference"] = [pd.NA, pd.NA]
    signal_reference = pd.DataFrame(
        [
            {"timestamp": "2024-07-08T00:10:00Z", "signal": -1},
            {"timestamp": "2024-08-02T12:00:00Z", "signal": 1},
        ]
    )

    payload = build_trade_replay_payload(
        account_path,
        start="2024-07-01",
        end="2026-06-12",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
        signal_reference=signal_reference,
    )

    assert payload["trades"][0]["side"] == "short"
    assert payload["trades"][0]["side_source"] == "signal_reference"
    assert payload["trades"][1]["side"] == "short"
    assert payload["trades"][1]["side_source"] == "account_path"


def test_build_trade_replay_payload_does_not_render_pandas_missing_values() -> None:
    account_path = _sample_account_path()
    account_path.loc[0, "signal"] = pd.NA

    payload = build_trade_replay_payload(
        account_path,
        start="2024-07-01",
        end="2026-06-12",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
    )

    assert payload["trades"][0]["side"] == "n/a"
    assert payload["trades"][0]["side_source"] == ""


def test_build_trade_replay_payload_monthly_return_uses_balance_change_not_trade_sum() -> None:
    account_path = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "source": "m1",
                "leg": "base",
                "signal": 1,
                "position_weight": 1.0,
                "account_leverage": 1.0,
                "account_pnl_bps": 1000.0,
                "account_return_pct": 10.0,
                "equity_return_pct": 10.0,
                "drawdown_pct": 0.0,
            },
            {
                "timestamp": "2026-01-02T00:00:00Z",
                "source": "m2",
                "leg": "base",
                "signal": 1,
                "position_weight": 1.0,
                "account_leverage": 1.0,
                "account_pnl_bps": -1000.0,
                "account_return_pct": -10.0,
                "equity_return_pct": -1.0,
                "drawdown_pct": -1.0,
            },
        ]
    )

    payload = build_trade_replay_payload(
        account_path,
        start="2026-01-01",
        end="2026-01-31",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
    )

    assert round(payload["monthly_returns_pct"]["2026-01"], 8) == -1.0


def test_build_trade_replay_payload_uses_selected_strategy_return_column() -> None:
    account_path = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "source": "candidate_1",
                "leg": "base",
                "signal": 1,
                "position_weight": 1.0,
                "account_leverage": 1.0,
                "account_pnl_bps": -9999.0,
                "account_return_pct": -99.0,
                "equity_return_pct": -99.0,
                "drawdown_pct": -99.0,
                "v193_account_pnl_bps": 1000.0,
                "v193_account_return_pct": 10.0,
            },
            {
                "timestamp": "2026-01-02T00:00:00Z",
                "source": "candidate_2",
                "leg": "base",
                "signal": 1,
                "position_weight": 1.0,
                "account_leverage": 1.0,
                "account_pnl_bps": -9999.0,
                "account_return_pct": -99.0,
                "equity_return_pct": -198.0,
                "drawdown_pct": -198.0,
                "v193_account_pnl_bps": -1500.0,
                "v193_account_return_pct": -15.0,
            },
            {
                "timestamp": "2026-01-03T00:00:00Z",
                "source": "candidate_3",
                "leg": "base",
                "signal": 1,
                "position_weight": 1.0,
                "account_leverage": 1.0,
                "account_pnl_bps": -9999.0,
                "account_return_pct": -99.0,
                "equity_return_pct": -297.0,
                "drawdown_pct": -297.0,
                "v193_account_pnl_bps": 2000.0,
                "v193_account_return_pct": 20.0,
            },
        ]
    )

    payload = build_trade_replay_payload(
        account_path,
        start="2026-01-01",
        end="2026-01-31",
        initial_balance_usdc=10_000.0,
        title="V193 BTCUSDC Replay",
        account_return_col="v193_account_return_pct",
        account_pnl_col="v193_account_pnl_bps",
    )

    assert round(payload["summary"]["total_return_pct"], 8) == 15.0
    assert payload["summary"]["final_balance_usdc"] == 11_500.0
    assert payload["summary"]["max_drawdown_pct"] == -15.0
    assert [trade["profit_pct"] for trade in payload["trades"]] == [10.0, -15.0, 20.0]
    assert [trade["account_pnl_bps"] for trade in payload["trades"]] == [1000.0, -1500.0, 2000.0]


def test_write_trade_replay_page_contains_playback_controls_chart_metrics_and_logs(tmp_path: Path) -> None:
    html_path = tmp_path / "replay.html"

    result = write_trade_replay_page(
        account_path=_sample_account_path(),
        out=html_path,
        start="2024-07-01",
        end="2026-06-12",
        initial_balance_usdc=10_000.0,
        title="V142 BTCUSDC Replay",
    )

    html = html_path.read_text(encoding="utf-8")
    data = json.loads((tmp_path / "replay_data.json").read_text(encoding="utf-8"))
    assert result["html"] == str(html_path)
    assert result["data_json"] == str(tmp_path / "replay_data.json")
    assert "<canvas id=\"balanceChart\"" in html
    assert "id=\"playPause\"" in html
    assert "id=\"speedSelect\"" in html
    assert "id=\"timeSlider\"" in html
    assert "Since Start" in html
    assert "Since This Month" in html
    assert "Amount" in html
    assert "Leverage" in html
    assert "Profit %" in html
    assert data["summary"]["trade_count"] == 2
    assert "Side Source" in html


def test_trade_replay_v142_cli_writes_page_and_data(tmp_path: Path, monkeypatch) -> None:
    from lob_microprice_lab.cli import main

    account_path = tmp_path / "account_path.csv"
    out_path = tmp_path / "replay" / "index.html"
    _sample_account_path().to_csv(account_path, index=False)
    monkeypatch.chdir(tmp_path)

    rc = main(
        [
            "trade-replay-v142",
            "--account-path",
            str(account_path),
            "--out",
            str(out_path),
            "--start",
            "2024-07-01",
            "--end",
            "2026-06-12",
            "--initial-balance-usdc",
            "10000",
            "--account-return-col",
            "account_return_pct",
            "--account-pnl-col",
            "account_pnl_bps",
        ]
    )

    assert rc == 0
    assert out_path.exists()
    assert (out_path.parent / "replay_data.json").exists()


def test_trade_replay_v193_cli_defaults_to_v193_strategy_columns(tmp_path: Path, monkeypatch) -> None:
    from lob_microprice_lab.cli import main

    account_path = tmp_path / "v193_account_path.csv"
    out_path = tmp_path / "replay" / "index.html"
    sample = _sample_account_path()
    sample["v193_account_return_pct"] = [10.0, -2.5]
    sample["v193_account_pnl_bps"] = [1000.0, -250.0]
    sample.to_csv(account_path, index=False)
    monkeypatch.chdir(tmp_path)

    rc = main(
        [
            "trade-replay-v193",
            "--account-path",
            str(account_path),
            "--out",
            str(out_path),
        ]
    )

    data = json.loads((out_path.parent / "replay_data.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert data["title"] == "BTCUSDC V193 Trading Replay"
    assert data["period"]["end"] == "2026-06-15T23:59:59.999999+00:00"
    assert [trade["profit_pct"] for trade in data["trades"]] == [10.0, -2.5]
