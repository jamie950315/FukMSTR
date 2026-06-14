from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v94_high_frequency_scan as v94
import run_btcusdc_v98_cost_sensitivity as v98
import run_btcusdc_v99_low_cost_headroom as v99


V99_DIR = ROOT / "runs" / "research_v99_btcusdc_low_cost_headroom"
OUT_DIR = ROOT / "runs" / "research_v100_btcusdc_maker_fill_risk"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V100_BTCUSDC_MAKER_FILL_RISK_RESULTS.md"

FILL_MODELS = ("time_stride", "adverse_selection")
FILL_RATES = (1.0, 0.95, 0.9, 0.8, 0.7)
EXTRA_ADVERSE_BPS = (0.0, 0.125, 0.25, 0.5)

REQUIRED_FILL_MODELS = ("time_stride", "adverse_selection")
REQUIRED_MIN_FILL_RATE = 0.9
REQUIRED_MAX_EXTRA_ADVERSE_BPS = 0.25


def _stress_ledger(
    ledger: pd.DataFrame,
    *,
    fill_model: str,
    fill_rate: float,
    extra_adverse_bps: float,
) -> pd.DataFrame:
    if fill_model not in FILL_MODELS:
        raise ValueError(f"unknown fill model: {fill_model}")
    frame = ledger.copy()
    if frame.empty:
        out = frame.copy()
        out["fill_model"] = fill_model
        out["fill_rate"] = float(fill_rate)
        out["extra_adverse_bps"] = float(extra_adverse_bps)
        return out

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    keep_n = int(math.ceil(len(frame) * max(0.0, min(1.0, float(fill_rate)))))
    keep_n = max(0, min(len(frame), keep_n))
    if keep_n == 0:
        out = frame.iloc[0:0].copy()
    elif keep_n == len(frame):
        out = frame.copy()
    elif fill_model == "time_stride":
        positions = np.linspace(0, len(frame) - 1, keep_n, dtype=int)
        out = frame.iloc[np.unique(positions)].copy()
    else:
        out = frame.sort_values(["net_pnl_bps", "timestamp"], ascending=[True, True]).head(keep_n).sort_index().copy()

    out["net_pnl_bps"] = pd.to_numeric(out["net_pnl_bps"], errors="coerce").fillna(0.0) - float(extra_adverse_bps)
    out["equity_bps"] = out["net_pnl_bps"].cumsum()
    out["fill_model"] = str(fill_model)
    out["fill_rate"] = float(fill_rate)
    out["extra_adverse_bps"] = float(extra_adverse_bps)
    return out.sort_values("timestamp").reset_index(drop=True)


def _required_stress(fill_model: str, fill_rate: float, extra_adverse_bps: float) -> bool:
    return (
        str(fill_model) in REQUIRED_FILL_MODELS
        and float(fill_rate) >= REQUIRED_MIN_FILL_RATE
        and float(extra_adverse_bps) <= REQUIRED_MAX_EXTRA_ADVERSE_BPS
    )


def _passes_maker_stress_gate(row: dict[str, object]) -> bool:
    return bool(v98._passes_cost_gate(row))


def _window_bounds(summary: dict[str, object], horizon_minutes: int) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    metas = summary.get("scan", {}).get("horizon_meta", [])
    for meta in metas:
        if int(meta.get("horizon_minutes", -1)) == int(horizon_minutes):
            return {
                "selector": (
                    pd.to_datetime(meta["selector_start_timestamp"], utc=True),
                    pd.to_datetime(meta["holdout_start_timestamp"], utc=True),
                ),
                "holdout": (
                    pd.to_datetime(meta["holdout_start_timestamp"], utc=True),
                    pd.to_datetime(meta["holdout_end_timestamp"], utc=True),
                ),
            }
    raise ValueError(f"missing V99 horizon metadata for horizon {horizon_minutes}")


