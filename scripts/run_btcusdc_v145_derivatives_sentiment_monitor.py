from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v145_derivatives_sentiment_monitor"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V145_BTCUSDC_DERIVATIVES_SENTIMENT_MONITOR.md"
V144_ACCOUNT_PATH = ROOT / "runs" / "research_v144_funding_sentiment_governor" / "v144_selected_account_path.csv"
SYMBOL = "BTCUSDC"
PERIOD = "1h"
LIMIT = 500
BINANCE_DATA_URL = "https://fapi.binance.com/futures/data"
MIN_STRATEGY_PROMOTION_DAYS = 90.0
MIN_STRATEGY_PROMOTION_TRADES = 80


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _request_json(url: str, params: dict[str, object]) -> list[dict[str, object]]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "FukMSTR-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict) and "code" in payload:
        raise RuntimeError(f"Binance API error: {payload}")
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Binance response: {payload!r}")
    return payload


def _download_recent_binance_metric(endpoint: str, *, symbol: str = SYMBOL, period: str = PERIOD) -> pd.DataFrame:
    rows = _request_json(
        f"{BINANCE_DATA_URL}/{endpoint}",
        {
            "symbol": symbol,
            "period": period,
            "limit": LIMIT,
        },
    )
    if not rows:
        raise RuntimeError(f"No Binance rows returned for {endpoint}")
    frame = pd.DataFrame(rows)
    frame["metric_time"] = pd.to_datetime(pd.to_numeric(frame["timestamp"]), unit="ms", utc=True)
    return frame.drop_duplicates("metric_time").sort_values("metric_time", kind="mergesort").reset_index(drop=True)


def _normalize_open_interest(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "metric_time": _to_utc(frame["metric_time"]),
            "sum_open_interest": pd.to_numeric(frame["sumOpenInterest"], errors="coerce"),
            "sum_open_interest_value": pd.to_numeric(frame["sumOpenInterestValue"], errors="coerce"),
        }
    )


def _normalize_long_short_ratio(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "metric_time": _to_utc(frame["metric_time"]),
            f"{prefix}_long_short_ratio": pd.to_numeric(frame["longShortRatio"], errors="coerce"),
            f"{prefix}_long_account": pd.to_numeric(frame["longAccount"], errors="coerce"),
            f"{prefix}_short_account": pd.to_numeric(frame["shortAccount"], errors="coerce"),
        }
    )


def _join_prior_metric(
    trades: pd.DataFrame,
    metric: pd.DataFrame,
    *,
    metric_time_col: str,
    metric_cols: list[str],
    output_time_col: str | None = None,
) -> pd.DataFrame:
    left = trades.copy()
    right = metric[[metric_time_col, *metric_cols]].copy()
    left["timestamp"] = _to_utc(left["timestamp"])
    right[metric_time_col] = _to_utc(right[metric_time_col])
    joined = pd.merge_asof(
        left.sort_values("timestamp", kind="mergesort"),
        right.sort_values(metric_time_col, kind="mergesort"),
        left_on="timestamp",
        right_on=metric_time_col,
        direction="backward",
        allow_exact_matches=True,
    ).reset_index(drop=True)
    if output_time_col and output_time_col != metric_time_col:
        joined = joined.rename(columns={metric_time_col: output_time_col})
    return joined


def _ratio_crowd_follow(signal: pd.Series, ratio: pd.Series) -> pd.Series:
    safe_ratio = pd.to_numeric(ratio, errors="coerce").where(lambda values: values > 0.0)
    signed_signal = pd.to_numeric(signal, errors="coerce").fillna(0.0)
    return signed_signal * safe_ratio.map(math.log)


def _add_derivatives_sentiment_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "timestamp" in out.columns:
        out["timestamp"] = _to_utc(out["timestamp"])
        out = out.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    out["signal"] = pd.to_numeric(out["signal"], errors="coerce").fillna(0.0)
    for col in (
        "sum_open_interest_value",
        "global_long_short_ratio",
        "top_account_long_short_ratio",
        "top_position_long_short_ratio",
    ):
        if col not in out.columns:
            out[col] = pd.NA
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["oi_value_change_pct"] = (
        out["sum_open_interest_value"].pct_change(fill_method=None).mul(100.0).fillna(0.0).round(10)
    )
    out["global_crowd_follow"] = _ratio_crowd_follow(out["signal"], out["global_long_short_ratio"]).fillna(0.0)
    out["top_account_crowd_follow"] = _ratio_crowd_follow(out["signal"], out["top_account_long_short_ratio"]).fillna(0.0)
    out["top_position_crowd_follow"] = _ratio_crowd_follow(
        out["signal"],
        out["top_position_long_short_ratio"],
    ).fillna(0.0)
    out["derivatives_crowd_score"] = out[
        ["global_crowd_follow", "top_account_crowd_follow", "top_position_crowd_follow"]
    ].mean(axis=1)
    return out


