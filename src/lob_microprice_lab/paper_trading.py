from __future__ import annotations

import csv
import html
import json
import math
import shutil
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from .data_schema import parse_timestamp_series


@dataclass(frozen=True)
class MarketSnapshot:
    timestamp: pd.Timestamp
    symbol: str
    price: float
    source: str


@dataclass(frozen=True)
class PaperSignal:
    timestamp: pd.Timestamp
    signal_id: str
    symbol: str
    side: int | float
    source: str
    leg: str
    direction_probability: float | None = None
    horizon_minutes: int = 30
    available_at: pd.Timestamp | None = None


@dataclass
class PaperPosition:
    signal_id: str
    symbol: str
    side: int
    source: str
    leg: str
    direction_probability: float | None
    entry_timestamp: pd.Timestamp
    exit_due_timestamp: pd.Timestamp
    entry_price: float
    leverage: float
    notional_usdc: float
    entry_fee_usdc: float


@dataclass(frozen=True)
class PaperTradingConfig:
    symbol: str = "BTCUSDC"
    strategy_mode: str = "realtime_safe"
    initial_balance_usdc: float = 10_000.0
    fee_bps_per_side: float = 4.0
    realtime_safe_leverage: float = 1.0
    max_realtime_signal_age_minutes: float = 5.0
    high_confidence_probability_floor: float = 0.66
    high_confidence_rescue_leverage: float = 5.0
    high_account_leverage: float = 3.5
    mid_account_leverage: float = 2.25
    low_account_leverage: float = 1.25
    mid_drawdown_trigger_pct: float = -5.0
    low_drawdown_trigger_pct: float = -15.0
    default_horizon_minutes: int = 30

    def __post_init__(self) -> None:
        if self.strategy_mode not in {"realtime_safe", "research_v142"}:
            raise ValueError("strategy_mode must be realtime_safe or research_v142")


EVENT_FIELDNAMES = [
    "timestamp",
    "event_type",
    "symbol",
    "price",
    "balance_usdc",
    "equity_usdc",
    "drawdown_pct",
    "open_positions",
    "opened",
    "closed",
    "rejected_signal_count",
    "source",
    "kill_switch_active",
    "error",
]

TRADE_FIELDNAMES = [
    "timestamp",
    "event_type",
    "signal_id",
    "symbol",
    "side",
    "source",
    "leg",
    "direction_probability",
    "high_confidence_rescue_5x",
    "entry_timestamp",
    "entry_price",
    "exit_price",
    "price",
    "leverage",
    "notional_usdc",
    "fee_usdc",
    "gross_pnl_usdc",
    "net_pnl_usdc",
    "balance_usdc",
    "equity_usdc",
    "drawdown_pct",
    "close_reason",
]

REJECTED_SIGNAL_FIELDNAMES = [
    "timestamp",
    "signal_id",
    "symbol",
    "snapshot_symbol",
    "signal_timestamp",
    "available_at",
    "side",
    "source",
    "leg",
    "reason",
    "max_realtime_signal_age_minutes",
]

POSITION_FIELDNAMES = [
    "snapshot_timestamp",
    "signal_id",
    "symbol",
    "side",
    "source",
    "leg",
    "direction_probability",
    "entry_timestamp",
    "exit_due_timestamp",
    "entry_price",
    "mark_price",
    "leverage",
    "notional_usdc",
    "entry_fee_usdc",
    "unrealized_pnl_usdc",
    "unrealized_return_pct",
    "age_minutes",
    "time_to_exit_minutes",
]

ORDER_EVENT_FIELDNAMES = [
    "timestamp",
    "signal_id",
    "symbol",
    "side",
    "status",
    "event_type",
    "source",
    "leg",
    "price",
    "notional_usdc",
    "leverage",
    "reason",
    "dry_run",
    "order_type",
]

DECISION_FIELDNAMES = [
    "timestamp",
    "signal_id",
    "symbol",
    "side",
    "source",
    "leg",
    "decision",
    "reason",
    "direction_probability",
    "snapshot_price",
    "result",
]


class MarketDataSource(Protocol):
    def next_snapshot(self) -> MarketSnapshot | None:
        ...


class SignalProvider(Protocol):
    def signals_for_snapshot(self, snapshot: MarketSnapshot) -> list[PaperSignal]:
        ...


