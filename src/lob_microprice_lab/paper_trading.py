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
    side: int
    source: str
    leg: str
    direction_probability: float | None = None
    horizon_minutes: int = 30


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
    initial_balance_usdc: float = 10_000.0
    fee_bps_per_side: float = 4.0
    high_confidence_probability_floor: float = 0.66
    high_confidence_rescue_leverage: float = 5.0
    high_account_leverage: float = 3.5
    mid_account_leverage: float = 2.25
    low_account_leverage: float = 1.25
    mid_drawdown_trigger_pct: float = -5.0
    low_drawdown_trigger_pct: float = -15.0
    default_horizon_minutes: int = 30


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
    "source",
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
]


class MarketDataSource(Protocol):
    def next_snapshot(self) -> MarketSnapshot | None:
        ...


class SignalProvider(Protocol):
    def signals_for_snapshot(self, snapshot: MarketSnapshot) -> list[PaperSignal]:
        ...


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
        side_col = "side" if "side" in frame.columns else "signal"
        frame["side"] = pd.to_numeric(frame[side_col], errors="coerce").fillna(0).astype(int).clip(-1, 1)
        frame["symbol"] = frame.get("symbol", default_symbol)
        frame["source"] = frame.get("source", "manual")
        frame["leg"] = frame.get("leg", "base")
        frame["direction_probability"] = pd.to_numeric(frame.get("direction_probability"), errors="coerce") if "direction_probability" in frame.columns else pd.NA
        frame["horizon_minutes"] = pd.to_numeric(frame.get("horizon_minutes", default_horizon_minutes), errors="coerce").fillna(default_horizon_minutes).astype(int)
        if "signal_id" not in frame.columns:
            frame["signal_id"] = [f"csv-{i}" for i in range(len(frame))]
        self.frame = frame.loc[frame["side"] != 0].sort_values("timestamp").reset_index(drop=True)
        self.emitted: set[str] = set()

    def signals_for_snapshot(self, snapshot: MarketSnapshot) -> list[PaperSignal]:
        ready = self.frame.loc[self.frame["timestamp"] <= snapshot.timestamp]
        out: list[PaperSignal] = []
        for _, row in ready.iterrows():
            signal_id = str(row["signal_id"])
            if signal_id in self.emitted:
                continue
            if str(row["symbol"]).upper() != snapshot.symbol.upper():
                continue
            self.emitted.add(signal_id)
            prob = row["direction_probability"]
            out.append(
                PaperSignal(
                    timestamp=pd.to_datetime(row["timestamp"], utc=True),
                    signal_id=signal_id,
                    symbol=str(row["symbol"]).upper(),
                    side=int(row["side"]),
                    source=str(row["source"]),
                    leg=str(row["leg"]),
                    direction_probability=None if pd.isna(prob) else float(prob),
                    horizon_minutes=int(row["horizon_minutes"]),
                )
            )
        return out


