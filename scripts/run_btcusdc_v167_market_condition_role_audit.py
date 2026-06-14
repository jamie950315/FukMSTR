from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v167_market_condition_role_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V167_BTCUSDC_MARKET_CONDITION_ROLE_AUDIT.md"


def _research_catalog() -> pd.DataFrame:
    rows = [
        {
            "version": "V143",
            "title": "Market emotion trend audit",
            "source_report": "reports/RESEARCH_V143_BTCUSDC_MARKET_EMOTION_TREND_AUDIT.md",
            "status": "selector_candidate_not_holdout_robust",
            "promoted_to_next_model": False,
            "role_hint": "external_market_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": False,
            "main_lesson": "Raw emotion/trend boosts can raise return but did not stay robust enough for promotion.",
        },
        {
            "version": "V144",
            "title": "Funding sentiment governor",
            "source_report": "reports/RESEARCH_V144_BTCUSDC_FUNDING_SENTIMENT_GOVERNOR.md",
            "status": "funding_sentiment_governor_passed",
            "promoted_to_next_model": True,
            "role_hint": "external_market_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Funding helped as a small not-crowded contrarian sizing layer.",
        },
        {
            "version": "V145",
            "title": "Derivatives sentiment monitor",
            "source_report": "reports/RESEARCH_V145_BTCUSDC_DERIVATIVES_SENTIMENT_MONITOR.md",
            "status": "derivatives_sentiment_recent_monitor_ready",
            "promoted_to_next_model": False,
            "role_hint": "derivatives_positioning",
            "mechanism": "monitor",
            "coverage_policy": "recent_monitoring_only",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": False,
            "main_lesson": "Open-interest and long/short ratios were useful context but had too little history.",
        },
        {
            "version": "V146",
            "title": "Fear and Greed macro overlay",
            "source_report": "reports/RESEARCH_V146_BTCUSDC_FEAR_GREED_MACRO_OVERLAY.md",
            "status": "fear_greed_macro_overlay_not_promoted",
            "promoted_to_next_model": False,
            "role_hint": "slow_macro_sentiment",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": False,
            "main_lesson": "Daily macro sentiment raised pockets of return but worsened promotion risk gates.",
        },
        {
            "version": "V147",
            "title": "Fear and Greed regime risk overlay",
            "source_report": "reports/RESEARCH_V147_BTCUSDC_FEAR_GREED_REGIME_RISK_OVERLAY.md",
            "status": "fear_greed_regime_risk_overlay_not_promoted",
            "promoted_to_next_model": False,
            "role_hint": "slow_macro_sentiment",
            "mechanism": "risk_trim",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": False,
            "main_lesson": "Fear and Greed risk trims did not generalize cleanly to holdout.",
        },
        {
            "version": "V148",
            "title": "Premium basis sentiment overlay",
            "source_report": "reports/RESEARCH_V148_BTCUSDC_PREMIUM_BASIS_SENTIMENT_OVERLAY.md",
            "status": "premium_basis_sentiment_overlay_passed",
            "promoted_to_next_model": True,
            "role_hint": "external_market_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Premium/basis helped when used as short-term positioning context.",
        },
        {
            "version": "V149",
            "title": "Confidence persistence overlay",
            "source_report": "reports/RESEARCH_V149_BTCUSDC_CONFIDENCE_PERSISTENCE_OVERLAY.md",
            "status": "confidence_persistence_overlay_passed",
            "promoted_to_next_model": True,
            "role_hint": "internal_signal_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Internal confidence persistence helped after external context already filtered sizing.",
        },
        {
            "version": "V150",
            "title": "Funding persistence overlay",
            "source_report": "reports/RESEARCH_V150_BTCUSDC_FUNDING_PERSISTENCE_OVERLAY.md",
            "status": "funding_persistence_overlay_passed",
            "promoted_to_next_model": True,
            "role_hint": "external_market_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Longer-horizon funding helped as sizing context, not as a new entry source.",
        },
        {
            "version": "V151",
            "title": "Range alignment overlay",
            "source_report": "reports/RESEARCH_V151_BTCUSDC_RANGE_ALIGNMENT_OVERLAY.md",
            "status": "range_alignment_overlay_passed",
            "promoted_to_next_model": True,
            "role_hint": "price_structure_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Long-horizon range alignment helped avoid weak sizing states.",
        },
        {
            "version": "V152",
            "title": "Short trend activity overlay",
            "source_report": "reports/RESEARCH_V152_BTCUSDC_SHORT_TREND_ACTIVITY_OVERLAY.md",
            "status": "short_trend_activity_overlay_passed",
            "promoted_to_next_model": True,
            "role_hint": "price_structure_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Short-term movement activity helped as a modest sizing layer.",
        },
        {
            "version": "V153",
            "title": "Premium balance overlay",
            "source_report": "reports/RESEARCH_V153_BTCUSDC_PREMIUM_BALANCE_OVERLAY.md",
            "status": "premium_balance_overlay_passed",
            "promoted_to_next_model": True,
            "role_hint": "external_market_condition",
            "mechanism": "boost_and_throttle",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Premium basis worked best as balance: boost calm long premium, throttle weak base-long premium.",
        },
        {
            "version": "V154",
            "title": "Rescue funding stabilizer",
            "source_report": "reports/RESEARCH_V154_BTCUSDC_RESCUE_FUNDING_STABILIZER.md",
            "status": "rescue_funding_stabilizer_passed",
            "promoted_to_next_model": True,
            "role_hint": "external_market_condition",
            "mechanism": "boost_and_stabilizer",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Rescue-long was strongest when funding pressure was not extreme.",
        },
        {
            "version": "V155",
            "title": "Base long premium expansion",
            "source_report": "reports/RESEARCH_V155_BTCUSDC_BASE_LONG_PREMIUM_EXPANSION.md",
            "status": "base_long_premium_expansion_passed",
            "promoted_to_next_model": True,
            "role_hint": "external_market_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Calm-premium base-long states were under-sized.",
        },
        {
            "version": "V156",
            "title": "Base long premium stepup",
            "source_report": "reports/RESEARCH_V156_BTCUSDC_BASE_LONG_PREMIUM_STEPUP.md",
            "status": "base_long_premium_stepup_passed",
            "promoted_to_next_model": True,
            "role_hint": "external_market_condition",
            "mechanism": "sizing_stepup",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "The already-promoted calm-premium base-long flag tolerated a small step-up.",
        },
        {
            "version": "V157",
            "title": "Market condition post-stepup audit",
            "source_report": "reports/RESEARCH_V157_BTCUSDC_MARKET_CONDITION_POST_STEPUP_AUDIT.md",
            "status": "market_condition_overlay_passed",
            "promoted_to_next_model": True,
            "role_hint": "candidate_scan",
            "mechanism": "audit",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Many raw high-return candidates failed risk gates; only strict sizing overlays were safe to consider.",
        },
        {
            "version": "V158",
            "title": "Base range position boost",
            "source_report": "reports/RESEARCH_V158_BTCUSDC_BASE_RANGE_POSITION_BOOST.md",
            "status": "base_range_position_boost_passed",
            "promoted_to_next_model": True,
            "role_hint": "price_structure_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Prior 1440-minute range position helped as a narrow base-trade sizing boost.",
        },
        {
            "version": "V159",
            "title": "Base trend abs boost",
            "source_report": "reports/RESEARCH_V159_BTCUSDC_BASE_TREND_ABS_BOOST.md",
            "status": "base_trend_abs_boost_passed",
            "promoted_to_next_model": True,
            "role_hint": "price_structure_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Large 1440-minute absolute trend move helped as base-trade sizing context.",
        },
        {
            "version": "V160",
            "title": "Base trend abs stepup",
            "source_report": "reports/RESEARCH_V160_BTCUSDC_BASE_TREND_ABS_STEPUP.md",
            "status": "base_trend_abs_stepup_passed",
            "promoted_to_next_model": True,
            "role_hint": "price_structure_condition",
            "mechanism": "sizing_stepup",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "The already-promoted trend-abs flag tolerated a small step-up.",
        },
        {
            "version": "V161",
            "title": "Day sofar count boost",
            "source_report": "reports/RESEARCH_V161_BTCUSDC_DAY_SOFAR_COUNT_BOOST.md",
            "status": "day_sofar_count_boost_passed",
            "promoted_to_next_model": True,
            "role_hint": "intraday_activity_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Earlier-in-day signal sequence states were under-sized.",
        },
        {
            "version": "V162",
            "title": "Long trend follow boost",
            "source_report": "reports/RESEARCH_V162_BTCUSDC_LONG_TREND_FOLLOW_BOOST.md",
            "status": "long_trend_follow_boost_passed",
            "promoted_to_next_model": True,
            "role_hint": "price_structure_condition",
            "mechanism": "sizing_overlay",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": True,
            "main_lesson": "Less-adverse 1440-minute trend helped long trades as sizing context.",
        },
        {
            "version": "V163",
            "title": "Post V162 candidate audit",
            "source_report": "reports/RESEARCH_V163_BTCUSDC_POST_V162_CANDIDATE_AUDIT.md",
            "status": "post_v162_no_clean_candidate",
            "promoted_to_next_model": False,
            "role_hint": "stop_condition",
            "mechanism": "audit",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": False,
            "main_lesson": "No clean independent post-V162 candidate cleared promotion gates.",
        },
        {
            "version": "V164",
            "title": "V162 robustness audit",
            "source_report": "reports/RESEARCH_V164_BTCUSDC_V162_ROBUSTNESS_AUDIT.md",
            "status": "v162_robustness_warning",
            "promoted_to_next_model": False,
            "role_hint": "robustness",
            "mechanism": "robustness_audit",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": False,
            "main_lesson": "The candidate is fragile to realistic extra execution cost.",
        },
        {
            "version": "V165",
            "title": "Cost fragility audit",
            "source_report": "reports/RESEARCH_V165_BTCUSDC_COST_FRAGILITY_AUDIT.md",
            "status": "cost_fragility_warning",
            "promoted_to_next_model": False,
            "role_hint": "execution",
            "mechanism": "execution_risk_audit",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": False,
            "main_lesson": "Some months have very small extra-cost headroom.",
        },
        {
            "version": "V166",
            "title": "Execution budget audit",
            "source_report": "reports/RESEARCH_V166_BTCUSDC_EXECUTION_BUDGET_AUDIT.md",
            "status": "execution_budget_warning",
            "promoted_to_next_model": False,
            "role_hint": "execution",
            "mechanism": "execution_risk_audit",
            "coverage_policy": "full_history",
            "adds_new_trades": False,
            "changes_trade_side": False,
            "uses_holdout_for_thresholds": False,
            "passed_holdout_gate": False,
            "main_lesson": "Six months require maker or otherwise low-cost execution quality under 4 bps taker extra cost.",
        },
    ]
    return pd.DataFrame(rows)