def _utc_timestamp(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


class BinancePublicTickerSource:
    """Public price adapter. It does not require API keys and does not place orders."""

    def __init__(self, *, symbol: str = "BTCUSDC", market: str = "spot") -> None:
        self.symbol = symbol.upper()
        self.market = market

    def _url(self) -> str:
        query = urllib.parse.urlencode({"symbol": self.symbol})
        if self.market == "um-futures":
            return f"https://fapi.binance.com/fapi/v1/ticker/price?{query}"
        return f"https://api.binance.com/api/v3/ticker/price?{query}"

    def next_snapshot(self) -> MarketSnapshot:
        req = urllib.request.Request(self._url(), headers={"User-Agent": "lob-microprice-lab-paper/0.1"})
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return MarketSnapshot(
            timestamp=pd.Timestamp.utcnow(),
            symbol=str(payload.get("symbol", self.symbol)).upper(),
            price=float(payload["price"]),
            source=f"binance-public-{self.market}",
        )


class CsvPriceSource:
    def __init__(self, path: str | Path, *, symbol: str = "BTCUSDC") -> None:
        frame = pd.read_csv(path)
        if "timestamp" not in frame.columns or "price" not in frame.columns:
            raise ValueError("price CSV must contain timestamp and price columns")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
        self.frame = frame.dropna(subset=["timestamp", "price"]).sort_values("timestamp").reset_index(drop=True)
        self.symbol = symbol.upper()
        self.index = 0

    def next_snapshot(self) -> MarketSnapshot | None:
        if self.index >= len(self.frame):
            return None
        row = self.frame.iloc[self.index]
        self.index += 1
        return MarketSnapshot(
            timestamp=pd.to_datetime(row["timestamp"], utc=True),
            symbol=self.symbol,
            price=float(row["price"]),
            source="csv",
        )


class BookCsvPriceSource:
    def __init__(self, path: str | Path, *, symbol: str = "BTCUSDC") -> None:
        frame = pd.read_csv(path)
        required = {"timestamp", "bid_px_1", "ask_px_1"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"book CSV missing required columns: {sorted(missing)}")
        frame["timestamp"] = parse_timestamp_series(frame["timestamp"])
        frame["bid_px_1"] = pd.to_numeric(frame["bid_px_1"], errors="coerce")
        frame["ask_px_1"] = pd.to_numeric(frame["ask_px_1"], errors="coerce")
        frame["price"] = (frame["bid_px_1"] + frame["ask_px_1"]) / 2.0
        valid = (
            frame["timestamp"].notna()
            & frame["bid_px_1"].gt(0)
            & frame["ask_px_1"].gt(0)
            & frame["bid_px_1"].lt(frame["ask_px_1"])
            & frame["price"].map(_is_valid_market_price)
        )
        self.frame = frame.loc[valid, ["timestamp", "price"]].sort_values("timestamp").reset_index(drop=True)
        self.symbol = symbol.upper()
        self.index = 0

    def next_snapshot(self) -> MarketSnapshot | None:
        if self.index >= len(self.frame):
            return None
        row = self.frame.iloc[self.index]
        self.index += 1
        return MarketSnapshot(
            timestamp=pd.to_datetime(row["timestamp"], utc=True),
            symbol=self.symbol,
            price=float(row["price"]),
            source="book-csv",
        )


class SyntheticPriceSource:
    def __init__(self, *, symbol: str = "BTCUSDC", start_price: float = 100_000.0, step_bps: float = 4.0, start: str = "2026-01-01T00:00:00Z", interval_sec: float = 60.0) -> None:
        self.symbol = symbol.upper()
        self.start_price = float(start_price)
        self.step_bps = float(step_bps)
        self.timestamp = pd.Timestamp(start)
        self.interval = pd.Timedelta(seconds=float(interval_sec))
        self.index = 0

    def next_snapshot(self) -> MarketSnapshot:
        # Deterministic wave: useful for smoke tests and local demos without network access.
        price = self.start_price * (1.0 + math.sin(self.index / 4.0) * self.step_bps / 10_000.0)
        snapshot = MarketSnapshot(self.timestamp, self.symbol, float(price), "synthetic")
        self.timestamp += self.interval
        self.index += 1
        return snapshot


class NoSignalProvider:
    def signals_for_snapshot(self, snapshot: MarketSnapshot) -> list[PaperSignal]:
        return []


class CsvSignalProvider:
    def __init__(self, path: str | Path, *, default_symbol: str = "BTCUSDC", default_horizon_minutes: int = 30) -> None:
        frame = pd.read_csv(path)
        if "timestamp" not in frame.columns:
            raise ValueError("signal CSV must contain a timestamp column")
        if "side" not in frame.columns and "signal" not in frame.columns:
            raise ValueError("signal CSV must contain side or signal column")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        available_col = "available_at" if "available_at" in frame.columns else "generated_at" if "generated_at" in frame.columns else None
        frame["available_at"] = (
            pd.to_datetime(frame[available_col], utc=True, errors="coerce")
            if available_col
            else pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
        )
        side_col = "side" if "side" in frame.columns else "signal"
        frame["side"] = pd.to_numeric(frame[side_col], errors="coerce").fillna(0)
        frame["symbol"] = frame.get("symbol", default_symbol)
        frame["source"] = frame.get("source", "manual")
        frame["leg"] = frame.get("leg", "base")
        frame["direction_probability"] = pd.to_numeric(frame.get("direction_probability"), errors="coerce") if "direction_probability" in frame.columns else pd.NA
        horizon_values = frame["horizon_minutes"] if "horizon_minutes" in frame.columns else pd.Series(
            [default_horizon_minutes] * len(frame),
            index=frame.index,
        )
        frame["horizon_minutes"] = pd.to_numeric(horizon_values, errors="coerce").fillna(default_horizon_minutes).astype(int)
        if "signal_id" not in frame.columns:
            frame["signal_id"] = [f"csv-{i}" for i in range(len(frame))]
        self.frame = frame.sort_values("timestamp").reset_index(drop=True)
        self.emitted: set[str] = set()

    def signals_for_snapshot(self, snapshot: MarketSnapshot) -> list[PaperSignal]:
        snapshot_ts = _utc_timestamp(snapshot.timestamp)
        effective_available_at = self.frame["available_at"].fillna(self.frame["timestamp"])
        ready = self.frame.loc[(self.frame["timestamp"] <= snapshot_ts) & (effective_available_at <= snapshot_ts)]
        out: list[PaperSignal] = []
        for _, row in ready.iterrows():
            signal_id = str(row["signal_id"])
            if signal_id in self.emitted:
                continue
            self.emitted.add(signal_id)
            prob = row["direction_probability"]
            out.append(
                PaperSignal(
                    timestamp=pd.to_datetime(row["timestamp"], utc=True),
                    signal_id=signal_id,
                    symbol=str(row["symbol"]).upper(),
                    side=float(row["side"]),
                    source=str(row["source"]),
                    leg=str(row["leg"]),
                    direction_probability=None if pd.isna(prob) else float(prob),
                    horizon_minutes=int(row["horizon_minutes"]),
                    available_at=None if pd.isna(row["available_at"]) else pd.to_datetime(row["available_at"], utc=True),
                )
            )
        return out


class V142LeveragePolicy:
    def __init__(self, config: PaperTradingConfig) -> None:
        self.config = config

    def leverage_for_signal(self, signal: PaperSignal, *, prior_drawdown_pct: float) -> tuple[float, bool]:
        if self.config.strategy_mode == "realtime_safe":
            return self.config.realtime_safe_leverage, False
        if prior_drawdown_pct <= self.config.low_drawdown_trigger_pct:
            return self.config.low_account_leverage, False
        if prior_drawdown_pct <= self.config.mid_drawdown_trigger_pct:
            return self.config.mid_account_leverage, False
        high_confidence = (
            signal.leg == "rescue"
            and signal.direction_probability is not None
            and signal.direction_probability >= self.config.high_confidence_probability_floor
        )
        if high_confidence:
            return self.config.high_confidence_rescue_leverage, True
        return self.config.high_account_leverage, False


class PaperBroker:
    def __init__(self, config: PaperTradingConfig) -> None:
        self.config = config
        self.balance_usdc = float(config.initial_balance_usdc)
        self.peak_equity_usdc = float(config.initial_balance_usdc)
        self.open_positions: list[PaperPosition] = []
        self.trades: list[dict[str, object]] = []
        self.events: list[dict[str, object]] = []
        self.rejected_signals: list[dict[str, object]] = []
        self.leverage_policy = V142LeveragePolicy(config)

    def equity_usdc(self, snapshot: MarketSnapshot | None = None) -> float:
        if snapshot is None:
            return self.balance_usdc
        unrealized = 0.0
        for position in self.open_positions:
            ret = (snapshot.price - position.entry_price) / position.entry_price * position.side
            unrealized += position.notional_usdc * ret
        return self.balance_usdc + unrealized

    def drawdown_pct(self, snapshot: MarketSnapshot | None = None) -> float:
        equity = self.equity_usdc(snapshot)
        return self._drawdown_from_equity(equity)

    def _drawdown_from_equity(self, equity: float) -> float:
        if equity > self.peak_equity_usdc:
            self.peak_equity_usdc = equity
        return (equity / self.peak_equity_usdc - 1.0) * 100.0 if self.peak_equity_usdc else 0.0

    def open_notional_usdc(self) -> float:
        return sum(position.notional_usdc for position in self.open_positions)

    def on_snapshot(self, snapshot: MarketSnapshot, signals: list[PaperSignal]) -> dict[str, object]:
        if not _is_valid_market_price(snapshot.price):
            event = _market_data_error_event(config=self.config, broker=self, snapshot=snapshot)
            self.events.append(event)
            return event
        closed = self._close_due_positions(snapshot)
        admitted, rejected = self._admitted_signals(snapshot, signals)
        self.rejected_signals.extend(rejected)
        opened = [self._open_position(snapshot, signal) for signal in admitted]
        event = self.snapshot_event(
            snapshot,
            opened=len([row for row in opened if row is not None]),
            closed=len(closed),
            rejected_signal_count=len(rejected),
            kill_switch_active=False,
        )
        self.events.append(event)
        return event

    def snapshot_event(
        self,
        snapshot: MarketSnapshot,
        *,
        opened: int,
        closed: int,
        rejected_signal_count: int,
        kill_switch_active: bool,
    ) -> dict[str, object]:
        equity = self.equity_usdc(snapshot)
        if equity > self.peak_equity_usdc:
            self.peak_equity_usdc = equity
        drawdown = (equity / self.peak_equity_usdc - 1.0) * 100.0 if self.peak_equity_usdc else 0.0
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "event_type": "snapshot",
            "symbol": snapshot.symbol,
            "price": snapshot.price,
            "balance_usdc": self.balance_usdc,
            "equity_usdc": equity,
            "drawdown_pct": drawdown,
            "open_positions": len(self.open_positions),
            "opened": opened,
            "closed": closed,
            "rejected_signal_count": rejected_signal_count,
            "source": snapshot.source,
            "kill_switch_active": kill_switch_active,
        }

    def _admitted_signals(self, snapshot: MarketSnapshot, signals: list[PaperSignal]) -> tuple[list[PaperSignal], list[dict[str, object]]]:
        if self.config.strategy_mode != "realtime_safe":
            return [signal for signal in signals if self._matches_snapshot_symbol(signal, snapshot) and self._has_valid_side(signal)], []
        admitted: list[PaperSignal] = []
        rejected: list[dict[str, object]] = []
        for signal in signals:
            if not self._matches_snapshot_symbol(signal, snapshot):
                rejected.append(self._rejected_signal_row(snapshot, signal, reason="wrong_symbol"))
                continue
            if not self._has_valid_side(signal):
                rejected.append(self._rejected_signal_row(snapshot, signal, reason="invalid_side"))
                continue
            signal_ts = _utc_timestamp(signal.timestamp)
            snapshot_ts = _utc_timestamp(snapshot.timestamp)
            available_at = None if signal.available_at is None else _utc_timestamp(signal.available_at)
            if available_at is not None and snapshot_ts < available_at:
                rejected.append(self._rejected_signal_row(snapshot, signal, reason="future_available_at"))
                continue
            age = snapshot_ts - signal_ts
            max_age = pd.Timedelta(minutes=float(self.config.max_realtime_signal_age_minutes))
            if age < pd.Timedelta(0):
                rejected.append(self._rejected_signal_row(snapshot, signal, reason="future_signal"))
                continue
            if age > max_age:
                rejected.append(self._rejected_signal_row(snapshot, signal, reason="stale_signal"))
                continue
            admitted.append(signal)
        return admitted, rejected

    def _matches_snapshot_symbol(self, signal: PaperSignal, snapshot: MarketSnapshot) -> bool:
        return str(signal.symbol).upper() == snapshot.symbol.upper()

    def _has_valid_side(self, signal: PaperSignal) -> bool:
        side = float(signal.side)
        return math.isfinite(side) and side in {-1.0, 1.0}

    def _rejected_signal_row(self, snapshot: MarketSnapshot, signal: PaperSignal, *, reason: str) -> dict[str, object]:
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "signal_id": signal.signal_id,
            "symbol": signal.symbol,
            "snapshot_symbol": snapshot.symbol,
            "signal_timestamp": signal.timestamp.isoformat(),
            "available_at": "" if signal.available_at is None else _utc_timestamp(signal.available_at).isoformat(),
            "side": signal.side,
            "source": signal.source,
            "leg": signal.leg,
            "reason": reason,
            "max_realtime_signal_age_minutes": self.config.max_realtime_signal_age_minutes,
        }

    def _open_position(self, snapshot: MarketSnapshot, signal: PaperSignal) -> dict[str, object] | None:
        prior_drawdown = self.drawdown_pct(snapshot)
        leverage, high_confidence_5x = self.leverage_policy.leverage_for_signal(signal, prior_drawdown_pct=prior_drawdown)
        max_total_notional = max(0.0, self.equity_usdc(snapshot)) * leverage
        remaining_notional = max(0.0, max_total_notional - self.open_notional_usdc())
        notional = min(max(0.0, self.balance_usdc) * leverage, remaining_notional)
        if notional <= 0.0:
            return None
        fee = notional * self.config.fee_bps_per_side / 10_000.0
        self.balance_usdc -= fee
        position = PaperPosition(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            side=int(signal.side),
            source=signal.source,
            leg=signal.leg,
            direction_probability=signal.direction_probability,
            entry_timestamp=snapshot.timestamp,
            exit_due_timestamp=snapshot.timestamp + pd.Timedelta(minutes=int(signal.horizon_minutes)),
            entry_price=float(snapshot.price),
            leverage=float(leverage),
            notional_usdc=float(notional),
            entry_fee_usdc=float(fee),
        )
        self.open_positions.append(position)
        row = {
            "timestamp": snapshot.timestamp.isoformat(),
            "event_type": "open",
            "signal_id": signal.signal_id,
            "symbol": signal.symbol,
            "side": int(signal.side),
            "source": signal.source,
            "leg": signal.leg,
            "direction_probability": signal.direction_probability,
            "high_confidence_rescue_5x": high_confidence_5x,
            "price": snapshot.price,
            "leverage": leverage,
            "notional_usdc": notional,
            "fee_usdc": fee,
            "balance_usdc": self.balance_usdc,
            "equity_usdc": self.equity_usdc(snapshot),
            "drawdown_pct": self.drawdown_pct(snapshot),
        }
        self.trades.append(row)
        return row

    def _close_due_positions(self, snapshot: MarketSnapshot) -> list[dict[str, object]]:
        still_open: list[PaperPosition] = []
        due: list[PaperPosition] = []
        closed: list[dict[str, object]] = []
        for position in self.open_positions:
            if snapshot.timestamp < position.exit_due_timestamp:
                still_open.append(position)
                continue
            due.append(position)
        self.open_positions = still_open
        for position in due:
            row = self._close_position_row(snapshot, position, event_type="close", close_reason="scheduled_exit")
            self.trades.append(row)
            closed.append(row)
        return closed

    def force_close_all_positions(self, snapshot: MarketSnapshot, *, reason: str = "kill_switch") -> list[dict[str, object]]:
        due = list(self.open_positions)
        self.open_positions = []
        closed: list[dict[str, object]] = []
        for position in due:
            row = self._close_position_row(snapshot, position, event_type="kill_switch_close", close_reason=reason)
            self.trades.append(row)
            closed.append(row)
        return closed

    def position_rows(self, snapshot: MarketSnapshot) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        snapshot_ts = _utc_timestamp(snapshot.timestamp)
        for position in self.open_positions:
            ret = (snapshot.price - position.entry_price) / position.entry_price * position.side
            age = snapshot_ts - _utc_timestamp(position.entry_timestamp)
            time_to_exit = _utc_timestamp(position.exit_due_timestamp) - snapshot_ts
            rows.append(
                {
                    "snapshot_timestamp": snapshot.timestamp.isoformat(),
                    "signal_id": position.signal_id,
                    "symbol": position.symbol,
                    "side": position.side,
                    "source": position.source,
                    "leg": position.leg,
                    "direction_probability": position.direction_probability,
                    "entry_timestamp": position.entry_timestamp.isoformat(),
                    "exit_due_timestamp": position.exit_due_timestamp.isoformat(),
                    "entry_price": position.entry_price,
                    "mark_price": snapshot.price,
                    "leverage": position.leverage,
                    "notional_usdc": position.notional_usdc,
                    "entry_fee_usdc": position.entry_fee_usdc,
                    "unrealized_pnl_usdc": position.notional_usdc * ret,
                    "unrealized_return_pct": ret * 100.0,
                    "age_minutes": age.total_seconds() / 60.0,
                    "time_to_exit_minutes": time_to_exit.total_seconds() / 60.0,
                }
            )
        return rows

    def _close_position_row(
        self,
        snapshot: MarketSnapshot,
        position: PaperPosition,
        *,
        event_type: str,
        close_reason: str,
    ) -> dict[str, object]:
        ret = (snapshot.price - position.entry_price) / position.entry_price * position.side
        gross_pnl = position.notional_usdc * ret
        exit_fee = position.notional_usdc * self.config.fee_bps_per_side / 10_000.0
        net_pnl = gross_pnl - exit_fee
        self.balance_usdc += net_pnl
        equity = self.equity_usdc(snapshot)
        drawdown = self._drawdown_from_equity(equity)
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "event_type": event_type,
            "signal_id": position.signal_id,
            "symbol": position.symbol,
            "side": position.side,
            "source": position.source,
            "leg": position.leg,
            "direction_probability": position.direction_probability,
            "entry_timestamp": position.entry_timestamp.isoformat(),
            "entry_price": position.entry_price,
            "exit_price": snapshot.price,
            "price": snapshot.price,
            "leverage": position.leverage,
            "notional_usdc": position.notional_usdc,
            "fee_usdc": exit_fee,
            "gross_pnl_usdc": gross_pnl,
            "net_pnl_usdc": net_pnl,
            "balance_usdc": self.balance_usdc,
            "equity_usdc": equity,
            "drawdown_pct": drawdown,
            "close_reason": close_reason,
        }


