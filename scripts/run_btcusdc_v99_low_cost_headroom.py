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
import run_btcusdc_v98_cost_sensitivity as v98


OUT_DIR = ROOT / "runs" / "research_v99_btcusdc_low_cost_headroom"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V99_BTCUSDC_LOW_COST_HEADROOM_RESULTS.md"

FEE_SCENARIOS_BPS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)


def _optional_float(row: pd.Series, column: str) -> float | None:
    if column not in row.index:
        return None
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None
    return float(value)


def _passes_low_cost_gate(row: dict[str, object]) -> bool:
    return bool(v98._passes_cost_gate(row))


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
                    selector_ledger = v98._ledger_with_fee(selector_gross, fee_bps=float(fee_bps))
                    holdout_ledger = v98._ledger_with_fee(holdout_gross, fee_bps=float(fee_bps))
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
                    row["passed_low_cost_gate"] = bool(_passes_low_cost_gate(row))
                    rows.append(row)
                    if bool(row["passed_low_cost_gate"]):
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
        print(f"evaluated low-cost headroom horizon {horizon} with {len(horizon_rows)} rows", flush=True)
    candidates = pd.DataFrame(rows)
    if not candidates.empty:
        candidates = candidates.sort_values(
            [
                "passed_low_cost_gate",
                "fee_bps",
                "holdout_total_net_pnl_bps",
                "holdout_win_rate",
                "selector_total_net_pnl_bps",
            ],
            ascending=[False, False, False, False, False],
        ).reset_index(drop=True)
    return candidates, ledgers, metas