def _classify_roles(catalog: pd.DataFrame) -> pd.DataFrame:
    out = catalog.copy()
    out["direct_entry_allowed"] = False
    out["recommended_role"] = "not_promoted"
    out.loc[out["coverage_policy"].eq("recent_monitoring_only"), "recommended_role"] = "monitor_only"
    out.loc[out["mechanism"].eq("monitor"), "recommended_role"] = "monitor_only"
    out.loc[out["role_hint"].eq("slow_macro_sentiment"), "recommended_role"] = "macro_context_only"
    passed_sizing = (
        out["promoted_to_next_model"].astype(bool)
        & out["passed_holdout_gate"].astype(bool)
        & ~out["adds_new_trades"].astype(bool)
        & ~out["changes_trade_side"].astype(bool)
        & ~out["uses_holdout_for_thresholds"].astype(bool)
        & out["mechanism"].isin(["sizing_overlay", "sizing_stepup", "boost_and_throttle", "boost_and_stabilizer"])
    )
    out.loc[passed_sizing, "recommended_role"] = "sizing_or_risk_governor"
    out.loc[out["role_hint"].eq("candidate_scan"), "recommended_role"] = "candidate_scan_only"
    out.loc[out["role_hint"].eq("stop_condition"), "recommended_role"] = "stop_condition"
    out.loc[out["role_hint"].eq("robustness"), "recommended_role"] = "robustness_gate"
    out.loc[out["role_hint"].eq("execution"), "recommended_role"] = "execution_risk_control"
    out["entry_policy"] = "Do not use as a standalone entry or side signal."
    out.loc[out["recommended_role"].eq("sizing_or_risk_governor"), "entry_policy"] = (
        "May be used only as a small sizing, throttle, or risk governor on already-approved trades."
    )
    out.loc[out["recommended_role"].eq("monitor_only"), "entry_policy"] = (
        "Use only for monitoring until enough history exists for promotion testing."
    )
    out.loc[out["recommended_role"].eq("macro_context_only"), "entry_policy"] = (
        "Use only as slow macro context; do not promote without new robust evidence."
    )
    out.loc[out["recommended_role"].eq("execution_risk_control"), "entry_policy"] = (
        "Use as execution-quality constraint before considering live use."
    )
    return out


