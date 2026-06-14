from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_btcusdc_v165_cost_fragility_audit as v165


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v166_execution_budget_audit"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V166_BTCUSDC_EXECUTION_BUDGET_AUDIT.md"
V165_MONTHLY_PATH = ROOT / "runs" / "research_v165_cost_fragility_audit" / "v165_monthly_cost_fragility.csv"
TAKER_EXTRA_COST_BPS = 4.0
SECONDARY_TAKER_EXTRA_COST_BPS = 2.0


def _execution_budget(monthly: pd.DataFrame, *, taker_extra_cost_bps: float = TAKER_EXTRA_COST_BPS) -> pd.DataFrame:
    out = monthly.copy()
    breakeven = pd.to_numeric(out["breakeven_extra_cost_bps"], errors="coerce").fillna(0.0)
    raw_share = breakeven / float(taker_extra_cost_bps)
    out["taker_extra_cost_bps"] = float(taker_extra_cost_bps)
    out["max_taker_share"] = raw_share.clip(lower=0.0, upper=1.0)
    out["required_maker_share"] = 1.0 - out["max_taker_share"]
    out["execution_budget_tag"] = "taker_ok"
    out.loc[(breakeven > 0.0) & (breakeven < float(taker_extra_cost_bps)), "execution_budget_tag"] = "maker_required"
    out.loc[breakeven <= 0.0, "execution_budget_tag"] = "no_cost_headroom"
    return out


def _decision(budget: pd.DataFrame, *, taker_extra_cost_bps: float = TAKER_EXTRA_COST_BPS) -> dict[str, object]:
    maker_required = budget.loc[budget["execution_budget_tag"].eq("maker_required")].copy()
    no_headroom = budget.loc[budget["execution_budget_tag"].eq("no_cost_headroom")].copy()
    minimum_share = float(pd.to_numeric(budget["max_taker_share"], errors="coerce").min()) if not budget.empty else 0.0
    passed = maker_required.empty and no_headroom.empty
    strictest = budget.sort_values("max_taker_share", ascending=True).iloc[0].to_dict() if not budget.empty else {}
    return {
        "status": "execution_budget_passed" if passed else "execution_budget_warning",
        "promote_to_live": False,
        "message": (
            "Every month can tolerate the modeled taker extra cost."
            if passed
            else "Some months require maker or low-cost execution to stay above their breakeven cost budget."
        ),
        "taker_extra_cost_bps": float(taker_extra_cost_bps),
        "month_count": int(len(budget)),
        "maker_required_month_count": int(len(maker_required)),
        "no_cost_headroom_month_count": int(len(no_headroom)),
        "minimum_max_taker_share": minimum_share,
        "strictest_month": str(strictest.get("month", "")),
        "strictest_required_maker_share": float(strictest.get("required_maker_share", 0.0)) if strictest else 0.0,
    }


def _write_report(
    payload: dict[str, object],
    primary_budget: pd.DataFrame,
    secondary_budget: pd.DataFrame,
) -> None:
    decision = payload["decision"]
    report_cols = [
        "month",
        "breakeven_extra_cost_bps",
        "taker_extra_cost_bps",
        "max_taker_share",
        "required_maker_share",
        "base_return_pct",
        "trade_count",
        "cost_fragility_tag",
        "execution_budget_tag",
    ]
    maker_required = primary_budget.loc[primary_budget["execution_budget_tag"].ne("taker_ok")].copy()
    lines = [
        "# Research V166 BTCUSDC Execution Budget Audit",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Promote to live: `{decision['promote_to_live']}`",
        f"- Message: {decision['message']}",
        f"- Modeled taker extra cost: `{TAKER_EXTRA_COST_BPS}` bps",
        f"- Maker-required months: `{decision['maker_required_month_count']}` / `{decision['month_count']}`",
        f"- Minimum max taker share: `{decision['minimum_max_taker_share']}`",
        f"- Strictest month: `{decision['strictest_month']}`",
        "",
        "## Audit Rules",
        "",
        "- Base input: V165 monthly cost fragility table.",
        "- `max_taker_share = min(1, breakeven_extra_cost_bps / taker_extra_cost_bps)`.",
        "- `required_maker_share = 1 - max_taker_share`.",
        "- This audit converts cost fragility into execution-quality budgets. It does not add trades, change sides, or promote live trading.",
        "",
        "## Primary Execution Budget",
        "",
        primary_budget[report_cols].to_csv(index=False).strip(),
        "",
        f"## Secondary Execution Budget ({SECONDARY_TAKER_EXTRA_COST_BPS:g} bps taker extra cost)",
        "",
        secondary_budget[report_cols].to_csv(index=False).strip(),
        "",
        "## Maker-Required Months",
        "",
        maker_required[report_cols].to_csv(index=False).strip() if not maker_required.empty else "No month requires maker execution under the modeled cost.",
        "",
        "## Interpretation",
        "",
        "V166 translates the V165 cost fragility into execution requirements. The strictest months cannot tolerate mostly-taker execution; they require very high maker or otherwise low-cost fill quality before any live use should be considered.",
        "",
        "This is a research audit, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not V165_MONTHLY_PATH.exists():
        v165.run()
    monthly = pd.read_csv(V165_MONTHLY_PATH)
    primary_budget = _execution_budget(monthly, taker_extra_cost_bps=TAKER_EXTRA_COST_BPS)
    secondary_budget = _execution_budget(monthly, taker_extra_cost_bps=SECONDARY_TAKER_EXTRA_COST_BPS)
    primary_budget = primary_budget.sort_values("max_taker_share", ascending=True).reset_index(drop=True)
    secondary_budget = secondary_budget.sort_values("max_taker_share", ascending=True).reset_index(drop=True)
    decision = _decision(primary_budget, taker_extra_cost_bps=TAKER_EXTRA_COST_BPS)
    payload = {
        "config": {
            "base": "v165_cost_fragility_audit",
            "taker_extra_cost_bps": TAKER_EXTRA_COST_BPS,
            "secondary_taker_extra_cost_bps": SECONDARY_TAKER_EXTRA_COST_BPS,
            "adds_new_trades": False,
            "changes_existing_threshold": False,
            "promotes_live_trading": False,
        },
        "decision": decision,
    }
    primary_budget.to_csv(OUT_DIR / "v166_execution_budget_taker4bps.csv", index=False)
    secondary_budget.to_csv(OUT_DIR / "v166_execution_budget_taker2bps.csv", index=False)
    (OUT_DIR / "v166_execution_budget_audit_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, primary_budget, secondary_budget)
    return payload


def main() -> None:
    payload = run()
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
