from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_adaptive_safety_lock import (
    BTCAdaptiveLeveragePolicy,
    BTCAdaptiveSafetyGate,
    _account_level_stress,
    _account_path,
    _loss_injection_table,
    _v23_jsonable,
)
from .profit_lock import _jsonable


@dataclass(frozen=True)
class BTCFourLossSafetyGate:
    """V25 capital safety gate for the frozen BTC trade rule.

    V25 does not alter entries or exits. It chooses a safer account-level
    leverage response after a severe realized loss. The promoted target is to
    keep the 5x normal research cap while surviving four injected -40 bps
    notional failures on every insertion pattern in the bundled ledger.
    """

    min_base_trades: int = 11
    min_base_hit_rate: float = 1.0
    min_base_total_net_pnl_bps: float = 185.0
    min_base_mean_net_pnl_bps: float = 17.0
    max_entry_exit_family_addone_p: float = 0.01
    normal_leverage_required: float = 5.0
    synthetic_loss_bps: float = -40.0
    promoted_loss_count: int = 4
    warning_loss_count: int = 5
    min_no_loss_account_return_pct: float = 9.5
    min_four_loss_account_return_pct: float = 0.0
    min_four_loss_p05_account_return_pct: float = 0.0
    min_four_loss_max_drawdown_pct: float = -5.25
    min_extreme_stress_account_return_pct: float = 1.5
    min_missed_trade_p05_account_return_pct: float = 1.25
    min_extra_cost_account_return_pct: float = 0.5

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _load_v24_summary(v24_run_dir: Path) -> dict[str, object]:
    for name in ["summary_v24.json", "summary.json"]:
        path = v24_run_dir / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"No v24 summary found in {v24_run_dir}")


def _base_metric(base_agg: dict[str, object], preferred: str, fallback: str | None = None, default: float = 0.0) -> float:
    if preferred in base_agg:
        try:
            return float(base_agg.get(preferred, default))
        except (TypeError, ValueError):
            return float(default)
    if fallback is not None and fallback in base_agg:
        try:
            return float(base_agg.get(fallback, default))
        except (TypeError, ValueError):
            return float(default)
    return float(default)


