from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import quote
from urllib.request import urlopen

import pandas as pd

BINANCE_PUBLIC_BASE_URL = "https://data.binance.vision/data"
BINANCE_FAPI_BASE = "https://fapi.binance.com"
BYBIT_PUBLIC_BASE = "https://api.bybit.com"


@dataclass(frozen=True)
class DataSourceInfo:
    name: str
    venue: str
    instruments: tuple[str, ...]
    data_types: tuple[str, ...]
    access: str
    quality_use: str
    caveat: str
    reference_url: str

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["instruments"] = list(self.instruments)
        d["data_types"] = list(self.data_types)
        return d


def default_btc_contract_sources() -> list[DataSourceInfo]:
    return [
        DataSourceInfo(
            name="Binance Public Data - USD-M Futures",
            venue="Binance Futures",
            instruments=("BTCUSDT perpetual", "BTCUSDT delivery where available"),
            data_types=("klines", "aggTrades", "trades"),
            access="public daily/monthly zipped CSV files",
            quality_use="Free large-scale BTCUSDT futures K-line and trade-history expansion.",
            caveat="Bulk public files do not replay full historical L2 order-book depth.",
            reference_url="https://github.com/binance/binance-public-data",
        ),
        DataSourceInfo(
            name="Binance USD-M Futures REST API",
            venue="Binance Futures",
            instruments=("BTCUSDT perpetual",),
            data_types=("klines", "funding", "open interest", "mark price klines"),
            access="public REST API with request limits",
            quality_use="Incremental updates and contract-specific features after the bulk files are synced.",
            caveat="REST is less convenient than bulk files for long backfills.",
            reference_url="https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data",
        ),
        DataSourceInfo(
            name="Tardis.dev",
            venue="Multi-exchange",
            instruments=("Deribit BTC-PERPETUAL", "Binance BTCUSDT", "Bybit/OKX BTC contracts"),
            data_types=("tick trades", "L2/L3 order book", "quotes", "open interest", "funding", "liquidations"),
            access="historical API/downloadable files",
            quality_use="Best fit for extending the existing LOB model beyond the bundled single L2 sample.",
            caveat="Broad historical tick/L2 coverage may require a paid plan.",
            reference_url="https://tardis.dev/",
        ),
        DataSourceInfo(
            name="Crypto Lake",
            venue="Multi-exchange",
            instruments=("BTC contracts across supported venues",),
            data_types=("order book", "tick trades", "1m candles"),
            access="Python API with caching/parallelization",
            quality_use="Convenient Python workflow for larger BTC validation sets.",
            caveat="Check subscription and exact venue/date coverage.",
            reference_url="https://github.com/crypto-lake/lake-api",
        ),
        DataSourceInfo(
            name="CryptoHFTData",
            venue="Multi-exchange",
            instruments=("BTC derivatives on supported venues",),
            data_types=("L2 snapshots", "L2 deltas", "trades", "funding", "liquidations"),
            access="open-data-lake style Parquet access",
            quality_use="Potential zero-cost high-frequency BTC derivatives data route.",
            caveat="Coverage and schema should be verified before production research.",
            reference_url="https://www.cryptohftdata.com/",
        ),
        DataSourceInfo(
            name="Amberdata / CoinDesk Data",
            venue="Multi-exchange",
            instruments=("institutional BTC derivative datasets",),
            data_types=("order book", "trades", "OHLCV", "derivatives fields"),
            access="commercial data product",
            quality_use="Production-grade independent validation if budget allows.",
            caveat="Commercial licensing and coverage need confirmation.",
            reference_url="https://www.amberdata.io/order-book",
        ),
    ]


