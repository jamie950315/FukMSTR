from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .paper_trading import MarketDataSource, MarketSnapshot, PaperSignal, SignalProvider, _utc_timestamp


FILL_AUDIT_FIELDNAMES = [
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
    "signal_id",
    "signal_source",
    "market_source",
    "places_live_orders",
]


@dataclass(frozen=True)
class PaperShadowCaptureConfig:
    symbol: str = "BTCUSDC"
    venue: str = "binance"
    execution_mode: str = "paper_shadow_live"
    evidence_source: str = "live_capture"
    capture_id: str = "paper-shadow-capture"
    places_live_orders: bool = False


def _valid_price(price: object) -> bool:
    try:
        value = float(price)
    except (TypeError, ValueError):
        return False
    return pd.notna(value) and value > 0.0


def _valid_signal(signal: PaperSignal, snapshot: MarketSnapshot, *, symbol: str) -> bool:
    if signal.symbol.upper() != symbol.upper() or snapshot.symbol.upper() != symbol.upper():
        return False
    try:
        side = float(signal.side)
    except (TypeError, ValueError):
        return False
    return side in {-1.0, 1.0}


def _shadow_fill_row(
    *,
    snapshot: MarketSnapshot,
    signal: PaperSignal,
    config: PaperShadowCaptureConfig,
    sequence: int,
) -> dict[str, object]:
    timestamp = _utc_timestamp(snapshot.timestamp).isoformat()
    signal_id = str(signal.signal_id)
    order_id = f"{config.capture_id}-{sequence:06d}-{signal_id}"
    return {
        "timestamp": timestamp,
        "symbol": config.symbol.upper(),
        "side": int(float(signal.side)),
        "intended_price": float(snapshot.price),
        "fill_price": float(snapshot.price),
        "status": "filled",
        "venue": config.venue,
        "execution_mode": config.execution_mode,
        "evidence_source": config.evidence_source,
        "capture_id": config.capture_id,
        "order_id": order_id,
        "client_order_id": f"shadow-{order_id}",
        "exchange_timestamp": timestamp,
        "signal_id": signal_id,
        "signal_source": signal.source,
        "market_source": snapshot.source,
        "places_live_orders": config.places_live_orders,
    }


def _write_fill_audit(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=FILL_AUDIT_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_paper_shadow_fill_capture(
    *,
    market_source: MarketDataSource,
    signal_provider: SignalProvider,
    fill_audit_path: str | Path,
    config: PaperShadowCaptureConfig | None = None,
    ticks: int = 0,
    interval_sec: float = 60.0,
    sleep: bool = True,
) -> dict[str, object]:
    config = config or PaperShadowCaptureConfig()
    fill_path = Path(fill_audit_path)
    rows: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    snapshots = 0
    count = 0

    while True:
        if ticks and count >= int(ticks):
            break
        snapshot = market_source.next_snapshot()
        if snapshot is None:
            break
        snapshots += 1
        count += 1
        if str(snapshot.source).lower() == "synthetic":
            rejected.append(
                {
                    "timestamp": _utc_timestamp(snapshot.timestamp).isoformat(),
                    "reason": "synthetic_market_source",
                    "symbol": snapshot.symbol,
                }
            )
            if sleep and interval_sec > 0 and (not ticks or count < int(ticks)):
                time.sleep(float(interval_sec))
            continue
        if not _valid_price(snapshot.price):
            rejected.append(
                {
                    "timestamp": _utc_timestamp(snapshot.timestamp).isoformat(),
                    "reason": "invalid_market_price",
                    "symbol": snapshot.symbol,
                }
            )
            if sleep and interval_sec > 0 and (not ticks or count < int(ticks)):
                time.sleep(float(interval_sec))
            continue
        signals = signal_provider.signals_for_snapshot(snapshot)
        for signal in signals:
            if not _valid_signal(signal, snapshot, symbol=config.symbol):
                rejected.append(
                    {
                        "timestamp": _utc_timestamp(snapshot.timestamp).isoformat(),
                        "reason": "invalid_or_wrong_symbol_signal",
                        "symbol": signal.symbol,
                        "signal_id": signal.signal_id,
                    }
                )
                continue
            rows.append(_shadow_fill_row(snapshot=snapshot, signal=signal, config=config, sequence=len(rows) + 1))
        if sleep and interval_sec > 0 and (not ticks or count < int(ticks)):
            time.sleep(float(interval_sec))

    _write_fill_audit(fill_path, rows)
    failed_checks: list[str] = []
    if not rows:
        failed_checks.append("fill_evidence_available")
    if any(row.get("reason") == "synthetic_market_source" for row in rejected):
        failed_checks.append("synthetic_market_source")
    ready = bool(rows) and not failed_checks
    return {
        "version": "v210_btcusdc_paper_shadow_fill_capture",
        "config": {
            "symbol": config.symbol,
            "venue": config.venue,
            "execution_mode": config.execution_mode,
            "evidence_source": config.evidence_source,
            "capture_id": config.capture_id,
            "places_live_orders": config.places_live_orders,
            "changes_strategy_thresholds": False,
            "changes_entry_exit_logic": False,
            "changes_leverage_logic": False,
        },
        "outputs": {
            "fill_audit_csv": str(fill_path),
        },
        "evidence": {
            "snapshot_count": snapshots,
            "fill_count": len(rows),
            "rejected_count": len(rejected),
            "rejected_reasons": sorted({str(row["reason"]) for row in rejected}),
        },
        "decision": {
            "status": "paper_shadow_fill_capture_ready_for_v205" if ready else "paper_shadow_fill_capture_blocked",
            "places_live_orders": False,
            "failed_checks": failed_checks,
            "message": (
                "Paper-shadow fill audit was written for V205/V209 validation."
                if ready
                else "Paper-shadow fill audit is not sufficient for real-money validation yet."
            ),
        },
    }
