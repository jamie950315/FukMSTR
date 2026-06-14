from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from lob_microprice_lab.btcusdc_sparse_tp import decide_sparse_tp_promotion


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v67_btcusdc_sparse_tp_route_closure"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V67_SPARSE_TP_ROUTE_CLOSURE.md"

TRUE_REPLAY_SUMMARY = ROOT / "runs" / "research_v26_btcusdc_full_public_replay" / "summary.json"
DOWNLOAD_SUMMARY = ROOT / "runs" / "research_v26_btcusdc_full_download" / "download_summary.json"
V60_SUMMARY = ROOT / "runs" / "research_v60_btcusdc_sparse_tp_design_selector_audit" / "v60_summary.json"
V64_SUMMARY = ROOT / "runs" / "research_v64_btcusdc_sparse_tp_dense_delay_scan" / "v64_summary.json"
V65_SUMMARY = ROOT / "runs" / "research_v65_btcusdc_sparse_tp_signal_fragility_audit" / "v65_summary.json"
V66_SUMMARY = ROOT / "runs" / "research_v66_btcusdc_sparse_tp_design_robust_selector" / "v66_summary.json"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _true_replay_evidence() -> dict[str, object]:
    summary = _load_json(TRUE_REPLAY_SUMMARY)
    aggregate = summary["aggregate"]
    return {
        "summary_path": str(TRUE_REPLAY_SUMMARY),
        "gate_passed": bool(aggregate["gate"]["passed"]),
        "failed_checks": list(aggregate["gate"]["failed_checks"]),
        "trades": int(aggregate["trades"]),
        "win_rate": float(aggregate["selected_trade_win_rate"]),
        "total_bps": float(aggregate["notional_total_net_pnl_bps"]),
        "account_return_pct": float(aggregate["account_return_pct_no_compounding"]),
    }


def _download_evidence() -> dict[str, object]:
    if not DOWNLOAD_SUMMARY.exists():
        return {"summary_path": str(DOWNLOAD_SUMMARY), "available": False}
    summary = _load_json(DOWNLOAD_SUMMARY)
    return {
        "summary_path": str(DOWNLOAD_SUMMARY),
        "available": True,
        "manifest_rows": int(summary.get("manifest_rows", 0)),
        "downloaded_files": int(summary.get("downloaded_files", summary.get("data_done", 0))),
        "linked_existing": int(summary.get("linked_existing", 0)),
        "missing_files": int(summary.get("missing_files", summary.get("failures", 0))),
    }


def _v60_evidence() -> dict[str, object]:
    summary = _load_json(V60_SUMMARY)
    selected = summary["design_selected_rule"]
    fixed = summary["fixed_v55_rule"]
    return {
        "summary_path": str(V60_SUMMARY),
        "design_selected_rule": {
            "direction": selected["direction"],
            "lookback_minutes": int(selected["lookback_minutes"]),
            "quantile": float(selected["quantile"]),
            "design_trades": int(selected["design_trades"]),
            "design_wins": int(selected["design_wins"]),
            "holdout_trades": int(selected["holdout_trades"]),
            "holdout_wins": int(selected["holdout_wins"]),
            "holdout_total_net_pnl_bps": float(selected["holdout_total_net_pnl_bps"]),
        },
        "fixed_v55_rule": {
            "design_rank": int(fixed["rank_design_total_net_pnl"]),
            "holdout_trades": int(fixed["holdout_trades"]),
            "holdout_wins": int(fixed["holdout_wins"]),
        },
    }


def _v64_evidence() -> dict[str, object]:
    summary = _load_json(V64_SUMMARY)
    return {
        "summary_path": str(V64_SUMMARY),
        "delay_count": int(summary["delay_count"]),
        "passing_delay_count": int(summary["passing_delay_count"]),
        "failing_delay_count": int(summary["failing_delay_count"]),
        "pass_rate": float(summary["pass_rate"]),
        "worst_delay_by_account_return": int(summary["worst_delay_by_account_return"]),
        "worst_account_return_pct": float(summary["worst_account_return_pct"]),
    }


