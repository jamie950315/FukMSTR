from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v166_execution_budget_audit as v166


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v168_execution_readiness_gate"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V168_BTCUSDC_EXECUTION_READINESS_GATE.md"
V166_BUDGET_PATH = ROOT / "runs" / "research_v166_execution_budget_audit" / "v166_execution_budget_taker4bps.csv"
MAKER_ONLY_REQUIRED_SHARE = 0.80
MAKER_PRIORITY_REQUIRED_SHARE = 0.50


def _readiness_gate(budget: pd.DataFrame) -> pd.DataFrame:
    out = budget.copy()
    required = pd.to_numeric(out["required_maker_share"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    max_taker = pd.to_numeric(out["max_taker_share"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    out["required_maker_share"] = required
    out["max_taker_share"] = max_taker
    out["execution_readiness_mode"] = "taker_allowed"
    out["live_gate_action"] = "normal_cost_monitoring"
    out.loc[(required > 0.0) & (required < MAKER_PRIORITY_REQUIRED_SHARE), "execution_readiness_mode"] = (
        "mixed_execution_allowed"
    )
    out.loc[(required > 0.0) & (required < MAKER_PRIORITY_REQUIRED_SHARE), "live_gate_action"] = "cap_taker_share"
    out.loc[
        (required >= MAKER_PRIORITY_REQUIRED_SHARE) & (required < MAKER_ONLY_REQUIRED_SHARE),
        "execution_readiness_mode",
    ] = "maker_priority_required"
    out.loc[
        (required >= MAKER_PRIORITY_REQUIRED_SHARE) & (required < MAKER_ONLY_REQUIRED_SHARE),
        "live_gate_action",
    ] = "prefer_maker_or_skip"
    out.loc[required >= MAKER_ONLY_REQUIRED_SHARE, "execution_readiness_mode"] = "maker_only_required"
    out.loc[required >= MAKER_ONLY_REQUIRED_SHARE, "live_gate_action"] = "block_taker_execution"
    no_headroom = out["execution_budget_tag"].eq("no_cost_headroom") if "execution_budget_tag" in out else pd.Series(False, index=out.index)
    out.loc[no_headroom, "execution_readiness_mode"] = "no_trade_unless_cost_improves"
    out.loc[no_headroom, "live_gate_action"] = "skip_until_edge_or_cost_improves"
    out["max_taker_share_pct"] = out["max_taker_share"] * 100.0
    out["required_maker_share_pct"] = out["required_maker_share"] * 100.0
    return out


def _decision(gate: pd.DataFrame) -> dict[str, object]:
    modes = gate["execution_readiness_mode"].value_counts().to_dict()
    maker_only = int(modes.get("maker_only_required", 0))
    maker_priority = int(modes.get("maker_priority_required", 0))
    no_trade = int(modes.get("no_trade_unless_cost_improves", 0))
    strictest_required = float(pd.to_numeric(gate["required_maker_share"], errors="coerce").max()) if not gate.empty else 0.0
    strictest_month = ""
    if not gate.empty and "month" in gate:
        strictest_month = str(gate.sort_values("required_maker_share", ascending=False).iloc[0]["month"])
    passed = maker_only == 0 and no_trade == 0
    return {
        "status": "execution_readiness_passed" if passed else "execution_readiness_warning",
        "promote_to_live": False,
        "message": (
            "No month requires maker-only execution under the current gate."
            if passed
            else "Some months require maker-only or skip-if-not-maker execution before any live use."
        ),
        "month_count": int(len(gate)),
        "maker_only_required_month_count": maker_only,
        "maker_priority_required_month_count": maker_priority,
        "mixed_execution_allowed_month_count": int(modes.get("mixed_execution_allowed", 0)),
        "taker_allowed_month_count": int(modes.get("taker_allowed", 0)),
        "no_trade_unless_cost_improves_month_count": no_trade,
        "strictest_month": strictest_month,
        "strictest_required_maker_share": strictest_required,
    }


def _payload_for_gate(gate: pd.DataFrame) -> dict[str, object]:
    return {
        "config": {
            "base": "v166_execution_budget_taker4bps",
            "maker_only_required_share": MAKER_ONLY_REQUIRED_SHARE,
            "maker_priority_required_share": MAKER_PRIORITY_REQUIRED_SHARE,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "promotes_live_trading": False,
        },
        "decision": _decision(gate),
    }


def _write_report(payload: dict[str, object], gate: pd.DataFrame, summary: pd.DataFrame) -> None:
    decision = payload["decision"]
    cols = [
        "month",
        "execution_readiness_mode",
        "live_gate_action",
        "max_taker_share_pct",
        "required_maker_share_pct",
        "breakeven_extra_cost_bps",
        "base_return_pct",
        "trade_count",
    ]
    lines = [
        "# Research V168 BTCUSDC Execution Readiness Gate",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Message: {decision['message']}",
        f"- Maker-only required months: `{decision['maker_only_required_month_count']}`",
        f"- Maker-priority required months: `{decision['maker_priority_required_month_count']}`",
        f"- Mixed execution allowed months: `{decision['mixed_execution_allowed_month_count']}`",
        f"- Taker allowed months: `{decision['taker_allowed_month_count']}`",
        f"- Strictest month: `{decision['strictest_month']}`",
        f"- Strictest required maker share: `{decision['strictest_required_maker_share']}`",
        "",
        "## Gate Rules",
        "",
        f"- `required_maker_share >= {MAKER_ONLY_REQUIRED_SHARE}`: maker-only required; taker execution should be blocked.",
        f"- `{MAKER_PRIORITY_REQUIRED_SHARE} <= required_maker_share < {MAKER_ONLY_REQUIRED_SHARE}`: maker-priority required; skip if maker or low-cost execution is unavailable.",
        f"- `0 < required_maker_share < {MAKER_PRIORITY_REQUIRED_SHARE}`: mixed execution allowed, but taker share must be capped.",
        "- `required_maker_share == 0`: normal cost monitoring.",
        "- This gate does not add trades, change sides, change strategy thresholds, or promote live trading.",
        "",
        "## Mode Summary",
        "",
        summary.to_csv(index=False).strip(),
        "",
        "## Monthly Readiness Gate",
        "",
        gate[cols].to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V168 turns V166 cost budgets into execution actions. The most fragile months should not be traded with mostly-taker fills. If maker or otherwise low-cost execution cannot be verified, those months should be treated as not ready for live use.",
        "",
        "This is a research execution gate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V166_BUDGET_PATH.exists():
        v166.run()
    budget = pd.read_csv(V166_BUDGET_PATH)
    gate = _readiness_gate(budget).sort_values("required_maker_share", ascending=False).reset_index(drop=True)
    summary = (
        gate.groupby(["execution_readiness_mode", "live_gate_action"], dropna=False)
        .agg(
            month_count=("month", "count"),
            avg_required_maker_share_pct=("required_maker_share_pct", "mean"),
            max_required_maker_share_pct=("required_maker_share_pct", "max"),
        )
        .reset_index()
        .sort_values("max_required_maker_share_pct", ascending=False)
    )
    payload = _payload_for_gate(gate)
    gate.to_csv(OUT_DIR / "v168_execution_readiness_gate.csv", index=False)
    summary.to_csv(OUT_DIR / "v168_execution_readiness_summary.csv", index=False)
    (OUT_DIR / "v168_execution_readiness_gate_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, gate, summary)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
