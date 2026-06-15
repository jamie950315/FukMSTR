from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v194_long_rescue_premium_discount_stepup as v194


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v196_forward_monitoring_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V196_BTCUSDC_FORWARD_MONITORING_GATE.md"
V194_ACCOUNT_PATH = (
    ROOT / "runs" / "research_v194_long_rescue_premium_discount_stepup" / "v194_selected_account_path.csv"
)
FREEZE_TIMESTAMP = pd.Timestamp("2026-06-09T16:40:00Z")
MIN_FORWARD_TRADES = 5


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = returns.cumsum()
    drawdown = equity - equity.cummax()
    return float(drawdown.min()) if len(drawdown) else 0.0


def _positive_months(frame: pd.DataFrame, returns: pd.Series) -> str:
    monthly = returns.groupby(frame["month"], sort=True).sum()
    return f"{int((monthly > 0.0).sum())}/{int(len(monthly))}"


def _holdout_months(frame: pd.DataFrame, returns: pd.Series) -> str:
    monthly = returns.groupby(frame["month"], sort=True).sum()
    holdout_monthly = monthly[monthly.index >= "2026-01"]
    return f"{int((holdout_monthly > 0.0).sum())}/{int(len(holdout_monthly))}"


def _version_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    work["month"] = work["timestamp"].dt.strftime("%Y-%m")
    rows = []
    for version, return_col in (("V193", "v193_account_return_pct"), ("V194", "v194_account_return_pct")):
        returns = pd.to_numeric(work[return_col], errors="coerce").fillna(0.0)
        holdout_returns = returns.loc[work["timestamp"].ge(pd.Timestamp("2026-01-01T00:00:00Z"))]
        rows.append(
            {
                "version": version,
                "account_return_pct": float(returns.sum()),
                "improvement_pct": "-",
                "max_drawdown_pct": _max_drawdown(returns),
                "positive_months": _positive_months(work, returns),
                "holdout_return_pct": float(holdout_returns.sum()),
                "holdout_months": _holdout_months(work, returns),
            }
        )
    out = pd.DataFrame(rows)
    out["improvement_pct"] = out["improvement_pct"].astype(object)
    out.loc[out["version"].eq("V194"), "improvement_pct"] = (
        float(out.loc[out["version"].eq("V194"), "account_return_pct"].iloc[0])
        - float(out.loc[out["version"].eq("V193"), "account_return_pct"].iloc[0])
    )
    return out


