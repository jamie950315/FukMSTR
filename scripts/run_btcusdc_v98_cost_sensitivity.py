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
import run_btcusdc_v96_ml_probability_gate as v96
import run_btcusdc_v97_hgb_regime_gate as v97


OUT_DIR = ROOT / "runs" / "research_v98_btcusdc_cost_sensitivity"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V98_BTCUSDC_COST_SENSITIVITY_RESULTS.md"

FEE_SCENARIOS_BPS = (8.5, 4.0, 0.0)
MIN_WIN_RATE = 0.55
MIN_AVG_TRADES_PER_CALENDAR_DAY = 1.0
MIN_CALENDAR_POSITIVE_MONTH_RATE = 0.50


def _ledger_with_fee(ledger: pd.DataFrame, *, fee_bps: float) -> pd.DataFrame:
    out = ledger.copy()
    gross = pd.to_numeric(out["gross_pnl_bps"], errors="coerce").fillna(0.0)
    out["net_pnl_bps"] = gross - float(fee_bps)
    out["fee_bps"] = float(fee_bps)
    out["equity_bps"] = out["net_pnl_bps"].cumsum()
    return out


def _passes_cost_gate(row: dict[str, object]) -> bool:
    return (
        float(row["selector_total_net_pnl_bps"]) > 0.0
        and float(row["holdout_total_net_pnl_bps"]) > 0.0
        and float(row["selector_win_rate"]) > MIN_WIN_RATE
        and float(row["holdout_win_rate"]) > MIN_WIN_RATE
        and float(row["selector_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["holdout_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["selector_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
        and float(row["holdout_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
    )


def _evaluate_horizon(bars: pd.DataFrame, *, horizon: int) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame], dict[str, object]]:
    data, feature_cols = v96._feature_frame(bars, horizon_minutes=int(horizon))
    full_end = pd.to_datetime(data["timestamp"].max(), utc=True)
    holdout_start = full_end - pd.Timedelta(days=v96.HOLDOUT_DAYS)
    selector_start = holdout_start - pd.Timedelta(days=v96.SELECTOR_DAYS)
    train = data.loc[data["timestamp"] < selector_start].copy()
    selector = data.loc[(data["timestamp"] >= selector_start) & (data["timestamp"] < holdout_start)].copy()
    holdout = data.loc[data["timestamp"] >= holdout_start].copy()
    if len(train) < 1000 or len(selector) < 100 or len(holdout) < 100:
        return [], {}, {"horizon_minutes": int(horizon), "skipped": True, "reason": "insufficient rows"}

    model = v97._fit_hgb(train, feature_cols)
    selector_pred = v97._prediction_frame(model, selector, feature_cols)
    holdout_pred = v97._prediction_frame(model, holdout, feature_cols)
    selector_start_ts = pd.to_datetime(selector["timestamp"].min(), utc=True)
    selector_end_ts = pd.to_datetime(selector["timestamp"].max(), utc=True)
    holdout_start_ts = pd.to_datetime(holdout["timestamp"].min(), utc=True)
    holdout_end_ts = pd.to_datetime(holdout["timestamp"].max(), utc=True)

    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}
    for probability_threshold in v97.PROBABILITY_THRESHOLDS:
        for range_quantile in v97.REGIME_QUANTILES:
            for flow_quantile in v97.REGIME_QUANTILES:
                selector_mask = v97._regime_mask(
                    selector_pred,
                    selector_pred,
                    range_quantile=float(range_quantile),
                    flow_quantile=float(flow_quantile),
                )
                holdout_mask = v97._regime_mask(
                    holdout_pred,
                    selector_pred,
                    range_quantile=float(range_quantile),
                    flow_quantile=float(flow_quantile),
                )
                selector_gross = v96._prediction_ledger(
                    selector_pred.loc[selector_mask].copy(),
                    probability_threshold=float(probability_threshold),
                    horizon_minutes=int(horizon),
                    fee_bps=0.0,
                )
                holdout_gross = v96._prediction_ledger(
                    holdout_pred.loc[holdout_mask].copy(),
                    probability_threshold=float(probability_threshold),
                    horizon_minutes=int(horizon),
                    fee_bps=0.0,
                )
                base_policy = f"hgb_h{int(horizon)}_p{float(probability_threshold):.2f}_rq{float(range_quantile):.2f}_fq{float(flow_quantile):.2f}"
                for fee_bps in FEE_SCENARIOS_BPS:
                    selector_ledger = _ledger_with_fee(selector_gross, fee_bps=float(fee_bps))
                    holdout_ledger = _ledger_with_fee(holdout_gross, fee_bps=float(fee_bps))
                    selector_summary = v94._trade_summary(selector_ledger, start_ts=selector_start_ts, end_ts=selector_end_ts)
                    holdout_summary = v94._trade_summary(holdout_ledger, start_ts=holdout_start_ts, end_ts=holdout_end_ts)
                    row = {
                        "policy_id": f"{base_policy}_fee{float(fee_bps):g}",
                        "base_policy_id": base_policy,
                        "horizon_minutes": int(horizon),
                        "probability_threshold": float(probability_threshold),
                        "range_quantile": float(range_quantile),
                        "flow_quantile": float(flow_quantile),
                        "fee_bps": float(fee_bps),
                        "train_rows": int(len(train)),
                        "selector_rows": int(len(selector)),
                        "holdout_rows": int(len(holdout)),
                        **{f"selector_{key}": value for key, value in selector_summary.items()},
                        **{f"holdout_{key}": value for key, value in holdout_summary.items()},
                    }
                    row["passed_cost_gate"] = bool(_passes_cost_gate(row))
                    rows.append(row)
                    if bool(row["passed_cost_gate"]):
                        ledgers[str(row["policy_id"])] = pd.concat(
                            [selector_ledger.assign(window="selector"), holdout_ledger.assign(window="holdout")],
                            ignore_index=True,
                        )
    meta = {
        "horizon_minutes": int(horizon),
        "train_rows": int(len(train)),
        "selector_rows": int(len(selector)),
        "holdout_rows": int(len(holdout)),
        "feature_count": int(len(feature_cols)),
        "selector_start_timestamp": selector_start_ts.isoformat(),
        "holdout_start_timestamp": holdout_start_ts.isoformat(),
        "holdout_end_timestamp": holdout_end_ts.isoformat(),
    }
    return rows, ledgers, meta


def _scan(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    ledgers: dict[str, pd.DataFrame] = {}
    metas: list[dict[str, object]] = []
    for horizon in v97.HORIZONS:
        horizon_rows, horizon_ledgers, meta = _evaluate_horizon(bars, horizon=int(horizon))
        rows.extend(horizon_rows)
        ledgers.update(horizon_ledgers)
        metas.append(meta)
        print(f"evaluated cost sensitivity horizon {horizon} with {len(horizon_rows)} rows", flush=True)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_cost_gate",
                "fee_bps",
                "holdout_total_net_pnl_bps",
                "holdout_win_rate",
                "selector_total_net_pnl_bps",
            ],
            ascending=[False, True, False, False, False],
        ).reset_index(drop=True)
    return candidates, ledgers, metas


def _fee_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if candidates.empty:
        return pd.DataFrame(columns=["fee_bps", "candidate_count", "passing_candidate_count", "best_holdout_total_net_pnl_bps", "best_holdout_win_rate"])
    for fee_bps, group in candidates.groupby("fee_bps", sort=True):
        best = group.sort_values("holdout_total_net_pnl_bps", ascending=False).iloc[0]
        rows.append(
            {
                "fee_bps": float(fee_bps),
                "candidate_count": int(len(group)),
                "passing_candidate_count": int(group["passed_cost_gate"].astype(bool).sum()),
                "best_policy_id": str(best["policy_id"]),
                "best_selector_total_net_pnl_bps": float(best["selector_total_net_pnl_bps"]),
                "best_selector_win_rate": float(best["selector_win_rate"]),
                "best_selector_avg_trades_per_calendar_day": float(best["selector_avg_trades_per_calendar_day"]),
                "best_holdout_total_net_pnl_bps": float(best["holdout_total_net_pnl_bps"]),
                "best_holdout_win_rate": float(best["holdout_win_rate"]),
                "best_holdout_avg_trades_per_calendar_day": float(best["holdout_avg_trades_per_calendar_day"]),
            }
        )
    return pd.DataFrame(rows)


def _decision_from_passed(passed: pd.DataFrame) -> dict[str, object]:
    if passed.empty:
        return {
            "passing_candidate_count": 0,
            "passing_nonzero_fee_candidate_count": 0,
            "zero_fee_only_candidate_count": 0,
            "selected_policy": None,
            "zero_fee_research_policy": None,
            "goal_satisfied_by_scan": False,
            "failed_reason": "no candidate passed the high-frequency profitability, win-rate, frequency, and month-stability gate under tested fee scenarios",
        }
    frame = passed.copy()
    frame["fee_bps"] = pd.to_numeric(frame["fee_bps"], errors="coerce").fillna(0.0)
    nonzero = frame.loc[frame["fee_bps"] > 0.0].copy()
    zero_fee = frame.loc[frame["fee_bps"] <= 0.0].copy()
    if not nonzero.empty:
        return {
            "passing_candidate_count": int(len(frame)),
            "passing_nonzero_fee_candidate_count": int(len(nonzero)),
            "zero_fee_only_candidate_count": int(len(zero_fee)),
            "selected_policy": str(nonzero.iloc[0]["policy_id"]),
            "zero_fee_research_policy": str(zero_fee.iloc[0]["policy_id"]) if not zero_fee.empty else None,
            "goal_satisfied_by_scan": True,
            "failed_reason": None,
        }
    return {
        "passing_candidate_count": int(len(frame)),
        "passing_nonzero_fee_candidate_count": 0,
        "zero_fee_only_candidate_count": int(len(zero_fee)),
        "selected_policy": None,
        "zero_fee_research_policy": str(zero_fee.iloc[0]["policy_id"]) if not zero_fee.empty else None,
        "goal_satisfied_by_scan": False,
        "failed_reason": "passing candidates require 0 bps cost; no nonzero-fee scenario passed",
    }


def _write_report(payload: dict[str, object], candidates: pd.DataFrame, passed: pd.DataFrame, fee_summary: pd.DataFrame) -> None:
    report_cols = [
        "policy_id",
        "passed_cost_gate",
        "fee_bps",
        "selector_trade_count",
        "selector_avg_trades_per_calendar_day",
        "selector_total_net_pnl_bps",
        "selector_win_rate",
        "holdout_trade_count",
        "holdout_avg_trades_per_calendar_day",
        "holdout_total_net_pnl_bps",
        "holdout_win_rate",
    ]
    top = candidates.head(10).copy() if not candidates.empty else pd.DataFrame()
    lines = [
        "# Research V98 BTCUSDC Cost Sensitivity Results",
        "",
        "## Decision",
        "",
        f"- Evaluated rows: `{payload['scan']['candidate_count']}`",
        f"- Passing cost-sensitive candidates: `{payload['decision']['passing_candidate_count']}`",
        f"- Passing nonzero-fee candidates: `{payload['decision']['passing_nonzero_fee_candidate_count']}`",
        f"- Selected nonzero-fee candidate: `{payload['decision']['selected_policy']}`",
        f"- Zero-fee research candidate: `{payload['decision']['zero_fee_research_policy']}`",
        f"- Fee scenarios: `{list(FEE_SCENARIOS_BPS)}` bps",
        "",
        "## Fee Summary",
        "",
        fee_summary.to_csv(index=False).strip() if not fee_summary.empty else "No rows were produced.",
        "",
        "## Top Candidates",
        "",
        top[report_cols].to_csv(index=False).strip() if not top.empty else "No candidates were produced.",
        "",
        "## Passing Candidates",
        "",
        passed[report_cols].to_csv(index=False).strip() if not passed.empty else "No candidate passed the cost-sensitivity gate.",
        "",
        "## Interpretation",
        "",
        "V98 replays the V97 HGB regime candidate grid under alternative fee assumptions without changing probability or regime thresholds. This tests whether high-frequency failure is mainly a cost issue. It is a research scan, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_cost_gate"]].copy() if not candidates.empty else pd.DataFrame()
    fee_summary = _fee_summary(candidates)

    candidates_path = OUT_DIR / "v98_cost_sensitivity_candidates.csv"
    passed_path = OUT_DIR / "v98_cost_sensitivity_passed_candidates.csv"
    fee_summary_path = OUT_DIR / "v98_cost_sensitivity_fee_summary.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    fee_summary.to_csv(fee_summary_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v98_{policy_id}_trade_ledger.csv", index=False)

    decision = _decision_from_passed(passed)
    payload = {
        "version": "v98_btcusdc_cost_sensitivity",
        "scan": {
            "candidate_count": int(len(candidates)),
            "fee_scenarios_bps": list(FEE_SCENARIOS_BPS),
            "base": "v97_hgb_regime_gate",
            "horizon_meta": metas,
        },
        "decision": decision,
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "fee_summary": str(fee_summary_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v98_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed, fee_summary)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