def _v65_evidence() -> dict[str, object]:
    summary = _load_json(V65_SUMMARY)
    top = summary["top_fragile_signal"]
    return {
        "summary_path": str(V65_SUMMARY),
        "signal_count": int(summary["signal_count"]),
        "signals_with_loss_count": int(summary["signals_with_loss_count"]),
        "total_losing_signal_delay_rows": int(summary["total_losing_signal_delay_rows"]),
        "failed_delay_losing_rows": int(summary["failed_delay_losing_rows"]),
        "top_fragile_signal": {
            "fold": int(top["fold"]),
            "signal_idx": int(top["signal_idx"]),
            "signal_timestamp": str(top["signal_timestamp"]),
            "signal": int(top["signal"]),
            "loss_delay_count": int(top["loss_delay_count"]),
            "loss_delay_ranges": str(top["loss_delay_ranges"]),
            "worst_final_net_pnl_bps": float(top["worst_final_net_pnl_bps"]),
        },
    }


def _v66_evidence() -> dict[str, object]:
    summary = _load_json(V66_SUMMARY)
    selected = summary["design_robust_selected_rule"]
    return {
        "summary_path": str(V66_SUMMARY),
        "selected_same_as_v60": bool(summary["selected_same_as_v60"]),
        "design_robust_selected_rule": {
            "direction": selected["direction"],
            "lookback_minutes": int(selected["lookback_minutes"]),
            "quantile": float(selected["quantile"]),
            "design_pass_count": int(selected["pass_count"]),
            "delay_count": int(selected["delay_count"]),
            "fail_delay_ranges": str(selected["fail_delay_ranges"]),
        },
        "selected_holdout_pass_count": int(summary["selected_holdout_pass_count"]),
        "selected_holdout_fail_ranges": str(summary["selected_holdout_fail_ranges"]),
        "v60_holdout_pass_count": int(summary["v60_holdout_pass_count"]),
        "v60_holdout_fail_ranges": str(summary["v60_holdout_fail_ranges"]),
        "delay_count": int(summary["delay_count"]),
    }


