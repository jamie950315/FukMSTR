from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94
import run_btcusdc_v104_ma_hgb_daily_topk_classifier as v104
import run_btcusdc_v109_feature_family_ensemble_exact_daily as v109
import run_btcusdc_v111_high_confidence_daily_fallback as v111
import run_btcusdc_v112_expanded_topk_daily_fallback as v112


OUT_DIR = ROOT / "runs" / "research_v113_btcusdc_v112_earliest_walk_forward"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V113_BTCUSDC_V112_EARLIEST_WALK_FORWARD_RESULTS.md"

REQUESTED_THROUGH_DATE = "2026-06-13"
POLICY_ID = "hgb_v112_expanded_topk_fallback_top9_h30_p0.420000_fb1"
HORIZON_MINUTES = 30
DAILY_TOP_K = 9
PRIMARY_PROBABILITY_FLOOR = 0.42
FALLBACK_MIN_DAILY_TRADES = 1
FEE_BPS = v112.FEE_BPS
TRAIN_DAYS = 180
TEST_DAYS = 60
MIN_TRAIN_ROWS = 10_000


def _ceil_day(ts: pd.Timestamp) -> pd.Timestamp:
    normalized = ts.normalize()
    return normalized if ts == normalized else normalized + pd.Timedelta(days=1)


def _fold_windows(
    *,
    data_start: pd.Timestamp,
    data_end: pd.Timestamp,
    train_days: int,
    test_days: int,
) -> list[dict[str, pd.Timestamp]]:
    first_test_start = _ceil_day(pd.to_datetime(data_start, utc=True) + pd.Timedelta(days=int(train_days)))
    data_end = pd.to_datetime(data_end, utc=True)
    windows: list[dict[str, pd.Timestamp]] = []
    test_start = first_test_start
    while test_start <= data_end:
        test_end_exclusive = min(test_start + pd.Timedelta(days=int(test_days)), data_end + pd.Timedelta(minutes=1))
        if test_end_exclusive <= test_start:
            break
        train_end_exclusive = test_start - pd.Timedelta(minutes=int(HORIZON_MINUTES))
        windows.append(
            {
                "train_start": pd.to_datetime(data_start, utc=True),
                "train_end_exclusive": train_end_exclusive,
                "test_start": test_start,
                "test_end_exclusive": test_end_exclusive,
            }
        )
        test_start = test_end_exclusive
    return windows


def _family_feature_frames(bars: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, list[str]]]:
    frames: dict[str, tuple[pd.DataFrame, list[str]]] = {}
    for family in v112.FEATURE_FAMILIES:
        data, feature_cols = v109._feature_frame_for_family(family, bars, horizon_minutes=HORIZON_MINUTES)
        data = data.copy()
        data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
        frames[str(family)] = (data, feature_cols)
    return frames


