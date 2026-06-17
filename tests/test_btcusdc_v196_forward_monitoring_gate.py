from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_btcusdc_v196_forward_monitoring_gate.py"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "configs" / "btcusdc_v224_forward_freeze_manifest.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_btcusdc_v196_forward_monitoring_gate", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest_kwargs() -> dict[str, str]:
    module = _load_module()
    return {
        "forward_freeze_manifest_path": str(MANIFEST_PATH),
        "forward_freeze_manifest_hash": module._file_sha256(MANIFEST_PATH),
    }


def test_v196_forward_window_uses_only_rows_after_freeze_timestamp() -> None:
    module = _load_module()
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-06-09T16:40:00Z",
                    "2026-06-09T16:45:00Z",
                    "2026-06-10T00:00:00Z",
                ],
                utc=True,
            ),
            "v193_account_return_pct": [10.0, 2.0, -1.0],
            "v194_account_return_pct": [11.0, 3.0, -2.0],
            "v193_account_pnl_bps": [1000.0, 200.0, -100.0],
            "v194_account_pnl_bps": [1100.0, 300.0, -200.0],
        }
    )

    forward = module._forward_monitoring_table(frame, freeze_timestamp=pd.Timestamp("2026-06-09T16:40:00Z"))

    v193 = forward.loc[forward["version"].eq("V193")].iloc[0]
    v194 = forward.loc[forward["version"].eq("V194")].iloc[0]
    assert v193["forward_trade_count"] == 2
    assert v193["forward_return_pct"] == 1.0
    assert v193["forward_win_rate_pct"] == 50.0
    assert v194["forward_return_pct"] == 1.0
    assert v194["forward_win_rate_pct"] == 50.0


def test_v196_payload_blocks_forward_claim_when_no_new_rows_exist() -> None:
    module = _load_module()
    forward_table = pd.DataFrame(
        {
            "version": ["V193", "V194"],
            "forward_trade_count": [0, 0],
            "forward_return_pct": [0.0, 0.0],
            "forward_win_rate_pct": [0.0, 0.0],
        }
    )

    payload = module._payload_for_monitoring(
        forward_table,
        latest_timestamp="2026-06-09 16:40:00+00:00",
        **_manifest_kwargs(),
    )

    assert payload["decision"]["status"] == "no_forward_evidence"
    assert payload["decision"]["forward_evidence_available"] is False
    assert payload["decision"]["allow_historical_optimization"] is False
    assert payload["decision"]["promote_to_live"] is False


def test_v196_payload_blocks_forward_claim_without_freeze_manifest() -> None:
    module = _load_module()
    forward_table = pd.DataFrame(
        {
            "version": ["V193", "V194"],
            "forward_trade_count": [5, 5],
            "forward_return_pct": [1.0, 2.0],
            "forward_win_rate_pct": [60.0, 60.0],
        }
    )

    payload = module._payload_for_monitoring(forward_table, latest_timestamp="2026-06-10 00:00:00+00:00")

    assert payload["decision"]["status"] == "forward_freeze_manifest_missing"
    assert payload["decision"]["forward_evidence_available"] is False
    assert payload["decision"]["allow_historical_optimization"] is False


def test_v196_metrics_table_keeps_v193_v194_comparison() -> None:
    module = _load_module()
    version_metrics = pd.DataFrame(
        {
            "version": ["V193", "V194"],
            "account_return_pct": [3950.66, 4044.70],
            "improvement_pct": ["-", 94.04],
            "max_drawdown_pct": [-30.20, -30.20],
            "positive_months": ["24/24", "24/24"],
            "holdout_return_pct": [1386.21, 1452.80],
            "holdout_months": ["6/6", "6/6"],
        }
    )

    markdown = module._metrics_table_markdown(version_metrics)

    assert "| Account return estimate | +3950.66% | +4044.70% |" in markdown
    assert "| Improvement | - | +94.04 percentage points |" in markdown
    assert "| Holdout months | 6/6 | 6/6 |" in markdown