def _summarize_stressed_ledger(stressed: pd.DataFrame, *, summary: dict[str, object], horizon_minutes: int) -> dict[str, object]:
    bounds = _window_bounds(summary, int(horizon_minutes))
    selector = stressed.loc[stressed["window"] == "selector"].copy() if "window" in stressed.columns else stressed.iloc[0:0].copy()
    holdout = stressed.loc[stressed["window"] == "holdout"].copy() if "window" in stressed.columns else stressed.iloc[0:0].copy()
    selector_summary = v94._trade_summary(selector, start_ts=bounds["selector"][0], end_ts=bounds["selector"][1])
    holdout_summary = v94._trade_summary(holdout, start_ts=bounds["holdout"][0], end_ts=bounds["holdout"][1])
    return {
        **{f"selector_{key}": value for key, value in selector_summary.items()},
        **{f"holdout_{key}": value for key, value in holdout_summary.items()},
    }


def _decision_from_stress(stress: pd.DataFrame) -> dict[str, object]:
    if stress.empty:
        return {
            "candidate_count": 0,
            "required_stress_row_count": 0,
            "candidate_count_passing_required_stress": 0,
            "selected_policy": None,
            "maker_execution_viable": False,
            "failed_reason": "no maker stress rows were produced",
        }
    frame = stress.copy()
    frame["required_stress"] = frame["required_stress"].astype(bool)
    frame["passed_maker_stress_gate"] = frame["passed_maker_stress_gate"].astype(bool)
    required = frame.loc[frame["required_stress"]].copy()
    passing_rows: list[dict[str, object]] = []
    for base_policy_id, group in required.groupby("base_policy_id", sort=False):
        if bool(group["passed_maker_stress_gate"].all()):
            worst_holdout = pd.to_numeric(group.get("holdout_total_net_pnl_bps", pd.Series([0.0])), errors="coerce").fillna(0.0).min()
            passing_rows.append(
                {
                    "base_policy_id": str(base_policy_id),
                    "worst_required_holdout_total_net_pnl_bps": float(worst_holdout),
                }
            )
    passing = pd.DataFrame(passing_rows)
    if passing.empty:
        return {
            "candidate_count": int(frame["base_policy_id"].nunique()),
            "required_stress_row_count": int(len(required)),
            "candidate_count_passing_required_stress": 0,
            "selected_policy": None,
            "maker_execution_viable": False,
            "failed_reason": "no candidate passed every required maker fill stress",
        }
    passing = passing.sort_values("worst_required_holdout_total_net_pnl_bps", ascending=False).reset_index(drop=True)
    return {
        "candidate_count": int(frame["base_policy_id"].nunique()),
        "required_stress_row_count": int(len(required)),
        "candidate_count_passing_required_stress": int(len(passing)),
        "selected_policy": str(passing.iloc[0]["base_policy_id"]),
        "maker_execution_viable": True,
        "failed_reason": None,
    }


def _ensure_v99_outputs() -> dict[str, object]:
    summary_path = V99_DIR / "v99_summary.json"
    passed_path = V99_DIR / "v99_low_cost_passed_candidates.csv"
    if not summary_path.exists() or not passed_path.exists():
        return v99.run()
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _load_passed_candidates() -> pd.DataFrame:
    path = V99_DIR / "v99_low_cost_passed_candidates.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing V99 passed candidates: {path}")
    return pd.read_csv(path)