def write_dashboard(
    *,
    out_dir: str | Path,
    config: PaperTradingConfig,
    events: list[dict[str, object]],
    trades: list[dict[str, object]],
    rejected_signals: list[dict[str, object]] | None = None,
) -> Path:
    out = Path(out_dir)
    dashboard = out / "dashboard.html"
    points = [(float(row["equity_usdc"]), str(row["timestamp"])) for row in events]
    svg = _equity_svg(points)
    recent_events = events[-20:]
    recent_trades = trades[-20:]
    rejected_signal_reasons = _rejected_signal_reason_counts(rejected_signals or [])
    dashboard.write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html><head><meta charset='utf-8'><meta http-equiv='refresh' content='30'>",
                "<title>V142 Paper Trading</title>",
                "<style>body{font-family:Arial,sans-serif;margin:24px;color:#17202a}table{border-collapse:collapse;width:100%;font-size:12px}td,th{border:1px solid #d8dee9;padding:5px;text-align:right}th{text-align:left;background:#f4f6f8}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{border:1px solid #d8dee9;padding:12px;border-radius:6px}.muted{color:#6b7280}</style>",
                "</head><body>",
                "<h1>V142 Paper Trading</h1>",
                "<div class='grid'>",
                _metric_card("Symbol", config.symbol),
                _metric_card("Initial Balance", f"{config.initial_balance_usdc:.2f} USDC"),
                _metric_card("Last Equity", f"{points[-1][0]:.2f} USDC" if points else "n/a"),
                _metric_card("Events", str(len(events))),
                "</div>",
                "<h2>Balance</h2>",
                svg,
                "<h2>Recent Logs</h2>",
                _rows_table(recent_events),
                "<h2>Recent Trades</h2>",
                _rows_table(recent_trades),
                "<h2>Rejected Signal Reasons</h2>",
                _rows_table([{"reason": key, "count": value} for key, value in rejected_signal_reasons.items()]),
                "<p class='muted'>This is paper trading only. No live orders are placed.</p>",
                "</body></html>",
            ]
        ),
        encoding="utf-8",
    )
    return dashboard


