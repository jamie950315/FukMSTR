from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v144_funding_sentiment_governor as v144


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v148_premium_basis_sentiment_overlay"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V148_BTCUSDC_PREMIUM_BASIS_SENTIMENT_OVERLAY.md"
V144_ACCOUNT_PATH = ROOT / "runs" / "research_v144_funding_sentiment_governor" / "v144_selected_account_path.csv"
PREMIUM_CACHE = OUT_DIR / "btcusdc_premium_index_1h.csv"
SYMBOL = "BTCUSDC"
INTERVAL = "1h"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_SELECTOR_TRADES = 80
MIN_FULL_IMPROVEMENT_RATE = 1.03
BINANCE_PREMIUM_KLINES_URL = "https://fapi.binance.com/fapi/v1/premiumIndexKlines"


@dataclass(frozen=True)
class PremiumOverlaySpec:
    name: str
    policy_type: str
    crowd_operator: str
    crowd_threshold: float
    trend_operator: str | None = None
    trend_threshold: float | None = None
    multiplier: float = 1.0


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _request_json(url: str, params: dict[str, object]) -> list[list[object]]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "FukMSTR-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict) and "code" in payload:
        raise RuntimeError(f"Binance API error: {payload}")
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Binance response: {payload!r}")
    return payload


def _parse_premium_klines(rows: list[list[object]]) -> pd.DataFrame:
    if not rows:
        raise RuntimeError("No premium index kline rows returned")
    frame = pd.DataFrame(
        rows,
        columns=[
            "open_time_ms",
            "premium_open",
            "premium_high",
            "premium_low",
            "premium_close",
            "ignore_volume",
            "close_time_ms",
            "ignore_quote_volume",
            "ignore_trade_count",
            "ignore_taker_base",
            "ignore_taker_quote",
            "ignore_unused",
        ],
    )
    out = pd.DataFrame(
        {
            "premium_open_time": pd.to_datetime(pd.to_numeric(frame["open_time_ms"]), unit="ms", utc=True).astype(
                "datetime64[ns, UTC]"
            ),
            # Use close_time + 1ms as the first moment the closed kline is safely available.
            "premium_time": pd.to_datetime(pd.to_numeric(frame["close_time_ms"]) + 1, unit="ms", utc=True).astype(
                "datetime64[ns, UTC]"
            ),
            "premium_open": pd.to_numeric(frame["premium_open"], errors="coerce"),
            "premium_high": pd.to_numeric(frame["premium_high"], errors="coerce"),
            "premium_low": pd.to_numeric(frame["premium_low"], errors="coerce"),
            "premium_close": pd.to_numeric(frame["premium_close"], errors="coerce"),
        }
    )
    return out.drop_duplicates("premium_time").sort_values("premium_time", kind="mergesort").reset_index(drop=True)


def _download_premium_klines(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    sleep_seconds: float = 0.05,
) -> pd.DataFrame:
    rows: list[list[object]] = []
    cursor_ms = int(start.floor("h").timestamp() * 1000)
    end_ms = int(end.ceil("h").timestamp() * 1000)
    while cursor_ms <= end_ms:
        batch = _request_json(
            BINANCE_PREMIUM_KLINES_URL,
            {
                "symbol": SYMBOL,
                "interval": INTERVAL,
                "startTime": cursor_ms,
                "endTime": end_ms,
                "limit": 1500,
            },
        )
        if not batch:
            break
        rows.extend(batch)
        last_open_ms = int(batch[-1][0])
        next_ms = last_open_ms + 3_600_000
        if next_ms <= cursor_ms:
            break
        cursor_ms = next_ms
        if len(batch) < 1500:
            break
        time.sleep(sleep_seconds)
    return _parse_premium_klines(rows)


