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
    _account_path,
    _loss_injection_table,
    _v23_jsonable,
)
from .btc_leverage_lock import _leverage_scenarios


@dataclass(frozen=True)
class BTCPortfolioRiskPolicy:
    """Portfolio-level survivor governor layered after V24.

    The BTC entry rule, direction model, fee model, and adaptive exits remain
    frozen from V24.  This policy only changes account-level exposure after a
    realized bad trade.  The default is intentionally a high-profit research
    mode: 8x normal exposure with an emergency reduction to 6.75x after a loss.
    """

    normal_leverage: float = 8.0
    emergency_leverage: float = 6.75
    emergency_trades: int = 10
    loss_trigger_bps: float = -20.0
    session_stop_drawdown_pct: float = -10.0

    def to_adaptive_policy(self) -> BTCAdaptiveLeveragePolicy:
        return BTCAdaptiveLeveragePolicy(
            normal_leverage=float(self.normal_leverage),
            risk_off_leverage=float(self.emergency_leverage),
            risk_off_trades=int(self.emergency_trades),
            loss_trigger_bps=float(self.loss_trigger_bps),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BTCPortfolioRiskGate:
    min_trades: int = 11
    min_win_rate: float = 1.0
    min_no_loss_account_return_pct: float = 15.0
    max_promoted_leverage: float = 8.0
    promoted_synthetic_loss_count: int = 4
    synthetic_loss_bps: float = -40.0
    min_promoted_loss_return_pct: float = 1.25
    min_promoted_loss_drawdown_pct: float = -10.0
    min_extreme_stress_account_return_pct: float = 3.0
    min_missed_trade_p05_account_return_pct: float = 2.0
    min_extra_cost_account_return_pct: float = 1.0
    shock_buffer_bps: float = 1000.0
    maintenance_margin_bps: float = 50.0
    max_entry_exit_family_addone_p: float = 0.01
    require_v24_gate: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _load_v24_summary(v24_run_dir: Path) -> dict[str, object]:
    for name in ["summary_v24.json", "summary.json"]:
        p = v24_run_dir / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"missing V24 summary in {v24_run_dir}")


def _metric(summary: dict[str, object], key: str, default: float = 0.0) -> float:
    agg = summary.get("aggregate", {}) if isinstance(summary.get("aggregate"), dict) else {}
    val = agg.get(key, default) if isinstance(agg, dict) else default
    try:
        return float(val)
    except Exception:
        return float(default)


def _gate_passed(summary: dict[str, object]) -> bool:
    agg = summary.get("aggregate", {}) if isinstance(summary.get("aggregate"), dict) else {}
    gate = agg.get("gate", {}) if isinstance(agg, dict) else {}
    return bool(gate.get("passed", False)) if isinstance(gate, dict) else False


def _row_for_value(df: pd.DataFrame, column: str, value: float) -> dict[str, object]:
    if df.empty or column not in df.columns:
        return {}
    vals = pd.to_numeric(df[column], errors="coerce")
    rows = df.loc[np.isclose(vals, float(value))]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _read_optional_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _account_stress_from_v24(v24: Path, *, normal_leverage: float, gate: BTCPortfolioRiskGate) -> dict[str, object]:
    stress = _read_optional_csv(v24 / "btc_adaptive_fee_latency_stress.csv")
    missed = _read_optional_csv(v24 / "btc_adaptive_missed_trade_stress.csv")
    extra = _read_optional_csv(v24 / "btc_adaptive_extra_cost_reserve.csv")
    extreme = pd.DataFrame()
    if not stress.empty:
        extreme = stress.loc[
            np.isclose(pd.to_numeric(stress.get("taker_fee_bps_per_side", 0.0), errors="coerce"), 10.0)
            & np.isclose(pd.to_numeric(stress.get("latency_sec", 0.0), errors="coerce"), 5.0)
        ]
    extreme_total_bps = float(pd.to_numeric(extreme.get("total_net_pnl_bps", pd.Series([0.0])), errors="coerce").iloc[0]) if not extreme.empty else 0.0
    miss50 = _row_for_value(missed, "miss_probability", 0.50)
    extra16 = _row_for_value(extra, "extra_cost_bps_per_trade", 16.0)
    missed_p05_bps = float(miss50.get("p05_total_bps", 0.0))
    extra_total_bps = float(extra16.get("total_net_pnl_bps", 0.0))
    return {
        "normal_leverage": float(normal_leverage),
        "extreme_10bps_side_5s_notional_total_bps": extreme_total_bps,
        "extreme_10bps_side_5s_account_return_pct": extreme_total_bps * float(normal_leverage) / 100.0,
        "missed_50pct_p05_notional_total_bps": missed_p05_bps,
        "missed_50pct_p05_account_return_pct": missed_p05_bps * float(normal_leverage) / 100.0,
        "extra_16bps_notional_total_bps": extra_total_bps,
        "extra_16bps_account_return_pct": extra_total_bps * float(normal_leverage) / 100.0,
    }


