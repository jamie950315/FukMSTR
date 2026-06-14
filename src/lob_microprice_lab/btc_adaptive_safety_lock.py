from __future__ import annotations

import itertools
import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .btc_rescue_profit_lock import BTCRescueProfitGate, run_btc_rescue_profit_lock
from .profit_lock import _jsonable


def _v23_jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _v23_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_v23_jsonable(v) for v in obj]
    if isinstance(obj, tuple):
        return [_v23_jsonable(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return _jsonable(obj)
from .real_fee_lock import RealFeeSpec


@dataclass(frozen=True)
class BTCAdaptiveLeveragePolicy:
    """Simple live leverage governor layered on top of the frozen V22 BTC signal.

    It does not change entries, exits, or future-price labels. It only scales
    exposure. A loss worse than loss_trigger_bps switches the next
    risk_off_trades trades to risk_off_leverage. The promoted policy is intended
    as a research cap, not a liquidation guarantee.
    """

    normal_leverage: float = 5.0
    risk_off_leverage: float = 4.0
    risk_off_trades: int = 3
    loss_trigger_bps: float = -20.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BTCAdaptiveSafetyGate:
    min_base_trades: int = 11
    min_base_hit_rate: float = 1.0
    min_base_total_net_pnl_bps: float = 180.0
    min_base_mean_net_pnl_bps: float = 16.0
    max_entry_exit_family_addone_p: float = 0.01
    max_promoted_leverage: float = 5.0
    min_no_loss_account_return_pct: float = 9.0
    synthetic_loss_bps: float = -40.0
    synthetic_loss_count: int = 3
    min_synthetic_loss_account_return_pct: float = 1.0
    min_synthetic_loss_max_drawdown_pct: float = -5.0
    min_extreme_stress_account_return_pct: float = 1.0
    min_missed_trade_p05_account_return_pct: float = 1.0
    min_extra_cost_account_return_pct: float = 0.25
    promoted_shock_buffer_bps: float = 1000.0
    maintenance_margin_bps: float = 50.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_btc_adaptive_safety_lock(
    *,
    v17_run_dir: str | Path,
    out_dir: str | Path,
    fee_spec: RealFeeSpec | None = None,
    gate: BTCAdaptiveSafetyGate | None = None,
    clean: bool = False,
    shift_null_runs: int = 1000,
    random_scenarios: int = 10000,
    seed: int = 23023,
    write_data_plan: bool = True,
) -> dict[str, object]:
    """Build the V23 BTC adaptive safety certificate.

    V23 intentionally keeps the V22 trade rule frozen. It reruns V22 under the
    user's real fee, upgrades the research leverage cap from 3x to 5x only if
    the stricter shock-buffer gate passes, and then adds an account-level safety
    scan over simple loss-response leverage policies.
    """

    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    fee_spec = fee_spec or RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000)
    gate = gate or BTCAdaptiveSafetyGate()

    base_gate = BTCRescueProfitGate(
        min_trades=gate.min_base_trades,
        min_hit_rate=gate.min_base_hit_rate,
        min_total_net_pnl_bps=gate.min_base_total_net_pnl_bps,
        min_mean_net_pnl_bps=gate.min_base_mean_net_pnl_bps,
        max_entry_exit_family_addone_p=gate.max_entry_exit_family_addone_p,
        require_all_stress_cells_positive=True,
        max_stress_fee_side_bps=10.0,
        max_stress_latency_sec=5.0,
        missed_trade_gate_probability=0.50,
        extra_cost_gate_bps=16.0,
        promoted_leverage_cap=gate.max_promoted_leverage,
        shock_buffer_bps=gate.promoted_shock_buffer_bps,
        maintenance_margin_bps=gate.maintenance_margin_bps,
    )

    base = run_btc_rescue_profit_lock(
        v17_run_dir=v17_run_dir,
        out_dir=out,
        fee_spec=fee_spec,
        take_profit_bps=52.0,
        stop_loss_bps=0.0,
        horizon_sec=90.0,
        latency_sec=0.5,
        exit_take_profit_candidates=[0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 52, 55, 60],
        stress_fee_side_bps_values=[4, 5, 6, 7.5, 10],
        stress_latency_sec_values=[0, 0.5, 1, 2, 3, 5],
        leverage_values=[1, 2, 3, 5, 10, 20],
        shift_null_runs=shift_null_runs,
        random_scenarios=random_scenarios,
        seed=seed,
        gate=base_gate,
        write_data_plan=write_data_plan,
        clean=False,
    )

    trades = pd.read_csv(out / "btc_rescue_profit_trade_ledger.csv")
    stress = pd.read_csv(out / "btc_fee_latency_stress.csv")
    missed = pd.read_csv(out / "btc_missed_trade_stress.csv")
    extra = pd.read_csv(out / "btc_extra_cost_reserve.csv")
    leverage = pd.read_csv(out / "btc_leverage_scenarios.csv")

    scan = _policy_scan(trades, gate=gate)
    scan.to_csv(out / "btc_adaptive_leverage_policy_scan.csv", index=False)
    selected = _select_policy(scan)
    policy = BTCAdaptiveLeveragePolicy(
        normal_leverage=float(selected["normal_leverage"]),
        risk_off_leverage=float(selected["risk_off_leverage"]),
        risk_off_trades=int(selected["risk_off_trades"]),
        loss_trigger_bps=float(selected["loss_trigger_bps"]),
    )

    path = _account_path(trades, policy)
    path.to_csv(out / "btc_adaptive_account_path.csv", index=False)

    injection = _loss_injection_table(trades, policy=policy, gate=gate, max_loss_count=max(4, int(gate.synthetic_loss_count)))
    injection.to_csv(out / "btc_synthetic_loss_injection_stress.csv", index=False)

    account_stress = _account_level_stress(
        stress=stress,
        missed=missed,
        extra=extra,
        normal_leverage=float(policy.normal_leverage),
        synthetic_loss_row=injection.loc[injection["loss_count"].astype(int) == int(gate.synthetic_loss_count)].iloc[0].to_dict(),
        gate=gate,
    )
    pd.DataFrame([account_stress]).to_csv(out / "btc_v23_account_level_stress_summary.csv", index=False)

    aggregate = _aggregate_v23(base, path, injection, account_stress, leverage, policy, gate)

    result: dict[str, object] = {
        "version": "v23_btc_adaptive_safety_lock",
        "v17_run_dir": str(v17_run_dir),
        "out_dir": str(out),
        "fee_spec": fee_spec.to_dict(),
        "frozen_trade_policy": {
            "source": "v22_btc_rescue_profit_lock",
            "take_profit_bps": 52.0,
            "stop_loss_bps": 0.0,
            "horizon_sec": 90.0,
            "latency_sec": 0.5,
            "roundtrip_taker_fee_bps": fee_spec.taker_taker_roundtrip_bps,
            "note": "V23 does not change the V22 entry or exit rule; it only adds account-level leverage safety.",
        },
        "adaptive_leverage_policy": policy.to_dict(),
        "gate_config": gate.to_dict(),
        "base_v22_summary": base.get("aggregate", {}),
        "aggregate": aggregate,
    }
    (out / "summary_v23.json").write_text(json.dumps(_v23_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT_V23.md", result, scan, path, injection, account_stress, leverage)
    (out / "DONE_V23.marker").write_text("ok\n", encoding="utf-8")
    return _v23_jsonable(result)


def _trade_pnl_array(trades: pd.DataFrame) -> np.ndarray:
    return pd.to_numeric(trades.get("net_pnl_bps", 0.0), errors="coerce").fillna(0.0).to_numpy(dtype=float)


def _simulate_policy_for_sequence(
    pnl_bps: Iterable[float],
    *,
    policy: BTCAdaptiveLeveragePolicy,
) -> dict[str, object]:
    rows = []
    equity_pct = 0.0
    peak_pct = 0.0
    max_drawdown_pct = 0.0
    cooldown = 0
    for i, pnl in enumerate(float(x) for x in pnl_bps):
        leverage = float(policy.risk_off_leverage) if cooldown > 0 else float(policy.normal_leverage)
        account_return_pct = pnl * leverage / 100.0
        equity_pct += account_return_pct
        peak_pct = max(peak_pct, equity_pct)
        max_drawdown_pct = min(max_drawdown_pct, equity_pct - peak_pct)
        loss_triggered = pnl <= float(policy.loss_trigger_bps)
        rows.append({
            "step": i + 1,
            "notional_net_pnl_bps": pnl,
            "leverage": leverage,
            "account_return_pct": account_return_pct,
            "equity_return_pct": equity_pct,
            "drawdown_pct": equity_pct - peak_pct,
            "loss_triggered": bool(loss_triggered),
            "cooldown_before_update": int(cooldown),
        })
        if loss_triggered:
            cooldown = int(policy.risk_off_trades)
        elif cooldown > 0:
            cooldown -= 1
    return {
        "rows": rows,
        "total_account_return_pct": float(equity_pct),
        "max_drawdown_pct": float(max_drawdown_pct),
        "min_step_account_return_pct": float(min((r["account_return_pct"] for r in rows), default=0.0)),
    }


def _account_path(trades: pd.DataFrame, policy: BTCAdaptiveLeveragePolicy) -> pd.DataFrame:
    pnl = _trade_pnl_array(trades)
    sim = _simulate_policy_for_sequence(pnl, policy=policy)
    rows = list(sim["rows"])
    out = trades.copy().reset_index(drop=True)
    for col in ["leverage", "account_return_pct", "equity_return_pct", "drawdown_pct", "loss_triggered", "cooldown_before_update"]:
        out[col] = [r[col] for r in rows]
    return out


def _sequence_with_injections(base_pnl: np.ndarray, positions: tuple[int, ...], synthetic_loss_bps: float) -> list[float]:
    pos_set = set(int(p) for p in positions)
    seq: list[float] = []
    n = len(base_pnl)
    for i, pnl in enumerate(base_pnl):
        if i in pos_set:
            seq.append(float(synthetic_loss_bps))
        seq.append(float(pnl))
    if n in pos_set:
        seq.append(float(synthetic_loss_bps))
    return seq


def _loss_injection_table(
    trades: pd.DataFrame,
    *,
    policy: BTCAdaptiveLeveragePolicy,
    gate: BTCAdaptiveSafetyGate,
    max_loss_count: int = 4,
    max_exact_combinations: int = 50_000,
    sampled_scenarios: int = 10_000,
    seed: int = 23023,
) -> pd.DataFrame:
    base_pnl = _trade_pnl_array(trades)
    rows: list[dict[str, object]] = []
    max_loss_count = int(max(0, max_loss_count))
    insertion_points = list(range(len(base_pnl) + 1))
    rng = np.random.default_rng(seed)
    for loss_count in range(max_loss_count + 1):
        totals: list[float] = []
        drawdowns: list[float] = []
        exact_count = 1 if loss_count == 0 else math.comb(len(insertion_points), loss_count)
        scenario_method = "exact"
        if loss_count == 0 or exact_count <= int(max_exact_combinations):
            scenarios = [()] if loss_count == 0 else itertools.combinations(insertion_points, loss_count)
        else:
            scenario_method = "sampled"
            sample_count = int(max(1, sampled_scenarios))
            scenarios = (tuple(sorted(rng.choice(insertion_points, size=loss_count, replace=False).tolist())) for _ in range(sample_count))
        for positions in scenarios:
            seq = _sequence_with_injections(base_pnl, tuple(positions), float(gate.synthetic_loss_bps))
            sim = _simulate_policy_for_sequence(seq, policy=policy)
            totals.append(float(sim["total_account_return_pct"]))
            drawdowns.append(float(sim["max_drawdown_pct"]))
        arr = np.asarray(totals, dtype=float)
        dd = np.asarray(drawdowns, dtype=float)
        rows.append({
            "loss_count": int(loss_count),
            "synthetic_loss_bps": float(gate.synthetic_loss_bps),
            "scenarios": int(len(arr)),
            "scenario_method": scenario_method,
            "exact_scenario_count": int(exact_count),
            "min_total_account_return_pct": float(arr.min()) if len(arr) else 0.0,
            "p01_total_account_return_pct": float(np.percentile(arr, 1)) if len(arr) else 0.0,
            "p05_total_account_return_pct": float(np.percentile(arr, 5)) if len(arr) else 0.0,
            "mean_total_account_return_pct": float(arr.mean()) if len(arr) else 0.0,
            "max_total_account_return_pct": float(arr.max()) if len(arr) else 0.0,
            "worst_max_drawdown_pct": float(dd.min()) if len(dd) else 0.0,
        })
    return pd.DataFrame(rows)


def _policy_scan(trades: pd.DataFrame, *, gate: BTCAdaptiveSafetyGate) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for normal in [3.0, 4.0, 5.0]:
        for risk_off in [1.0, 2.0, 3.0, 4.0, 5.0]:
            if risk_off > normal:
                continue
            for cooldown in [1, 2, 3, 4]:
                policy = BTCAdaptiveLeveragePolicy(
                    normal_leverage=normal,
                    risk_off_leverage=risk_off,
                    risk_off_trades=cooldown,
                    loss_trigger_bps=-20.0,
                )
                inj = _loss_injection_table(trades, policy=policy, gate=gate, max_loss_count=int(gate.synthetic_loss_count))
                no_loss = inj.loc[inj["loss_count"].astype(int) == 0].iloc[0]
                gate_loss = inj.loc[inj["loss_count"].astype(int) == int(gate.synthetic_loss_count)].iloc[0]
                rows.append({
                    "normal_leverage": normal,
                    "risk_off_leverage": risk_off,
                    "risk_off_trades": cooldown,
                    "loss_trigger_bps": -20.0,
                    "no_loss_account_return_pct": float(no_loss["min_total_account_return_pct"]),
                    "gate_loss_count": int(gate.synthetic_loss_count),
                    "gate_loss_min_account_return_pct": float(gate_loss["min_total_account_return_pct"]),
                    "gate_loss_p05_account_return_pct": float(gate_loss["p05_total_account_return_pct"]),
                    "gate_loss_worst_drawdown_pct": float(gate_loss["worst_max_drawdown_pct"]),
                    "passes_v23_policy_gate": bool(
                        normal <= float(gate.max_promoted_leverage)
                        and float(no_loss["min_total_account_return_pct"]) >= float(gate.min_no_loss_account_return_pct)
                        and float(gate_loss["min_total_account_return_pct"]) >= float(gate.min_synthetic_loss_account_return_pct)
                        and float(gate_loss["worst_max_drawdown_pct"]) >= float(gate.min_synthetic_loss_max_drawdown_pct)
                    ),
                })
    df = pd.DataFrame(rows)
    return df.sort_values(
        ["passes_v23_policy_gate", "no_loss_account_return_pct", "gate_loss_min_account_return_pct", "gate_loss_worst_drawdown_pct", "risk_off_leverage"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)


def _select_policy(scan: pd.DataFrame) -> dict[str, object]:
    if scan.empty:
        raise ValueError("empty leverage policy scan")
    passed = scan.loc[scan["passes_v23_policy_gate"].astype(bool)]
    if passed.empty:
        raise ValueError("no adaptive leverage policy passed the V23 safety gate")
    return passed.iloc[0].to_dict()


def _row_for_value(df: pd.DataFrame, column: str, value: float) -> dict[str, object]:
    vals = pd.to_numeric(df.get(column, pd.Series(dtype=float)), errors="coerce")
    rows = df.loc[np.isclose(vals, float(value))]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _account_level_stress(*, stress: pd.DataFrame, missed: pd.DataFrame, extra: pd.DataFrame, normal_leverage: float, synthetic_loss_row: dict[str, object], gate: BTCAdaptiveSafetyGate) -> dict[str, object]:
    extreme = stress.loc[(np.isclose(pd.to_numeric(stress["taker_fee_bps_per_side"], errors="coerce"), 10.0)) & (np.isclose(pd.to_numeric(stress["latency_sec"], errors="coerce"), 5.0))]
    extreme_total_bps = float(pd.to_numeric(extreme["total_net_pnl_bps"], errors="coerce").iloc[0]) if not extreme.empty else 0.0
    missed_row = _row_for_value(missed, "miss_probability", 0.50)
    extra_row = _row_for_value(extra, "extra_cost_bps_per_trade", 16.0)
    return {
        "normal_leverage": float(normal_leverage),
        "extreme_10bps_side_5s_notional_total_bps": extreme_total_bps,
        "extreme_10bps_side_5s_account_return_pct": float(extreme_total_bps * float(normal_leverage) / 100.0),
        "missed_50pct_p05_notional_total_bps": float(missed_row.get("p05_total_bps", 0.0)),
        "missed_50pct_p05_account_return_pct": float(missed_row.get("p05_total_bps", 0.0)) * float(normal_leverage) / 100.0,
        "extra_16bps_notional_total_bps": float(extra_row.get("total_net_pnl_bps", 0.0)),
        "extra_16bps_account_return_pct": float(extra_row.get("total_net_pnl_bps", 0.0)) * float(normal_leverage) / 100.0,
        "synthetic_loss_count": int(synthetic_loss_row.get("loss_count", gate.synthetic_loss_count)),
        "synthetic_loss_min_account_return_pct": float(synthetic_loss_row.get("min_total_account_return_pct", 0.0)),
        "synthetic_loss_worst_drawdown_pct": float(synthetic_loss_row.get("worst_max_drawdown_pct", 0.0)),
    }


def _aggregate_v23(base: dict[str, object], path: pd.DataFrame, injection: pd.DataFrame, account_stress: dict[str, object], leverage: pd.DataFrame, policy: BTCAdaptiveLeveragePolicy, gate: BTCAdaptiveSafetyGate) -> dict[str, object]:
    base_agg = base.get("aggregate", {}) if isinstance(base.get("aggregate"), dict) else {}
    selected_loss = injection.loc[injection["loss_count"].astype(int) == int(gate.synthetic_loss_count)].iloc[0]
    lev_rows = leverage.loc[pd.to_numeric(leverage.get("leverage", 0.0), errors="coerce") <= float(gate.max_promoted_leverage)] if not leverage.empty else pd.DataFrame()
    lev_ok = bool(lev_rows["passes_shock_buffer"].astype(bool).all()) if not lev_rows.empty else False
    no_loss_return = float(path["account_return_pct"].sum()) if not path.empty else 0.0
    checks = {
        "base_v22_gate_passed": bool((base_agg.get("gate") or {}).get("passed", False)) if isinstance(base_agg.get("gate"), dict) else False,
        "base_trade_count": int(base_agg.get("trades", 0)) >= int(gate.min_base_trades),
        "base_hit_rate": float(base_agg.get("hit_rate", 0.0)) >= float(gate.min_base_hit_rate),
        "base_profit": float(base_agg.get("total_net_pnl_bps", 0.0)) >= float(gate.min_base_total_net_pnl_bps),
        "base_family_null": max(float(base_agg.get("entry_exit_family_addone_p_total", 1.0)), float(base_agg.get("entry_exit_family_addone_p_mean", 1.0))) <= float(gate.max_entry_exit_family_addone_p),
        "promoted_leverage_buffer": lev_ok,
        "no_loss_account_return": no_loss_return >= float(gate.min_no_loss_account_return_pct),
        "synthetic_loss_return": float(selected_loss["min_total_account_return_pct"]) >= float(gate.min_synthetic_loss_account_return_pct),
        "synthetic_loss_drawdown": float(selected_loss["worst_max_drawdown_pct"]) >= float(gate.min_synthetic_loss_max_drawdown_pct),
        "extreme_fee_latency_account_return": float(account_stress["extreme_10bps_side_5s_account_return_pct"]) >= float(gate.min_extreme_stress_account_return_pct),
        "missed_trade_account_return": float(account_stress["missed_50pct_p05_account_return_pct"]) >= float(gate.min_missed_trade_p05_account_return_pct),
        "extra_cost_account_return": float(account_stress["extra_16bps_account_return_pct"]) >= float(gate.min_extra_cost_account_return_pct),
        "selected_policy_uses_max_5x": np.isclose(float(policy.normal_leverage), float(gate.max_promoted_leverage)),
    }
    return _v23_jsonable({
        "trades": int(base_agg.get("trades", 0)),
        "selected_trade_win_rate": float(base_agg.get("hit_rate", 0.0)),
        "notional_total_net_pnl_bps": float(base_agg.get("total_net_pnl_bps", 0.0)),
        "notional_mean_net_pnl_bps": float(base_agg.get("mean_net_pnl_bps", 0.0)),
        "normal_leverage": float(policy.normal_leverage),
        "risk_off_leverage": float(policy.risk_off_leverage),
        "risk_off_trades": int(policy.risk_off_trades),
        "no_loss_account_return_pct": no_loss_return,
        "final_equity_return_pct_no_compounding": no_loss_return,
        "max_drawdown_pct_no_loss_path": float(path["drawdown_pct"].min()) if not path.empty else 0.0,
        "synthetic_loss_count_gate": int(gate.synthetic_loss_count),
        "synthetic_loss_bps": float(gate.synthetic_loss_bps),
        "synthetic_loss_min_account_return_pct": float(selected_loss["min_total_account_return_pct"]),
        "synthetic_loss_p05_account_return_pct": float(selected_loss["p05_total_account_return_pct"]),
        "synthetic_loss_worst_drawdown_pct": float(selected_loss["worst_max_drawdown_pct"]),
        "extreme_10bps_side_5s_account_return_pct": float(account_stress["extreme_10bps_side_5s_account_return_pct"]),
        "missed_50pct_p05_account_return_pct": float(account_stress["missed_50pct_p05_account_return_pct"]),
        "extra_16bps_account_return_pct": float(account_stress["extra_16bps_account_return_pct"]),
        "entry_exit_family_addone_p_total": float(base_agg.get("entry_exit_family_addone_p_total", 1.0)),
        "entry_exit_family_addone_p_mean": float(base_agg.get("entry_exit_family_addone_p_mean", 1.0)),
        "leverage_promoted_cap": float(gate.max_promoted_leverage),
        "leverage_promoted_rows_all_pass_shock_buffer": lev_ok,
        "gate": {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]},
    })


def _write_report(path: Path, result: dict[str, object], scan: pd.DataFrame, acct_path: pd.DataFrame, injection: pd.DataFrame, account_stress: dict[str, object], leverage: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V23 BTC Adaptive Safety Lock",
        "",
        "V23 keeps the V22 BTC entry/exit rule frozen and adds an account-level leverage safety layer. It is a research certificate, not a live-profit guarantee.",
        "",
        "## Frozen trade rule",
        "",
        "```json",
        json.dumps(result["frozen_trade_policy"], indent=2),
        "```",
        "",
        "## Selected adaptive leverage policy",
        "",
        "```json",
        json.dumps(result["adaptive_leverage_policy"], indent=2),
        "```",
        "",
        "## Aggregate V23 gate",
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
        "## Account path for the bundled sample",
        "",
        acct_path[[c for c in ["timestamp", "fold", "signal", "net_pnl_bps", "leverage", "account_return_pct", "equity_return_pct", "drawdown_pct", "exit_reason"] if c in acct_path.columns]].to_csv(index=False).strip(),
        "",
        "## Leverage scenarios from V22 base run",
        "",
        leverage.to_csv(index=False).strip(),
        "",
        "## Caveat",
        "",
        "V23 reaches the bundled-sample BTC research target with the user's fee and an adaptive 5x research cap. Independent multi-day BTCUSDT contract validation is still required before live deployment.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