class V142LeveragePolicy:
    def __init__(self, config: PaperTradingConfig) -> None:
        self.config = config

    def leverage_for_signal(self, signal: PaperSignal, *, prior_drawdown_pct: float) -> tuple[float, bool]:
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
        closed = self._close_due_positions(snapshot)
        opened = [self._open_position(snapshot, signal) for signal in signals]
        equity = self.equity_usdc(snapshot)
        if equity > self.peak_equity_usdc:
            self.peak_equity_usdc = equity
        drawdown = (equity / self.peak_equity_usdc - 1.0) * 100.0 if self.peak_equity_usdc else 0.0
        event = {
            "timestamp": snapshot.timestamp.isoformat(),
            "event_type": "snapshot",
            "symbol": snapshot.symbol,
            "price": snapshot.price,
            "balance_usdc": self.balance_usdc,
            "equity_usdc": equity,
            "drawdown_pct": drawdown,
            "open_positions": len(self.open_positions),
            "opened": len([row for row in opened if row is not None]),
            "closed": len(closed),
            "source": snapshot.source,
        }
        self.events.append(event)
        return event

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
            side=signal.side,
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
            "side": signal.side,
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
            ret = (snapshot.price - position.entry_price) / position.entry_price * position.side
            gross_pnl = position.notional_usdc * ret
            exit_fee = position.notional_usdc * self.config.fee_bps_per_side / 10_000.0
            net_pnl = gross_pnl - exit_fee
            self.balance_usdc += net_pnl
            equity = self.equity_usdc(snapshot)
            drawdown = self._drawdown_from_equity(equity)
            row = {
                "timestamp": snapshot.timestamp.isoformat(),
                "event_type": "close",
                "signal_id": position.signal_id,
                "symbol": position.symbol,
                "side": position.side,
                "source": position.source,
                "leg": position.leg,
                "direction_probability": position.direction_probability,
                "entry_timestamp": position.entry_timestamp.isoformat(),
                "entry_price": position.entry_price,
                "exit_price": snapshot.price,
                "leverage": position.leverage,
                "notional_usdc": position.notional_usdc,
                "fee_usdc": exit_fee,
                "gross_pnl_usdc": gross_pnl,
                "net_pnl_usdc": net_pnl,
                "balance_usdc": self.balance_usdc,
                "equity_usdc": equity,
                "drawdown_pct": drawdown,
            }
            self.trades.append(row)
            closed.append(row)
        return closed


def write_dashboard(*, out_dir: str | Path, config: PaperTradingConfig, events: list[dict[str, object]], trades: list[dict[str, object]]) -> Path:
    out = Path(out_dir)
    dashboard = out / "dashboard.html"
    points = [(float(row["equity_usdc"]), str(row["timestamp"])) for row in events]
    svg = _equity_svg(points)
    recent_events = events[-20:]
    recent_trades = trades[-20:]
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
    config_path = out / "paper_config.json"
    config_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    for path in (events_path, balance_path, trades_path):
        path.unlink(missing_ok=True)
    _ensure_csv_header(balance_path, EVENT_FIELDNAMES)
    _ensure_csv_header(trades_path, TRADE_FIELDNAMES)

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
                dashboard = write_dashboard(out_dir=out, config=config, events=broker.events, trades=broker.trades)
                count += 1
                if _should_sleep(sleep=sleep, interval_sec=interval_sec, ticks=ticks, count=count):
                    time.sleep(float(interval_sec))
                continue
            if snapshot is None:
                break
            signals = signal_provider.signals_for_snapshot(snapshot)
            trade_start = len(broker.trades)
            event = broker.on_snapshot(snapshot, signals)
            event_sink.write(json.dumps(event, default=str) + "\n")
            event_sink.flush()
            _append_csv_rows(balance_path, [event], EVENT_FIELDNAMES)
            _append_csv_rows(trades_path, broker.trades[trade_start:], TRADE_FIELDNAMES)
            dashboard = write_dashboard(out_dir=out, config=config, events=broker.events, trades=broker.trades)
            count += 1
            if _should_sleep(sleep=sleep, interval_sec=interval_sec, ticks=ticks, count=count):
                time.sleep(float(interval_sec))

    last_snapshot = None
    last_market_event = next((row for row in reversed(broker.events) if row.get("price") is not None), None)
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
        "open_positions": len(broker.open_positions),
        "final_balance_usdc": broker.balance_usdc,
        "final_equity_usdc": broker.equity_usdc(last_snapshot),
        "dashboard": str(out / "dashboard.html"),
        "events_jsonl": str(events_path),
        "balance_csv": str(balance_path),
        "trades_csv": str(trades_path),
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
        "source": "market_source",
        "error": f"{type(error).__name__}: {error}",
    }


def _should_sleep(*, sleep: bool, interval_sec: float, ticks: int, count: int) -> bool:
    return bool(sleep and interval_sec > 0 and (not ticks or count < int(ticks)))


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
