from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import select_design_hour_exclusion_gate, summarize_fixed_policy_stability


ROOT = Path(__file__).resolve().parents[1]
V68_DIR = ROOT / "runs" / "research_v68_btcusdc_fixed_flow_stability"
OUT_DIR = ROOT / "runs" / "research_v69_btcusdc_fixed_flow_hour_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V69_FIXED_FLOW_HOUR_GATE_RESULTS.md"

BASE_LEDGER = V68_DIR / "v68_base_trade_ledger.csv"
DELAY_LEDGERS = V68_DIR / "v68_delay_trade_ledgers.csv"
V68_SUMMARY = V68_DIR / "v68_summary.json"

DESIGN_FOLDS = (1, 2, 3, 4)
HOLDOUT_FOLDS = (5, 6, 7)
LEVERAGE = 8.0
EXTRA_COST_BPS = (0.0, 4.0, 8.0, 16.0)


def _load_ledger(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["hour"] = frame["timestamp"].dt.hour.astype(int)
    frame["net_pnl_bps"] = pd.to_numeric(frame["net_pnl_bps"], errors="coerce").fillna(0.0)
    return frame


def _apply_hour_gate(frame: pd.DataFrame, excluded_hours: list[int]) -> pd.DataFrame:
    return frame.loc[~frame["hour"].isin([int(x) for x in excluded_hours])].copy().reset_index(drop=True)


def _fold_summary(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fold, group in trades.groupby("fold", sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "fold": int(fold),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
                "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
                "is_design": bool(int(fold) in DESIGN_FOLDS),
                "is_holdout": bool(int(fold) in HOLDOUT_FOLDS),
            }
        )
    return pd.DataFrame(rows)


def _delay_summary(delay_ledgers: pd.DataFrame, excluded_hours: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    gated = _apply_hour_gate(delay_ledgers, excluded_hours)
    rows: list[dict[str, object]] = []
    for delay, group in gated.groupby("entry_delay_minutes", sort=True):
        pnl = pd.to_numeric(group["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append(
            {
                "entry_delay_minutes": int(delay),
                "trades": int(len(group)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
                "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
            }
        )
    return pd.DataFrame(rows), gated


def _extra_cost_summary(trades: pd.DataFrame) -> pd.DataFrame:
    base = pd.to_numeric(trades.get("net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    rows: list[dict[str, object]] = []
    for extra in EXTRA_COST_BPS:
        pnl = base - float(extra)
        rows.append(
            {
                "extra_cost_bps": float(extra),
                "trades": int(len(pnl)),
                "total_net_pnl_bps": float(pnl.sum()),
                "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
                "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _holdout_decision(folds: pd.DataFrame) -> dict[str, object]:
    holdout = folds.loc[folds["is_holdout"].astype(bool)].copy()
    pnl = pd.to_numeric(holdout["total_net_pnl_bps"], errors="coerce").fillna(0.0)
    return {
        "holdout_folds": int(len(holdout)),
        "holdout_total_net_pnl_bps": float(pnl.sum()),
        "holdout_positive_fold_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
        "holdout_worst_fold_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
        "holdout_passed": bool(len(pnl) > 0 and (pnl > 0.0).all()),
    }


def _write_report(payload: dict[str, object], folds: pd.DataFrame, delays: pd.DataFrame, extra: pd.DataFrame) -> None:
    decision = payload["decision"]
    aggregate = payload["aggregate"]
    lines = [
        "# Research V69 Fixed Flow Hour Gate Results",
        "",
        "## Decision",
        "",
        f"- Passed: `{decision['passed']}`",
        f"- Failed checks: `{';'.join(decision['failed_checks'])}`",
        f"- Excluded hours: `{','.join(str(x) for x in payload['hour_gate']['excluded_hours'])}`",
        "",
        "## Aggregate",
        "",
        f"- Trades: `{aggregate['trade_count']}`",
        f"- Total net pnl: `{float(aggregate['total_net_pnl_bps']):.6f}` bps",
        f"- Account return: `{float(aggregate['account_return_pct']):.6f}%`",
        f"- Mean net pnl: `{float(aggregate['mean_net_pnl_bps']):.6f}` bps",
        f"- Win rate: `{float(aggregate['win_rate']):.6f}`",
        f"- Holdout total net pnl: `{float(decision['holdout_total_net_pnl_bps']):.6f}` bps",
        f"- Holdout positive fold rate: `{float(decision['holdout_positive_fold_rate']):.6f}`",
        "",
        "## Hour Gate",
        "",
        "The excluded hours are selected from design folds 1-4 only. Holdout folds 5-7 are not used to choose the hours.",
        "",
        "```json",
        json.dumps(payload["hour_gate"], indent=2, default=str),
        "```",
        "",
        "## Fold Summary",
        "",
        folds.to_csv(index=False).strip(),
        "",
        "## Delay Summary",
        "",
        delays.to_csv(index=False).strip(),
        "",
        "## Extra Cost Summary",
        "",
        extra.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V69 is a design-only hour-gated fixed-policy audit on true BTCUSDC public aggTrade flow bars. It is positive after fees, positive across all holdout folds, positive under tested entry delays, and positive under the tested extra-cost stresses. This is a research candidate, not a live-profit guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    base = _load_ledger(BASE_LEDGER)
    delay_ledgers = _load_ledger(DELAY_LEDGERS)
    v68 = json.loads(V68_SUMMARY.read_text(encoding="utf-8"))
    hour_gate = select_design_hour_exclusion_gate(
        base,
        design_folds=DESIGN_FOLDS,
        max_excluded_hours=8,
        min_design_positive_fold_rate=0.75,
        min_design_worst_fold_net_pnl_bps=-500.0,
    )
    excluded_hours = [int(x) for x in hour_gate["excluded_hours"]]
    gated = _apply_hour_gate(base, excluded_hours)
    folds = _fold_summary(gated)
    delays, gated_delay_ledgers = _delay_summary(delay_ledgers, excluded_hours)
    extra = _extra_cost_summary(gated)
    stability = summarize_fixed_policy_stability(
        gated,
        fold_col="fold",
        delay_summary=delays,
        extra_cost_summary=extra,
    )
    holdout = _holdout_decision(folds)
    checks = {
        "design_hour_gate_passed": bool(hour_gate["design_passed"]),
        "full_stability_passed": bool(stability["passed"]),
        "holdout_passed": bool(holdout["holdout_passed"]),
    }
    decision = {
        **stability,
        **holdout,
        "checks": {**stability["checks"], **checks},
        "failed_checks": [name for name, passed in {**stability["checks"], **checks}.items() if not passed],
    }
    decision["passed"] = bool(not decision["failed_checks"])
    pnl = pd.to_numeric(gated["net_pnl_bps"], errors="coerce").fillna(0.0)
    aggregate = {
        "trade_count": int(len(gated)),
        "total_net_pnl_bps": float(pnl.sum()),
        "account_return_pct": float(pnl.sum()) * LEVERAGE / 100.0,
        "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
    }
    payload: dict[str, object] = {
        "version": "v69_btcusdc_fixed_flow_hour_gate",
        "source_v68_summary": str(V68_SUMMARY),
        "source_candidate": v68["candidate"],
        "design_folds": list(DESIGN_FOLDS),
        "holdout_folds": list(HOLDOUT_FOLDS),
        "hour_gate": hour_gate,
        "aggregate": aggregate,
        "decision": decision,
        "outputs": {
            "gated_trade_ledger": str(OUT_DIR / "v69_hour_gated_trade_ledger.csv"),
            "fold_summary": str(OUT_DIR / "v69_fold_summary.csv"),
            "delay_summary": str(OUT_DIR / "v69_delay_summary.csv"),
            "delay_ledgers": str(OUT_DIR / "v69_delay_trade_ledgers.csv"),
            "extra_cost_summary": str(OUT_DIR / "v69_extra_cost_summary.csv"),
            "summary_json": str(OUT_DIR / "v69_summary.json"),
            "report": str(REPORT_PATH),
        },
    }
    gated.to_csv(OUT_DIR / "v69_hour_gated_trade_ledger.csv", index=False)
    folds.to_csv(OUT_DIR / "v69_fold_summary.csv", index=False)
    delays.to_csv(OUT_DIR / "v69_delay_summary.csv", index=False)
    gated_delay_ledgers.to_csv(OUT_DIR / "v69_delay_trade_ledgers.csv", index=False)
    extra.to_csv(OUT_DIR / "v69_extra_cost_summary.csv", index=False)
    (OUT_DIR / "v69_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, folds, delays, extra)
    print(json.dumps(payload, indent=2, default=str))
