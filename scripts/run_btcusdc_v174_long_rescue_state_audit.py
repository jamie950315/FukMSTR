from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v162_long_trend_follow_boost as v162
import run_btcusdc_v171_max_drawdown_source_audit as v171


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v174_long_rescue_state_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V174_BTCUSDC_LONG_RESCUE_STATE_AUDIT.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
V171_WINDOW_PATH = ROOT / "runs" / "research_v171_max_drawdown_source_audit" / "v171_max_drawdown_window.csv"

FEATURE_COLUMNS = [
    "direction_probability",
    "position_weight",
    "account_leverage",
    "prior_ret_30_bps",
    "prior_ret_60_bps",
    "prior_ret_120_bps",
    "prior_ret_240_bps",
    "prior_ret_720_bps",
    "prior_ret_1440_bps",
    "prior_range_pos_30",
    "prior_range_pos_60",
    "prior_range_pos_120",
    "prior_range_pos_240",
    "prior_range_pos_720",
    "prior_range_pos_1440",
    "trend_follow_30_bps",
    "trend_follow_60_bps",
    "trend_follow_120_bps",
    "trend_follow_240_bps",
    "trend_follow_720_bps",
    "trend_follow_1440_bps",
    "trend_abs_30_bps",
    "trend_abs_60_bps",
    "trend_abs_120_bps",
    "trend_abs_240_bps",
    "trend_abs_720_bps",
    "trend_abs_1440_bps",
    "funding_rate_bps",
    "funding_z_30d",
    "funding_z_120d",
    "premium_close_bps",
    "premium_z_30d",
    "premium_z_120d",
    "day_sofar_count",
]


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="mixed").astype("datetime64[ns, UTC]")


def _identity_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp"] = _to_utc(out["timestamp"])
    for col in ("source", "side", "leg"):
        out[col] = out[col].fillna("").astype(str)
    return out


def _mark_v171_window_members(trades: pd.DataFrame, window: pd.DataFrame) -> pd.DataFrame:
    out = _identity_frame(trades)
    key_cols = ["timestamp", "source", "side", "leg"]
    window_keys = _identity_frame(window)[key_cols].drop_duplicates()
    window_keys["v174_in_v171_drawdown_window"] = True
    out = out.merge(window_keys, on=key_cols, how="left")
    out["v174_in_v171_drawdown_window"] = out["v174_in_v171_drawdown_window"].fillna(False).astype(bool)
    return out


def _long_rescue_frame(trades: pd.DataFrame, window: pd.DataFrame) -> pd.DataFrame:
    marked = _mark_v171_window_members(trades, window)
    out = marked.loc[marked["side"].eq("long") & marked["leg"].eq("rescue")].copy()
    out["v174_rescue_group"] = "other_long_rescue"
    out.loc[out["v174_in_v171_drawdown_window"], "v174_rescue_group"] = "v171_drawdown_long_rescue"
    return out


