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
import run_btcusdc_v143_market_emotion_trend_audit as v143


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v144_funding_sentiment_governor"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V144_BTCUSDC_FUNDING_SENTIMENT_GOVERNOR.md"
V142_ACCOUNT_PATH = ROOT / "runs" / "research_v142_high_confidence_rescue_5x" / "v142_selected_account_path.csv"
V119_FEATURE_FRAME = ROOT / "runs" / "research_v119_btcusdc_live_entry_model" / "v119_live_feature_frame.csv"
FUNDING_CACHE = OUT_DIR / "btc_usdc_funding_rates.csv"
SYMBOL = "BTCUSDC"
SELECTOR_END = pd.Timestamp("2026-01-01T00:00:00Z")
MIN_SELECTOR_TRADES = 80
MIN_FULL_IMPROVEMENT_RATE = 1.05
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


@dataclass(frozen=True)
class GovernorSpec:
    name: str
    policy_type: str
    crowd_operator: str
    crowd_threshold: float
    trend_operator: str | None = None
    trend_threshold: float | None = None


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


def _download_funding_rates(
    *,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    sleep_seconds: float = 0.05,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    cursor_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    while cursor_ms <= end_ms:
        batch = _request_json(
            BINANCE_FUNDING_URL,
            {
                "symbol": symbol,
                "startTime": cursor_ms,
                "endTime": end_ms,
                "limit": 1000,
            },
        )
        if not batch:
            break
        rows.extend(batch)
        last_ms = int(batch[-1]["fundingTime"])
        next_ms = last_ms + 1
        if next_ms <= cursor_ms:
            break
        cursor_ms = next_ms
        if len(batch) < 1000:
            break
        time.sleep(sleep_seconds)

    if not rows:
        raise RuntimeError("No funding rows downloaded")
    frame = pd.DataFrame(rows)
    out = pd.DataFrame(
        {
            "funding_time": pd.to_datetime(pd.to_numeric(frame["fundingTime"]), unit="ms", utc=True),
            "symbol": frame["symbol"],
            "funding_rate": pd.to_numeric(frame["fundingRate"], errors="coerce"),
            "mark_price": pd.to_numeric(frame["markPrice"], errors="coerce"),
        }
    )
    return out.drop_duplicates("funding_time").sort_values("funding_time", kind="mergesort").reset_index(drop=True)


def _load_or_download_funding_rates(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if FUNDING_CACHE.exists():
        cached = pd.read_csv(FUNDING_CACHE)
        cached["funding_time"] = _to_utc(cached["funding_time"])
        if cached["funding_time"].min() <= start and cached["funding_time"].max() >= end - pd.Timedelta(hours=8):
            return cached.sort_values("funding_time", kind="mergesort").reset_index(drop=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    funding = _download_funding_rates(symbol=SYMBOL, start=start, end=end)
    funding.to_csv(FUNDING_CACHE, index=False)
    return funding


def _add_funding_history_features(funding: pd.DataFrame) -> pd.DataFrame:
    out = funding.copy()
    out["funding_time"] = _to_utc(out["funding_time"])
    out["funding_rate"] = pd.to_numeric(out["funding_rate"], errors="coerce")
    out = out.sort_values("funding_time", kind="mergesort").reset_index(drop=True)
    out["funding_rate_bps"] = out["funding_rate"] * 10_000.0
    for label, window, min_periods in (("30d", 90, 10), ("120d", 360, 30)):
        mean = out["funding_rate_bps"].rolling(window=window, min_periods=min_periods).mean()
        std = out["funding_rate_bps"].rolling(window=window, min_periods=min_periods).std(ddof=0)
        out[f"funding_z_{label}"] = ((out["funding_rate_bps"] - mean) / std.replace(0.0, pd.NA)).fillna(0.0)
    out["funding_rate_bps_3"] = out["funding_rate_bps"].rolling(window=3, min_periods=1).mean()
    return out


def _join_prior_funding(trades: pd.DataFrame, funding_features: pd.DataFrame) -> pd.DataFrame:
    left = trades.copy()
    right = funding_features.copy()
    left["timestamp"] = _to_utc(left["timestamp"])
    right["funding_time"] = _to_utc(right["funding_time"])
    joined = pd.merge_asof(
        left.sort_values("timestamp", kind="mergesort"),
        right.sort_values("funding_time", kind="mergesort"),
        left_on="timestamp",
        right_on="funding_time",
        direction="backward",
        allow_exact_matches=True,
    )
    return joined.reset_index(drop=True)


def _add_signed_funding_sentiment_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    signal = pd.to_numeric(out["signal"], errors="coerce").fillna(0.0)
    for col in ("funding_z_30d", "funding_z_120d", "funding_rate_bps", "funding_rate_bps_3"):
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out["funding_crowd_follow_30d"] = signal * out["funding_z_30d"]
    out["funding_crowd_follow_120d"] = signal * out["funding_z_120d"]
    out["funding_crowd_follow_bps"] = signal * out["funding_rate_bps"]
    out["funding_abs_z_30d"] = out["funding_z_30d"].abs()
    out["funding_abs_bps"] = out["funding_rate_bps"].abs()
    return out


def _compare(series: pd.Series, operator: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if operator == ">=":
        return values >= threshold
    if operator == "<=":
        return values <= threshold
    raise ValueError(f"unsupported operator: {operator}")


def _candidate_specs(frame: pd.DataFrame, selector_mask: pd.Series) -> list[GovernorSpec]:
    crowd = pd.to_numeric(frame.loc[selector_mask, "funding_crowd_follow_30d"], errors="coerce").dropna()
    trend = pd.to_numeric(frame.loc[selector_mask, "trend_follow_720_bps"], errors="coerce").dropna()
    if crowd.nunique() < 4 or trend.nunique() < 4:
        return []
    crowd_quantiles = crowd.quantile([0.2, 0.33, 0.67, 0.8]).drop_duplicates()
    trend_quantiles = trend.quantile([0.2, 0.33, 0.67, 0.8]).drop_duplicates()
    specs: list[GovernorSpec] = []
    for quantile, threshold in crowd_quantiles.items():
        qname = str(quantile).replace(".", "p")
        specs.append(
            GovernorSpec(
                name=f"halfsize_crowded_funding_q{qname}",
                policy_type="halfsize_crowded",
                crowd_operator=">=",
                crowd_threshold=float(threshold),
            )
        )
        specs.append(
            GovernorSpec(
                name=f"boost115_not_crowded_funding_q{qname}",
                policy_type="boost_not_crowded",
                crowd_operator="<=",
                crowd_threshold=float(threshold),
            )
        )
    for c_quantile, c_threshold in crowd_quantiles.items():
        for t_quantile, t_threshold in trend_quantiles.items():
            c_name = str(c_quantile).replace(".", "p")
            t_name = str(t_quantile).replace(".", "p")
            specs.append(
                GovernorSpec(
                    name=f"halfsize_crowded_trend_q{c_name}_t{t_name}",
                    policy_type="halfsize_crowded",
                    crowd_operator=">=",
                    crowd_threshold=float(c_threshold),
                    trend_operator=">=",
                    trend_threshold=float(t_threshold),
                )
            )
            specs.append(
                GovernorSpec(
                    name=f"boost115_not_crowded_contrarian_q{c_name}_t{t_name}",
                    policy_type="boost_not_crowded",
                    crowd_operator="<=",
                    crowd_threshold=float(c_threshold),
                    trend_operator="<=",
                    trend_threshold=float(t_threshold),
                )
            )
    return specs


def _apply_governor(frame: pd.DataFrame, spec: GovernorSpec) -> pd.DataFrame:
    out = frame.copy()
    condition = _compare(out["funding_crowd_follow_30d"], spec.crowd_operator, spec.crowd_threshold)
    if spec.trend_operator is not None and spec.trend_threshold is not None:
        condition &= _compare(out["trend_follow_720_bps"], spec.trend_operator, spec.trend_threshold)

    multiplier = pd.Series(1.0, index=out.index)
    if spec.policy_type == "halfsize_crowded":
        multiplier.loc[condition.fillna(False)] = 0.5
    elif spec.policy_type == "boost_not_crowded":
        boostable = condition.fillna(False)
        if "prior_drawdown_pct" in out.columns:
            boostable &= pd.to_numeric(out["prior_drawdown_pct"], errors="coerce").fillna(-999.0) > -5.0
        multiplier.loc[boostable] = 1.15
    else:
        raise ValueError(f"unsupported policy type: {spec.policy_type}")
    out["candidate_account_return_pct"] = out["account_return_pct"] * multiplier
    out["candidate_account_pnl_bps"] = out["account_pnl_bps"] * multiplier
    out["v144_multiplier"] = multiplier
    return out


def _baseline_metrics(frame: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[dict[str, dict[str, object]], dict[str, pd.Index]]:
    metrics: dict[str, dict[str, object]] = {}
    months: dict[str, pd.Index] = {}
    for period, mask in masks.items():
        period_path = frame.loc[mask].copy()
        months[period] = v143._month_index(period_path)
        metrics[period] = v143._account_metrics(
            f"v142_{period}",
            period_path,
            return_col="account_return_pct",
            pnl_col="account_pnl_bps",
            baseline_months=months[period],
        )
    return metrics, months


def _evaluate_candidate(
    frame: pd.DataFrame,
    spec: GovernorSpec,
    *,
    masks: dict[str, pd.Series],
    baseline_metrics: dict[str, dict[str, object]],
    baseline_months: dict[str, pd.Index],
) -> dict[str, object]:
    candidate_path = _apply_governor(frame, spec)
    row: dict[str, object] = {
        "candidate": spec.name,
        "policy_type": spec.policy_type,
        "crowd_operator": spec.crowd_operator,
        "crowd_threshold": spec.crowd_threshold,
        "trend_operator": spec.trend_operator or "",
        "trend_threshold": spec.trend_threshold if spec.trend_threshold is not None else "",
        "changed_trade_count": int((candidate_path["v144_multiplier"] != 1.0).sum()),
    }
    for period, mask in masks.items():
        period_path = candidate_path.loc[mask].copy()
        metrics = v143._account_metrics(
            f"{spec.name}_{period}",
            period_path,
            return_col="candidate_account_return_pct",
            pnl_col="candidate_account_pnl_bps",
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
        ["selector_delta_return_pct", "selector_delta_drawdown_pct", "holdout_delta_return_pct"],
        ascending=[False, False, False],
        kind="mergesort",
    )
    return eligible.iloc[0].to_dict()


def _passes_v144_gate(candidate: dict[str, object], baseline: dict[str, dict[str, object]]) -> bool:
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


def _write_report(
    payload: dict[str, object],
    baseline_table: pd.DataFrame,
    top_candidates: pd.DataFrame,
    funding_summary: dict[str, object],
    selected_monthly: pd.DataFrame,
) -> None:
    selected = payload["selected_candidate"]
    decision = payload["decision"]
    lines = [
        "# Research V144 BTCUSDC Funding Sentiment Governor",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to next model: `{decision['promote_to_v145']}`",
        f"- Message: {decision['message']}",
        f"- Selector period: `< {SELECTOR_END.isoformat()}`",
        f"- Holdout period: `>= {SELECTOR_END.isoformat()}`",
        "",
        "## Funding Data",
        "",
        pd.DataFrame([funding_summary]).to_csv(index=False).strip(),
        "",
        "## Research Inputs",
        "",
        "- Binance documentation describes funding rates as a perpetual-futures mechanism that also reflects market sentiment and position holding cost.",
        "- Binance futures market metrics include funding, open interest, and long/short ratio; BTCUSDC open interest and long/short endpoints were available only for recent history in this environment, while funding covered the full V142 trade window.",
        "- Fear & Greed research is mixed for short-horizon prediction: one study finds a U-shaped relationship with crypto synchronicity, while another 2018-2025 study finds Bitcoin returns lead Fear & Greed changes more than the reverse. V144 therefore uses funding as the primary short-term emotion proxy and leaves Fear & Greed as a future macro-risk overlay.",
        "",
        "## Baseline",
        "",
        baseline_table.to_csv(index=False).strip(),
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
            "V144 uses Binance BTCUSDC perpetual funding as an external market-emotion proxy. The signed funding crowding feature is positive when the trade direction follows the side paying elevated funding and negative when the trade fades it. The selected candidate does not trade funding alone: it applies a small 1.15x boost only when the trade is in an extreme prior-trend contrarian zone and is not highly funding-crowded. Candidate selection uses only the selector period; the later holdout is reported after selection.",
            "",
            "This is a research audit, not a live trading guarantee.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v142_frame = pd.read_csv(V142_ACCOUNT_PATH)
    v119_frame = pd.read_csv(V119_FEATURE_FRAME)
    base = v143._add_market_emotion_trend_features(v143._join_v142_with_v119_features(v142_frame, v119_frame))
    start = pd.to_datetime(base["timestamp"], utc=True).min() - pd.Timedelta(days=2)
    end = pd.to_datetime(base["timestamp"], utc=True).max() + pd.Timedelta(days=2)
    funding = _load_or_download_funding_rates(start, end)
    funding_features = _add_funding_history_features(funding)
    frame = _add_signed_funding_sentiment_features(_join_prior_funding(base, funding_features))
    frame.to_csv(OUT_DIR / "v144_v142_with_funding_sentiment_features.csv", index=False)

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
            ["selector_delta_return_pct", "selector_delta_drawdown_pct"],
            ascending=[False, False],
            kind="mergesort",
        )
    candidates.to_csv(OUT_DIR / "v144_funding_sentiment_candidates.csv", index=False)
    selected = _select_best_candidate(candidates)
    passed = _passes_v144_gate(selected, baseline)
    decision = {
        "status": "funding_sentiment_governor_passed" if passed else "funding_sentiment_governor_not_promoted",
        "promote_to_v145": bool(passed),
        "message": (
            "Funding sentiment improved return without worsening holdout/full drawdown."
            if passed
            else "Funding sentiment contains useful context, but the selected governor did not clear the full risk gate."
        ),
    }
    funding_summary = {
        "symbol": SYMBOL,
        "funding_rows": int(len(funding_features)),
        "funding_start": funding_features["funding_time"].min().isoformat(),
        "funding_end": funding_features["funding_time"].max().isoformat(),
        "avg_funding_rate_bps": float(funding_features["funding_rate_bps"].mean()),
        "min_funding_rate_bps": float(funding_features["funding_rate_bps"].min()),
        "max_funding_rate_bps": float(funding_features["funding_rate_bps"].max()),
    }
    payload = {
        "config": {
            "base": "v142_high_confidence_rescue_5x",
            "trend_emotion_base": "v143_market_emotion_trend_features",
            "external_sentiment_source": "binance_usdm_btcusdc_funding_rate",
            "selector_end": SELECTOR_END.isoformat(),
            "min_full_improvement_rate": MIN_FULL_IMPROVEMENT_RATE,
            "uses_holdout_for_selection": False,
        },
        "funding_summary": funding_summary,
        "baseline": baseline,
        "selected_candidate": selected,
        "decision": decision,
    }
    selected_monthly = pd.DataFrame()
    if selected:
        selected_spec = next((spec for spec in specs if spec.name == selected["candidate"]), None)
        if selected_spec is not None:
            selected_path = _apply_governor(frame, selected_spec)
            selected_path.to_csv(OUT_DIR / "v144_selected_account_path.csv", index=False)
            selected_monthly = (
                selected_path.assign(month=selected_path["timestamp"].dt.strftime("%Y-%m"))
                .groupby("month", sort=True)["candidate_account_return_pct"]
                .sum()
                .reset_index()
                .rename(columns={"candidate_account_return_pct": "account_return_pct"})
            )
    (OUT_DIR / "v144_funding_sentiment_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, pd.DataFrame(baseline.values()), candidates.head(20), funding_summary, selected_monthly)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