def _scan_four_loss_policies(trades: pd.DataFrame, *, gate: BTCFourLossSafetyGate) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    synthetic_gate = BTCAdaptiveSafetyGate(
        synthetic_loss_bps=float(gate.synthetic_loss_bps),
        synthetic_loss_count=int(gate.promoted_loss_count),
    )
    normal_values = [3.0, 4.0, 5.0]
    risk_values = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    cooldown_values = [1, 2, 3, 4, 5, 6, 8, 10]
    for normal in normal_values:
        for risk_off in risk_values:
            if risk_off > normal:
                continue
            for cooldown in cooldown_values:
                policy = BTCAdaptiveLeveragePolicy(
                    normal_leverage=float(normal),
                    risk_off_leverage=float(risk_off),
                    risk_off_trades=int(cooldown),
                    loss_trigger_bps=-20.0,
                )
                inj = _loss_injection_table(
                    trades,
                    policy=policy,
                    gate=synthetic_gate,
                    max_loss_count=max(int(gate.promoted_loss_count), int(gate.warning_loss_count)),
                )
                no_loss = inj.loc[inj["loss_count"].astype(int) == 0].iloc[0]
                promoted = inj.loc[inj["loss_count"].astype(int) == int(gate.promoted_loss_count)].iloc[0]
                warning = inj.loc[inj["loss_count"].astype(int) == int(gate.warning_loss_count)].iloc[0]
                passes = bool(
                    np.isclose(float(normal), float(gate.normal_leverage_required))
                    and float(no_loss["min_total_account_return_pct"]) >= float(gate.min_no_loss_account_return_pct)
                    and float(promoted["min_total_account_return_pct"]) > float(gate.min_four_loss_account_return_pct)
                    and float(promoted["p05_total_account_return_pct"]) > float(gate.min_four_loss_p05_account_return_pct)
                    and float(promoted["worst_max_drawdown_pct"]) >= float(gate.min_four_loss_max_drawdown_pct)
                )
                rows.append({
                    "normal_leverage": float(normal),
                    "risk_off_leverage": float(risk_off),
                    "risk_off_trades": int(cooldown),
                    "loss_trigger_bps": -20.0,
                    "no_loss_account_return_pct": float(no_loss["min_total_account_return_pct"]),
                    "promoted_loss_count": int(gate.promoted_loss_count),
                    "promoted_loss_min_account_return_pct": float(promoted["min_total_account_return_pct"]),
                    "promoted_loss_p01_account_return_pct": float(promoted["p01_total_account_return_pct"]),
                    "promoted_loss_p05_account_return_pct": float(promoted["p05_total_account_return_pct"]),
                    "promoted_loss_worst_drawdown_pct": float(promoted["worst_max_drawdown_pct"]),
                    "warning_loss_count": int(gate.warning_loss_count),
                    "warning_loss_min_account_return_pct": float(warning["min_total_account_return_pct"]),
                    "warning_loss_p05_account_return_pct": float(warning["p05_total_account_return_pct"]),
                    "warning_loss_worst_drawdown_pct": float(warning["worst_max_drawdown_pct"]),
                    "passes_v25_four_loss_gate": passes,
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(
        [
            "passes_v25_four_loss_gate",
            "normal_leverage",
            "no_loss_account_return_pct",
            "promoted_loss_worst_drawdown_pct",
            "promoted_loss_min_account_return_pct",
            "risk_off_leverage",
            "risk_off_trades",
        ],
        ascending=[False, False, False, False, False, False, False],
    ).reset_index(drop=True)


def _select_four_loss_policy(scan: pd.DataFrame) -> BTCAdaptiveLeveragePolicy:
    if scan.empty:
        raise ValueError("empty V25 policy scan")
    passed = scan.loc[scan["passes_v25_four_loss_gate"].astype(bool)]
    if passed.empty:
        raise ValueError("no V25 four-loss safety policy passed")
    row = passed.iloc[0]
    return BTCAdaptiveLeveragePolicy(
        normal_leverage=float(row["normal_leverage"]),
        risk_off_leverage=float(row["risk_off_leverage"]),
        risk_off_trades=int(row["risk_off_trades"]),
        loss_trigger_bps=float(row["loss_trigger_bps"]),
    )


def _base_gate_passed(base_agg: dict[str, object]) -> bool:
    gate = base_agg.get("gate") if isinstance(base_agg.get("gate"), dict) else {}
    return bool(gate.get("passed", False))


def _aggregate_v25(
    *,
    base_summary: dict[str, object],
    selected_policy: BTCAdaptiveLeveragePolicy,
    path: pd.DataFrame,
    injection: pd.DataFrame,
    account_stress: dict[str, object],
    gate: BTCFourLossSafetyGate,
) -> dict[str, object]:
    base_agg = base_summary.get("aggregate", {}) if isinstance(base_summary.get("aggregate"), dict) else {}
    promoted = injection.loc[injection["loss_count"].astype(int) == int(gate.promoted_loss_count)].iloc[0]
    warning = injection.loc[injection["loss_count"].astype(int) == int(gate.warning_loss_count)].iloc[0]
    no_loss_return = float(path["account_return_pct"].sum()) if not path.empty else 0.0
    hit_rate = _base_metric(base_agg, "hit_rate", "selected_trade_win_rate")
    total_pnl = _base_metric(base_agg, "total_net_pnl_bps", "notional_total_net_pnl_bps")
    mean_pnl = _base_metric(base_agg, "mean_net_pnl_bps", "notional_mean_net_pnl_bps")
    p_total = float(base_agg.get("entry_exit_family_addone_p_total", 1.0))
    p_mean = float(base_agg.get("entry_exit_family_addone_p_mean", 1.0))
    checks = {
        "base_v24_gate_passed": _base_gate_passed(base_agg),
        "base_trade_count": int(base_agg.get("trades", 0)) >= int(gate.min_base_trades),
        "base_hit_rate": hit_rate >= float(gate.min_base_hit_rate),
        "base_profit": total_pnl >= float(gate.min_base_total_net_pnl_bps) and mean_pnl >= float(gate.min_base_mean_net_pnl_bps),
        "base_family_null": max(p_total, p_mean) <= float(gate.max_entry_exit_family_addone_p),
        "normal_leverage_is_5x": np.isclose(float(selected_policy.normal_leverage), float(gate.normal_leverage_required)),
        "no_loss_account_return": no_loss_return >= float(gate.min_no_loss_account_return_pct),
        "four_loss_min_return_positive": float(promoted["min_total_account_return_pct"]) > float(gate.min_four_loss_account_return_pct),
        "four_loss_p05_return_positive": float(promoted["p05_total_account_return_pct"]) > float(gate.min_four_loss_p05_account_return_pct),
        "four_loss_drawdown_control": float(promoted["worst_max_drawdown_pct"]) >= float(gate.min_four_loss_max_drawdown_pct),
        "extreme_fee_latency_account_return": float(account_stress["extreme_10bps_side_5s_account_return_pct"]) >= float(gate.min_extreme_stress_account_return_pct),
        "missed_trade_account_return": float(account_stress["missed_50pct_p05_account_return_pct"]) >= float(gate.min_missed_trade_p05_account_return_pct),
        "extra_cost_account_return": float(account_stress["extra_16bps_account_return_pct"]) >= float(gate.min_extra_cost_account_return_pct),
    }
    return _v23_jsonable({
        "trades": int(base_agg.get("trades", 0)),
        "selected_trade_win_rate": hit_rate,
        "notional_total_net_pnl_bps": total_pnl,
        "notional_mean_net_pnl_bps": mean_pnl,
        "normal_leverage": float(selected_policy.normal_leverage),
        "risk_off_leverage": float(selected_policy.risk_off_leverage),
        "risk_off_trades": int(selected_policy.risk_off_trades),
        "loss_trigger_bps": float(selected_policy.loss_trigger_bps),
        "no_loss_account_return_pct": no_loss_return,
        "max_drawdown_pct_no_loss_path": float(path["drawdown_pct"].min()) if not path.empty else 0.0,
        "promoted_loss_count": int(gate.promoted_loss_count),
        "synthetic_loss_bps": float(gate.synthetic_loss_bps),
        "four_loss_min_account_return_pct": float(promoted["min_total_account_return_pct"]),
        "four_loss_p01_account_return_pct": float(promoted["p01_total_account_return_pct"]),
        "four_loss_p05_account_return_pct": float(promoted["p05_total_account_return_pct"]),
        "four_loss_mean_account_return_pct": float(promoted["mean_total_account_return_pct"]),
        "four_loss_worst_drawdown_pct": float(promoted["worst_max_drawdown_pct"]),
        "warning_loss_count": int(gate.warning_loss_count),
        "five_loss_min_account_return_pct": float(warning["min_total_account_return_pct"]),
        "five_loss_p05_account_return_pct": float(warning["p05_total_account_return_pct"]),
        "five_loss_worst_drawdown_pct": float(warning["worst_max_drawdown_pct"]),
        "extreme_10bps_side_5s_account_return_pct": float(account_stress["extreme_10bps_side_5s_account_return_pct"]),
        "missed_50pct_p05_account_return_pct": float(account_stress["missed_50pct_p05_account_return_pct"]),
        "extra_16bps_account_return_pct": float(account_stress["extra_16bps_account_return_pct"]),
        "entry_exit_family_addone_p_total": p_total,
        "entry_exit_family_addone_p_mean": p_mean,
        "gate": {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]},
    })


def run_btc_four_loss_safety_lock(
    *,
    v24_run_dir: str | Path,
    out_dir: str | Path,
    gate: BTCFourLossSafetyGate | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Build the V25 four-loss safety certificate from a frozen V24 run.

    V25 intentionally does not change the BTC entry rule, exit ladder, fees,
    or selected trade ledger. It only replaces the V24 account-level risk-off
    rule with a stricter four-loss safety governor.
    """

    v24 = Path(v24_run_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    gate = gate or BTCFourLossSafetyGate()

    base_summary = _load_v24_summary(v24)
    trades = pd.read_csv(v24 / "btc_adaptive_exit_trade_ledger.csv")
    stress = pd.read_csv(v24 / "btc_adaptive_fee_latency_stress.csv")
    missed = pd.read_csv(v24 / "btc_adaptive_missed_trade_stress.csv")
    extra = pd.read_csv(v24 / "btc_adaptive_extra_cost_reserve.csv")

    scan = _scan_four_loss_policies(trades, gate=gate)
    selected_policy = _select_four_loss_policy(scan)
    path = _account_path(trades, selected_policy)
    synthetic_gate = BTCAdaptiveSafetyGate(
        synthetic_loss_bps=float(gate.synthetic_loss_bps),
        synthetic_loss_count=int(gate.promoted_loss_count),
    )
    injection = _loss_injection_table(
        trades,
        policy=selected_policy,
        gate=synthetic_gate,
        max_loss_count=max(int(gate.promoted_loss_count), int(gate.warning_loss_count)),
    )
    promoted_row = injection.loc[injection["loss_count"].astype(int) == int(gate.promoted_loss_count)].iloc[0].to_dict()
    account_stress = _account_level_stress(
        stress=stress,
        missed=missed,
        extra=extra,
        normal_leverage=float(selected_policy.normal_leverage),
        synthetic_loss_row=promoted_row,
        gate=BTCAdaptiveSafetyGate(
            synthetic_loss_bps=float(gate.synthetic_loss_bps),
            synthetic_loss_count=int(gate.promoted_loss_count),
            min_extreme_stress_account_return_pct=float(gate.min_extreme_stress_account_return_pct),
            min_missed_trade_p05_account_return_pct=float(gate.min_missed_trade_p05_account_return_pct),
            min_extra_cost_account_return_pct=float(gate.min_extra_cost_account_return_pct),
        ),
    )
    aggregate = _aggregate_v25(
        base_summary=base_summary,
        selected_policy=selected_policy,
        path=path,
        injection=injection,
        account_stress=account_stress,
        gate=gate,
    )
    result = {
        "version": "v25_btc_four_loss_safety_lock",
        "v24_run_dir": str(v24),
        "out_dir": str(out),
        "frozen_trade_policy": {
            "source": "v24 BTC adaptive exit selected ledger",
            "entry_changed": False,
            "exit_changed": False,
            "fee_changed": False,
            "note": "V25 only changes account-level leverage after a severe realized loss.",
        },
        "selected_risk_policy": selected_policy.to_dict(),
        "gate_config": gate.to_dict(),
        "base_v24_summary": base_summary.get("aggregate", {}),
        "aggregate": aggregate,
    }

    scan.to_csv(out / "btc_v25_four_loss_policy_scan.csv", index=False)
    path.to_csv(out / "btc_v25_account_path.csv", index=False)
    injection.to_csv(out / "btc_v25_synthetic_loss_injection_stress.csv", index=False)
    pd.DataFrame([account_stress]).to_csv(out / "btc_v25_account_level_stress_summary.csv", index=False)
    (out / "summary_v25.json").write_text(json.dumps(_v23_jsonable(result), indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(_v23_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT_V25.md", result, scan, path, injection, account_stress)
    _write_report(out / "REPORT.md", result, scan, path, injection, account_stress)
    (out / "DONE_V25.marker").write_text("ok\n", encoding="utf-8")
    return _v23_jsonable(result)


def _write_report(path: Path, result: dict[str, object], scan: pd.DataFrame, acct_path: pd.DataFrame, injection: pd.DataFrame, account_stress: dict[str, object]) -> None:
    agg = result["aggregate"]
    lines = [
        "# V25 BTC Four-Loss Safety Lock",
        "",
        "V25 keeps the V24 BTC trade ledger frozen and upgrades only the account-level safety governor.",
        "",
        "## Frozen trade policy",
        "",
        "```json",
        json.dumps(result["frozen_trade_policy"], indent=2),
        "```",
        "",
        "## Selected risk policy",
        "",
        "```json",
        json.dumps(result["selected_risk_policy"], indent=2),
        "```",
        "",
        "## Aggregate V25 gate",
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
        "## Top policy scan rows",
        "",
        scan.head(40).to_csv(index=False).strip(),
        "",
        "## Account path on bundled sample",
        "",
        acct_path[[c for c in ["timestamp", "fold", "signal", "net_pnl_bps", "take_profit_bps", "exit_reason", "leverage", "account_return_pct", "equity_return_pct", "drawdown_pct"] if c in acct_path.columns]].to_csv(index=False).strip(),
        "",
        "## Caveat",
        "",
        "V25 reaches a stricter bundled-sample BTC safety target, but independent multi-day BTCUSDT contract validation is still required before live use.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