def _fold_predictions(
    family_frames: dict[str, tuple[pd.DataFrame, list[str]]],
    window: dict[str, pd.Timestamp],
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    prediction_frames: list[pd.DataFrame] = []
    metas: list[dict[str, object]] = []
    for family, (data, feature_cols) in family_frames.items():
        train = data.loc[
            (data["timestamp"] >= window["train_start"]) & (data["timestamp"] < window["train_end_exclusive"])
        ].copy()
        test = data.loc[
            (data["timestamp"] >= window["test_start"]) & (data["timestamp"] < window["test_end_exclusive"])
        ].copy()
        if len(train) < MIN_TRAIN_ROWS or len(test) == 0:
            metas.append(
                {
                    "family": family,
                    "skipped": True,
                    "train_rows": int(len(train)),
                    "test_rows": int(len(test)),
                }
            )
            continue
        model = v104._fit_hgb_classifier(train, feature_cols)
        prediction_frames.append(v104._probability_predictions(model, test, feature_cols))
        metas.append(
            {
                "family": family,
                "skipped": False,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "feature_count": int(len(feature_cols)),
            }
        )
    if not prediction_frames:
        return pd.DataFrame(columns=["timestamp", "future_return_bps", "prob_down", "prob_flat", "prob_up"]), metas
    return v109._average_probability_frames(prediction_frames), metas


def _monthly_table(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return pd.DataFrame(columns=["month", "trade_count", "total_net_pnl_bps", "win_rate"])
    frame = ledger.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    frame["month"] = frame["timestamp"].dt.tz_convert(None).dt.to_period("M").astype(str)
    grouped = frame.groupby("month", sort=True)["net_pnl_bps"]
    return pd.DataFrame(
        {
            "month": grouped.size().index,
            "trade_count": grouped.size().to_numpy(int),
            "total_net_pnl_bps": grouped.sum().to_numpy(float),
            "win_rate": frame.groupby("month", sort=True)["net_pnl_bps"].apply(lambda pnl: float((pnl > 0.0).mean())).to_numpy(float),
        }
    )


def _write_report(payload: dict[str, object], fold_table: pd.DataFrame, month_table: pd.DataFrame) -> None:
    lines = [
        "# Research V113 BTCUSDC V112 Earliest Walk-Forward Results",
        "",
        "## Decision",
        "",
        f"- Requested through date: `{payload['data']['requested_through_date']}`",
        f"- Latest available data end: `{payload['data']['available_end']}`",
        f"- Full data start: `{payload['data']['available_start']}`",
        f"- First fair test timestamp: `{payload['period']['test_start']}`",
        f"- Test end timestamp: `{payload['period']['test_end']}`",
        f"- Policy: `{payload['policy']['policy_id']}`",
        f"- Fold count: `{payload['walk_forward']['fold_count']}`",
        f"- Trade count: `{payload['summary']['trade_count']}`",
        f"- Total net PnL: `{payload['summary']['total_net_pnl_bps']:.6f}` bps",
        f"- Mean net PnL: `{payload['summary']['mean_net_pnl_bps']:.6f}` bps",
        f"- Win rate: `{payload['summary']['win_rate']:.6f}`",
        f"- Max drawdown: `{payload['summary']['max_drawdown_bps']:.6f}` bps",
        f"- Calendar positive month rate: `{payload['summary']['calendar_positive_month_rate']:.6f}`",
        f"- Active positive month rate: `{payload['summary']['active_positive_month_rate']:.6f}`",
        "",
        "## Fold Table",
        "",
        fold_table.to_csv(index=False).strip() if not fold_table.empty else "No folds were produced.",
        "",
        "## Month Table",
        "",
        month_table.to_csv(index=False).strip() if not month_table.empty else "No trades were produced.",
        "",
        "## Interpretation",
        "",
        "V113 applies the locked V112 policy in a walk-forward test. Each fold trains only on data before that fold and tests the next 60 days. The first 180 calendar days are used only to create enough model history, so the earliest fair test begins after that warm-up period. This remains a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    data_start = pd.to_datetime(bars["timestamp"].min(), utc=True)
    data_end = pd.to_datetime(bars["timestamp"].max(), utc=True)
    family_frames = _family_feature_frames(bars)
    windows = _fold_windows(data_start=data_start, data_end=data_end, train_days=TRAIN_DAYS, test_days=TEST_DAYS)

    ledgers: list[pd.DataFrame] = []
    fold_rows: list[dict[str, object]] = []
    fold_metas: list[dict[str, object]] = []
    for fold_idx, window in enumerate(windows, start=1):
        predictions, metas = _fold_predictions(family_frames, window)
        ledger = v111._daily_topk_probability_ledger_with_fallback(
            predictions,
            daily_top_k=DAILY_TOP_K,
            primary_probability_floor=PRIMARY_PROBABILITY_FLOOR,
            fallback_min_daily_trades=FALLBACK_MIN_DAILY_TRADES,
            horizon_minutes=HORIZON_MINUTES,
            fee_bps=FEE_BPS,
        )
        if not ledger.empty:
            ledger["fold"] = int(fold_idx)
            ledgers.append(ledger)
        fold_summary = v94._trade_summary(
            ledger,
            start_ts=window["test_start"],
            end_ts=window["test_end_exclusive"] - pd.Timedelta(minutes=1),
        )
        fold_rows.append(
            {
                "fold": int(fold_idx),
                "train_start": window["train_start"].isoformat(),
                "train_end_exclusive": window["train_end_exclusive"].isoformat(),
                "test_start": window["test_start"].isoformat(),
                "test_end_exclusive": window["test_end_exclusive"].isoformat(),
                **fold_summary,
            }
        )
        fold_metas.append({"fold": int(fold_idx), **{key: value.isoformat() for key, value in window.items()}, "families": metas})
        print(
            f"evaluated V113 fold {fold_idx}/{len(windows)} "
            f"{window['test_start'].date()} to {(window['test_end_exclusive'] - pd.Timedelta(minutes=1)).date()} "
            f"with {fold_summary['trade_count']} trades",
            flush=True,
        )

    combined = pd.concat(ledgers, ignore_index=True) if ledgers else v111._empty_fallback_ledger()
    combined = combined.sort_values("timestamp").reset_index(drop=True) if not combined.empty else combined
    if not combined.empty:
        combined["equity_bps"] = pd.to_numeric(combined["net_pnl_bps"], errors="coerce").fillna(0.0).cumsum()
    test_start = windows[0]["test_start"] if windows else data_start
    test_end = windows[-1]["test_end_exclusive"] - pd.Timedelta(minutes=1) if windows else data_end
    summary = v94._trade_summary(combined, start_ts=test_start, end_ts=test_end)
    fold_table = pd.DataFrame(fold_rows)
    month_table = _monthly_table(combined)

    ledger_path = OUT_DIR / "v113_v112_earliest_walk_forward_trade_ledger.csv"
    fold_path = OUT_DIR / "v113_v112_earliest_walk_forward_folds.csv"
    month_path = OUT_DIR / "v113_v112_earliest_walk_forward_months.csv"
    combined.to_csv(ledger_path, index=False)
    fold_table.to_csv(fold_path, index=False)
    month_table.to_csv(month_path, index=False)

    payload = {
        "version": "v113_btcusdc_v112_earliest_walk_forward",
        "policy": {
            "policy_id": POLICY_ID,
            "horizon_minutes": HORIZON_MINUTES,
            "daily_top_k": DAILY_TOP_K,
            "primary_probability_floor": PRIMARY_PROBABILITY_FLOOR,
            "fallback_min_daily_trades": FALLBACK_MIN_DAILY_TRADES,
            "fee_bps": FEE_BPS,
            "feature_families": list(v112.FEATURE_FAMILIES),
        },
        "data": {
            "requested_through_date": REQUESTED_THROUGH_DATE,
            "requested_date_included": bool(data_end.date().isoformat() >= REQUESTED_THROUGH_DATE),
            "available_start": data_start.isoformat(),
            "available_end": data_end.isoformat(),
            "bar_count": int(len(bars)),
        },
        "walk_forward": {
            "train_days": TRAIN_DAYS,
            "test_days": TEST_DAYS,
            "min_train_rows": MIN_TRAIN_ROWS,
            "fold_count": int(len(windows)),
            "fold_meta": fold_metas,
        },
        "period": {
            "test_start": test_start.isoformat(),
            "test_end": test_end.isoformat(),
        },
        "summary": summary,
        "outputs": {
            "summary_json": str(OUT_DIR / "v113_summary.json"),
            "trade_ledger": str(ledger_path),
            "folds": str(fold_path),
            "months": str(month_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v113_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, fold_table, month_table)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