def _policy_headroom(candidates: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "base_policy_id",
        "passing_fee_count",
        "max_passing_fee_bps",
        "max_passing_nonzero_fee_bps",
        "zero_fee_only",
        "selected_policy_id_at_max_fee",
        "max_fee_selector_total_net_pnl_bps",
        "max_fee_selector_win_rate",
        "max_fee_selector_avg_trades_per_calendar_day",
        "max_fee_holdout_total_net_pnl_bps",
        "max_fee_holdout_win_rate",
        "max_fee_holdout_avg_trades_per_calendar_day",
    ]
    if candidates.empty:
        return pd.DataFrame(columns=columns)

    frame = candidates.copy()
    frame["fee_bps"] = pd.to_numeric(frame["fee_bps"], errors="coerce").fillna(0.0)
    frame["passed_low_cost_gate"] = frame["passed_low_cost_gate"].astype(bool)
    rows: list[dict[str, object]] = []
    for base_policy_id, group in frame.groupby("base_policy_id", sort=False):
        passed = group.loc[group["passed_low_cost_gate"]].copy()
        if passed.empty:
            rows.append(
                {
                    "base_policy_id": str(base_policy_id),
                    "passing_fee_count": 0,
                    "max_passing_fee_bps": None,
                    "max_passing_nonzero_fee_bps": None,
                    "zero_fee_only": False,
                    "selected_policy_id_at_max_fee": None,
                    "max_fee_selector_total_net_pnl_bps": None,
                    "max_fee_selector_win_rate": None,
                    "max_fee_selector_avg_trades_per_calendar_day": None,
                    "max_fee_holdout_total_net_pnl_bps": None,
                    "max_fee_holdout_win_rate": None,
                    "max_fee_holdout_avg_trades_per_calendar_day": None,
                }
            )
            continue
        passed = passed.sort_values(["fee_bps", "holdout_total_net_pnl_bps"], ascending=[False, False])
        best = passed.iloc[0]
        nonzero = passed.loc[passed["fee_bps"] > 0.0]
        max_nonzero = None if nonzero.empty else float(nonzero["fee_bps"].max())
        rows.append(
            {
                "base_policy_id": str(base_policy_id),
                "passing_fee_count": int(len(passed)),
                "max_passing_fee_bps": float(best["fee_bps"]),
                "max_passing_nonzero_fee_bps": max_nonzero,
                "zero_fee_only": bool(float(best["fee_bps"]) <= 0.0),
                "selected_policy_id_at_max_fee": str(best["policy_id"]),
                "max_fee_selector_total_net_pnl_bps": _optional_float(best, "selector_total_net_pnl_bps"),
                "max_fee_selector_win_rate": _optional_float(best, "selector_win_rate"),
                "max_fee_selector_avg_trades_per_calendar_day": _optional_float(best, "selector_avg_trades_per_calendar_day"),
                "max_fee_holdout_total_net_pnl_bps": _optional_float(best, "holdout_total_net_pnl_bps"),
                "max_fee_holdout_win_rate": _optional_float(best, "holdout_win_rate"),
                "max_fee_holdout_avg_trades_per_calendar_day": _optional_float(best, "holdout_avg_trades_per_calendar_day"),
            }
        )

    out = pd.DataFrame(rows, columns=columns)
    out["zero_fee_only"] = out["zero_fee_only"].astype(object)
    out = out.sort_values(
        ["max_passing_nonzero_fee_bps", "max_passing_fee_bps", "max_fee_holdout_total_net_pnl_bps"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    return out


def _decision_from_headroom(headroom: pd.DataFrame) -> dict[str, object]:
    if headroom.empty:
        return {
            "passing_base_policy_count": 0,
            "passing_nonzero_fee_policy_count": 0,
            "zero_fee_only_policy_count": 0,
            "selected_policy": None,
            "zero_fee_research_policy": None,
            "max_passing_nonzero_fee_bps": None,
            "goal_satisfied_by_scan": False,
            "failed_reason": "no base policy passed the high-frequency gate at any tested low-cost scenario",
        }
    frame = headroom.copy()
    if "passing_fee_count" not in frame.columns:
        frame["passing_fee_count"] = 1
    frame["passing_fee_count"] = pd.to_numeric(frame["passing_fee_count"], errors="coerce").fillna(1).astype(int)
    frame["max_passing_nonzero_fee_bps"] = pd.to_numeric(frame["max_passing_nonzero_fee_bps"], errors="coerce")
    passing = frame.loc[frame["passing_fee_count"] > 0].copy()
    nonzero = passing.loc[passing["max_passing_nonzero_fee_bps"] > 0.0].copy()
    zero_fee = passing.loc[passing["max_passing_nonzero_fee_bps"].isna()].copy()
    if not nonzero.empty:
        if "max_fee_holdout_total_net_pnl_bps" not in nonzero.columns:
            nonzero["max_fee_holdout_total_net_pnl_bps"] = 0.0
        nonzero = nonzero.sort_values(
            ["max_passing_nonzero_fee_bps", "max_fee_holdout_total_net_pnl_bps"],
            ascending=[False, False],
            na_position="last",
        )
        selected = nonzero.iloc[0]
        return {
            "passing_base_policy_count": int(len(passing)),
            "passing_nonzero_fee_policy_count": int(len(nonzero)),
            "zero_fee_only_policy_count": int(len(zero_fee)),
            "selected_policy": str(selected["base_policy_id"]),
            "zero_fee_research_policy": str(zero_fee.iloc[0]["base_policy_id"]) if not zero_fee.empty else None,
            "max_passing_nonzero_fee_bps": float(selected["max_passing_nonzero_fee_bps"]),
            "goal_satisfied_by_scan": True,
            "failed_reason": None,
        }
    return {
        "passing_base_policy_count": int(len(passing)),
        "passing_nonzero_fee_policy_count": 0,
        "zero_fee_only_policy_count": int(len(zero_fee)),
        "selected_policy": None,
        "zero_fee_research_policy": str(zero_fee.iloc[0]["base_policy_id"]) if not zero_fee.empty else None,
        "max_passing_nonzero_fee_bps": None,
        "goal_satisfied_by_scan": False,
        "failed_reason": "passing base policies require 0 bps cost; no nonzero low-cost scenario passed",
    }


def _write_report(payload: dict[str, object], candidates: pd.DataFrame, passed: pd.DataFrame, headroom: pd.DataFrame) -> None:
    candidate_cols = [
        "policy_id",
        "base_policy_id",
        "passed_low_cost_gate",
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
    headroom_cols = [
        "base_policy_id",
        "passing_fee_count",
        "max_passing_fee_bps",
        "max_passing_nonzero_fee_bps",
        "zero_fee_only",
        "selected_policy_id_at_max_fee",
        "max_fee_selector_total_net_pnl_bps",
        "max_fee_selector_win_rate",
        "max_fee_holdout_total_net_pnl_bps",
        "max_fee_holdout_win_rate",
    ]
    top = candidates.head(12).copy() if not candidates.empty else pd.DataFrame()
    lines = [
        "# Research V99 BTCUSDC Low-Cost Headroom Results",
        "",
        "## Decision",
        "",
        f"- Evaluated rows: `{payload['scan']['candidate_count']}`",
        f"- Passing low-cost rows: `{payload['scan']['passing_row_count']}`",
        f"- Passing base policies: `{payload['decision']['passing_base_policy_count']}`",
        f"- Passing nonzero-fee base policies: `{payload['decision']['passing_nonzero_fee_policy_count']}`",
        f"- Selected nonzero-fee base policy: `{payload['decision']['selected_policy']}`",
        f"- Maximum passing nonzero fee: `{payload['decision']['max_passing_nonzero_fee_bps']}` bps",
        f"- Zero-fee research policy: `{payload['decision']['zero_fee_research_policy']}`",
        f"- Fee scenarios: `{list(FEE_SCENARIOS_BPS)}` bps",
        "",
        "## Policy Headroom",
        "",
        headroom[headroom_cols].head(20).to_csv(index=False).strip() if not headroom.empty else "No headroom rows were produced.",
        "",
        "## Top Candidate Rows",
        "",
        top[candidate_cols].to_csv(index=False).strip() if not top.empty else "No candidate rows were produced.",
        "",
        "## Passing Candidate Rows",
        "",
        passed[candidate_cols].head(30).to_csv(index=False).strip() if not passed.empty else "No candidate row passed the low-cost gate.",
        "",
        "## Interpretation",
        "",
        "V99 replays the V97 HGB regime candidate grid with fine-grained low-cost assumptions. It does not retune probability or regime thresholds. This measures execution-cost headroom for the high-frequency research route and is not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bars = v94._full_bars()
    candidates, ledgers, metas = _scan(bars)
    passed = candidates.loc[candidates["passed_low_cost_gate"]].copy() if not candidates.empty else pd.DataFrame()
    headroom = _policy_headroom(candidates)
    decision = _decision_from_headroom(headroom)

    candidates_path = OUT_DIR / "v99_low_cost_candidates.csv"
    passed_path = OUT_DIR / "v99_low_cost_passed_candidates.csv"
    headroom_path = OUT_DIR / "v99_policy_headroom.csv"
    candidates.to_csv(candidates_path, index=False)
    passed.to_csv(passed_path, index=False)
    headroom.to_csv(headroom_path, index=False)
    for policy_id, ledger in ledgers.items():
        ledger.to_csv(OUT_DIR / f"v99_{policy_id}_trade_ledger.csv", index=False)

    payload = {
        "version": "v99_btcusdc_low_cost_headroom",
        "scan": {
            "candidate_count": int(len(candidates)),
            "passing_row_count": int(len(passed)),
            "fee_scenarios_bps": list(FEE_SCENARIOS_BPS),
            "base": "v97_hgb_regime_gate",
            "horizon_meta": metas,
        },
        "decision": decision,
        "outputs": {
            "candidates": str(candidates_path),
            "passed_candidates": str(passed_path),
            "policy_headroom": str(headroom_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v99_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, passed, headroom)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