def _group_summary(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    returns = pd.to_numeric(work["v162_account_return_pct"], errors="coerce").fillna(0.0)
    work["win"] = returns > 0.0
    summary = (
        work.groupby("v174_rescue_group", dropna=False)
        .agg(
            trade_count=("v162_account_return_pct", "size"),
            account_return_pct=("v162_account_return_pct", "sum"),
            account_pnl_bps=("v162_account_pnl_bps", "sum"),
            win_rate_pct=("win", "mean"),
            avg_position_weight=("position_weight", "mean"),
            avg_account_leverage=("account_leverage", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
        )
        .reset_index()
    )
    summary["win_rate_pct"] = summary["win_rate_pct"] * 100.0
    return summary


def _feature_delta_table(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for feature in features:
        if feature not in frame.columns:
            continue
        values = pd.to_numeric(frame[feature], errors="coerce")
        drawdown = values.loc[frame["v174_rescue_group"].eq("v171_drawdown_long_rescue")].dropna()
        other = values.loc[frame["v174_rescue_group"].eq("other_long_rescue")].dropna()
        if drawdown.empty or other.empty:
            continue
        drawdown_mean = float(drawdown.mean())
        other_mean = float(other.mean())
        other_std = float(other.std(ddof=0)) if len(other) else 0.0
        delta = drawdown_mean - other_mean
        rows.append(
            {
                "feature": feature,
                "drawdown_mean": drawdown_mean,
                "other_mean": other_mean,
                "drawdown_minus_other": delta,
                "abs_drawdown_minus_other": abs(delta),
                "other_std": other_std,
                "standardized_delta_vs_other": delta / other_std if other_std else 0.0,
                "drawdown_non_null_count": int(len(drawdown)),
                "other_non_null_count": int(len(other)),
            }
        )
    return pd.DataFrame(rows).sort_values("abs_drawdown_minus_other", ascending=False).reset_index(drop=True)


def _payload_for_audit(group_summary: pd.DataFrame, feature_deltas: pd.DataFrame) -> dict[str, object]:
    drawdown_row = group_summary.loc[group_summary["v174_rescue_group"].eq("v171_drawdown_long_rescue")]
    other_row = group_summary.loc[group_summary["v174_rescue_group"].eq("other_long_rescue")]
    top_feature = str(feature_deltas.iloc[0]["feature"]) if not feature_deltas.empty else ""
    return {
        "config": {
            "base": "v162_long_rescue_vs_v171_max_drawdown_window",
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "changes_trade_side": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": "long_rescue_state_audit_ready",
            "promote_to_live": False,
            "drawdown_long_rescue_trade_count": int(drawdown_row["trade_count"].sum()) if not drawdown_row.empty else 0,
            "other_long_rescue_trade_count": int(other_row["trade_count"].sum()) if not other_row.empty else 0,
            "drawdown_long_rescue_return_pct": float(drawdown_row["account_return_pct"].sum()) if not drawdown_row.empty else 0.0,
            "other_long_rescue_return_pct": float(other_row["account_return_pct"].sum()) if not other_row.empty else 0.0,
            "top_state_difference_feature": top_feature,
            "message": "Long-rescue failure state differences are audited for future guard research only.",
        },
    }


def _write_report(
    payload: dict[str, object],
    group_summary: pd.DataFrame,
    feature_deltas: pd.DataFrame,
    long_rescue: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    detail_cols = [
        "timestamp",
        "source",
        "v174_rescue_group",
        "v162_account_return_pct",
        "position_weight",
        "direction_probability",
        "prior_ret_120_bps",
        "prior_ret_240_bps",
        "trend_abs_120_bps",
        "trend_abs_240_bps",
        "funding_rate_bps",
        "premium_close_bps",
        "day_sofar_count",
    ]
    detail_cols = [col for col in detail_cols if col in long_rescue.columns]
    drawdown_detail = long_rescue.loc[long_rescue["v174_rescue_group"].eq("v171_drawdown_long_rescue"), detail_cols]
    lines = [
        "# Research V174 BTCUSDC Long Rescue State Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Drawdown long-rescue trades: `{decision['drawdown_long_rescue_trade_count']}`",
        f"- Other long-rescue trades: `{decision['other_long_rescue_trade_count']}`",
        f"- Drawdown long-rescue return: `{decision['drawdown_long_rescue_return_pct']}` pct",
        f"- Other long-rescue return: `{decision['other_long_rescue_return_pct']}` pct",
        f"- Top state-difference feature: `{decision['top_state_difference_feature']}`",
        f"- Message: {decision['message']}",
        "",
        "## Audit Rules",
        "",
        "- Base path: V162 selected account path.",
        "- Failure group: long rescue trades that also appear in the V171 max-drawdown window.",
        "- Comparison group: all other long rescue trades.",
        "- This audit does not add trades, change side, change thresholds, or promote live trading.",
        "",
        "## Group Summary",
        "",
        group_summary.to_csv(index=False).strip(),
        "",
        "## Feature Difference Ranking",
        "",
        feature_deltas.to_csv(index=False).strip(),
        "",
        "## Drawdown Long Rescue Detail",
        "",
        drawdown_detail.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V174 looks for pre-trade state differences between the largest-drawdown long rescue trades and the rest of the long rescue sample. The output should guide the next hypothesis, not serve as a deployment rule by itself.",
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
    if not V171_WINDOW_PATH.exists():
        v171.run()
    trades = pd.read_csv(V162_ACCOUNT_PATH)
    window = pd.read_csv(V171_WINDOW_PATH)
    long_rescue = _long_rescue_frame(trades, window)
    group_summary = _group_summary(long_rescue)
    feature_deltas = _feature_delta_table(long_rescue, FEATURE_COLUMNS)
    payload = _payload_for_audit(group_summary, feature_deltas)
    long_rescue.to_csv(OUT_DIR / "v174_long_rescue_marked.csv", index=False)
    group_summary.to_csv(OUT_DIR / "v174_long_rescue_group_summary.csv", index=False)
    feature_deltas.to_csv(OUT_DIR / "v174_long_rescue_feature_deltas.csv", index=False)
    (OUT_DIR / "v174_long_rescue_state_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, group_summary, feature_deltas, long_rescue)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
