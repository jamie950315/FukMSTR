from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from lob_microprice_lab.btc_contract_data import parse_binance_public_zip
from lob_microprice_lab.btcusdc_direct_ml import build_direct_ml_features, run_prequential_gate_selection


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_input"
OUT_DIR = ROOT / "runs" / "research_v48_btcusdc_full_1m_direct_ml_probe"
BAR_CACHE = INPUT_DIR / "btcusdc_full_1m_bars.csv"


def _load_or_build_bars() -> pd.DataFrame:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    if BAR_CACHE.exists():
        return pd.read_csv(BAR_CACHE, parse_dates=["timestamp"])

    paths = sorted((ROOT / "data" / "binance_public" / "um" / "daily" / "klines" / "BTCUSDC" / "1m").glob("BTCUSDC-1m-*.zip"))
    if not paths:
        raise FileNotFoundError("missing BTCUSDC 1m public kline zip files")
    frames: list[pd.DataFrame] = []
    for path in paths:
        bars = parse_binance_public_zip(path, data_type="klines", interval="1m")
        frames.append(
            bars[
                [
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "quote_volume",
                    "trade_count",
                    "taker_buy_base_volume",
                    "taker_buy_quote_volume",
                ]
            ]
        )
    out = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    out.to_csv(BAR_CACHE, index=False)
    return out