def _forward_monitoring_table(frame: pd.DataFrame, *, freeze_timestamp: pd.Timestamp = FREEZE_TIMESTAMP) -> pd.DataFrame:
    work = frame.copy()
    work["timestamp"] = _to_utc(work["timestamp"])
    forward = work.loc[work["timestamp"].gt(freeze_timestamp)].copy()
    rows = []
    for version, return_col, pnl_col in (
        ("V193", "v193_account_return_pct", "v193_account_pnl_bps"),
        ("V194", "v194_account_return_pct", "v194_account_pnl_bps"),
    ):
        returns = pd.to_numeric(forward.get(return_col, pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        pnl = pd.to_numeric(forward.get(pnl_col, pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        rows.append(
            {
                "version": version,
                "freeze_timestamp": str(freeze_timestamp),
                "forward_trade_count": int(len(forward)),
                "forward_return_pct": float(returns.sum()),
                "forward_max_drawdown_pct": _max_drawdown(returns),
                "forward_win_rate_pct": float((pnl > 0.0).mean() * 100.0) if len(pnl) else 0.0,
                "forward_first_timestamp": str(forward["timestamp"].min()) if len(forward) else "",
                "forward_last_timestamp": str(forward["timestamp"].max()) if len(forward) else "",
            }
        )
    return pd.DataFrame(rows)


def _payload_for_monitoring(forward_table: pd.DataFrame, *, latest_timestamp: str) -> dict[str, object]:
    max_trades = int(forward_table["forward_trade_count"].max()) if not forward_table.empty else 0
    evidence_available = max_trades >= MIN_FORWARD_TRADES
    return {
        "config": {
            "base": "v194_selected_account_path",
            "freeze_timestamp": str(FREEZE_TIMESTAMP),
            "min_forward_trades": MIN_FORWARD_TRADES,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
            "allow_historical_optimization": False,
        },
        "decision": {
            "status": "forward_evidence_available" if evidence_available else "no_forward_evidence",
            "promote_to_live": False,
            "forward_evidence_available": evidence_available,
            "allow_historical_optimization": False,
            "latest_timestamp": latest_timestamp,
            "forward_trade_count": max_trades,
            "message": (
                "Forward rows are available after the freeze timestamp; review the monitoring table before any claim."
                if evidence_available
                else "No enough post-freeze rows exist; do not claim forward validation and do not resume historical optimization."
            ),
        },
    }


def _metrics_table_markdown(version_metrics: pd.DataFrame) -> str:
    rows = version_metrics.reset_index(drop=True)
    lines = [
        f"| Metric | {rows.iloc[0]['version']} | {rows.iloc[1]['version']} |",
        "|---|---:|---:|",
        f"| Account return estimate | +{rows.iloc[0]['account_return_pct']:.2f}% | +{rows.iloc[1]['account_return_pct']:.2f}% |",
        f"| Improvement | - | +{float(rows.iloc[1]['improvement_pct']):.2f} percentage points |",
        f"| Max drawdown | {rows.iloc[0]['max_drawdown_pct']:.2f}% | {rows.iloc[1]['max_drawdown_pct']:.2f}% |",
        f"| Positive months | {rows.iloc[0]['positive_months']} | {rows.iloc[1]['positive_months']} |",
        f"| Holdout return | +{rows.iloc[0]['holdout_return_pct']:.2f}% | +{rows.iloc[1]['holdout_return_pct']:.2f}% |",
        f"| Holdout months | {rows.iloc[0]['holdout_months']} | {rows.iloc[1]['holdout_months']} |",
    ]
    return "\n".join(lines)


def _write_report(payload: dict[str, object], version_metrics: pd.DataFrame, forward_table: pd.DataFrame) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V196 BTCUSDC Forward Monitoring Gate",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Forward evidence available: `{decision['forward_evidence_available']}`",
        f"- Allow historical optimization: `{decision['allow_historical_optimization']}`",
        f"- Freeze timestamp: `{payload['config']['freeze_timestamp']}`",
        f"- Latest timestamp: `{decision['latest_timestamp']}`",
        f"- Forward trade count: `{decision['forward_trade_count']}`",
        f"- Message: {decision['message']}",
        "",
        "## Required Iteration Metrics",
        "",
        _metrics_table_markdown(version_metrics),
        "",
        "## Monitoring Rules",
        "",
        "- V196 is a monitoring gate, not a new strategy overlay.",
        "- V193 remains the conservative comparison.",
        "- V194 remains the aggressive research candidate.",
        "- Rows at or before the freeze timestamp are historical and cannot validate V194.",
        "- Historical optimization remains frozen regardless of this monitor's result.",
        "",
        "## Forward Monitoring Table",
        "",
        forward_table.to_csv(index=False).strip(),
        "",
        "## Version Metrics",
        "",
        version_metrics.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V196 enforces the V195 overfitting-audit conclusion. Without enough post-freeze trades, there is no forward evidence. The correct next action is to collect new data and rerun this monitor.",
        "",
        "This is a research monitoring gate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V194_ACCOUNT_PATH.exists():
        v194.run()
    frame = pd.read_csv(V194_ACCOUNT_PATH)
    frame["timestamp"] = _to_utc(frame["timestamp"])
    latest_timestamp = str(frame["timestamp"].max()) if len(frame) else ""
    version_metrics = _version_metrics(frame)
    forward_table = _forward_monitoring_table(frame, freeze_timestamp=FREEZE_TIMESTAMP)
    payload = _payload_for_monitoring(forward_table, latest_timestamp=latest_timestamp)
    version_metrics.to_csv(OUT_DIR / "v196_version_metrics.csv", index=False)
    forward_table.to_csv(OUT_DIR / "v196_forward_monitoring_table.csv", index=False)
    (OUT_DIR / "v196_forward_monitoring_gate_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, version_metrics, forward_table)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