def _stress_candidates(passed: pd.DataFrame, summary: dict[str, object]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, candidate in passed.iterrows():
        policy_id = str(candidate["policy_id"])
        base_policy_id = str(candidate["base_policy_id"])
        horizon_minutes = int(candidate["horizon_minutes"])
        ledger_path = V99_DIR / f"v99_{policy_id}_trade_ledger.csv"
        if not ledger_path.exists():
            continue
        ledger = pd.read_csv(ledger_path)
        for fill_model in FILL_MODELS:
            for fill_rate in FILL_RATES:
                for extra_adverse_bps in EXTRA_ADVERSE_BPS:
                    stressed = _stress_ledger(
                        ledger,
                        fill_model=str(fill_model),
                        fill_rate=float(fill_rate),
                        extra_adverse_bps=float(extra_adverse_bps),
                    )
                    row = {
                        "policy_id": policy_id,
                        "base_policy_id": base_policy_id,
                        "horizon_minutes": horizon_minutes,
                        "base_fee_bps": float(candidate["fee_bps"]),
                        "fill_model": str(fill_model),
                        "fill_rate": float(fill_rate),
                        "extra_adverse_bps": float(extra_adverse_bps),
                        "required_stress": bool(_required_stress(str(fill_model), float(fill_rate), float(extra_adverse_bps))),
                        **_summarize_stressed_ledger(stressed, summary=summary, horizon_minutes=horizon_minutes),
                    }
                    row["passed_maker_stress_gate"] = bool(_passes_maker_stress_gate(row))
                    rows.append(row)
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(
            [
                "required_stress",
                "passed_maker_stress_gate",
                "base_policy_id",
                "fill_model",
                "fill_rate",
                "extra_adverse_bps",
            ],
            ascending=[False, True, True, True, False, True],
        ).reset_index(drop=True)
    return out


def _write_report(payload: dict[str, object], stress: pd.DataFrame) -> None:
    report_cols = [
        "policy_id",
        "base_policy_id",
        "base_fee_bps",
        "fill_model",
        "fill_rate",
        "extra_adverse_bps",
        "required_stress",
        "passed_maker_stress_gate",
        "selector_trade_count",
        "selector_avg_trades_per_calendar_day",
        "selector_total_net_pnl_bps",
        "selector_win_rate",
        "holdout_trade_count",
        "holdout_avg_trades_per_calendar_day",
        "holdout_total_net_pnl_bps",
        "holdout_win_rate",
    ]
    required = stress.loc[stress["required_stress"]].copy() if not stress.empty else pd.DataFrame()
    failed_required = required.loc[~required["passed_maker_stress_gate"].astype(bool)].copy() if not required.empty else pd.DataFrame()
    lines = [
        "# Research V100 BTCUSDC Maker Fill Risk Results",
        "",
        "## Decision",
        "",
        f"- Candidate count: `{payload['decision']['candidate_count']}`",
        f"- Required stress rows: `{payload['decision']['required_stress_row_count']}`",
        f"- Candidates passing all required stresses: `{payload['decision']['candidate_count_passing_required_stress']}`",
        f"- Selected maker-viable policy: `{payload['decision']['selected_policy']}`",
        f"- Maker execution viable: `{payload['decision']['maker_execution_viable']}`",
        f"- Failed reason: `{payload['decision']['failed_reason']}`",
        "",
        "## Required Stress Contract",
        "",
        f"- Fill models: `{list(REQUIRED_FILL_MODELS)}`",
        f"- Minimum fill rate: `{REQUIRED_MIN_FILL_RATE}`",
        f"- Maximum extra adverse cost: `{REQUIRED_MAX_EXTRA_ADVERSE_BPS}` bps",
        "",
        "## Failed Required Rows",
        "",
        failed_required[report_cols].head(40).to_csv(index=False).strip() if not failed_required.empty else "No required stress row failed.",
        "",
        "## All Required Rows",
        "",
        required[report_cols].head(80).to_csv(index=False).strip() if not required.empty else "No required stress rows were produced.",
        "",
        "## Interpretation",
        "",
        "V100 tests whether the V99 low-cost high-frequency candidate survives maker-style missed fills and adverse selection. It does not retune the signal. This is still a historical research stress test, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = _ensure_v99_outputs()
    passed = _load_passed_candidates()
    stress = _stress_candidates(passed, summary)
    decision = _decision_from_stress(stress)

    stress_path = OUT_DIR / "v100_maker_fill_stress.csv"
    stress.to_csv(stress_path, index=False)
    payload = {
        "version": "v100_btcusdc_maker_fill_risk",
        "source": {
            "v99_summary": str(V99_DIR / "v99_summary.json"),
            "v99_passed_candidates": str(V99_DIR / "v99_low_cost_passed_candidates.csv"),
        },
        "stress": {
            "fill_models": list(FILL_MODELS),
            "fill_rates": list(FILL_RATES),
            "extra_adverse_bps": list(EXTRA_ADVERSE_BPS),
            "required_fill_models": list(REQUIRED_FILL_MODELS),
            "required_min_fill_rate": REQUIRED_MIN_FILL_RATE,
            "required_max_extra_adverse_bps": REQUIRED_MAX_EXTRA_ADVERSE_BPS,
            "stress_row_count": int(len(stress)),
        },
        "decision": decision,
        "outputs": {
            "stress": str(stress_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v100_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, stress)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
