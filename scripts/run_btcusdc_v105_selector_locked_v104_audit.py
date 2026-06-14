from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_btcusdc_v101_thick_edge_regression as v101
import run_btcusdc_v104_ma_hgb_daily_topk_classifier as v104


OUT_DIR = ROOT / "runs" / "research_v105_btcusdc_selector_locked_v104_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V105_BTCUSDC_SELECTOR_LOCKED_V104_AUDIT_RESULTS.md"
V104_CANDIDATES_PATH = v104.OUT_DIR / "v104_ma_hgb_daily_topk_candidates.csv"

MIN_WIN_RATE = v101.MIN_WIN_RATE
MIN_AVG_TRADES_PER_CALENDAR_DAY = v101.MIN_AVG_TRADES_PER_CALENDAR_DAY
MIN_CALENDAR_POSITIVE_MONTH_RATE = v101.MIN_CALENDAR_POSITIVE_MONTH_RATE


def _passes_selector_gate(row: dict[str, object]) -> bool:
    return (
        float(row["selector_total_net_pnl_bps"]) > 0.0
        and float(row["selector_win_rate"]) > MIN_WIN_RATE
        and float(row["selector_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["selector_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
    )


def _passes_holdout_gate(row: dict[str, object]) -> bool:
    return (
        float(row["holdout_total_net_pnl_bps"]) > 0.0
        and float(row["holdout_win_rate"]) > MIN_WIN_RATE
        and float(row["holdout_avg_trades_per_calendar_day"]) >= MIN_AVG_TRADES_PER_CALENDAR_DAY
        and float(row["holdout_calendar_positive_month_rate"]) >= MIN_CALENDAR_POSITIVE_MONTH_RATE
    )


def _selector_locked_decision(candidates: pd.DataFrame) -> dict[str, object]:
    if candidates.empty:
        return {
            "selector_candidate_count": 0,
            "selected_policy": None,
            "selector_locked_holdout_passed": False,
            "goal_satisfied_by_selector_locked_selection": False,
            "failed_reason": "no candidates available",
        }

    frame = candidates.copy()
    selector_mask = frame.apply(lambda row: _passes_selector_gate(row.to_dict()), axis=1)
    selector_candidates = frame.loc[selector_mask].copy()
    if selector_candidates.empty:
        return {
            "selector_candidate_count": 0,
            "selected_policy": None,
            "selector_locked_holdout_passed": False,
            "goal_satisfied_by_selector_locked_selection": False,
            "failed_reason": "no candidate passed selector-only gate",
        }

    selected = selector_candidates.sort_values(
        [
            "selector_total_net_pnl_bps",
            "selector_win_rate",
            "selector_calendar_positive_month_rate",
            "selector_avg_trades_per_calendar_day",
        ],
        ascending=[False, False, False, False],
    ).iloc[0]
    selected_dict = selected.to_dict()
    holdout_passed = bool(_passes_holdout_gate(selected_dict))
    return {
        "selector_candidate_count": int(len(selector_candidates)),
        "selected_policy": str(selected_dict["policy_id"]),
        "selector_locked_holdout_passed": holdout_passed,
        "goal_satisfied_by_selector_locked_selection": holdout_passed,
        "failed_reason": None if holdout_passed else "selector-locked candidate failed holdout gate",
    }


def _load_v104_candidates() -> pd.DataFrame:
    if not V104_CANDIDATES_PATH.exists():
        v104.run()
    return pd.read_csv(V104_CANDIDATES_PATH)


def _write_report(payload: dict[str, object], candidates: pd.DataFrame, selected_row: pd.DataFrame) -> None:
    report_cols = [
        "policy_id",
        "horizon_minutes",
        "daily_top_k",
        "probability_floor",
        "selector_trade_count",
        "selector_avg_trades_per_calendar_day",
        "selector_active_day_rate",
        "selector_total_net_pnl_bps",
        "selector_win_rate",
        "selector_max_drawdown_bps",
        "selector_calendar_positive_month_rate",
        "selector_worst_month_net_pnl_bps",
        "holdout_trade_count",
        "holdout_avg_trades_per_calendar_day",
        "holdout_active_day_rate",
        "holdout_total_net_pnl_bps",
        "holdout_win_rate",
        "holdout_max_drawdown_bps",
        "holdout_calendar_positive_month_rate",
        "holdout_worst_month_net_pnl_bps",
    ]
    selector_candidates = candidates.loc[candidates.apply(lambda row: _passes_selector_gate(row.to_dict()), axis=1)].copy()
    top_selector = selector_candidates.sort_values(
        [
            "selector_total_net_pnl_bps",
            "selector_win_rate",
            "selector_calendar_positive_month_rate",
            "selector_avg_trades_per_calendar_day",
        ],
        ascending=[False, False, False, False],
    ).head(12)
    lines = [
        "# Research V105 BTCUSDC Selector-Locked V104 Audit Results",
        "",
        "## Decision",
        "",
        f"- V104 candidates: `{payload['scan']['candidate_count']}`",
        f"- Selector-only passing candidates: `{payload['decision']['selector_candidate_count']}`",
        f"- Selector-locked selected candidate: `{payload['decision']['selected_policy']}`",
        f"- Holdout passed after selector lock: `{payload['decision']['selector_locked_holdout_passed']}`",
        f"- Goal satisfied by selector-locked selection: `{payload['decision']['goal_satisfied_by_selector_locked_selection']}`",
        "",
        "## Selected Candidate",
        "",
        selected_row[report_cols].to_csv(index=False).strip() if not selected_row.empty else "No selector-locked candidate.",
        "",
        "## Top Selector-Ranked Candidates",
        "",
        top_selector[report_cols].to_csv(index=False).strip() if not top_selector.empty else "No selector-only candidates.",
        "",
        "## Interpretation",
        "",
        "V105 locks the policy using selector-window evidence only, then audits the locked policy on the holdout window. This reduces holdout-ranking bias, but it is still a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    candidates = _load_v104_candidates()
    decision = _selector_locked_decision(candidates)
    selected_policy = decision["selected_policy"]
    selected_row = candidates.loc[candidates["policy_id"] == selected_policy].copy() if selected_policy is not None else pd.DataFrame()

    selected_path = OUT_DIR / "v105_selector_locked_selected_candidate.csv"
    selector_candidates_path = OUT_DIR / "v105_selector_only_candidates.csv"
    selector_candidates = candidates.loc[candidates.apply(lambda row: _passes_selector_gate(row.to_dict()), axis=1)].copy()
    selected_row.to_csv(selected_path, index=False)
    selector_candidates.to_csv(selector_candidates_path, index=False)

    payload = {
        "version": "v105_btcusdc_selector_locked_v104_audit",
        "scan": {
            "candidate_count": int(len(candidates)),
            "source_candidates": str(V104_CANDIDATES_PATH),
            "fee_bps": float(v104.FEE_BPS),
            "selection_rule": [
                "selector_total_net_pnl_bps desc",
                "selector_win_rate desc",
                "selector_calendar_positive_month_rate desc",
                "selector_avg_trades_per_calendar_day desc",
            ],
        },
        "decision": decision,
        "outputs": {
            "selected_candidate": str(selected_path),
            "selector_only_candidates": str(selector_candidates_path),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v105_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(payload, candidates, selected_row)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
