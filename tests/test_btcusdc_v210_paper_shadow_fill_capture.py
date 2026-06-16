from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from lob_microprice_lab.paper_shadow_capture import PaperShadowCaptureConfig, run_paper_shadow_fill_capture
from lob_microprice_lab.paper_trading import CsvPriceSource, CsvSignalProvider, SyntheticPriceSource


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v210_paper_shadow_fill_capture.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v210_paper_shadow_fill_capture", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_price_csv(path: Path, *, rows: int = 32) -> None:
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-16T00:00:00Z", periods=rows, freq="min"),
            "price": [100_000.0 + idx for idx in range(rows)],
        }
    ).to_csv(path, index=False)


def _write_signal_csv(path: Path, *, rows: int = 32) -> None:
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-16T00:00:00Z", periods=rows, freq="min"),
            "signal_id": [f"sig-{idx}" for idx in range(rows)],
            "symbol": ["BTCUSDC"] * rows,
            "side": [1, -1] * (rows // 2),
            "source": ["v210_test_signal"] * rows,
            "leg": ["base"] * rows,
            "direction_probability": [0.61] * rows,
        }
    ).to_csv(path, index=False)


def test_paper_shadow_capture_writes_v205_provenance_fill_audit(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    fill_audit = tmp_path / "fill_audit.csv"
    _write_price_csv(price_csv)
    _write_signal_csv(signal_csv)

    payload = run_paper_shadow_fill_capture(
        market_source=CsvPriceSource(price_csv),
        signal_provider=CsvSignalProvider(signal_csv),
        fill_audit_path=fill_audit,
        config=PaperShadowCaptureConfig(capture_id="capture-unit", evidence_source="unit_live_capture"),
        ticks=32,
        sleep=False,
    )

    fills = pd.read_csv(fill_audit)
    assert payload["decision"]["status"] == "paper_shadow_fill_capture_ready_for_v205"
    assert payload["decision"]["places_live_orders"] is False
    assert payload["evidence"]["fill_count"] == 32
    assert set(
        [
            "timestamp",
            "symbol",
            "side",
            "intended_price",
            "fill_price",
            "status",
            "venue",
            "execution_mode",
            "evidence_source",
            "capture_id",
            "order_id",
            "client_order_id",
            "exchange_timestamp",
        ]
    ).issubset(fills.columns)
    assert fills["execution_mode"].eq("paper_shadow_live").all()
    assert fills["evidence_source"].eq("unit_live_capture").all()
    assert fills["status"].eq("filled").all()


def test_paper_shadow_capture_does_not_convert_synthetic_prices_into_fill_evidence(tmp_path: Path) -> None:
    signal_csv = tmp_path / "signals.csv"
    fill_audit = tmp_path / "fill_audit.csv"
    _write_signal_csv(signal_csv, rows=2)

    payload = run_paper_shadow_fill_capture(
        market_source=SyntheticPriceSource(),
        signal_provider=CsvSignalProvider(signal_csv),
        fill_audit_path=fill_audit,
        config=PaperShadowCaptureConfig(capture_id="capture-synthetic"),
        ticks=2,
        sleep=False,
    )

    assert payload["decision"]["status"] == "paper_shadow_fill_capture_blocked"
    assert payload["evidence"]["fill_count"] == 0
    assert "synthetic_market_source" in payload["decision"]["failed_checks"]


def test_paper_shadow_capture_handles_empty_signal_csv_without_timezone_error(tmp_path: Path) -> None:
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    fill_audit = tmp_path / "fill_audit.csv"
    _write_price_csv(price_csv, rows=1)
    pd.DataFrame(columns=["timestamp", "side", "signal_id", "symbol", "source", "leg"]).to_csv(signal_csv, index=False)

    payload = run_paper_shadow_fill_capture(
        market_source=CsvPriceSource(price_csv),
        signal_provider=CsvSignalProvider(signal_csv),
        fill_audit_path=fill_audit,
        ticks=1,
        sleep=False,
    )

    assert payload["decision"]["status"] == "paper_shadow_fill_capture_blocked"
    assert payload["evidence"]["fill_count"] == 0


def test_v210_script_writes_report_and_fill_audit(tmp_path: Path) -> None:
    module = _load_module()
    price_csv = tmp_path / "prices.csv"
    signal_csv = tmp_path / "signals.csv"
    _write_price_csv(price_csv)
    _write_signal_csv(signal_csv)

    payload = module.run(
        price_csv=price_csv,
        signal_csv=signal_csv,
        out_dir=tmp_path / "out",
        fill_audit_path=tmp_path / "fill_audit.csv",
        report_path=tmp_path / "report.md",
        ticks=32,
        no_sleep=True,
        capture_id="capture-script",
        evidence_source="unit_live_capture",
    )

    assert payload["decision"]["status"] == "paper_shadow_fill_capture_ready_for_v205"
    assert Path(payload["outputs"]["fill_audit_csv"]).exists()
    assert Path(payload["outputs"]["report"]).exists()
