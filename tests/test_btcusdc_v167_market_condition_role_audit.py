from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v167_market_condition_role_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v167_market_condition_role_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v167_classifies_market_condition_roles_without_direct_entry_promotion() -> None:
    module = _load_module()
    rows = pd.DataFrame(
        [
            {
                "version": "V144",
                "promoted_to_next_model": True,
                "role_hint": "external_market_condition",
                "mechanism": "sizing_overlay",
                "coverage_policy": "full_history",
                "adds_new_trades": False,
                "changes_trade_side": False,
                "uses_holdout_for_thresholds": False,
                "passed_holdout_gate": True,
            },
            {
                "version": "V145",
                "promoted_to_next_model": False,
                "role_hint": "derivatives_positioning",
                "mechanism": "monitor",
                "coverage_policy": "recent_monitoring_only",
                "adds_new_trades": False,
                "changes_trade_side": False,
                "uses_holdout_for_thresholds": False,
                "passed_holdout_gate": False,
            },
        ]
    )

    out = module._classify_roles(rows)

    assert out.loc[out["version"].eq("V144"), "recommended_role"].item() == "sizing_or_risk_governor"
    assert out.loc[out["version"].eq("V145"), "recommended_role"].item() == "monitor_only"
    assert out["direct_entry_allowed"].sum() == 0


def test_v167_decision_requires_no_direct_entry_and_warns_live_use() -> None:
    module = _load_module()
    roles = pd.DataFrame(
        {
            "recommended_role": ["sizing_or_risk_governor", "monitor_only", "not_promoted"],
            "direct_entry_allowed": [False, False, False],
            "promoted_to_next_model": [True, False, False],
        }
    )

    decision = module._decision(roles)

    assert decision["status"] == "market_condition_role_audit_passed"
    assert decision["promote_to_live"] is False
    assert decision["direct_entry_allowed_count"] == 0
    assert decision["sizing_or_risk_governor_count"] == 1


def test_v167_built_catalog_marks_slow_macro_sentiment_as_not_promoted() -> None:
    module = _load_module()

    roles = module._classify_roles(module._research_catalog())
    fng = roles.loc[roles["version"].isin(["V146", "V147"])]

    assert set(fng["recommended_role"]) == {"macro_context_only"}
    assert not bool(fng["direct_entry_allowed"].any())