def run_v142_paper_trading(
    *,
    out_dir: str | Path,
    market_source: MarketDataSource,
    signal_provider: SignalProvider | None = None,
    config: PaperTradingConfig | None = None,
    ticks: int = 0,
    interval_sec: float = 60.0,
    clean: bool = False,
    sleep: bool = True,
) -> dict[str, object]:
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    config = config or PaperTradingConfig()
    signal_provider = signal_provider or NoSignalProvider()
    broker = PaperBroker(config)
    events_path = out / "paper_events.jsonl"
    balance_path = out / "balance.csv"
    trades_path = out / "trades.csv"
    rejected_signals_path = out / "rejected_signals.csv"
    positions_path = out / "positions.csv"
    order_events_path = out / "order_events.csv"
    decisions_path = out / "decisions.csv"
    config_path = out / "paper_config.json"
    config_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    for path in (events_path, balance_path, trades_path, rejected_signals_path, positions_path, order_events_path, decisions_path):
        path.unlink(missing_ok=True)
    _ensure_csv_header(balance_path, EVENT_FIELDNAMES)
    _ensure_csv_header(trades_path, TRADE_FIELDNAMES)
    _ensure_csv_header(rejected_signals_path, REJECTED_SIGNAL_FIELDNAMES)
    _ensure_csv_header(positions_path, POSITION_FIELDNAMES)
    _ensure_csv_header(order_events_path, ORDER_EVENT_FIELDNAMES)
    _ensure_csv_header(decisions_path, DECISION_FIELDNAMES)

    count = 0
    with events_path.open("w", encoding="utf-8") as event_sink:
        while True:
            if ticks and count >= int(ticks):
                break
            try:
                snapshot = market_source.next_snapshot()
            except Exception as exc:
                event = _error_event(config=config, broker=broker, error=exc)
                broker.events.append(event)
                event_sink.write(json.dumps(event, default=str) + "\n")
                event_sink.flush()
                _append_csv_rows(balance_path, [event], EVENT_FIELDNAMES)
                _write_positions_snapshot(positions_path, [])
                dashboard = write_dashboard(
                    out_dir=out,
                    config=config,
                    events=broker.events,
                    trades=broker.trades,
                    rejected_signals=broker.rejected_signals,
                )
                count += 1
                if _should_sleep(sleep=sleep, interval_sec=interval_sec, ticks=ticks, count=count):
                    time.sleep(float(interval_sec))
                continue
            if snapshot is None:
                break
            if not _is_valid_market_price(snapshot.price):
                event = _market_data_error_event(config=config, broker=broker, snapshot=snapshot)
                broker.events.append(event)
                event_sink.write(json.dumps(event, default=str) + "\n")
                event_sink.flush()
                _append_csv_rows(balance_path, [event], EVENT_FIELDNAMES)
                _write_positions_snapshot(positions_path, broker.position_rows(snapshot))
                dashboard = write_dashboard(
                    out_dir=out,
                    config=config,
                    events=broker.events,
                    trades=broker.trades,
                    rejected_signals=broker.rejected_signals,
                )
                count += 1
                if _should_sleep(sleep=sleep, interval_sec=interval_sec, ticks=ticks, count=count):
                    time.sleep(float(interval_sec))
                continue
            signals = signal_provider.signals_for_snapshot(snapshot)
            trade_start = len(broker.trades)
            rejected_start = len(broker.rejected_signals)
            kill_switch = _read_kill_switch_state(out)
            if bool(kill_switch.get("active")):
                closed = broker.force_close_all_positions(
                    snapshot,
                    reason=str(kill_switch.get("reason") or "manual_dashboard"),
                )
                event = broker.snapshot_event(
                    snapshot,
                    opened=0,
                    closed=len(closed),
                    rejected_signal_count=0,
                    kill_switch_active=True,
                )
                broker.events.append(event)
                new_trades = broker.trades[trade_start:]
                new_rejections: list[dict[str, object]] = []
                order_rows = _order_event_rows(new_trades, new_rejections)
                decision_rows = _decision_rows(
                    snapshot=snapshot,
                    signals=signals,
                    new_trades=new_trades,
                    new_rejections=new_rejections,
                    kill_switch_active=True,
                )
            else:
                event = broker.on_snapshot(snapshot, signals)
                new_trades = broker.trades[trade_start:]
                new_rejections = broker.rejected_signals[rejected_start:]
                order_rows = _order_event_rows(new_trades, new_rejections)
                decision_rows = _decision_rows(
                    snapshot=snapshot,
                    signals=signals,
                    new_trades=new_trades,
                    new_rejections=new_rejections,
                    kill_switch_active=False,
                )
            event_sink.write(json.dumps(event, default=str) + "\n")
            event_sink.flush()
            _append_csv_rows(balance_path, [event], EVENT_FIELDNAMES)
            _append_csv_rows(trades_path, broker.trades[trade_start:], TRADE_FIELDNAMES)
            _append_csv_rows(
                rejected_signals_path,
                broker.rejected_signals[rejected_start:],
                REJECTED_SIGNAL_FIELDNAMES,
            )
            _append_csv_rows(order_events_path, order_rows, ORDER_EVENT_FIELDNAMES)
            _append_csv_rows(decisions_path, decision_rows, DECISION_FIELDNAMES)
            _write_positions_snapshot(positions_path, broker.position_rows(snapshot))
            dashboard = write_dashboard(
                out_dir=out,
                config=config,
                events=broker.events,
                trades=broker.trades,
                rejected_signals=broker.rejected_signals,
            )
            count += 1
            if _should_sleep(sleep=sleep, interval_sec=interval_sec, ticks=ticks, count=count):
                time.sleep(float(interval_sec))

    last_snapshot = None
    last_market_event = next((row for row in reversed(broker.events) if row.get("event_type") == "snapshot" and row.get("price") is not None), None)
    if last_market_event is not None:
        last_event = last_market_event
        last_snapshot = MarketSnapshot(
            timestamp=pd.Timestamp(last_event["timestamp"]),
            symbol=config.symbol,
            price=float(last_event["price"]),
            source="summary",
        )
    summary = {
        "version": "v142_paper_trading_mvp",
        "out_dir": str(out),
        "events": len(broker.events),
        "trades": len(broker.trades),
        "rejected_signals": len(broker.rejected_signals),
        "rejected_signal_reasons": _rejected_signal_reason_counts(broker.rejected_signals),
        "market_data_errors": _market_data_error_count(broker.events),
        "open_positions": len(broker.open_positions),
        "final_balance_usdc": broker.balance_usdc,
        "final_equity_usdc": broker.equity_usdc(last_snapshot),
        "dashboard": str(out / "dashboard.html"),
        "events_jsonl": str(events_path),
        "balance_csv": str(balance_path),
        "trades_csv": str(trades_path),
        "rejected_signals_csv": str(rejected_signals_path),
        "positions_csv": str(positions_path),
        "order_events_csv": str(order_events_path),
        "decisions_csv": str(decisions_path),
        "config_json": str(config_path),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return summary


def _error_event(*, config: PaperTradingConfig, broker: PaperBroker, error: Exception) -> dict[str, object]:
    return {
        "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "event_type": "error",
        "symbol": config.symbol,
        "price": None,
        "balance_usdc": broker.balance_usdc,
        "equity_usdc": broker.equity_usdc(),
        "drawdown_pct": broker.drawdown_pct(),
        "open_positions": len(broker.open_positions),
        "opened": 0,
        "closed": 0,
        "rejected_signal_count": 0,
        "source": "market_source",
        "error": f"{type(error).__name__}: {error}",
    }


def _market_data_error_event(*, config: PaperTradingConfig, broker: PaperBroker, snapshot: MarketSnapshot) -> dict[str, object]:
    return {
        "timestamp": snapshot.timestamp.isoformat(),
        "event_type": "market_data_error",
        "symbol": snapshot.symbol or config.symbol,
        "price": snapshot.price,
        "balance_usdc": broker.balance_usdc,
        "equity_usdc": broker.equity_usdc(),
        "drawdown_pct": broker.drawdown_pct(),
        "open_positions": len(broker.open_positions),
        "opened": 0,
        "closed": 0,
        "rejected_signal_count": 0,
        "source": snapshot.source,
        "error": f"invalid market price: {snapshot.price}",
    }


def _should_sleep(*, sleep: bool, interval_sec: float, ticks: int, count: int) -> bool:
    return bool(sleep and interval_sec > 0 and (not ticks or count < int(ticks)))


def _is_valid_market_price(price: object) -> bool:
    try:
        value = float(price)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and value > 0.0


def _market_data_error_count(events: list[dict[str, object]]) -> int:
    return sum(1 for row in events if row.get("event_type") == "market_data_error")


def _rejected_signal_reason_counts(rejected_signals: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rejected_signals:
        reason = str(row.get("reason", "")).strip()
        if not reason:
            continue
        counts[reason] = counts.get(reason, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _order_event_rows(trades: list[dict[str, object]], rejected_signals: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in trades:
        event_type = str(row.get("event_type", ""))
        if event_type == "open":
            status = "filled"
            reason = "accepted"
        elif event_type == "kill_switch_close":
            status = "closed_by_kill_switch"
            reason = str(row.get("close_reason") or "kill_switch")
        elif event_type == "close":
            status = "closed"
            reason = str(row.get("close_reason") or "scheduled_exit")
        else:
            status = event_type or "recorded"
            reason = event_type or "recorded"
        rows.append(
            {
                "timestamp": row.get("timestamp", ""),
                "signal_id": row.get("signal_id", ""),
                "symbol": row.get("symbol", ""),
                "side": row.get("side", ""),
                "status": status,
                "event_type": event_type,
                "source": row.get("source", ""),
                "leg": row.get("leg", ""),
                "price": row.get("price", row.get("exit_price", row.get("entry_price", ""))),
                "notional_usdc": row.get("notional_usdc", ""),
                "leverage": row.get("leverage", ""),
                "reason": reason,
                "dry_run": True,
                "order_type": "paper_market",
            }
        )
    for row in rejected_signals:
        rows.append(
            {
                "timestamp": row.get("timestamp", ""),
                "signal_id": row.get("signal_id", ""),
                "symbol": row.get("symbol", ""),
                "side": row.get("side", ""),
                "status": "rejected",
                "event_type": "reject",
                "source": row.get("source", ""),
                "leg": row.get("leg", ""),
                "price": "",
                "notional_usdc": "",
                "leverage": "",
                "reason": row.get("reason", ""),
                "dry_run": True,
                "order_type": "paper_market",
            }
        )
    return rows


def _decision_rows(
    *,
    snapshot: MarketSnapshot,
    signals: list[PaperSignal],
    new_trades: list[dict[str, object]],
    new_rejections: list[dict[str, object]],
    kill_switch_active: bool,
) -> list[dict[str, object]]:
    if kill_switch_active:
        if not signals:
            return [
                {
                    "timestamp": snapshot.timestamp.isoformat(),
                    "signal_id": "",
                    "symbol": snapshot.symbol,
                    "side": "",
                    "source": snapshot.source,
                    "leg": "",
                    "decision": "kill_switch_active",
                    "reason": "manual_dashboard",
                    "direction_probability": "",
                    "snapshot_price": snapshot.price,
                    "result": "new_entries_blocked",
                }
            ]
        return [
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "signal_id": signal.signal_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "source": signal.source,
                "leg": signal.leg,
                "decision": "kill_switch_active",
                "reason": "manual_dashboard",
                "direction_probability": signal.direction_probability,
                "snapshot_price": snapshot.price,
                "result": "signal_blocked",
            }
            for signal in signals
        ]
    rows: list[dict[str, object]] = []
    opened_ids = {str(row.get("signal_id")) for row in new_trades if row.get("event_type") == "open"}
    rejected_by_id = {str(row.get("signal_id")): row for row in new_rejections}
    for signal in signals:
        if signal.signal_id in opened_ids:
            decision = "accepted"
            reason = "passed_realtime_safe_checks"
            result = "paper_order_filled"
        elif signal.signal_id in rejected_by_id:
            decision = "rejected"
            reason = str(rejected_by_id[signal.signal_id].get("reason", "rejected"))
            result = "paper_order_not_opened"
        else:
            decision = "accepted"
            reason = "no_available_notional"
            result = "paper_order_not_opened"
        rows.append(
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "signal_id": signal.signal_id,
                "symbol": signal.symbol,
                "side": signal.side,
                "source": signal.source,
                "leg": signal.leg,
                "decision": decision,
                "reason": reason,
                "direction_probability": signal.direction_probability,
                "snapshot_price": snapshot.price,
                "result": result,
            }
        )
    if not signals:
        rows.append(
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "signal_id": "",
                "symbol": snapshot.symbol,
                "side": "",
                "source": snapshot.source,
                "leg": "",
                "decision": "no_signal",
                "reason": "no_ready_signal",
                "direction_probability": "",
                "snapshot_price": snapshot.price,
                "result": "hold",
            }
        )
    return rows


def _read_kill_switch_state(out_dir: Path) -> dict[str, object]:
    path = out_dir / "kill_switch.json"
    if not path.exists():
        return {"active": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"active": False, "error": "invalid_kill_switch_json"}
    if not isinstance(payload, dict):
        return {"active": False, "error": "invalid_kill_switch_payload"}
    return payload


def _write_positions_snapshot(path: Path, rows: list[dict[str, object]]) -> None:
    _ensure_csv_header(path, POSITION_FIELDNAMES)
    _append_csv_rows(path, rows, POSITION_FIELDNAMES)


def _append_csv_rows(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    if not rows:
        return
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=fieldnames, extrasaction="ignore")
        if needs_header:
            writer.writeheader()
        writer.writerows(rows)


def _ensure_csv_header(path: Path, fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as sink:
        csv.DictWriter(sink, fieldnames=fieldnames).writeheader()


def _metric_card(label: str, value: str) -> str:
    return f"<div class='card'><div class='muted'>{html.escape(label)}</div><strong>{html.escape(value)}</strong></div>"


def _rows_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p class='muted'>No rows yet.</p>"
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    header = "".join(f"<th>{html.escape(key)}</th>" for key in keys)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(_format_cell(row.get(key, '')))}</td>" for key in keys)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _format_cell(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _equity_svg(points: list[tuple[float, str]]) -> str:
    width, height, pad = 900, 260, 28
    if not points:
        return f"<svg width='{width}' height='{height}'><text x='20' y='40'>No balance data yet.</text></svg>"
    values = [p[0] for p in points]
    lo, hi = min(values), max(values)
    if hi == lo:
        hi += 1.0
        lo -= 1.0
    coords = []
    for idx, (value, _) in enumerate(points):
        x = pad + (width - 2 * pad) * (idx / max(1, len(points) - 1))
        y = height - pad - (height - 2 * pad) * ((value - lo) / (hi - lo))
        coords.append(f"{x:.2f},{y:.2f}")
    line = " ".join(coords)
    return (
        f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' role='img'>"
        f"<rect x='0' y='0' width='{width}' height='{height}' fill='#ffffff'/>"
        f"<line x1='{pad}' y1='{height-pad}' x2='{width-pad}' y2='{height-pad}' stroke='#cbd5e1'/>"
        f"<line x1='{pad}' y1='{pad}' x2='{pad}' y2='{height-pad}' stroke='#cbd5e1'/>"
        f"<polyline points='{line}' fill='none' stroke='#2563eb' stroke-width='2.5'/>"
        f"<text x='{pad}' y='18' font-size='12'>max {hi:.2f}</text>"
        f"<text x='{pad}' y='{height-6}' font-size='12'>min {lo:.2f}</text>"
        f"</svg>"
    )