@dataclass(frozen=True)
class DataManifestRow:
    source: str
    venue: str
    market: str
    symbol: str
    data_type: str
    interval: str
    period: str
    date: str
    url: str
    checksum_url: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class BtcContractDataSpec:
    symbol: str = "BTCUSDT"
    market_type: str = "um"
    start_date: str = "2026-05-01"
    end_date: str = "2026-06-11"
    intervals: tuple[str, ...] = ("1m", "5m", "15m", "1h")
    include_klines: bool = True
    include_agg_trades: bool = True
    include_trades: bool = False
    storage_scope: str = "daily"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PublicDataItem:
    venue: str
    symbol: str
    market_type: str
    storage_scope: str
    data_type: str
    interval: str
    date_value: str
    url: str
    checksum_url: str
    local_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BinancePublicFileSpec:
    market: str = "um"
    data_type: str = "klines"
    symbol: str = "BTCUSDT"
    interval: str | None = "1m"
    date_value: str = "2024-01-01"
    frequency: str = "daily"

    def filename(self) -> str:
        if self.data_type == "klines":
            if not self.interval:
                raise ValueError("klines require an interval")
            return f"{self.symbol}-{self.interval}-{self.date_value}.zip"
        if self.data_type in {"aggTrades", "trades"}:
            return f"{self.symbol}-{self.data_type}-{self.date_value}.zip"
        raise ValueError(f"unsupported Binance data_type: {self.data_type}")

    def relative_path(self) -> str:
        parts = [self.market, self.frequency, self.data_type, self.symbol]
        if self.data_type == "klines":
            parts.append(str(self.interval))
        parts.append(self.filename())
        return "/".join(parts)

    def url(self) -> str:
        if self.market in {"um", "cm"}:
            return f"{BINANCE_PUBLIC_BASE_URL}/futures/{self.relative_path()}"
        if self.market == "spot":
            if self.data_type == "klines":
                return f"{BINANCE_PUBLIC_BASE_URL}/spot/{self.frequency}/{self.data_type}/{self.symbol}/{self.interval}/{self.filename()}"
            return f"{BINANCE_PUBLIC_BASE_URL}/spot/{self.frequency}/{self.data_type}/{self.symbol}/{self.filename()}"
        raise ValueError("market must be um, cm, or spot")

    def local_path(self, root: str | Path) -> Path:
        return Path(root) / "binance" / self.relative_path()

    def to_dict(self, root: str | Path | None = None) -> dict[str, object]:
        d = asdict(self)
        d.update({"filename": self.filename(), "relative_path": self.relative_path(), "url": self.url()})
        if root is not None:
            d["local_path"] = str(self.local_path(root))
        return d


def _parse_date(x: str | date) -> date:
    if isinstance(x, date):
        return x
    return datetime.strptime(str(x), "%Y-%m-%d").date()


def date_strings(start_date: str, end_date: str) -> list[str]:
    return [d.isoformat() for d in _daily_dates(start_date, end_date)]


def _daily_dates(start_date: str | date, end_date: str | date) -> list[date]:
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def binance_public_data_url(*, symbol: str, market_type: str, storage_scope: str, data_type: str, interval: str | None = None, date_value: str) -> str:
    mt = str(market_type).lower()
    if mt not in {"um", "cm"}:
        raise ValueError("market_type must be 'um' or 'cm'")
    scope = str(storage_scope).lower()
    if scope != "daily":
        raise ValueError("only daily scope is supported by the V20 manifest builder")
    dtype = str(data_type)
    sym = str(symbol).upper()
    if dtype == "klines":
        if not interval:
            raise ValueError("interval is required for klines")
        return f"https://data.binance.vision/data/futures/{mt}/daily/klines/{quote(sym)}/{quote(interval)}/{quote(sym)}-{quote(interval)}-{quote(date_value)}.zip"
    if dtype in {"aggTrades", "trades"}:
        return f"https://data.binance.vision/data/futures/{mt}/daily/{quote(dtype)}/{quote(sym)}/{quote(sym)}-{quote(dtype)}-{quote(date_value)}.zip"
    raise ValueError(f"unsupported data_type: {data_type}")


def binance_vision_url(*, symbol: str = "BTCUSDT", market: str = "futures/um", period: str = "daily", data_type: str = "klines", interval: str = "1m", day: str | date = "2024-01-01") -> str:
    spec = BinancePublicFileSpec(market="um" if market.endswith("um") else "cm" if market.endswith("cm") else "spot", data_type=data_type, symbol=symbol, interval=interval or None, date_value=_parse_date(day).isoformat(), frequency=period)
    return spec.url()


