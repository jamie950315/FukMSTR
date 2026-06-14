from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_independent_validation import summarize_cost_delay_surface


ROOT = Path(__file__).resolve().parents[1]
V71_DIR = ROOT / "runs" / "research_v71_btcusdc_fixed_flow_dense_delay_stress"
V70_SUMMARY = ROOT / "runs" / "research_v70_btcusdc_fixed_flow_extended_validation" / "v70_summary.json"
V71_SUMMARY = V71_DIR / "v71_summary.json"
OUT_DIR = ROOT / "runs" / "research_v72_btcusdc_fixed_flow_cost_delay_contract"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V72_FIXED_FLOW_COST_DELAY_CONTRACT_RESULTS.md"

EXTRA_COST_BPS = (0.0, 2.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0, 32.0)
MAX_DELAY_MINUTES = (0, 1, 2, 5, 10, 15, 30, 45, 60, 75, 90, 120)
CONTRACT_MAX_DELAY_MINUTES = 60
CONTRACT_EXTRA_COST_BPS = 16.0


def _load_trades(path: Path) -> pd.DataFrame:
    trades = pd.read_csv(path)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    trades["entry_delay_minutes"] = pd.to_numeric(trades["entry_delay_minutes"], errors="coerce").astype("Int64")
    return trades.dropna(subset=["entry_delay_minutes"]).copy()


def _row_passed(rows: pd.DataFrame, *, max_delay: int, extra_cost: float) -> bool:
    match = rows.loc[
        (pd.to_numeric(rows["max_delay_minutes"], errors="coerce").astype(int) == int(max_delay))
        & (pd.to_numeric(rows["extra_cost_bps"], errors="coerce").astype(float) == float(extra_cost))
    ]
    return bool((not match.empty) and bool(match.iloc[0]["passed"]))