def _label_recent_derivatives_context(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["signal"] = pd.to_numeric(out["signal"], errors="coerce").fillna(0.0)
    out["global_crowd_follow"] = pd.to_numeric(out["global_crowd_follow"], errors="coerce").fillna(0.0)
    out["top_position_crowd_follow"] = pd.to_numeric(out["top_position_crowd_follow"], errors="coerce").fillna(0.0)
    out["oi_value_change_pct"] = pd.to_numeric(out["oi_value_change_pct"], errors="coerce").fillna(0.0)

    crowded = (
        (out["global_crowd_follow"] >= 0.5)
        & (out["top_position_crowd_follow"] >= 0.5)
        & (out["oi_value_change_pct"] > 0.0)
    )
    out["derivatives_context"] = "balanced_or_unknown"
    out.loc[(out["oi_value_change_pct"] <= 0.0) | (out["global_crowd_follow"] <= 0.0), "derivatives_context"] = (
        "not_crowded_or_deleveraging"
    )
    out.loc[crowded & (out["signal"] > 0.0), "derivatives_context"] = "crowded_long_risk"
    out.loc[crowded & (out["signal"] < 0.0), "derivatives_context"] = "crowded_short_risk"
    return out


def _sentiment_coverage_summary(frame: pd.DataFrame) -> dict[str, object]:
    valid = frame.loc[
        frame["timestamp"].notna()
        & frame.get("global_long_short_ratio", pd.Series(index=frame.index, dtype=float)).notna()
        & frame.get("sum_open_interest_value", pd.Series(index=frame.index, dtype=float)).notna()
    ].copy()
    if valid.empty:
        return {
            "monitored_trade_count": 0,
            "coverage_start": "",
            "coverage_end": "",
            "coverage_days": 0.0,
            "coverage_policy": "no_recent_derivatives_data",
            "eligible_for_strategy_promotion": False,
        }
    valid["timestamp"] = _to_utc(valid["timestamp"])
    coverage_days = (valid["timestamp"].max() - valid["timestamp"].min()).total_seconds() / 86400.0
    eligible = coverage_days >= MIN_STRATEGY_PROMOTION_DAYS and len(valid) >= MIN_STRATEGY_PROMOTION_TRADES
    return {
        "monitored_trade_count": int(len(valid)),
        "coverage_start": valid["timestamp"].min().isoformat(),
        "coverage_end": valid["timestamp"].max().isoformat(),
        "coverage_days": float(coverage_days),
        "coverage_policy": "strategy_research_ready" if eligible else "recent_monitoring_only",
        "eligible_for_strategy_promotion": bool(eligible),
    }


def _context_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return_col = "candidate_account_return_pct" if "candidate_account_return_pct" in frame.columns else "account_return_pct"
    out = frame.copy()
    out[return_col] = pd.to_numeric(out[return_col], errors="coerce").fillna(0.0)
    out["win"] = out[return_col] > 0.0
    grouped = (
        out.groupby("derivatives_context", dropna=False)
        .agg(
            trade_count=(return_col, "size"),
            account_return_pct=(return_col, "sum"),
            win_rate=("win", "mean"),
            avg_global_crowd_follow=("global_crowd_follow", "mean"),
            avg_oi_value_change_pct=("oi_value_change_pct", "mean"),
        )
        .reset_index()
        .sort_values("trade_count", ascending=False, kind="mergesort")
    )
    grouped["win_rate"] = grouped["win_rate"] * 100.0
    return grouped


def _load_v144_account_path() -> pd.DataFrame:
    if not V144_ACCOUNT_PATH.exists():
        v144.run()
    frame = pd.read_csv(V144_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    return frame


def _load_recent_derivatives_metrics() -> tuple[pd.DataFrame, dict[str, dict[str, object]]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    specs = {
        "open_interest": ("openInterestHist", _normalize_open_interest),
        "global_ratio": ("globalLongShortAccountRatio", lambda frame: _normalize_long_short_ratio(frame, "global")),
        "top_account_ratio": ("topLongShortAccountRatio", lambda frame: _normalize_long_short_ratio(frame, "top_account")),
        "top_position_ratio": ("topLongShortPositionRatio", lambda frame: _normalize_long_short_ratio(frame, "top_position")),
    }
    normalized: dict[str, pd.DataFrame] = {}
    summaries: dict[str, dict[str, object]] = {}
    for name, (endpoint, normalizer) in specs.items():
        raw = _download_recent_binance_metric(endpoint)
        raw.to_csv(OUT_DIR / f"v145_raw_{name}.csv", index=False)
        metric = normalizer(raw)
        metric.to_csv(OUT_DIR / f"v145_{name}.csv", index=False)
        normalized[name] = metric
        summaries[name] = {
            "endpoint": endpoint,
            "rows": int(len(metric)),
            "start": metric["metric_time"].min().isoformat(),
            "end": metric["metric_time"].max().isoformat(),
        }
        time.sleep(0.05)

    merged = normalized["open_interest"]
    for name in ("global_ratio", "top_account_ratio", "top_position_ratio"):
        merged = pd.merge_asof(
            merged.sort_values("metric_time", kind="mergesort"),
            normalized[name].sort_values("metric_time", kind="mergesort"),
            on="metric_time",
            direction="nearest",
            tolerance=pd.Timedelta(minutes=1),
        )
    return merged.reset_index(drop=True), summaries


def _join_derivatives_to_trades(trades: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    metric_cols = [col for col in metrics.columns if col != "metric_time"]
    joined = _join_prior_metric(
        trades,
        metrics,
        metric_time_col="metric_time",
        metric_cols=metric_cols,
        output_time_col="derivatives_metric_time",
    )
    return _label_recent_derivatives_context(_add_derivatives_sentiment_features(joined))


def _write_report(
    payload: dict[str, object],
    context_table: pd.DataFrame,
    recent_trades: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    coverage = payload["coverage"]
    lines = [
        "# Research V145 BTCUSDC Derivatives Sentiment Monitor",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v146']}`",
        f"- Message: {decision['message']}",
        "",
        "## Coverage",
        "",
        pd.DataFrame([coverage]).to_csv(index=False).strip(),
        "",
        "## Source Metrics",
        "",
        pd.DataFrame(payload["source_metrics"].values()).to_csv(index=False).strip(),
        "",
        "## Recent Context Metrics",
        "",
        context_table.to_csv(index=False).strip() if not context_table.empty else "No monitored trades.",
        "",
        "## Recent Monitored Trades",
        "",
        recent_trades.to_csv(index=False).strip() if not recent_trades.empty else "No monitored trades.",
        "",
        "## Interpretation",
        "",
        "V145 treats Binance open interest and long/short ratios as recent derivatives-positioning context. These endpoints only provide the latest 30 days or latest 1 month of history, so this report does not promote a new strategy and does not claim a two-year backtest improvement.",
        "",
        "The useful role is monitoring: flag when a V144 trade is aligned with a crowded derivatives side while open interest is expanding. That is a risk label, not a standalone buy/sell signal.",
        "",
        "This is a research monitor, not a live trading guarantee.",
        "",
        "## References",
        "",
        "- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics",
        "- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio",
        "- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio",
        "- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Ratio",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    trades = _load_v144_account_path()
    metrics, source_summaries = _load_recent_derivatives_metrics()
    monitored = _join_derivatives_to_trades(trades, metrics)
    monitored.to_csv(OUT_DIR / "v145_v144_with_derivatives_sentiment.csv", index=False)

    coverage = _sentiment_coverage_summary(monitored)
    recent = monitored.loc[monitored["global_long_short_ratio"].notna()].copy()
    context_table = _context_metrics(recent)
    context_table.to_csv(OUT_DIR / "v145_derivatives_context_metrics.csv", index=False)
    recent_cols = [
        "timestamp",
        "signal",
        "candidate_account_return_pct",
        "derivatives_context",
        "global_long_short_ratio",
        "top_position_long_short_ratio",
        "sum_open_interest_value",
        "oi_value_change_pct",
        "global_crowd_follow",
        "top_position_crowd_follow",
    ]
    recent_trades = recent[[col for col in recent_cols if col in recent.columns]].tail(30)
    recent_trades.to_csv(OUT_DIR / "v145_recent_monitored_trades.csv", index=False)

    decision = {
        "status": "derivatives_sentiment_recent_monitor_ready",
        "promote_to_v146": False,
        "message": (
            "Recent OI and long/short ratios are useful monitoring context, but their Binance history window is too short for strategy promotion."
        ),
    }
    payload = {
        "config": {
            "base": "v144_funding_sentiment_governor",
            "symbol": SYMBOL,
            "period": PERIOD,
            "limit": LIMIT,
            "strategy_promotion_min_days": MIN_STRATEGY_PROMOTION_DAYS,
            "strategy_promotion_min_trades": MIN_STRATEGY_PROMOTION_TRADES,
        },
        "source_metrics": source_summaries,
        "coverage": coverage,
        "decision": decision,
    }
    (OUT_DIR / "v145_derivatives_sentiment_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, context_table, recent_trades)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