def build_public_data_manifest(spec: BtcContractDataSpec, *, local_root: str = "data/binance_public") -> list[PublicDataItem]:
    items: list[PublicDataItem] = []
    for d in date_strings(spec.start_date, spec.end_date):
        if spec.include_klines:
            for interval in spec.intervals:
                url = binance_public_data_url(symbol=spec.symbol, market_type=spec.market_type, storage_scope=spec.storage_scope, data_type="klines", interval=interval, date_value=d)
                items.append(PublicDataItem("binance", spec.symbol, spec.market_type, spec.storage_scope, "klines", interval, d, url, url + ".CHECKSUM", f"{local_root}/{spec.market_type}/daily/klines/{spec.symbol}/{interval}/{spec.symbol}-{interval}-{d}.zip"))
        if spec.include_agg_trades:
            url = binance_public_data_url(symbol=spec.symbol, market_type=spec.market_type, storage_scope=spec.storage_scope, data_type="aggTrades", interval=None, date_value=d)
            items.append(PublicDataItem("binance", spec.symbol, spec.market_type, spec.storage_scope, "aggTrades", "", d, url, url + ".CHECKSUM", f"{local_root}/{spec.market_type}/daily/aggTrades/{spec.symbol}/{spec.symbol}-aggTrades-{d}.zip"))
        if spec.include_trades:
            url = binance_public_data_url(symbol=spec.symbol, market_type=spec.market_type, storage_scope=spec.storage_scope, data_type="trades", interval=None, date_value=d)
            items.append(PublicDataItem("binance", spec.symbol, spec.market_type, spec.storage_scope, "trades", "", d, url, url + ".CHECKSUM", f"{local_root}/{spec.market_type}/daily/trades/{spec.symbol}/{spec.symbol}-trades-{d}.zip"))
    return items


def binance_um_daily_urls(*, symbol: str = "BTCUSDT", start: str = "2024-01-01", end: str = "2024-01-07", intervals: list[str] | None = None, data_types: list[str] | tuple[str, ...] | None = None) -> list[dict[str, object]]:
    """Build Binance Vision USD-M daily URLs for BTC contract data.

    `data_types` is kept for compatibility with the older V20 test harness.
    Supported values are `klines`, `aggTrades`, and `trades`.
    """
    requested = set(data_types or ["klines", "aggTrades"])
    spec = BtcContractDataSpec(
        symbol=symbol,
        market_type="um",
        start_date=start,
        end_date=end,
        intervals=tuple(intervals or ["1s", "5s", "15s", "1m", "5m", "15m"]),
        include_klines="klines" in requested,
        include_agg_trades="aggTrades" in requested,
        include_trades="trades" in requested,
    )
    return [x.to_dict() for x in build_public_data_manifest(spec)]


def build_binance_btc_download_plan(*, symbol: str = "BTCUSDT", start_date: str = "2024-01-01", end_date: str = "2024-01-07", market: str = "um", intervals: Iterable[str] = ("1s", "5s", "15s", "1m", "5m", "15m"), include_agg_trades: bool = True, include_raw_trades: bool = False, frequency: str = "daily", root: str | Path = "data/external") -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for d in date_strings(start_date, end_date):
        for interval in intervals:
            spec = BinancePublicFileSpec(market=market, data_type="klines", symbol=symbol, interval=interval, date_value=d, frequency=frequency)
            row = spec.to_dict(root)
            row.update({"schema": "binance_kline_12_column", "priority": 1 if interval in {"1s", "5s", "15s", "1m"} else 2})
            rows.append(row)
        if include_agg_trades:
            spec = BinancePublicFileSpec(market=market, data_type="aggTrades", symbol=symbol, interval=None, date_value=d, frequency=frequency)
            row = spec.to_dict(root)
            row.update({"schema": "binance_agg_trades", "priority": 1})
            rows.append(row)
        if include_raw_trades:
            spec = BinancePublicFileSpec(market=market, data_type="trades", symbol=symbol, interval=None, date_value=d, frequency=frequency)
            row = spec.to_dict(root)
            row.update({"schema": "binance_raw_trades", "priority": 2})
            rows.append(row)
    return pd.DataFrame(rows)


def futures_metric_api_urls(symbol: str = "BTCUSDT", period: str = "5m", limit: int = 500) -> dict[str, str]:
    sym = quote(str(symbol).upper())
    per = quote(str(period))
    lim = int(limit)
    return {
        "open_interest_hist": f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}&period={per}&limit={lim}",
        "taker_long_short_ratio": f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={sym}&period={per}&limit={lim}",
        "funding_rate_history": f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit={lim}",
        "mark_price_klines_1m": f"https://fapi.binance.com/fapi/v1/markPriceKlines?symbol={sym}&interval=1m&limit={lim}",
    }


