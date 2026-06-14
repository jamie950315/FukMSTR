from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v162_long_trend_follow_boost as v162
import run_btcusdc_v168_execution_readiness_gate as v168


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v171_max_drawdown_source_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V171_BTCUSDC_MAX_DRAWDOWN_SOURCE_AUDIT.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
V168_GATE_PATH = ROOT / "runs" / "research_v168_execution_readiness_gate" / "v168_execution_readiness_gate.csv"


METRIC_COLUMNS = {
    "trade_count",
    "account_return_pct",
    "account_pnl_bps",
    "loss_trade_count",
    "win_trade_count",
    "win_rate_pct",
    "avg_account_leverage",
    "avg_position_weight",
    "avg_direction_probability",
    "return_share_of_window_pct",
}


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _attach_execution_mode(trades: pd.DataFrame, gate: pd.DataFrame) -> pd.DataFrame:
    gate_cols = ["month", "execution_readiness_mode", "live_gate_action"]
    available_cols = [col for col in gate_cols if col in gate.columns]
    out = trades.merge(gate[available_cols], on="month", how="left", validate="many_to_one").copy()
    out["execution_readiness_mode"] = out["execution_readiness_mode"].fillna("unknown_execution_mode")
    out["live_gate_action"] = out["live_gate_action"].fillna("investigate_missing_gate")
    return out


