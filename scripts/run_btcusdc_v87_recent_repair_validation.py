from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import (
    summarize_short_term_candidate_validation,
    summarize_short_term_repair_candidates,
)


ROOT = Path(__file__).resolve().parents[1]
V69_DIR = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate"
OUT_DIR = ROOT / "runs" / "research_v87_btcusdc_recent_repair_validation"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V87_BTCUSDC_RECENT_REPAIR_VALIDATION_RESULTS.md"

INPUT_LEDGER = V69_DIR / "v69_hour_gated_trade_ledger.csv"
INPUT_DELAY_LEDGERS = V69_DIR / "v69_delay_trade_ledgers.csv"
HOLDOUT_FOLDS = (5, 6, 7)
EXTRA_COST_BPS = (0.0, 4.0, 8.0, 16.0)
OVERSOLD_SHORT_LOOKBACK_BPS = -650.0
RECENT_TAIL_RATE = 2.0 / 3.0


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out["hour"] = out["timestamp"].dt.hour.astype(int)
    out["net_pnl_bps"] = pd.to_numeric(out["net_pnl_bps"], errors="coerce").fillna(0.0)
    out["signal"] = pd.to_numeric(out["signal"], errors="coerce").fillna(0).astype(int)
    out["lookback_return_bps"] = pd.to_numeric(out["lookback_return_bps"], errors="coerce").fillna(0.0)
    return out