def _write_report(payload: dict[str, object], surface: pd.DataFrame) -> None:
    decision = payload["decision"]
    signal = payload["cost_delay_surface"]["signal_hour"]["aggregate"]
    entry = payload["cost_delay_surface"]["entry_hour"]["aggregate"]
    lines = [
        "# Research V72 Fixed Flow Cost Delay Contract Results",
        "",
        "## Decision",
        "",
        f"- Execution contract found: `{decision['execution_contract_found']}`",
        f"- Stronger validation promoted: `{decision['stronger_validation_promoted']}`",
        f"- Failed stricter checks: `{';'.join(decision['failed_stricter_checks'])}`",
        "",
        "## Candidate Contract",
        "",
        f"- Gate mode: `signal_hour`",
        f"- Max entry delay: `{CONTRACT_MAX_DELAY_MINUTES}` minutes",
        f"- Extra cost: `{CONTRACT_EXTRA_COST_BPS}` bps per trade",
        "",
        "## Surface Aggregates",
        "",
        f"- Signal-hour best passed max delay: `{signal['best_passed_max_delay_minutes']}` minutes",
        f"- Signal-hour best passed extra cost: `{signal['best_passed_extra_cost_bps']}` bps",
        f"- Signal-hour best passed worst delay total: `{signal['best_passed_worst_delay_total_net_pnl_bps']}` bps",
        f"- Entry-hour best passed max delay: `{entry['best_passed_max_delay_minutes']}` minutes",
        f"- Entry-hour best passed extra cost: `{entry['best_passed_extra_cost_bps']}` bps",
        "",
        "## Cost Delay Surface",
        "",
        surface.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V72 keeps the V68 candidate and V69 locked hour gate unchanged. It tests whether execution remains positive when extra cost is added on top of the existing fee while entry is delayed. A signal-hour execution contract can be stated, but this does not remove the V70/V71 monthly stability failure.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    v70 = json.loads(V70_SUMMARY.read_text(encoding="utf-8"))
    v71 = json.loads(V71_SUMMARY.read_text(encoding="utf-8"))
    surfaces: dict[str, object] = {}
    surface_frames: list[pd.DataFrame] = []
    for gate_mode in ("signal_hour", "entry_hour"):
        trades = _load_trades(V71_DIR / f"v71_dense_delay_{gate_mode}_gated_ledgers.csv")
        result = summarize_cost_delay_surface(
            trades,
            extra_cost_bps=EXTRA_COST_BPS,
            max_delay_minutes=MAX_DELAY_MINUTES,
            delay_col="entry_delay_minutes",
            min_positive_delay_rate=0.80,
            min_worst_delay_total_net_pnl_bps=0.0,
        )
        frame = pd.DataFrame(result["rows"])
        frame.insert(0, "gate_mode", gate_mode)
        frame.to_csv(OUT_DIR / f"v72_cost_delay_surface_{gate_mode}.csv", index=False)
        surfaces[gate_mode] = result
        surface_frames.append(frame)

    surface = pd.concat(surface_frames, ignore_index=True) if surface_frames else pd.DataFrame()
    surface.to_csv(OUT_DIR / "v72_cost_delay_surface.csv", index=False)

    signal_rows = surface.loc[surface["gate_mode"] == "signal_hour"].copy()
    entry_rows = surface.loc[surface["gate_mode"] == "entry_hour"].copy()
    signal_contract_passed = _row_passed(signal_rows, max_delay=CONTRACT_MAX_DELAY_MINUTES, extra_cost=CONTRACT_EXTRA_COST_BPS)
    signal_full_120_cost16_passed = _row_passed(signal_rows, max_delay=120, extra_cost=CONTRACT_EXTRA_COST_BPS)
    entry_contract_passed = _row_passed(entry_rows, max_delay=CONTRACT_MAX_DELAY_MINUTES, extra_cost=CONTRACT_EXTRA_COST_BPS)
    month_positive_rate = float(v70["decision"]["month_positive_rate"])
    quarter_positive_rate = float(v70["decision"]["quarter_positive_rate"])
    stricter_checks = {
        "v69_locked_gate_passed": bool(v71["decision"]["v69_retained"]),
        "signal_hour_contract_delay60_cost16_passed": bool(signal_contract_passed),
        "signal_hour_full_delay120_cost16_passed": bool(signal_full_120_cost16_passed),
        "entry_hour_contract_delay60_cost16_passed": bool(entry_contract_passed),
        "month_positive_rate_ge_0p60": month_positive_rate >= 0.60,
        "quarter_positive_rate_ge_0p75": quarter_positive_rate >= 0.75,
    }
    failed = [name for name, passed in stricter_checks.items() if not passed]
    decision = {
        "execution_contract_found": bool(signal_contract_passed),
        "stronger_validation_promoted": bool(not failed),
        "stricter_checks": stricter_checks,
        "failed_stricter_checks": failed,
        "contract_gate_mode": "signal_hour",
        "contract_max_delay_minutes": int(CONTRACT_MAX_DELAY_MINUTES),
        "contract_extra_cost_bps": float(CONTRACT_EXTRA_COST_BPS),
        "month_positive_rate": month_positive_rate,
        "quarter_positive_rate": quarter_positive_rate,
    }
    payload = {
        "version": "v72_btcusdc_fixed_flow_cost_delay_contract",
        "source_v70_summary": str(V70_SUMMARY),
        "source_v71_summary": str(V71_SUMMARY),
        "extra_cost_bps": list(EXTRA_COST_BPS),
        "max_delay_minutes": list(MAX_DELAY_MINUTES),
        "decision": decision,
        "cost_delay_surface": surfaces,
        "outputs": {
            "summary_json": str(OUT_DIR / "v72_summary.json"),
            "cost_delay_surface": str(OUT_DIR / "v72_cost_delay_surface.csv"),
            "report": str(REPORT_PATH),
        },
    }
    (OUT_DIR / "v72_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, surface)
    print(json.dumps(payload, indent=2, default=str))