def _annotate_drawdown_path(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.sort_values("timestamp", kind="mergesort").reset_index(drop=True).copy()
    out["timestamp"] = _to_utc(out["timestamp"])
    returns = pd.to_numeric(out["v162_account_return_pct"], errors="coerce").fillna(0.0)
    equity_values: list[float] = []
    peak_values: list[float] = []
    drawdown_values: list[float] = []
    peak_positions: list[int | None] = []
    equity = 0.0
    peak = 0.0
    peak_position: int | None = None
    for pos, value in enumerate(returns):
        equity += float(value)
        if equity > peak:
            peak = equity
            peak_position = pos
        equity_values.append(equity)
        peak_values.append(peak)
        drawdown_values.append(equity - peak)
        peak_positions.append(peak_position)
    out["v171_equity_return_pct"] = equity_values
    out["v171_peak_return_pct"] = peak_values
    out["v171_drawdown_pct"] = drawdown_values
    out["v171_peak_position"] = peak_positions
    return out


def _max_drawdown_window(annotated: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    if annotated.empty:
        return annotated.copy(), {
            "max_drawdown_pct": 0.0,
            "peak_timestamp": "initial_account_equity",
            "trough_timestamp": "",
            "window_start_timestamp": "",
            "window_trade_count": 0,
            "window_return_pct": 0.0,
        }
    trough_position = int(pd.to_numeric(annotated["v171_drawdown_pct"], errors="coerce").idxmin())
    trough = annotated.loc[trough_position]
    peak_position = trough.get("v171_peak_position")
    if pd.isna(peak_position):
        peak_position = None
    peak_position = int(peak_position) if peak_position is not None else None
    start_position = peak_position + 1 if peak_position is not None else 0
    window = annotated.loc[start_position:trough_position].copy()
    peak_timestamp = (
        str(annotated.loc[peak_position, "timestamp"]) if peak_position is not None else "initial_account_equity"
    )
    summary = {
        "max_drawdown_pct": float(trough["v171_drawdown_pct"]),
        "peak_timestamp": peak_timestamp,
        "trough_timestamp": str(trough["timestamp"]),
        "window_start_timestamp": str(window.iloc[0]["timestamp"]) if not window.empty else "",
        "window_trade_count": int(len(window)),
        "window_return_pct": float(pd.to_numeric(window["v162_account_return_pct"], errors="coerce").fillna(0.0).sum()),
    }
    return window, summary


def _attribute_window(window: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    available = [col for col in group_cols if col in window.columns]
    if window.empty or not available:
        return pd.DataFrame()
    work = window.copy()
    returns = pd.to_numeric(work["v162_account_return_pct"], errors="coerce").fillna(0.0)
    work["v171_loss_trade"] = returns < 0.0
    work["v171_win_trade"] = returns > 0.0
    profile = (
        work.groupby(available, dropna=False)
        .agg(
            trade_count=("v162_account_return_pct", "size"),
            account_return_pct=("v162_account_return_pct", "sum"),
            account_pnl_bps=("v162_account_pnl_bps", "sum"),
            loss_trade_count=("v171_loss_trade", "sum"),
            win_trade_count=("v171_win_trade", "sum"),
            avg_account_leverage=("account_leverage", "mean"),
            avg_position_weight=("position_weight", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
        )
        .reset_index()
    )
    profile["win_rate_pct"] = profile["win_trade_count"] / profile["trade_count"] * 100.0
    total_return = float(profile["account_return_pct"].sum())
    profile["return_share_of_window_pct"] = (
        profile["account_return_pct"] / total_return * 100.0 if total_return else 0.0
    )
    return profile.sort_values("account_return_pct", ascending=True).reset_index(drop=True)


def _dominant_loss_group(attribution: pd.DataFrame) -> str:
    if attribution.empty:
        return ""
    group_cols = [col for col in attribution.columns if col not in METRIC_COLUMNS]
    row = attribution.sort_values("account_return_pct", ascending=True).iloc[0]
    if not group_cols:
        return ""
    return ":".join(str(row[col]) for col in group_cols)


def _payload_for_audit(summary: dict[str, object], attribution: pd.DataFrame) -> dict[str, object]:
    return {
        "config": {
            "base": "v162_selected_account_path_joined_to_v168_execution_gate",
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": "max_drawdown_source_audit_ready",
            "promote_to_live": False,
            "max_drawdown_pct": float(summary.get("max_drawdown_pct", 0.0)),
            "peak_timestamp": str(summary.get("peak_timestamp", "")),
            "trough_timestamp": str(summary.get("trough_timestamp", "")),
            "window_trade_count": int(summary.get("window_trade_count", 0)),
            "window_return_pct": float(summary.get("window_return_pct", 0.0)),
            "dominant_loss_group": _dominant_loss_group(attribution),
            "message": "Max-drawdown trades are attributed by source, side, leg, and execution mode for risk research only.",
        },
    }


def _write_report(
    payload: dict[str, object],
    summary: dict[str, object],
    side_attr: pd.DataFrame,
    leg_attr: pd.DataFrame,
    source_attr: pd.DataFrame,
    side_leg_attr: pd.DataFrame,
    source_side_leg_attr: pd.DataFrame,
    execution_attr: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V171 BTCUSDC Max Drawdown Source Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Max drawdown: `{decision['max_drawdown_pct']}` pct",
        f"- Peak timestamp: `{decision['peak_timestamp']}`",
        f"- Trough timestamp: `{decision['trough_timestamp']}`",
        f"- Window trade count: `{decision['window_trade_count']}`",
        f"- Window return: `{decision['window_return_pct']}` pct",
        f"- Dominant loss group: `{decision['dominant_loss_group']}`",
        f"- Message: {decision['message']}",
        "",
        "## Audit Rules",
        "",
        "- Base path: V162 selected account path.",
        "- Execution mode: V168 monthly execution readiness gate.",
        "- Max drawdown window: trades after the latest equity peak through the max-drawdown trough.",
        "- This audit does not add trades, change side, change thresholds, or promote live trading.",
        "",
        "## Window Summary",
        "",
        pd.DataFrame([summary]).to_csv(index=False).strip(),
        "",
        "## Side Attribution",
        "",
        side_attr.to_csv(index=False).strip(),
        "",
        "## Leg Attribution",
        "",
        leg_attr.to_csv(index=False).strip(),
        "",
        "## Source Attribution",
        "",
        source_attr.to_csv(index=False).strip(),
        "",
        "## Side Leg Attribution",
        "",
        side_leg_attr.to_csv(index=False).strip(),
        "",
        "## Source Side Leg Attribution",
        "",
        source_side_leg_attr.to_csv(index=False).strip(),
        "",
        "## Execution Mode Attribution",
        "",
        execution_attr.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V171 identifies the realized trade cluster that caused the largest account drawdown. Use it to decide what specific risk hypothesis should be tested next. It is not a live-trading proof and does not change the promoted research path.",
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V162_ACCOUNT_PATH.exists():
        v162.run()
    if not V168_GATE_PATH.exists():
        v168.run()
    trades = pd.read_csv(V162_ACCOUNT_PATH)
    gate = pd.read_csv(V168_GATE_PATH)
    joined = _attach_execution_mode(trades, gate)
    annotated = _annotate_drawdown_path(joined)
    window, summary = _max_drawdown_window(annotated)
    side_attr = _attribute_window(window, ["side"])
    leg_attr = _attribute_window(window, ["leg"])
    source_attr = _attribute_window(window, ["source"])
    side_leg_attr = _attribute_window(window, ["side", "leg"])
    source_side_leg_attr = _attribute_window(window, ["source", "side", "leg"])
    execution_attr = _attribute_window(window, ["execution_readiness_mode", "live_gate_action"])
    payload = _payload_for_audit(summary, side_attr)
    annotated.to_csv(OUT_DIR / "v171_annotated_drawdown_path.csv", index=False)
    window.to_csv(OUT_DIR / "v171_max_drawdown_window.csv", index=False)
    side_attr.to_csv(OUT_DIR / "v171_side_attribution.csv", index=False)
    leg_attr.to_csv(OUT_DIR / "v171_leg_attribution.csv", index=False)
    source_attr.to_csv(OUT_DIR / "v171_source_attribution.csv", index=False)
    side_leg_attr.to_csv(OUT_DIR / "v171_side_leg_attribution.csv", index=False)
    source_side_leg_attr.to_csv(OUT_DIR / "v171_source_side_leg_attribution.csv", index=False)
    execution_attr.to_csv(OUT_DIR / "v171_execution_mode_attribution.csv", index=False)
    (OUT_DIR / "v171_max_drawdown_source_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(
        payload,
        summary,
        side_attr,
        leg_attr,
        source_attr,
        side_leg_attr,
        source_side_leg_attr,
        execution_attr,
    )
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