def _extra_cost_summary(trades: pd.DataFrame) -> pd.DataFrame:
    pnl = pd.to_numeric(trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    rows = []
    for extra in EXTRA_COST_BPS:
        adjusted = pnl - float(extra)
        rows.append(
            {
                "extra_cost_bps": float(extra),
                "trades": int(len(adjusted)),
                "total_net_pnl_bps": float(adjusted.sum()),
                "mean_net_pnl_bps": float(adjusted.mean()) if len(adjusted) else 0.0,
                "win_rate": float((adjusted > 0.0).mean()) if len(adjusted) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _delay_summary(delay_ledgers: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for delay, group in delay_ledgers.groupby("entry_delay_minutes", sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "entry_delay_minutes": int(delay),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _policy_mask(name: str, frame: pd.DataFrame) -> pd.Series:
    if name == "v69_baseline":
        return pd.Series(True, index=frame.index)
    if name == "remove_utc_00_04":
        return ~frame["hour"].isin([0, 1, 2, 3, 4])
    if name == "oversold_short_veto":
        return ~((frame["signal"] < 0) & (frame["lookback_return_bps"] < OVERSOLD_SHORT_LOOKBACK_BPS))
    if name == "session_plus_oversold_short_veto":
        return (~frame["hour"].isin([0, 1, 2, 3, 4])) & ~(
            (frame["signal"] < 0) & (frame["lookback_return_bps"] < OVERSOLD_SHORT_LOOKBACK_BPS)
        )
    if name == "keep_core_recent_sessions":
        return frame["hour"].isin([6, 7, 8, 9, 10, 11, 15, 17, 18, 19, 21, 22])
    raise ValueError(f"unknown policy: {name}")


POLICIES: tuple[dict[str, object], ...] = (
    {
        "policy": "remove_utc_00_04",
        "description": "Remove the UTC 00-04 session that is negative in full V69 and heavily negative in recent months.",
    },
    {
        "policy": "oversold_short_veto",
        "description": f"Skip short trades after a 24h lookback move below {OVERSOLD_SHORT_LOOKBACK_BPS:.0f} bps.",
    },
    {
        "policy": "session_plus_oversold_short_veto",
        "description": f"Remove UTC 00-04 and skip short trades after a 24h lookback move below {OVERSOLD_SHORT_LOOKBACK_BPS:.0f} bps.",
    },
    {
        "policy": "keep_core_recent_sessions",
        "description": "Keep UTC 06-11, 15, 17-19, and 21-22 only.",
    },
)


def _validate_policy(
    policy: str,
    trades: pd.DataFrame,
    delay_ledgers: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame, pd.DataFrame]:
    kept = trades.loc[_policy_mask(policy, trades)].copy().reset_index(drop=True)
    kept_delay = delay_ledgers.loc[_policy_mask(policy, delay_ledgers)].copy().reset_index(drop=True)
    delays = _delay_summary(kept_delay)
    extra = _extra_cost_summary(kept)
    result = summarize_short_term_candidate_validation(
        kept,
        delay_summary=delays,
        extra_cost_summary=extra,
        holdout_folds=HOLDOUT_FOLDS,
        min_recent_tail_positive_month_rate=RECENT_TAIL_RATE,
        recent_tail_active_months=3,
    )
    return kept, result, delays, extra


def _window_stats(trades: pd.DataFrame) -> pd.DataFrame:
    frame = trades.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["month"] = frame["timestamp"].dt.tz_convert(None).dt.to_period("M").astype(str)
    recent = frame.loc[frame["month"].between("2026-01", "2026-06")].copy()
    rows = []
    for month, group in recent.groupby("month", sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "month": str(month),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
                "positive": bool(float(pnl.sum()) > 0.0),
            }
        )
    return pd.DataFrame(rows)


def _write_report(payload: dict[str, object], candidates: pd.DataFrame, selected_months: pd.DataFrame) -> None:
    aggregate = payload["repair"]["aggregate"]
    selected = payload["selected"]
    lines = [
        "# Research V87 BTCUSDC Recent Repair Validation Results",
        "",
        "## Decision",
        "",
        f"- Promote repair candidate: `{aggregate['promote_repair_candidate']}`",
        f"- Selected policy: `{aggregate['selected_policy']}`",
        f"- Selected total improvement: `{float(aggregate['selected_total_improvement_bps']):.6f}` bps",
        f"- Selected recent improvement: `{float(aggregate['selected_recent_total_improvement_bps']):.6f}` bps",
        f"- Selected holdout improvement: `{float(aggregate['selected_holdout_improvement_bps']):.6f}` bps",
        "",
        "## Selected Policy",
        "",
        f"- Policy: `{selected['policy']}`",
        f"- Description: {selected['description']}",
        f"- Trades: `{selected['short_term']['trade_count']}`",
        f"- Total net PnL: `{float(selected['short_term']['total_net_pnl_bps']):.6f}` bps",
        f"- Mean net PnL: `{float(selected['short_term']['mean_net_pnl_bps']):.6f}` bps",
        f"- Win rate: `{float(selected['short_term']['win_rate']):.6f}`",
        f"- Positive fold rate: `{float(selected['short_term']['positive_fold_rate']):.6f}`",
        f"- Worst fold: `{float(selected['short_term']['worst_fold_net_pnl_bps']):.6f}` bps",
        f"- Holdout total: `{float(selected['short_term']['holdout_total_net_pnl_bps']):.6f}` bps",
        f"- Recent total: `{float(selected['recent']['recent_total_net_pnl_bps']):.6f}` bps",
        f"- Recent active positive month rate: `{float(selected['recent']['recent_active_positive_month_rate']):.6f}`",
        f"- Tail active positive month rate: `{float(selected['recent']['tail_active_positive_month_rate']):.6f}`",
        f"- Latest active month: `{selected['recent']['latest_active_month']}`",
        f"- Latest active month PnL: `{float(selected['recent']['latest_active_month_net_pnl_bps']):.6f}` bps",
        "",
        "## Repair Candidates",
        "",
        candidates.to_csv(index=False).strip(),
        "",
        "## Selected Recent Months",
        "",
        selected_months.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V87 tests pre-trade repair candidates for the V69 12-hour short-term BTCUSDC candidate. The selected repair skips shorts after a deep 24-hour down move. This directly targets the recent deterioration source without using outcome-only fields.",
        "",
        "The selected repair improves total, holdout, delay, cost, and recent-month behavior in the current evidence. It should still be treated as a repaired research candidate, not a live-profit guarantee, because the repair was motivated by observed recent deterioration and needs fresh forward monitoring.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not INPUT_LEDGER.exists():
        raise SystemExit(f"missing input ledger: {INPUT_LEDGER}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    trades = _normalize(pd.read_csv(INPUT_LEDGER))
    delay_ledgers = _normalize(pd.read_csv(INPUT_DELAY_LEDGERS))
    baseline_trades, baseline, _, _ = _validate_policy("v69_baseline", trades, delay_ledgers)

    candidate_payloads: list[dict[str, object]] = []
    selected_trades = baseline_trades
    for spec in POLICIES:
        policy = str(spec["policy"])
        kept, result, delays, extra = _validate_policy(policy, trades, delay_ledgers)
        result["policy"] = policy
        result["description"] = str(spec["description"])
        result["outputs"] = {
            "trade_ledger": str(OUT_DIR / f"v87_{policy}_trade_ledger.csv"),
            "delay_summary": str(OUT_DIR / f"v87_{policy}_delay_summary.csv"),
            "extra_cost_summary": str(OUT_DIR / f"v87_{policy}_extra_cost_summary.csv"),
        }
        kept.to_csv(OUT_DIR / f"v87_{policy}_trade_ledger.csv", index=False)
        delays.to_csv(OUT_DIR / f"v87_{policy}_delay_summary.csv", index=False)
        extra.to_csv(OUT_DIR / f"v87_{policy}_extra_cost_summary.csv", index=False)
        candidate_payloads.append(result)

    repair = summarize_short_term_repair_candidates(
        baseline,
        candidate_payloads,
        min_total_improvement_bps=0.0,
        min_recent_total_improvement_bps=0.0,
    )
    selected_policy = repair["aggregate"]["selected_policy"]
    selected = next((row for row in candidate_payloads if row["policy"] == selected_policy), None)
    if selected is None:
        selected = {"policy": None, "description": "", **baseline}
    else:
        selected_trades = pd.read_csv(selected["outputs"]["trade_ledger"])

    candidates = pd.DataFrame(repair["candidates"])
    selected_months = _window_stats(selected_trades)
    candidates.to_csv(OUT_DIR / "v87_repair_candidates.csv", index=False)
    selected_months.to_csv(OUT_DIR / "v87_selected_recent_months.csv", index=False)
    payload = {
        "version": "v87_btcusdc_recent_repair_validation",
        "input_ledger": str(INPUT_LEDGER),
        "baseline": baseline,
        "repair": repair,
        "selected": selected,
        "outputs": {
            "summary_json": str(OUT_DIR / "v87_summary.json"),
            "repair_candidates": str(OUT_DIR / "v87_repair_candidates.csv"),
            "selected_recent_months": str(OUT_DIR / "v87_selected_recent_months.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v87_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, candidates, selected_months)
    print(json.dumps(payload, indent=2, default=str))