def _decision(roles: pd.DataFrame) -> dict[str, object]:
    role_counts = roles["recommended_role"].value_counts().to_dict()
    direct_entry_allowed_count = int(roles["direct_entry_allowed"].astype(bool).sum())
    status = "market_condition_role_audit_passed" if direct_entry_allowed_count == 0 else "market_condition_role_audit_failed"
    return {
        "status": status,
        "promote_to_live": False,
        "message": (
            "Market condition data is useful mainly as sizing, risk, monitoring, or execution context; no direct-entry use is approved."
            if direct_entry_allowed_count == 0
            else "At least one direct-entry role was allowed, which violates the V167 safety rule."
        ),
        "catalog_count": int(len(roles)),
        "direct_entry_allowed_count": direct_entry_allowed_count,
        "sizing_or_risk_governor_count": int(role_counts.get("sizing_or_risk_governor", 0)),
        "monitor_only_count": int(role_counts.get("monitor_only", 0)),
        "macro_context_only_count": int(role_counts.get("macro_context_only", 0)),
        "execution_risk_control_count": int(role_counts.get("execution_risk_control", 0)),
        "not_promoted_count": int(role_counts.get("not_promoted", 0)),
    }


def _write_report(payload: dict[str, object], roles: pd.DataFrame, summary: pd.DataFrame) -> None:
    decision = payload["decision"]
    cols = [
        "version",
        "title",
        "status",
        "recommended_role",
        "entry_policy",
        "main_lesson",
        "source_report",
    ]
    lines = [
        "# Research V167 BTCUSDC Market Condition Role Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Message: {decision['message']}",
        f"- Cataloged research reports: `{decision['catalog_count']}`",
        f"- Direct-entry allowed count: `{decision['direct_entry_allowed_count']}`",
        f"- Sizing / risk governor count: `{decision['sizing_or_risk_governor_count']}`",
        f"- Monitor-only count: `{decision['monitor_only_count']}`",
        f"- Macro-context-only count: `{decision['macro_context_only_count']}`",
        f"- Execution-risk-control count: `{decision['execution_risk_control_count']}`",
        "",
        "## Role Summary",
        "",
        summary.to_csv(index=False).strip(),
        "",
        "## Role Catalog",
        "",
        roles[cols].to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V167 answers the market trend/emotion question by separating data value from data use. The historical evidence does not support using market emotion or trend as a standalone entry or side selector. The evidence is stronger when these fields are used as small sizing overlays, throttles, risk governors, monitoring context, or execution constraints on trades that the base system already wants to take.",
        "",
        "The practical rule is: market trend/emotion can help, but the wrong use is to let it become the main reason to open a trade.",
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    roles = _classify_roles(_research_catalog())
    summary = (
        roles.groupby("recommended_role", dropna=False)
        .agg(
            research_count=("version", "count"),
            promoted_count=("promoted_to_next_model", "sum"),
            direct_entry_allowed_count=("direct_entry_allowed", "sum"),
        )
        .reset_index()
        .sort_values(["direct_entry_allowed_count", "promoted_count", "research_count"], ascending=[False, False, False])
    )
    decision = _decision(roles)
    payload = {
        "config": {
            "base": "v143_to_v166_reports",
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "promotes_live_trading": False,
            "allows_direct_entry_from_market_condition": False,
        },
        "decision": decision,
    }
    roles.to_csv(OUT_DIR / "v167_market_condition_role_catalog.csv", index=False)
    summary.to_csv(OUT_DIR / "v167_market_condition_role_summary.csv", index=False)
    (OUT_DIR / "v167_market_condition_role_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, roles, summary)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