def bybit_rest_task_manifest(*, symbol: str = "BTCUSDT", category: str = "linear", intervals: Iterable[str] = ("1", "5", "15", "60")) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for interval in intervals:
        rows.append({
            "source": "bybit_v5_rest",
            "venue": "bybit",
            "market": "USDT perpetual contract",
            "symbol": symbol,
            "data_type": "klines",
            "interval": str(interval),
            "url_template": f"{BYBIT_PUBLIC_BASE}/v5/market/kline?category={category}&symbol={symbol}&interval={interval}&start={{start_ms}}&end={{end_ms}}&limit=1000",
            "notes": "page by millisecond start/end",
        })
    rows.append({
        "source": "bybit_v5_rest",
        "venue": "bybit",
        "market": "USDT perpetual contract",
        "symbol": symbol,
        "data_type": "funding_rate_history",
        "interval": "funding",
        "url_template": f"{BYBIT_PUBLIC_BASE}/v5/market/funding/history?category={category}&symbol={symbol}&startTime={{start_ms}}&endTime={{end_ms}}&limit=200",
        "notes": "funding history for carry/crowding features",
    })
    return rows


def write_manifest_csv(rows: Iterable[PublicDataItem | DataManifestRow | dict[str, object]], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized: list[dict[str, object]] = []
    for row in rows:
        if hasattr(row, "to_dict"):
            materialized.append(row.to_dict())
        else:
            materialized.append(dict(row))
    if not materialized:
        path.write_text("", encoding="utf-8")
        return path
    keys: list[str] = []
    for row in materialized:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(materialized)
    return path


def write_btc_contract_data_plan(out_dir: str | Path, spec: BtcContractDataSpec | None = None, *, symbol: str = "BTCUSDT", start: str = "2024-01-01", end: str = "2024-01-07", intervals: list[str] | None = None, start_date: str | None = None, end_date: str | None = None, root: str | Path | None = None) -> dict[str, object]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if start_date is not None:
        start = start_date
    if end_date is not None:
        end = end_date
    if spec is not None:
        symbol = spec.symbol
        start = spec.start_date
        end = spec.end_date
        intervals = list(spec.intervals)
        binance_items = build_public_data_manifest(spec)
        binance_urls = [item.to_dict() for item in binance_items]
    else:
        binance_items = build_public_data_manifest(BtcContractDataSpec(symbol=symbol, start_date=start, end_date=end, intervals=tuple(intervals or ["1s", "5s", "15s", "1m", "5m", "15m"])))
        binance_urls = [item.to_dict() for item in binance_items]
    sources = default_btc_contract_sources()
    manifest = {
        "created_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "target": "BTC contract/perpetual training expansion",
        "symbol": symbol,
        "start": start,
        "end": end,
        "recommended_minimum_validation": {
            "independent_days": 20,
            "non_overlap_trades": 100,
            "venues": ["Deribit", "Binance USD-M", "Bybit", "OKX"],
            "fixed_policy_required": True,
        },
        "sources": [s.to_dict() for s in sources],
        "public_data_manifest": binance_urls,
        "binance_metric_urls": futures_metric_api_urls(symbol=symbol),
        "bybit_rest_templates": bybit_rest_task_manifest(symbol=symbol),
        "conversion_contract": {
            "book_csv_required_columns": ["timestamp", "best_bid", "best_ask"],
            "optional_depth_columns": "bid_px_1..N, bid_sz_1..N, ask_px_1..N, ask_sz_1..N",
            "kline_timestamp_rule": "Only use closed candles: candle.close_ts <= event.timestamp - decision_lag.",
            "futures_fee_rule": "Use taker 0.0400% per side unless a live maker-fill simulator proves maker fills.",
        },
    }
    (out / "btc_contract_data_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "btc_contract_data_sources.json").write_text(json.dumps([src.to_dict() for src in sources], indent=2), encoding="utf-8")
    write_manifest_csv(binance_items, out / "binance_public_manifest.csv")
    plan_df = build_binance_btc_download_plan(symbol=symbol, start_date=start, end_date=end, intervals=intervals or ["1s", "5s", "15s", "1m", "5m", "15m"], root=root or "data/external")
    plan_df.to_csv(out / "binance_btcusdt_public_download_plan.csv", index=False)
    commands = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for row in binance_urls:
        local = row.get("local_path", "")
        url = row.get("url", "")
        if local and url:
            commands += [f"mkdir -p {Path(str(local)).parent}", f"curl -fL --retry 3 -o {local} {url}", f"curl -fL --retry 3 -o {local}.CHECKSUM {url}.CHECKSUM || true"]
    (out / "download_commands.sh").write_text("\n".join(commands) + "\n", encoding="utf-8")
    md = [
        "# BTC Contract Data Expansion Plan",
        "",
        "This plan lists BTC perpetual/futures data sources that can be added before claiming live-stable profit.",
        "The sandbox cannot download external files, so V20 ships deterministic URLs and adapters rather than pretending new data was trained here.",
        "",
        "## Minimum forward-validation target",
        "",
        "- 20+ independent BTC contract trading days",
        "- 100+ non-overlapping trades",
        "- Fixed V20 policy with no threshold retuning on validation days",
        "- Real fee: 0.0400% taker per side, 0.0000% maker per side",
        "- Separate venue checks for Deribit, Binance USD-M, Bybit, and OKX where available",
        "",
        "## Sources",
        "",
    ]
    for src in sources:
        md += [f"### {src.name}", "", f"- Venue: {src.venue}", f"- Instruments: {', '.join(src.instruments)}", f"- Data: {', '.join(src.data_types)}", f"- Access: {src.access}", f"- Use: {src.quality_use}", f"- Caveat: {src.caveat}", f"- Reference: {src.reference_url}", ""]
    md += ["## Binance USD-M daily URLs generated", "", "```text"]
    for row in binance_urls[:100]:
        md.append(str(row.get("url", "")))
    if len(binance_urls) > 100:
        md.append(f"... {len(binance_urls) - 100} more rows in binance_public_manifest.csv")
    md += ["```", ""]
    (out / "README.md").write_text("\n".join(md), encoding="utf-8")
    (out / "BTC_CONTRACT_DATA_PLAN.md").write_text((out / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "out_dir": str(out),
        "symbol": symbol,
        "start": start,
        "end": end,
        "rows": int(len(binance_urls)),
        "recommended_minimum_validation": manifest["recommended_minimum_validation"],
        "sources": [s.to_dict() for s in sources],
        "public_data_manifest": binance_urls,
        "binance_um_daily_urls": binance_urls,
        "manifest_path": str(out / "btc_contract_data_manifest.json"),
        "binance_manifest_csv": str(out / "binance_public_manifest.csv"),
        "download_commands": str(out / "download_commands.sh"),
    }


def download_file(url: str, out_path: str | Path, *, overwrite: bool = False, timeout: float = 60.0) -> Path:
    out = Path(out_path)
    if out.exists() and not overwrite:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - user-requested public data download
        data = response.read()
    out.write_bytes(data)
    return out


KLINE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"]
AGG_TRADE_COLUMNS = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]
RAW_TRADE_COLUMNS = ["trade_id", "price", "quantity", "quote_quantity", "transact_time", "is_buyer_maker"]


def parse_binance_public_zip(path: str | Path, *, data_type: str, interval: str | None = None) -> pd.DataFrame:
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if not members:
            raise ValueError(f"no CSV member in {path}")
        raw = zf.read(members[0])
    return parse_binance_public_csv_bytes(raw, data_type=data_type, interval=interval)


def parse_binance_public_csv_bytes(raw: bytes, *, data_type: str, interval: str | None = None) -> pd.DataFrame:
    first_line = raw.splitlines()[0].decode("utf-8", errors="replace") if raw else ""
    has_header = any(ch.isalpha() for ch in first_line)
    columns = KLINE_COLUMNS if data_type == "klines" else AGG_TRADE_COLUMNS if data_type == "aggTrades" else RAW_TRADE_COLUMNS if data_type == "trades" else None
    if columns is None:
        raise ValueError(f"unsupported data_type: {data_type}")
    df = pd.read_csv(io.BytesIO(raw), header=0 if has_header else None)
    if not has_header:
        df.columns = columns[: len(df.columns)]
    if data_type == "klines":
        return normalize_binance_klines(df, interval=interval)
    return normalize_binance_trades(df, time_col="transact_time", qty_col="quantity")


def normalize_binance_klines(df: pd.DataFrame, *, interval: str | None = None) -> pd.DataFrame:
    out = pd.DataFrame()
    out["timestamp"] = pd.to_datetime(pd.to_numeric(df["open_time"], errors="coerce"), unit="ms", utc=True)
    out["open"] = pd.to_numeric(df["open"], errors="coerce")
    out["high"] = pd.to_numeric(df["high"], errors="coerce")
    out["low"] = pd.to_numeric(df["low"], errors="coerce")
    out["close"] = pd.to_numeric(df["close"], errors="coerce")
    out["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    out["close_time"] = pd.to_datetime(pd.to_numeric(df["close_time"], errors="coerce"), unit="ms", utc=True)
    out["quote_volume"] = _numeric_column(df, "quote_volume")
    out["trade_count"] = _numeric_column(df, "trade_count", "count").fillna(0).astype(int)
    out["taker_buy_base_volume"] = _numeric_column(df, "taker_buy_base_volume", "taker_buy_volume")
    out["taker_buy_quote_volume"] = _numeric_column(df, "taker_buy_quote_volume")
    out["interval"] = interval or ""
    return out.dropna(subset=["timestamp", "open", "high", "low", "close"]).reset_index(drop=True)


def _numeric_column(df: pd.DataFrame, *names: str, default: float = 0.0) -> pd.Series:
    for name in names:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(default, index=df.index, dtype=float)


def normalize_binance_trades(df: pd.DataFrame, *, time_col: str, qty_col: str) -> pd.DataFrame:
    out = pd.DataFrame()
    out["timestamp"] = pd.to_datetime(pd.to_numeric(df[time_col], errors="coerce"), unit="ms", utc=True)
    out["price"] = pd.to_numeric(df["price"], errors="coerce")
    out["quantity"] = pd.to_numeric(df[qty_col], errors="coerce")
    out["is_buyer_maker"] = df.get("is_buyer_maker", False).astype(str).str.lower().isin(["true", "1"])
    return out.dropna(subset=["timestamp", "price", "quantity"]).reset_index(drop=True)


def download_manifest_files(manifest: str | Path, out_dir: str | Path, *, max_files: int = 0, overwrite: bool = False) -> dict[str, object]:
    """Download public data files from a V20 manifest CSV or JSON.

    This is intended for local use with internet access. The sandbox used to build the
    package cannot resolve external hosts, so tests only cover URL construction.
    """
    manifest = Path(manifest)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    if manifest.suffix.lower() == ".json":
        obj = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            rows = list(obj.get("public_data_manifest") or obj.get("binance_um_daily_urls") or [])
        elif isinstance(obj, list):
            rows = obj
    else:
        rows = pd.read_csv(manifest).to_dict(orient="records")
    downloaded: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    limit = int(max_files or 0)
    for pos, row in enumerate(rows):
        if limit and pos >= limit:
            break
        url = str(row.get("url", ""))
        if not url:
            continue
        local_name = str(row.get("local_path") or Path(url).name)
        target = out / local_name
        try:
            p = download_file(url, target, overwrite=overwrite)
            downloaded.append({"url": url, "path": str(p), "bytes": p.stat().st_size})
        except Exception as exc:  # pragma: no cover - depends on external network
            errors.append({"url": url, "error": repr(exc)})
    result = {"manifest": str(manifest), "out_dir": str(out), "attempted": len(downloaded) + len(errors), "downloaded": downloaded, "errors": errors}
    (out / "download_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result

# Backward-compatible alias for V20 tests/CLI.
def build_binance_btcusdt_um_manifest(*, start_date: str = "2024-01-01", end_date: str = "2024-01-07", intervals: tuple[str, ...] | list[str] = ("1m", "5m"), include_agg_trades: bool = True, include_raw_trades: bool = False) -> list[PublicDataItem]:
    return build_public_data_manifest(BtcContractDataSpec(symbol="BTCUSDT", market_type="um", start_date=start_date, end_date=end_date, intervals=tuple(intervals), include_klines=True, include_agg_trades=include_agg_trades, include_trades=include_raw_trades))

# Final override: monthly Binance public-data files use YYYY-MM filename suffix.
def binance_vision_url(*, symbol: str = "BTCUSDT", market: str = "futures/um", period: str = "daily", data_type: str = "klines", interval: str = "1m", day: str | date = "2024-01-01") -> str:  # type: ignore[no-redef]
    dt = _parse_date(day)
    suffix = dt.isoformat() if period == "daily" else dt.strftime("%Y-%m")
    m = "um" if market.endswith("um") else "cm" if market.endswith("cm") else "spot"
    spec = BinancePublicFileSpec(market=m, data_type=data_type, symbol=symbol, interval=interval or None, date_value=suffix, frequency=period)
    return spec.url()