def _mode_scan(trades: pd.DataFrame, *, gate: BTCPortfolioRiskGate, max_loss_count: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    normal_values = [3.0, 4.0, 5.0, 6.0, 7.0, 7.5, 8.0, 8.5, 9.0]
    emergency_values = sorted(set([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 6.25, 6.5, 6.75, 7.0, 7.5, 8.0, 8.5, 9.0]))
    for normal in normal_values:
        leverage = _leverage_scenarios(
            trades=trades,
            leverage_values=[normal],
            fee_roundtrip_bps=8.0,
            maintenance_margin_bps=float(gate.maintenance_margin_bps),
            shock_buffer_bps=float(gate.shock_buffer_bps),
        )
        lev_row = leverage.iloc[0].to_dict() if not leverage.empty else {}
        for emergency in emergency_values:
            if emergency > normal:
                continue
            for cooldown in [1, 2, 3, 4, 6, 8, 10, 12, 15]:
                pol = BTCAdaptiveLeveragePolicy(
                    normal_leverage=float(normal),
                    risk_off_leverage=float(emergency),
                    risk_off_trades=int(cooldown),
                    loss_trigger_bps=-20.0,
                )
                inj = _loss_injection_table(
                    trades,
                    policy=pol,
                    gate=BTCAdaptiveSafetyGate(
                        synthetic_loss_bps=float(gate.synthetic_loss_bps),
                        synthetic_loss_count=int(gate.promoted_synthetic_loss_count),
                    ),
                    max_loss_count=max_loss_count,
                )
                no_loss = inj.loc[inj["loss_count"].astype(int) == 0].iloc[0]
                promoted = inj.loc[inj["loss_count"].astype(int) == int(gate.promoted_synthetic_loss_count)].iloc[0]
                passes = bool(
                    normal <= float(gate.max_promoted_leverage)
                    and float(no_loss["min_total_account_return_pct"]) >= float(gate.min_no_loss_account_return_pct)
                    and float(promoted["min_total_account_return_pct"]) >= float(gate.min_promoted_loss_return_pct)
                    and float(promoted["worst_max_drawdown_pct"]) >= float(gate.min_promoted_loss_drawdown_pct)
                    and bool(lev_row.get("passes_shock_buffer", False))
                )
                rows.append({
                    "normal_leverage": float(normal),
                    "emergency_leverage": float(emergency),
                    "emergency_trades": int(cooldown),
                    "loss_trigger_bps": -20.0,
                    "no_loss_account_return_pct": float(no_loss["min_total_account_return_pct"]),
                    "promoted_loss_count": int(gate.promoted_synthetic_loss_count),
                    "promoted_loss_min_account_return_pct": float(promoted["min_total_account_return_pct"]),
                    "promoted_loss_p05_account_return_pct": float(promoted["p05_total_account_return_pct"]),
                    "promoted_loss_worst_drawdown_pct": float(promoted["worst_max_drawdown_pct"]),
                    "liquidation_buffer_bps_before_safety_shock": float(lev_row.get("approx_liquidation_buffer_bps_before_safety_shock", 0.0)),
                    "passes_shock_buffer": bool(lev_row.get("passes_shock_buffer", False)),
                    "passes_v25_promoted_gate": passes,
                })
    return pd.DataFrame(rows).sort_values(
        [
            "passes_v25_promoted_gate",
            "normal_leverage",
            "no_loss_account_return_pct",
            "promoted_loss_min_account_return_pct",
            "promoted_loss_worst_drawdown_pct",
            "liquidation_buffer_bps_before_safety_shock",
        ],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)


def run_btc_portfolio_risk_lock(
    *,
    v24_run_dir: str | Path,
    out_dir: str | Path,
    policy: BTCPortfolioRiskPolicy | None = None,
    gate: BTCPortfolioRiskGate | None = None,
    clean: bool = False,
    max_loss_count: int = 5,
) -> dict[str, object]:
    """V25: high-profit portfolio-risk lock on top of frozen V24.

    V25 does not change the trade ledger. It upgrades the account-level risk
    governor from the V24 5x certificate to an 8x survivor certificate while
    checking four synthetic -40 bps failures, severe fee/latency stress,
    missed-trade stress, extra-cost reserve, and liquidation buffer.
    """

    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    v24 = Path(v24_run_dir)
    policy = policy or BTCPortfolioRiskPolicy()
    gate = gate or BTCPortfolioRiskGate()

    summary = _load_v24_summary(v24)
    trades_path = v24 / "btc_adaptive_exit_trade_ledger.csv"
    if not trades_path.exists():
        raise FileNotFoundError(f"missing V24 trade ledger: {trades_path}")
    trades = pd.read_csv(trades_path)

    adaptive_policy = policy.to_adaptive_policy()
    account_path = _account_path(trades, adaptive_policy)
    account_path.to_csv(out / "btc_v25_portfolio_account_path.csv", index=False)

    inj_gate = BTCAdaptiveSafetyGate(
        synthetic_loss_bps=float(gate.synthetic_loss_bps),
        synthetic_loss_count=int(gate.promoted_synthetic_loss_count),
    )
    injection = _loss_injection_table(trades, policy=adaptive_policy, gate=inj_gate, max_loss_count=max_loss_count)
    injection.to_csv(out / "btc_v25_synthetic_loss_survival.csv", index=False)

    scan = _mode_scan(trades, gate=gate, max_loss_count=max_loss_count)
    scan.to_csv(out / "btc_v25_risk_mode_scan.csv", index=False)

    leverage = _leverage_scenarios(
        trades=trades,
        leverage_values=sorted(set([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 8.5, 9.0, 10.0, float(policy.normal_leverage)])),
        fee_roundtrip_bps=8.0,
        maintenance_margin_bps=float(gate.maintenance_margin_bps),
        shock_buffer_bps=float(gate.shock_buffer_bps),
    )
    leverage.to_csv(out / "btc_v25_leverage_scenarios.csv", index=False)
    selected_lev = leverage.loc[np.isclose(pd.to_numeric(leverage["leverage"], errors="coerce"), float(policy.normal_leverage))]
    selected_lev_row = selected_lev.iloc[0].to_dict() if not selected_lev.empty else {}

    account_stress = _account_stress_from_v24(v24, normal_leverage=float(policy.normal_leverage), gate=gate)
    pd.DataFrame([account_stress]).to_csv(out / "btc_v25_account_stress_summary.csv", index=False)

    promoted_row = injection.loc[injection["loss_count"].astype(int) == int(gate.promoted_synthetic_loss_count)].iloc[0]
    next_row = injection.loc[injection["loss_count"].astype(int) == int(gate.promoted_synthetic_loss_count) + 1]
    next_loss = next_row.iloc[0].to_dict() if not next_row.empty else {}

    v24_four_loss_min = None
    v24_four_loss_dd = None
    v24_inj = v24 / "btc_v24_synthetic_loss_injection_stress.csv"
    if v24_inj.exists():
        old = pd.read_csv(v24_inj)
        row = old.loc[old["loss_count"].astype(int) == int(gate.promoted_synthetic_loss_count)]
        if not row.empty:
            v24_four_loss_min = float(row.iloc[0]["min_total_account_return_pct"])
            v24_four_loss_dd = float(row.iloc[0]["worst_max_drawdown_pct"])

    no_loss_return = float(account_path["account_return_pct"].sum()) if not account_path.empty else 0.0
    family_p_total = _metric(summary, "entry_exit_family_addone_p_total", 1.0)
    family_p_mean = _metric(summary, "entry_exit_family_addone_p_mean", 1.0)
    checks = {
        "v24_gate_passed": (not gate.require_v24_gate) or _gate_passed(summary),
        "trade_count": int(len(trades)) >= int(gate.min_trades),
        "win_rate": _metric(summary, "selected_trade_win_rate") >= float(gate.min_win_rate),
        "no_loss_account_return": no_loss_return >= float(gate.min_no_loss_account_return_pct),
        "entry_exit_family_p": max(family_p_total, family_p_mean) <= float(gate.max_entry_exit_family_addone_p),
        "promoted_four_loss_return": float(promoted_row["min_total_account_return_pct"]) >= float(gate.min_promoted_loss_return_pct),
        "promoted_four_loss_drawdown": float(promoted_row["worst_max_drawdown_pct"]) >= float(gate.min_promoted_loss_drawdown_pct),
        "extreme_fee_latency_account_return": float(account_stress["extreme_10bps_side_5s_account_return_pct"]) >= float(gate.min_extreme_stress_account_return_pct),
        "missed_trade_account_return": float(account_stress["missed_50pct_p05_account_return_pct"]) >= float(gate.min_missed_trade_p05_account_return_pct),
        "extra_cost_account_return": float(account_stress["extra_16bps_account_return_pct"]) >= float(gate.min_extra_cost_account_return_pct),
        "promoted_leverage_buffer": bool(selected_lev_row.get("passes_shock_buffer", False)),
        "normal_mode_uses_promoted_8x": np.isclose(float(policy.normal_leverage), float(gate.max_promoted_leverage)),
        "emergency_mode_reduces_leverage": float(policy.emergency_leverage) < float(policy.normal_leverage),
    }

    aggregate = {
        "trades": int(len(trades)),
        "selected_trade_win_rate": _metric(summary, "selected_trade_win_rate"),
        "notional_total_net_pnl_bps": _metric(summary, "notional_total_net_pnl_bps"),
        "notional_mean_net_pnl_bps": _metric(summary, "notional_mean_net_pnl_bps"),
        "normal_leverage": float(policy.normal_leverage),
        "emergency_leverage": float(policy.emergency_leverage),
        "emergency_trades": int(policy.emergency_trades),
        "loss_trigger_bps": float(policy.loss_trigger_bps),
        "no_loss_account_return_pct": no_loss_return,
        "promoted_synthetic_loss_count": int(gate.promoted_synthetic_loss_count),
        "synthetic_loss_bps": float(gate.synthetic_loss_bps),
        "promoted_loss_min_account_return_pct": float(promoted_row["min_total_account_return_pct"]),
        "promoted_loss_p05_account_return_pct": float(promoted_row["p05_total_account_return_pct"]),
        "promoted_loss_worst_drawdown_pct": float(promoted_row["worst_max_drawdown_pct"]),
        "next_loss_count_warning": int(next_loss.get("loss_count", int(gate.promoted_synthetic_loss_count) + 1)) if next_loss else None,
        "next_loss_min_account_return_pct_warning": float(next_loss.get("min_total_account_return_pct", 0.0)) if next_loss else None,
        "next_loss_worst_drawdown_pct_warning": float(next_loss.get("worst_max_drawdown_pct", 0.0)) if next_loss else None,
        "v24_same_loss_min_account_return_pct": v24_four_loss_min,
        "v24_same_loss_worst_drawdown_pct": v24_four_loss_dd,
        "four_loss_min_return_improvement_pct": None if v24_four_loss_min is None else float(promoted_row["min_total_account_return_pct"]) - float(v24_four_loss_min),
        "extreme_10bps_side_5s_account_return_pct": float(account_stress["extreme_10bps_side_5s_account_return_pct"]),
        "missed_50pct_p05_account_return_pct": float(account_stress["missed_50pct_p05_account_return_pct"]),
        "extra_16bps_account_return_pct": float(account_stress["extra_16bps_account_return_pct"]),
        "liquidation_buffer_bps_before_safety_shock": float(selected_lev_row.get("approx_liquidation_buffer_bps_before_safety_shock", 0.0)),
        "shock_buffer_bps": float(gate.shock_buffer_bps),
        "entry_exit_family_addone_p_total": family_p_total,
        "entry_exit_family_addone_p_mean": family_p_mean,
        "gate": {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]},
    }

    result = {
        "version": "v25_btc_portfolio_risk_lock",
        "v24_run_dir": str(v24),
        "out_dir": str(out),
        "frozen_trade_policy": {
            "source": "v24_btc_adaptive_exit_safety_lock",
            "entry_exit_note": "No V25 entry, direction, fee, or exit-target changes. V25 only changes account-level emergency leverage after a realized loss.",
            "fee_note": "User fee remains taker 0.0400% per side and maker 0.0000%; research route remains taker+taker = 8 bps round trip.",
        },
        "portfolio_risk_policy": policy.to_dict(),
        "gate_config": gate.to_dict(),
        "v24_aggregate": summary.get("aggregate", {}),
        "aggregate": aggregate,
    }
    payload = _v23_jsonable(result)
    (out / "summary_v25.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(out / "REPORT_V25.md", payload, account_path, injection, scan, leverage, account_stress)
    _write_report(out / "REPORT.md", payload, account_path, injection, scan, leverage, account_stress)
    (out / "DONE_V25.marker").write_text("ok\n", encoding="utf-8")
    return payload


def _write_report(path: Path, result: dict[str, object], account_path: pd.DataFrame, injection: pd.DataFrame, scan: pd.DataFrame, leverage: pd.DataFrame, account_stress: dict[str, object]) -> None:
    agg = result["aggregate"]
    lines = [
        "# V25 BTC Portfolio Risk Lock",
        "",
        "V25 keeps the V24 BTC trade rule frozen and upgrades only the portfolio-level leverage governor.",
        "",
        "## Frozen trade policy",
        "",
        "```json",
        json.dumps(result["frozen_trade_policy"], indent=2),
        "```",
        "",
        "## Portfolio risk policy",
        "",
        "```json",
        json.dumps(result["portfolio_risk_policy"], indent=2),
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
        "## Synthetic loss survival table",
        "",
        injection.to_csv(index=False).strip(),
        "",
        "## Leverage scenarios",
        "",
        leverage.to_csv(index=False).strip(),
        "",
        "## Risk mode scan",
        "",
        scan.head(80).to_csv(index=False).strip(),
        "",
        "## Account path on bundled sample",
        "",
        account_path[[c for c in ["timestamp", "fold", "signal", "net_pnl_bps", "take_profit_bps", "exit_reason", "leverage", "account_return_pct", "equity_return_pct", "drawdown_pct"] if c in account_path.columns]].to_csv(index=False).strip(),
        "",
        "## Caveat",
        "",
        "V25 strengthens bundled-sample profit and synthetic-loss survivability. It still needs independent multi-day BTCUSDT contract validation before live use.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
