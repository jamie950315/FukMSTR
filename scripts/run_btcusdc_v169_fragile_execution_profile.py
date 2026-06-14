from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v162_long_trend_follow_boost as v162
import run_btcusdc_v168_execution_readiness_gate as v168


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v169_fragile_execution_profile"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V169_BTCUSDC_FRAGILE_EXECUTION_PROFILE.md"
V162_ACCOUNT_PATH = ROOT / "runs" / "research_v162_long_trend_follow_boost" / "v162_selected_account_path.csv"
V168_GATE_PATH = ROOT / "runs" / "research_v168_execution_readiness_gate" / "v168_execution_readiness_gate.csv"
FRAGILE_MODES = {"maker_only_required", "maker_priority_required", "no_trade_unless_cost_improves"}


def _attach_execution_mode(trades: pd.DataFrame, gate: pd.DataFrame) -> pd.DataFrame:
    gate_cols = [
        "month",
        "execution_readiness_mode",
        "live_gate_action",
        "max_taker_share_pct",
        "required_maker_share_pct",
    ]
    available_cols = [col for col in gate_cols if col in gate.columns]
    out = trades.merge(gate[available_cols], on="month", how="left", validate="many_to_one").copy()
    out["execution_readiness_mode"] = out["execution_readiness_mode"].fillna("unknown_execution_mode")
    out["live_gate_action"] = out["live_gate_action"].fillna("investigate_missing_gate")
    out["fragile_execution_group"] = "normal_execution"
    out.loc[out["execution_readiness_mode"].isin(FRAGILE_MODES), "fragile_execution_group"] = "fragile_execution"
    out.loc[out["execution_readiness_mode"].eq("unknown_execution_mode"), "fragile_execution_group"] = "unknown_execution"
    return out


def _group_profile(frame: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    work = frame.copy()
    work["win"] = pd.to_numeric(work["v162_account_return_pct"], errors="coerce") > 0.0
    work["is_long"] = work["side"].eq("long")
    work["is_short"] = work["side"].eq("short")
    work["is_base"] = work["leg"].eq("base")
    work["is_rescue"] = work["leg"].eq("rescue")
    profile = (
        work.groupby(group_cols, dropna=False)
        .agg(
            trade_count=("v162_account_return_pct", "size"),
            account_return_pct=("v162_account_return_pct", "sum"),
            account_pnl_bps=("v162_account_pnl_bps", "sum"),
            win_rate_pct=("win", "mean"),
            avg_return_per_trade_pct=("v162_account_return_pct", "mean"),
            median_return_per_trade_pct=("v162_account_return_pct", "median"),
            long_trade_count=("is_long", "sum"),
            short_trade_count=("is_short", "sum"),
            base_trade_count=("is_base", "sum"),
            rescue_trade_count=("is_rescue", "sum"),
            avg_account_leverage=("account_leverage", "mean"),
            avg_position_weight=("position_weight", "mean"),
            avg_direction_probability=("direction_probability", "mean"),
        )
        .reset_index()
    )
    profile["win_rate_pct"] = profile["win_rate_pct"] * 100.0
    profile["return_share_pct"] = profile["account_return_pct"] / profile["account_return_pct"].sum() * 100.0
    return profile


def _payload_for_profiles(group_profile: pd.DataFrame) -> dict[str, object]:
    fragile = group_profile.loc[group_profile["fragile_execution_group"].eq("fragile_execution")]
    normal = group_profile.loc[group_profile["fragile_execution_group"].eq("normal_execution")]
    fragile_trade_count = int(fragile["trade_count"].sum()) if not fragile.empty else 0
    normal_trade_count = int(normal["trade_count"].sum()) if not normal.empty else 0
    fragile_return = float(fragile["account_return_pct"].sum()) if not fragile.empty else 0.0
    normal_return = float(normal["account_return_pct"].sum()) if not normal.empty else 0.0
    return {
        "config": {
            "base": "v162_trades_joined_to_v168_execution_gate",
            "fragile_modes": sorted(FRAGILE_MODES),
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "promotes_live_trading": False,
        },
        "decision": {
            "status": "fragile_execution_profile_ready",
            "promote_to_live": False,
            "message": "Fragile execution months are profiled at trade level; use this as risk context only.",
            "fragile_trade_count": fragile_trade_count,
            "normal_trade_count": normal_trade_count,
            "fragile_return_pct": fragile_return,
            "normal_return_pct": normal_return,
            "fragile_avg_return_per_trade_pct": fragile_return / fragile_trade_count if fragile_trade_count else 0.0,
            "normal_avg_return_per_trade_pct": normal_return / normal_trade_count if normal_trade_count else 0.0,
        },
    }


def _write_report(
    payload: dict[str, object],
    group_profile: pd.DataFrame,
    mode_profile: pd.DataFrame,
    side_leg_profile: pd.DataFrame,
    monthly_profile: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    lines = [
        "# Research V169 BTCUSDC Fragile Execution Profile",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Message: {decision['message']}",
        f"- Fragile trade count: `{decision['fragile_trade_count']}`",
        f"- Normal trade count: `{decision['normal_trade_count']}`",
        f"- Fragile return: `{decision['fragile_return_pct']}` pct",
        f"- Normal return: `{decision['normal_return_pct']}` pct",
        f"- Fragile avg return / trade: `{decision['fragile_avg_return_per_trade_pct']}` pct",
        f"- Normal avg return / trade: `{decision['normal_avg_return_per_trade_pct']}` pct",
        "",
        "## Audit Rules",
        "",
        "- Base trades: V162 selected account path.",
        "- Execution gate: V168 monthly execution readiness gate.",
        "- Fragile execution group: maker-only, maker-priority, or no-trade-unless-cost-improves months.",
        "- This audit does not add trades, change sides, change thresholds, or promote live trading.",
        "",
        "## Fragile Vs Normal Profile",
        "",
        group_profile.to_csv(index=False).strip(),
        "",
        "## Execution Mode Profile",
        "",
        mode_profile.to_csv(index=False).strip(),
        "",
        "## Side And Leg Profile",
        "",
        side_leg_profile.to_csv(index=False).strip(),
        "",
        "## Monthly Profile",
        "",
        monthly_profile.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V169 shows whether the V168 execution-warning months are weak because of trade composition, side/leg mix, leverage, position weight, or return concentration. This converts the monthly execution gate into trade-level risk context for future monitoring.",
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
    group_profile = _group_profile(joined, ["fragile_execution_group"])
    mode_profile = _group_profile(joined, ["execution_readiness_mode", "live_gate_action"])
    side_leg_profile = _group_profile(joined, ["fragile_execution_group", "side", "leg"])
    monthly_profile = _group_profile(joined, ["month", "execution_readiness_mode", "live_gate_action"])
    payload = _payload_for_profiles(group_profile)
    joined.to_csv(OUT_DIR / "v169_trade_execution_profile.csv", index=False)
    group_profile.to_csv(OUT_DIR / "v169_fragile_vs_normal_profile.csv", index=False)
    mode_profile.to_csv(OUT_DIR / "v169_execution_mode_profile.csv", index=False)
    side_leg_profile.to_csv(OUT_DIR / "v169_side_leg_profile.csv", index=False)
    monthly_profile.to_csv(OUT_DIR / "v169_monthly_profile.csv", index=False)
    (OUT_DIR / "v169_fragile_execution_profile_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, group_profile, mode_profile, side_leg_profile, monthly_profile)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