def _write_report(payload: dict[str, object]) -> None:
    true_replay = payload["true_replay"]
    v60 = payload["v60_design_selector"]
    v64 = payload["v64_dense_delay"]
    v65 = payload["v65_signal_fragility"]
    v66 = payload["v66_design_robust_selector"]
    decision = payload["decision"]
    lines = [
        "# Research V67 Sparse TP Route Closure",
        "",
        "## Decision",
        "",
        f"- Promote sparse TP route: `{decision['promote_sparse_tp']}`",
        f"- Status: `{decision['status']}`",
        f"- Primary reasons: `{';'.join(decision['primary_reasons'])}`",
        "",
        "## Evidence",
        "",
        "### V26 True BTCUSDC Replay",
        "",
        f"- Gate passed: `{true_replay['gate_passed']}`",
        f"- Trades: `{true_replay['trades']}`",
        f"- Win rate: `{float(true_replay['win_rate']):.6f}`",
        f"- Total net pnl: `{float(true_replay['total_bps']):.6f}` bps",
        f"- Account return: `{float(true_replay['account_return_pct']):.6f}%`",
        f"- Failed checks: `{';'.join(true_replay['failed_checks'])}`",
        "",
        "### V60 Design-Selected Sparse TP",
        "",
        f"- Rule: `{v60['design_selected_rule']['direction']} / {v60['design_selected_rule']['lookback_minutes']}m / q{v60['design_selected_rule']['quantile']}`",
        f"- Design trades/wins: `{v60['design_selected_rule']['design_trades']}/{v60['design_selected_rule']['design_wins']}`",
        f"- Holdout trades/wins: `{v60['design_selected_rule']['holdout_trades']}/{v60['design_selected_rule']['holdout_wins']}`",
        f"- Holdout total net pnl: `{float(v60['design_selected_rule']['holdout_total_net_pnl_bps']):.6f}` bps",
        "",
        "### V64 Holdout Dense Delay",
        "",
        f"- Passing delays: `{v64['passing_delay_count']}/{v64['delay_count']}`",
        f"- Failing delays: `{v64['failing_delay_count']}`",
        f"- Worst delay by account return: `{v64['worst_delay_by_account_return']}`",
        f"- Worst account return: `{float(v64['worst_account_return_pct']):.6f}%`",
        "",
        "### V65 Signal Fragility",
        "",
        f"- Signals with loss: `{v65['signals_with_loss_count']}/{v65['signal_count']}`",
        f"- Losing signal-delay rows: `{v65['total_losing_signal_delay_rows']}`",
        f"- Top fragile signal: `{v65['top_fragile_signal']['signal_timestamp']}`",
        f"- Top fragile loss ranges: `{v65['top_fragile_signal']['loss_delay_ranges']}`",
        f"- Top fragile worst pnl: `{float(v65['top_fragile_signal']['worst_final_net_pnl_bps']):.6f}` bps",
        "",
        "### V66 Design-Robust Selector",
        "",
        f"- Selected same as V60: `{v66['selected_same_as_v60']}`",
        f"- Selected rule: `{v66['design_robust_selected_rule']['direction']} / {v66['design_robust_selected_rule']['lookback_minutes']}m / q{v66['design_robust_selected_rule']['quantile']}`",
        f"- Selected design pass count: `{v66['design_robust_selected_rule']['design_pass_count']}/{v66['design_robust_selected_rule']['delay_count']}`",
        f"- Selected holdout pass count: `{v66['selected_holdout_pass_count']}/{v66['delay_count']}`",
        f"- Selected holdout fail ranges: `{v66['selected_holdout_fail_ranges']}`",
        f"- V60 reference holdout pass count: `{v66['v60_holdout_pass_count']}/{v66['delay_count']}`",
        f"- V60 reference fail ranges: `{v66['v60_holdout_fail_ranges']}`",
        "",
        "## Closure",
        "",
        "The BTCUSDC sparse TP route is closed as not promotable under the current evidence. The route has historical pockets of success, but fails true replay, fails dense delay robustness, and the design-only robust selector does not produce a holdout-valid replacement.",
        "",
        "## Files",
        "",
        f"- Summary JSON: `{payload['summary_json']}`",
        f"- Decision CSV: `{payload['decision_csv']}`",
        f"- Source true replay: `{true_replay['summary_path']}`",
        f"- Source V64: `{v64['summary_path']}`",
        f"- Source V66: `{v66['summary_path']}`",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    true_replay = _true_replay_evidence()
    v64 = _v64_evidence()
    v66 = _v66_evidence()
    decision = decide_sparse_tp_promotion(
        true_replay_gate_passed=bool(true_replay["gate_passed"]),
        v60_holdout_dense_pass_count=int(v64["passing_delay_count"]),
        v60_holdout_dense_delay_count=int(v64["delay_count"]),
        design_robust_holdout_pass_count=int(v66["selected_holdout_pass_count"]),
        design_robust_holdout_delay_count=int(v66["delay_count"]),
    )
    payload: dict[str, object] = {
        "version": "v67_btcusdc_sparse_tp_route_closure",
        "download": _download_evidence(),
        "true_replay": true_replay,
        "v60_design_selector": _v60_evidence(),
        "v64_dense_delay": v64,
        "v65_signal_fragility": _v65_evidence(),
        "v66_design_robust_selector": v66,
        "decision": decision,
        "summary_json": str(OUT_DIR / "v67_summary.json"),
        "decision_csv": str(OUT_DIR / "v67_sparse_tp_route_decision.csv"),
        "report": str(REPORT_PATH),
    }
    (OUT_DIR / "v67_summary.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    pd.DataFrame([{**decision, "primary_reasons": ";".join(decision["primary_reasons"])}]).to_csv(OUT_DIR / "v67_sparse_tp_route_decision.csv", index=False)
    _write_report(payload)
    print(json.dumps(payload, indent=2, default=str))