def _walk_forward_folds(features: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    start = pd.to_datetime(features["timestamp"], utc=True).min().ceil("D")
    end = pd.to_datetime(features["timestamp"], utc=True).max().floor("D")
    folds: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    current = start + pd.Timedelta(days=365 + 90)
    while current + pd.Timedelta(days=60) <= end:
        folds.append((current - pd.Timedelta(days=455), current - pd.Timedelta(days=90), current, current + pd.Timedelta(days=60)))
        current += pd.Timedelta(days=60)
    return folds


def _non_overlapping(rows: pd.DataFrame, horizon_minutes: int) -> pd.DataFrame:
    if rows.empty:
        return rows
    ordered = rows.sort_values("timestamp")
    keep: list[int] = []
    last_ts: pd.Timestamp | None = None
    for idx, row in ordered.iterrows():
        ts = pd.Timestamp(row["timestamp"])
        if last_ts is None or ts >= last_ts + pd.Timedelta(minutes=int(horizon_minutes)):
            keep.append(idx)
            last_ts = ts
    return ordered.loc[keep]


def _score_slice(rows: pd.DataFrame) -> dict[str, float | int]:
    if rows.empty:
        return {"trades": 0, "total": 0.0, "mean": 0.0, "day_positive_rate": 0.0}
    daily = rows.assign(day=pd.to_datetime(rows["timestamp"], utc=True).dt.date).groupby("day")["net"].sum()
    return {
        "trades": int(len(rows)),
        "total": float(rows["net"].sum()),
        "mean": float(rows["net"].mean()),
        "day_positive_rate": float((daily > 0).mean()) if len(daily) else 0.0,
    }


def _ridge_probe(features: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    cost_bps = 8.5
    quantiles = [0.70, 0.80, 0.85, 0.90, 0.94, 0.97, 0.985, 0.995]
    horizons = [15, 30, 60, 120, 240, 480, 720, 1440]
    folds = _walk_forward_folds(features)
    rows: list[dict[str, object]] = []

    for horizon in horizons:
        data = features.copy()
        data["future_bps"] = (data["close"].shift(-int(horizon)) / data["close"] - 1.0) * 10000.0
        data = data.dropna(subset=feature_cols + ["future_bps"]).reset_index(drop=True)
        for fold_idx, (train_start, train_end, selector_end, validation_end) in enumerate(folds, start=1):
            train = data.loc[(data["timestamp"] >= train_start) & (data["timestamp"] < train_end)]
            selector = data.loc[(data["timestamp"] >= train_end) & (data["timestamp"] < selector_end)]
            validation = data.loc[(data["timestamp"] >= selector_end) & (data["timestamp"] < validation_end)]
            if len(train) < 10000 or len(selector) < 1000 or len(validation) < 1000:
                continue
            model = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
            model.fit(train[feature_cols], train["future_bps"])
            selector_scored = selector[["timestamp", "future_bps"]].copy()
            selector_scored["pred"] = model.predict(selector[feature_cols])
            validation_scored = validation[["timestamp", "future_bps"]].copy()
            validation_scored["pred"] = model.predict(validation[feature_cols])

            best: dict[str, object] | None = None
            for side in [1, -1]:
                selector_score = selector_scored["pred"] if side == 1 else -selector_scored["pred"]
                validation_score = validation_scored["pred"] if side == 1 else -validation_scored["pred"]
                for quantile in quantiles:
                    threshold = float(selector_score.quantile(float(quantile)))
                    selected = selector_scored.loc[selector_score >= threshold].copy()
                    selected["net"] = side * selected["future_bps"] - cost_bps
                    selected = _non_overlapping(selected, int(horizon))
                    selector_metrics = _score_slice(selected)
                    if int(selector_metrics["trades"]) < 20 or float(selector_metrics["day_positive_rate"]) < 0.45:
                        continue
                    candidate = {
                        "side": int(side),
                        "q": float(quantile),
                        "thr": threshold,
                        "selector_trades": int(selector_metrics["trades"]),
                        "selector_total": float(selector_metrics["total"]),
                        "selector_mean": float(selector_metrics["mean"]),
                        "selector_daypos": float(selector_metrics["day_positive_rate"]),
                    }
                    if best is None or (candidate["selector_total"], candidate["selector_mean"]) > (best["selector_total"], best["selector_mean"]):
                        validated = validation_scored.loc[validation_score >= threshold].copy()
                        validated["net"] = side * validated["future_bps"] - cost_bps
                        validated = _non_overlapping(validated, int(horizon))
                        validation_metrics = _score_slice(validated)
                        candidate.update(
                            {
                                "validation_trades": int(validation_metrics["trades"]),
                                "validation_total": float(validation_metrics["total"]),
                                "validation_mean": float(validation_metrics["mean"]),
                                "validation_daypos": float(validation_metrics["day_positive_rate"]),
                            }
                        )
                        best = candidate

            if best is None:
                rows.append({"horizon": int(horizon), "fold": int(fold_idx), "risk_off": True, "validation_trades": 0, "validation_total": 0.0, "validation_mean": 0.0, "validation_daypos": 0.0})
            else:
                rows.append({"horizon": int(horizon), "fold": int(fold_idx), "risk_off": False, **best})
    return pd.DataFrame(rows)


def _gate_candidates(folds: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for horizon, group in folds.groupby("horizon"):
        for min_selector_total in [0, 250, 500, 1000, 1500, 2000]:
            for min_selector_mean in [0, 5, 10, 15, 20, 30, 50]:
                for min_daypos in [0.45, 0.50, 0.55, 0.60, 0.65]:
                    config = f"h{int(horizon)}_tot{min_selector_total}_mean{min_selector_mean}_day{min_daypos}"
                    for _, row in group.iterrows():
                        active = (
                            not bool(row["risk_off"])
                            and float(row.get("selector_total", -1e9)) >= float(min_selector_total)
                            and float(row.get("selector_mean", -1e9)) >= float(min_selector_mean)
                            and float(row.get("selector_daypos", -1e9)) >= float(min_daypos)
                        )
                        rows.append(
                            {
                                "config": config,
                                "horizon": int(horizon),
                                "min_sel_total": float(min_selector_total),
                                "min_sel_mean": float(min_selector_mean),
                                "min_daypos": float(min_daypos),
                                "fold": int(row["fold"]),
                                "active": bool(active),
                                "validation_total": float(row["validation_total"]) if active else 0.0,
                                "validation_trades": int(row["validation_trades"]) if active else 0,
                            }
                        )
    return pd.DataFrame(rows)


def _summarize_folds(folds: pd.DataFrame) -> pd.DataFrame:
    return (
        folds.groupby("horizon")
        .agg(
            folds=("fold", "count"),
            active=("risk_off", lambda x: int((~x.astype(bool)).sum())),
            passed=("validation_total", lambda x: int((pd.to_numeric(x, errors="coerce") > 0).sum())),
            total=("validation_total", "sum"),
            min=("validation_total", "min"),
            median=("validation_total", "median"),
            trades=("validation_trades", "sum"),
        )
        .reset_index()
        .sort_values("total", ascending=False)
    )


def _write_report(path: Path, *, summary: pd.DataFrame, prequential: pd.DataFrame, payload: dict[str, object]) -> None:
    best = summary.iloc[0].to_dict() if not summary.empty else {}
    best_pre = prequential.sort_values("total", ascending=False).iloc[0].to_dict() if not prequential.empty else {}
    lines = [
        "# Research V48 Results: BTCUSDC Full 1m Direct ML Probe",
        "",
        "V48 tests whether the full available BTCUSDC public 1m bar history contains a direct, cost-aware linear signal after the transferred V26 rule failed on true BTCUSDC replay.",
        "",
        "## Data",
        "",
        "```text",
        f"bars: {payload['bar_rows']}",
        f"range: {payload['bar_start']} through {payload['bar_end']}",
        "cost: 8.5 bps per round trip",
        "model: Ridge(alpha=10) with standardized bar features",
        "validation: 365d train / 90d selector / 60d validation, stepped by 60d",
        "```",
        "",
        "## Best Raw Horizon",
        "",
        "```json",
        json.dumps(best, indent=2),
        "```",
        "",
        "## Prequential Gate Result",
        "",
        "```json",
        json.dumps(best_pre, indent=2),
        "```",
        "",
        "## Conclusion",
        "",
        "The direct Ridge probe finds weak long-horizon signal, but it is not stable enough for the target. The best raw horizon is still net negative, and the only positive prequential gate variant activates too few folds to prove stable performance.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bars = _load_or_build_bars()
    features, feature_cols = build_direct_ml_features(bars)
    folds = _ridge_probe(features, feature_cols)
    folds.to_csv(OUT_DIR / "ridge_probe_folds.csv", index=False)
    horizon_summary = _summarize_folds(folds)
    horizon_summary.to_csv(OUT_DIR / "ridge_probe_summary.csv", index=False)

    candidates = _gate_candidates(folds)
    candidates.to_csv(OUT_DIR / "ridge_prequential_gate_candidates.csv", index=False)
    pre_rows: list[dict[str, object]] = []
    for warmup in [1, 2, 3, 4]:
        selected, summary = run_prequential_gate_selection(candidates, warmup_folds=warmup)
        selected.to_csv(OUT_DIR / f"ridge_prequential_gate_warmup{warmup}.csv", index=False)
        pre_rows.append(summary)
    prequential = pd.DataFrame(pre_rows)
    prequential.to_csv(OUT_DIR / "ridge_prequential_gate_summary.csv", index=False)

    payload = {
        "version": "v48_btcusdc_full_1m_direct_ml_probe",
        "bar_rows": int(len(bars)),
        "bar_start": str(pd.to_datetime(bars["timestamp"], utc=True).min()),
        "bar_end": str(pd.to_datetime(bars["timestamp"], utc=True).max()),
        "feature_count": int(len(feature_cols)),
        "horizon_summary": horizon_summary.to_dict(orient="records"),
        "prequential_gate_summary": prequential.to_dict(orient="records"),
        "gate_passed": False,
        "conclusion": "weak long-horizon signal only; not stable enough for promoted target",
    }
    (OUT_DIR / "summary_v48.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(OUT_DIR / "REPORT_V48.md", summary=horizon_summary, prequential=prequential, payload=payload)
    print(json.dumps(payload, indent=2))