def _load_or_download_premium(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if PREMIUM_CACHE.exists():
        cached = pd.read_csv(PREMIUM_CACHE)
        cached["premium_time"] = _to_utc(cached["premium_time"])
        cached["premium_open_time"] = _to_utc(cached["premium_open_time"])
        if cached["premium_time"].min() <= start and cached["premium_time"].max() >= end:
            return cached.sort_values("premium_time", kind="mergesort").reset_index(drop=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    premium = _download_premium_klines(start=start - pd.Timedelta(days=2), end=end + pd.Timedelta(days=2))
    premium.to_csv(PREMIUM_CACHE, index=False)
    return premium


def _add_premium_features(premium: pd.DataFrame) -> pd.DataFrame:
    out = premium.copy()
    out["premium_time"] = _to_utc(out["premium_time"])
    out["premium_close"] = pd.to_numeric(out["premium_close"], errors="coerce")
    out = out.sort_values("premium_time", kind="mergesort").reset_index(drop=True)
    out["premium_close_bps"] = out["premium_close"] * 10_000.0
    out["premium_abs_bps"] = out["premium_close_bps"].abs()
    for label, window, min_periods in (("30d", 24 * 30, 24 * 5), ("120d", 24 * 120, 24 * 20)):
        mean = out["premium_close_bps"].rolling(window=window, min_periods=min_periods).mean()
        std = out["premium_close_bps"].rolling(window=window, min_periods=min_periods).std(ddof=0)
        out[f"premium_z_{label}"] = ((out["premium_close_bps"] - mean) / std.replace(0.0, pd.NA)).fillna(0.0)
    out["premium_close_bps_6h"] = out["premium_close_bps"].rolling(window=6, min_periods=1).mean()
    return out


def _join_prior_premium(trades: pd.DataFrame, premium_features: pd.DataFrame) -> pd.DataFrame:
    left = trades.copy()
    right = premium_features.copy()
    left["timestamp"] = _to_utc(left["timestamp"])
    right["premium_time"] = _to_utc(right["premium_time"])
    joined = pd.merge_asof(
        left.sort_values("timestamp", kind="mergesort"),
        right.sort_values("premium_time", kind="mergesort"),
        left_on="timestamp",
        right_on="premium_time",
        direction="backward",
        allow_exact_matches=True,
    )
    return joined.reset_index(drop=True)


def _add_signed_premium_sentiment_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    signal = pd.to_numeric(out["signal"], errors="coerce").fillna(0.0)
    for col in ("premium_z_30d", "premium_z_120d", "premium_close_bps", "premium_close_bps_6h"):
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out["premium_crowd_follow_30d"] = signal * out["premium_z_30d"]
    out["premium_crowd_follow_120d"] = signal * out["premium_z_120d"]
    out["premium_crowd_follow_bps"] = signal * out["premium_close_bps"]
    out["premium_crowd_follow_bps_6h"] = signal * out["premium_close_bps_6h"]
    return out


def _compare(series: pd.Series, operator: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if operator == ">=":
        return values >= threshold
    if operator == "<=":
        return values <= threshold
    raise ValueError(f"unsupported operator: {operator}")


def _candidate_specs(frame: pd.DataFrame, selector_mask: pd.Series) -> list[PremiumOverlaySpec]:
    crowd = pd.to_numeric(frame.loc[selector_mask, "premium_crowd_follow_30d"], errors="coerce").dropna()
    trend = pd.to_numeric(frame.loc[selector_mask, "trend_follow_720_bps"], errors="coerce").dropna()
    if crowd.nunique() < 4 or trend.nunique() < 4:
        return []
    crowd_quantiles = crowd.quantile([0.2, 0.33, 0.67, 0.8]).drop_duplicates()
    trend_quantiles = trend.quantile([0.2, 0.33, 0.67, 0.8]).drop_duplicates()
    specs: list[PremiumOverlaySpec] = []
    for quantile, threshold in crowd_quantiles.items():
        qname = str(quantile).replace(".", "p")
        for multiplier in (0.5, 0.75):
            mult_name = str(multiplier).replace(".", "p")
            specs.append(
                PremiumOverlaySpec(
                    name=f"trim{mult_name}_crowded_premium_q{qname}",
                    policy_type="trim_crowded",
                    crowd_operator=">=",
                    crowd_threshold=float(threshold),
                    multiplier=multiplier,
                )
            )
        for multiplier in (1.10, 1.15):
            mult_name = str(multiplier).replace(".", "p")
            specs.append(
                PremiumOverlaySpec(
                    name=f"boost{mult_name}_not_crowded_premium_q{qname}",
                    policy_type="boost_not_crowded",
                    crowd_operator="<=",
                    crowd_threshold=float(threshold),
                    multiplier=multiplier,
                )
            )
    for c_quantile, c_threshold in crowd_quantiles.items():
        for t_quantile, t_threshold in trend_quantiles.items():
            c_name = str(c_quantile).replace(".", "p")
            t_name = str(t_quantile).replace(".", "p")
            specs.append(
                PremiumOverlaySpec(
                    name=f"boost110_not_crowded_contrarian_premium_q{c_name}_t{t_name}",
                    policy_type="boost_not_crowded",
                    crowd_operator="<=",
                    crowd_threshold=float(c_threshold),
                    trend_operator="<=",
                    trend_threshold=float(t_threshold),
                    multiplier=1.10,
                )
            )
            specs.append(
                PremiumOverlaySpec(
                    name=f"boost115_not_crowded_contrarian_premium_q{c_name}_t{t_name}",
                    policy_type="boost_not_crowded",
                    crowd_operator="<=",
                    crowd_threshold=float(c_threshold),
                    trend_operator="<=",
                    trend_threshold=float(t_threshold),
                    multiplier=1.15,
                )
            )
    return specs


def _apply_overlay(frame: pd.DataFrame, spec: PremiumOverlaySpec) -> pd.DataFrame:
    out = frame.copy()
    condition = _compare(out["premium_crowd_follow_30d"], spec.crowd_operator, spec.crowd_threshold)
    if spec.trend_operator is not None and spec.trend_threshold is not None:
        condition &= _compare(out["trend_follow_720_bps"], spec.trend_operator, spec.trend_threshold)
    if spec.policy_type == "boost_not_crowded" and "prior_drawdown_pct" in out.columns:
        condition &= pd.to_numeric(out["prior_drawdown_pct"], errors="coerce").fillna(-999.0) > -5.0
    multiplier = pd.Series(1.0, index=out.index)
    multiplier.loc[condition.fillna(False)] = spec.multiplier
    out["v148_multiplier"] = multiplier
    out["v148_account_return_pct"] = out["candidate_account_return_pct"] * multiplier
    out["v148_account_pnl_bps"] = out["candidate_account_pnl_bps"] * multiplier
    return out


def _baseline_metrics(frame: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[dict[str, dict[str, object]], dict[str, pd.Index]]:
    metrics: dict[str, dict[str, object]] = {}
    months: dict[str, pd.Index] = {}
    for period, mask in masks.items():
        period_path = frame.loc[mask].copy()
        months[period] = v144.v143._month_index(period_path)
        metrics[period] = v144.v143._account_metrics(
            f"v144_{period}",
            period_path,
            return_col="candidate_account_return_pct",
            pnl_col="candidate_account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _evaluate_candidate(
    frame: pd.DataFrame,
    spec: PremiumOverlaySpec,
    *,
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    candidate_path = _apply_overlay(frame, spec)
    row: dict[str, object] = {
        "candidate": spec.name,
        "policy_type": spec.policy_type,
        "crowd_operator": spec.crowd_operator,
        "crowd_threshold": spec.crowd_threshold,
        "trend_operator": spec.trend_operator or "",
        "trend_threshold": spec.trend_threshold if spec.trend_threshold is not None else "",
        "multiplier": spec.multiplier,
        "changed_trade_count": int((candidate_path["v148_multiplier"] != 1.0).sum()),
    }
    for period, mask in masks.items():
        metrics = v144.v143._account_metrics(
            f"{spec.name}_{period}",
            candidate_path.loc[mask].copy(),
            return_col="v148_account_return_pct",
            pnl_col="v148_account_pnl_bps",
            baseline_months=baseline_months[period],
        )
        base = baseline_metrics[period]
        row[f"{period}_trade_count"] = metrics["trade_count"]
        row[f"{period}_return_pct"] = metrics["total_account_return_pct"]
        row[f"{period}_delta_return_pct"] = (
            float(metrics["total_account_return_pct"]) - float(base["total_account_return_pct"])
        )
        row[f"{period}_max_drawdown_pct"] = metrics["max_drawdown_pct"]
        row[f"{period}_delta_drawdown_pct"] = (
            float(metrics["max_drawdown_pct"]) - float(base["max_drawdown_pct"])
        )
        row[f"{period}_positive_months"] = metrics["positive_months"]
        row[f"{period}_month_count"] = metrics["month_count"]
        row[f"{period}_worst_month_pct"] = metrics["worst_month_pct"]
        row[f"{period}_win_rate"] = metrics["win_rate"]
    return row


def _select_best_candidate(candidates: pd.DataFrame) -> dict[str, object]:
    if candidates.empty:
        return {}
    eligible = candidates.loc[
        (candidates["selector_trade_count"] >= MIN_SELECTOR_TRADES)
        & (candidates["selector_delta_return_pct"] > 0.0)
        & (candidates["selector_delta_drawdown_pct"] >= 0.0)
        & (candidates["selector_positive_months"] == candidates["selector_month_count"])
    ].copy()
    if eligible.empty:
        return {}
    eligible = eligible.sort_values(
        ["selector_delta_return_pct", "selector_delta_drawdown_pct", "changed_trade_count"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    return eligible.iloc[0].to_dict()


def _passes_v148_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
    if not candidate:
        return False
    return (
        float(candidate["full_return_pct"])
        >= float(baseline["full"]["total_account_return_pct"]) * MIN_FULL_IMPROVEMENT_RATE
        and float(candidate["full_max_drawdown_pct"]) >= float(baseline["full"]["max_drawdown_pct"])
        and int(candidate["full_positive_months"]) == int(candidate["full_month_count"])
        and float(candidate["holdout_return_pct"]) > float(baseline["holdout"]["total_account_return_pct"])
        and float(candidate["holdout_max_drawdown_pct"]) >= float(baseline["holdout"]["max_drawdown_pct"])
        and int(candidate["holdout_positive_months"]) == int(candidate["holdout_month_count"])
    )


def _premium_context_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["premium_bucket"] = pd.qcut(
        pd.to_numeric(out["premium_crowd_follow_30d"], errors="coerce"),
        q=5,
        duplicates="drop",
    )
    out["win"] = pd.to_numeric(out["candidate_account_return_pct"], errors="coerce") > 0.0
    grouped = (
        out.groupby("premium_bucket", observed=False)
        .agg(
            trade_count=("candidate_account_return_pct", "size"),
            account_return_pct=("candidate_account_return_pct", "sum"),
            win_rate=("win", "mean"),
            avg_premium_close_bps=("premium_close_bps", "mean"),
            avg_premium_crowd_follow_30d=("premium_crowd_follow_30d", "mean"),
        )
        .reset_index()
    )
    grouped["premium_bucket"] = grouped["premium_bucket"].astype(str)
    grouped["win_rate"] = grouped["win_rate"] * 100.0
    return grouped


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    context_table: pd.DataFrame,
    top_candidates: pd.DataFrame,
    selected_monthly: pd.DataFrame,
) -> None:
    selected = payload["selected_candidate"]
    decision = payload["decision"]
    lines = [
        "# Research V148 BTCUSDC Premium Basis Sentiment Overlay",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v149']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Premium Data",
        "",
        pd.DataFrame([payload["premium_summary"]]).to_csv(index=False).strip(),
        "",
        "## Research Inputs",
        "",
        "- Binance premium index klines measure the perpetual premium/basis through time and can be fetched with historical start/end windows.",
        "- Perpetual premium is closer to short-term leverage demand than macro sentiment. Positive premium implies stronger long demand; negative premium implies stronger short demand or deleveraging.",
        "- V148 uses only closed premium klines, so current-hour close values are not visible to trades inside that hour.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
        "",
        "## Premium Context Metrics",
        "",
        context_table.to_csv(index=False).strip(),
        "",
        "## Selected Candidate",
        "",
    ]
    if selected:
        lines.extend(pd.DataFrame([selected]).to_csv(index=False).strip().splitlines())
    else:
        lines.append("No eligible selector candidate.")
    lines.extend(
        [
            "",
            "## Selected Monthly Account Return",
            "",
            selected_monthly.to_csv(index=False).strip() if not selected_monthly.empty else "No selected candidate.",
            "",
            "## Top Selector Candidates",
            "",
            top_candidates.to_csv(index=False).strip() if not top_candidates.empty else "No candidates.",
            "",
            "## Interpretation",
            "",
            "V148 tests whether premium/basis adds useful derivatives-sentiment information beyond V144 funding. Candidate selection uses only the pre-2026 selector period; the 2026 holdout is reported after selection.",
            "",
            "This is a research audit, not a live trading guarantee.",
            "",
            "## References",
            "",
            "- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data",
            "- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Basis",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V144_ACCOUNT_PATH.exists():
        v144.run()
    v144_frame = pd.read_csv(V144_ACCOUNT_PATH)
    v144_frame["timestamp"] = _to_utc(v144_frame["timestamp"])
    start = v144_frame["timestamp"].min()
    end = v144_frame["timestamp"].max()
    premium = _load_or_download_premium(start, end)
    premium_features = _add_premium_features(premium)
    frame = _add_signed_premium_sentiment_features(_join_prior_premium(v144_frame, premium_features))
    frame.to_csv(OUT_DIR / "v148_v144_with_premium_basis_features.csv", index=False)

    masks = {
        "full": pd.Series(True, index=frame.index),
        "selector": frame["timestamp"] < SELECTOR_END,
        "holdout": frame["timestamp"] >= SELECTOR_END,
    }
    baseline, months = _baseline_metrics(frame, masks)
    specs = _candidate_specs(frame, masks["selector"])
    candidates = pd.DataFrame(
        [
            _evaluate_candidate(frame, spec, masks=masks, baseline_metrics=baseline, baseline_months=months)
            for spec in specs
        ]
    )
    if not candidates.empty:
        candidates = candidates.sort_values(
            ["selector_delta_return_pct", "selector_delta_drawdown_pct", "changed_trade_count"],
            ascending=[False, False, True],
            kind="mergesort",
        )
    candidates.to_csv(OUT_DIR / "v148_premium_basis_candidates.csv", index=False)
    selected = _select_best_candidate(candidates)
    passed = _passes_v148_gate(selected, baseline)
    decision = {
        "status": "premium_basis_sentiment_overlay_passed" if passed else "premium_basis_sentiment_overlay_not_promoted",
        "promote_to_v149": bool(passed),
        "message": (
            "Premium/basis sentiment improved V144 without worsening holdout/full risk gates."
            if passed
            else "Premium/basis sentiment contains context, but the selected overlay did not clear the promotion gate."
        ),
    }
    premium_summary = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "rows": int(len(premium_features)),
        "start": premium_features["premium_time"].min().isoformat(),
        "end": premium_features["premium_time"].max().isoformat(),
        "avg_premium_close_bps": float(premium_features["premium_close_bps"].mean()),
        "min_premium_close_bps": float(premium_features["premium_close_bps"].min()),
        "max_premium_close_bps": float(premium_features["premium_close_bps"].max()),
    }
    payload = {
        "config": {
            "base": "v144_funding_sentiment_governor",
            "external_sentiment_source": "binance_usdm_premium_index_klines",
            "selector_end": SELECTOR_END.isoformat(),
            "min_full_improvement_rate": MIN_FULL_IMPROVEMENT_RATE,
            "uses_holdout_for_selection": False,
            "uses_closed_klines_only": True,
        },
        "premium_summary": premium_summary,
        "baseline": baseline,
        "selected_candidate": selected,
        "decision": decision,
    }
    selected_monthly = pd.DataFrame()
    if selected:
        selected_spec = next((spec for spec in specs if spec.name == selected["candidate"]), None)
        if selected_spec is not None:
            selected_path = _apply_overlay(frame, selected_spec)
            selected_path.to_csv(OUT_DIR / "v148_selected_account_path.csv", index=False)
            selected_monthly = (
                selected_path.assign(month=selected_path["timestamp"].dt.strftime("%Y-%m"))
                .groupby("month", sort=True)["v148_account_return_pct"]
                .sum()
                .reset_index()
                .rename(columns={"v148_account_return_pct": "account_return_pct"})
            )
    context_table = _premium_context_metrics(frame)
    context_table.to_csv(OUT_DIR / "v148_premium_context_metrics.csv", index=False)
    (OUT_DIR / "v148_premium_basis_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, pd.DataFrame(baseline.values()), context_table, candidates.head(20), selected_monthly)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
