from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from .btc_adaptive_exit_lock import BTCAdaptiveExitGate, run_btc_adaptive_exit_lock
from .btc_adaptive_safety_lock import (
    BTCAdaptiveSafetyGate,
    _account_level_stress,
    _account_path,
    _aggregate_v23,
    _loss_injection_table,
    _policy_scan,
    _select_policy,
    _v23_jsonable,
    BTCAdaptiveLeveragePolicy,
)
from .real_fee_lock import RealFeeSpec


def run_btc_adaptive_exit_safety_lock(
    *,
    v17_run_dir: str | Path,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    gate: BTCAdaptiveSafetyGate | None = None,
    clean: bool = False,
    shift_null_runs: int = 1000,
    random_scenarios: int = 10000,
    seed: int = 24024,
    write_data_plan: bool = True,
) -> dict[str, object]:
    """V24 certificate: V24 adaptive exit plus strict 5x safety layer.

    Entries remain the frozen V22 BTC entries. V24 adaptive take-profit ladder
    is kept, then V24 adds an account-level leverage governor and synthetic loss
    stress. No new entry signals are introduced here.
    """

    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    fee_spec = fee_spec or RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000)
    gate = gate or BTCAdaptiveSafetyGate(
        max_promoted_leverage=5.0,
        min_no_loss_account_return_pct=9.5,
        min_synthetic_loss_account_return_pct=1.25,
        min_synthetic_loss_max_drawdown_pct=-5.0,
        min_extreme_stress_account_return_pct=1.5,
        min_missed_trade_p05_account_return_pct=1.25,
        min_extra_cost_account_return_pct=0.5,
        promoted_shock_buffer_bps=1000.0,
    )

    base = run_btc_adaptive_exit_lock(
        v17_run_dir=v17_run_dir,
        out_dir=out,
        fee_spec=fee_spec,
        horizon_sec=90.0,
        latency_sec=0.5,
        stress_fee_side_bps_values=[4, 5, 6, 7.5, 10],
        stress_latency_sec_values=[0, 0.5, 1, 2, 3, 5],
        leverage_values=[1, 2, 3, 5, 10, 20],
        shift_null_runs=shift_null_runs,
        random_scenarios=random_scenarios,
        seed=seed,
        gate=BTCAdaptiveExitGate(
            min_trades=gate.min_base_trades,
            min_hit_rate=gate.min_base_hit_rate,
            min_total_net_pnl_bps=185.0,
            min_mean_net_pnl_bps=17.0,
            max_entry_exit_family_addone_p=gate.max_entry_exit_family_addone_p,
            require_all_stress_cells_positive=True,
            max_stress_fee_side_bps=10.0,
            max_stress_latency_sec=5.0,
            missed_trade_gate_probability=0.50,
            extra_cost_gate_bps=16.0,
            promoted_leverage_cap=gate.max_promoted_leverage,
            shock_buffer_bps=gate.promoted_shock_buffer_bps,
            maintenance_margin_bps=gate.maintenance_margin_bps,
        ),
        write_data_plan=write_data_plan,
        clean=False,
    )

    trades = pd.read_csv(out / "btc_adaptive_exit_trade_ledger.csv")
    stress = pd.read_csv(out / "btc_adaptive_fee_latency_stress.csv")
    missed = pd.read_csv(out / "btc_adaptive_missed_trade_stress.csv")
    extra = pd.read_csv(out / "btc_adaptive_extra_cost_reserve.csv")
    leverage = pd.read_csv(out / "btc_adaptive_leverage_scenarios.csv")

    scan = _policy_scan(trades, gate=gate)
    scan.to_csv(out / "btc_v24_adaptive_leverage_policy_scan.csv", index=False)
    selected = _select_policy(scan)
    policy = BTCAdaptiveLeveragePolicy(
        normal_leverage=float(selected["normal_leverage"]),
        risk_off_leverage=float(selected["risk_off_leverage"]),
        risk_off_trades=int(selected["risk_off_trades"]),
        loss_trigger_bps=float(selected["loss_trigger_bps"]),
    )
    path = _account_path(trades, policy)
    path.to_csv(out / "btc_v24_adaptive_account_path.csv", index=False)
    injection = _loss_injection_table(trades, policy=policy, gate=gate, max_loss_count=max(4, int(gate.synthetic_loss_count)))
    injection.to_csv(out / "btc_v24_synthetic_loss_injection_stress.csv", index=False)
    loss_row = injection.loc[injection["loss_count"].astype(int) == int(gate.synthetic_loss_count)].iloc[0].to_dict()
    account_stress = _account_level_stress(stress=stress, missed=missed, extra=extra, normal_leverage=float(policy.normal_leverage), synthetic_loss_row=loss_row, gate=gate)
    pd.DataFrame([account_stress]).to_csv(out / "btc_v24_account_level_stress_summary.csv", index=False)

    aggregate = _aggregate_v23(base, path, injection, account_stress, leverage, policy, gate)
    result = {
        "version": "v24_btc_adaptive_exit_safety_lock",
        "v17_run_dir": str(v17_run_dir),
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "frozen_trade_policy": {
            "source": "v22 entries plus v24 adaptive exit ladder",
            "horizon_sec": 90.0,
            "latency_sec": 0.5,
            "roundtrip_taker_fee_bps": fee_spec.taker_taker_roundtrip_bps,
            "entry_note": "No V24 entry changes; entries are inherited from the V22 BTC rescue rule.",
            "exit_note": "V24 adaptive take-profit ladder is inherited unchanged.",
        },
        "adaptive_leverage_policy": policy.to_dict(),
        "gate_config": gate.to_dict(),
        "base_v24_adaptive_exit_summary": base.get("aggregate", {}),
        "aggregate": aggregate,
    }
    (out / "summary_v24.json").write_text(json.dumps(_v23_jsonable(result), indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(_v23_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT_V24.md", result, scan, path, injection, account_stress, leverage)
    _write_report(out / "REPORT.md", result, scan, path, injection, account_stress, leverage)
    (out / "DONE_V24.marker").write_text("ok\n", encoding="utf-8")
    return _v23_jsonable(result)


def _write_report(path: Path, result: dict[str, object], scan: pd.DataFrame, acct_path: pd.DataFrame, injection: pd.DataFrame, account_stress: dict[str, object], leverage: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V24 BTC Adaptive Exit + Safety Lock",
        "",
        "V24 keeps the V22 BTC entries and V24 adaptive exit ladder frozen, then adds a 5x account-level safety certificate.",
        "",
        "## Frozen trade policy",
        "",
        "```json",
        json.dumps(result["frozen_trade_policy"], indent=2),
        "```",
        "",
        "## Selected leverage safety policy",
        "",
        "```json",
        json.dumps(result["adaptive_leverage_policy"], indent=2),
        "```",
        "",
        "## Aggregate V24 gate",
        "",
        "```json",
        json.dumps(_v23_jsonable(agg), indent=2),
        "```",
        "",
        "## Account-level stress summary",
        "",
        pd.DataFrame([account_stress]).to_csv(index=False).strip(),
        "",
        "## Synthetic loss injection stress",
        "",
        injection.to_csv(index=False).strip(),
        "",
        "## Adaptive leverage policy scan",
        "",
        scan.head(40).to_csv(index=False).strip(),
        "",
        "## Account path",
        "",
        acct_path[[c for c in ["timestamp", "fold", "signal", "net_pnl_bps", "take_profit_bps", "exit_reason", "leverage", "account_return_pct", "equity_return_pct", "drawdown_pct"] if c in acct_path.columns]].to_csv(index=False).strip(),
        "",
        "## Leverage scenarios from V24 adaptive exit base run",
        "",
        leverage.to_csv(index=False).strip(),
        "",
        "## Caveat",
        "",
        "V24 is the strongest bundled-sample BTC research certificate so far, but independent multi-day BTCUSDT contract validation is still required before live use.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
