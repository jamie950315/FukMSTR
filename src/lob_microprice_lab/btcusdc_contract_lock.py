from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_adaptive_safety_lock import BTCAdaptiveLeveragePolicy, _account_path, _loss_injection_table, _v23_jsonable
from .btc_contract_data import BtcContractDataSpec, write_btc_contract_data_plan
from .btc_leverage_lock import _leverage_scenarios


@dataclass(frozen=True)
class BTCUSDCContractPolicy:
    """BTCUSDC deployment-transfer policy layered on the frozen V24/V25 BTC rule.

    This class does not change the direction model or entry/exit logic.  It
    reprices the frozen BTC trade ledger for BTCUSDC use and adds a quote-market
    surcharge.  A true BTCUSDC run can replace the source ledger with a real
    BTCUSDC ledger that follows the same schema.
    """

    symbol: str = "BTCUSDC"
    source_symbol: str = "BTCUSDT/BTC bundled transfer proxy"
    taker_fee_bps_per_side: float = 4.0
    maker_fee_bps_per_side: float = 0.0
    route: str = "taker_entry_taker_exit"
    quote_transfer_surcharge_bps: float = 0.50
    normal_leverage: float = 8.0
    emergency_leverage: float = 6.5
    emergency_trades: int = 12
    loss_trigger_bps: float = -20.0
    horizon_sec: float = 90.0
    latency_sec: float = 0.5

    @property
    def roundtrip_fee_bps(self) -> float:
        return 2.0 * float(self.taker_fee_bps_per_side)

    def to_adaptive_policy(self) -> BTCAdaptiveLeveragePolicy:
        return BTCAdaptiveLeveragePolicy(
            normal_leverage=float(self.normal_leverage),
            risk_off_leverage=float(self.emergency_leverage),
            risk_off_trades=int(self.emergency_trades),
            loss_trigger_bps=float(self.loss_trigger_bps),
        )

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["roundtrip_fee_bps"] = self.roundtrip_fee_bps
        return d


@dataclass(frozen=True)
class BTCUSDCContractGate:
    min_trades: int = 11
    min_win_rate: float = 0.90
    min_total_net_pnl_bps: float = 175.0
    min_mean_net_pnl_bps: float = 15.0
    min_no_loss_account_return_pct: float = 14.0
    min_extreme_10bps_5s_account_return_pct: float = 2.5
    missed_trade_probability: float = 0.50
    min_missed_trade_p05_account_return_pct: float = 1.5
    extra_cost_gate_bps: float = 16.0
    min_extra_cost_account_return_pct: float = 0.5
    synthetic_loss_bps: float = -40.0
    promoted_synthetic_loss_count: int = 4
    min_promoted_loss_return_pct: float = 0.75
    min_promoted_loss_drawdown_pct: float = -10.0
    shock_buffer_bps: float = 1000.0
    maintenance_margin_bps: float = 50.0
    max_promoted_leverage: float = 8.0
    require_data_manifest: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_v24_summary(v24_run_dir: Path) -> dict[str, object]:
    for name in ["summary_v24.json", "summary.json"]:
        path = v24_run_dir / name
        if path.exists():
            return _load_json(path)
    return {}


def _metric(summary: dict[str, object], key: str, default: float = 0.0) -> float:
    agg = summary.get("aggregate", {}) if isinstance(summary.get("aggregate"), dict) else {}
    try:
        return float(agg.get(key, default))
    except Exception:
        return float(default)


def _gate_passed(summary: dict[str, object]) -> bool:
    agg = summary.get("aggregate", {}) if isinstance(summary.get("aggregate"), dict) else {}
    gate = agg.get("gate", {}) if isinstance(agg, dict) else {}
    return bool(gate.get("passed", False)) if isinstance(gate, dict) else False


def _prepare_btcusdc_ledger(source: pd.DataFrame, policy: BTCUSDCContractPolicy, *, true_data: bool = False) -> pd.DataFrame:
    ledger = source.copy()
    if "timestamp" in ledger.columns:
        ledger["timestamp"] = pd.to_datetime(ledger["timestamp"], utc=True)
    ledger["symbol"] = str(policy.symbol)
    ledger["data_mode"] = "true_btcusdc_ledger" if true_data else "transfer_proxy_from_frozen_btc_ledger"
    ledger["source_symbol"] = str(policy.source_symbol)
    ledger["btcusdc_quote_surcharge_bps"] = float(policy.quote_transfer_surcharge_bps)
    ledger["real_taker_fee_bps_per_side"] = float(policy.taker_fee_bps_per_side)
    ledger["real_maker_fee_bps_per_side"] = float(policy.maker_fee_bps_per_side)
    ledger["real_roundtrip_fee_bps"] = float(policy.roundtrip_fee_bps)

    # The frozen V24 ledger is already priced at the user's taker+taker fee.
    # BTCUSDC transfer mode only subtracts the extra quote/liquidity surcharge.
    base_cost = pd.to_numeric(ledger.get("cost_bps", policy.roundtrip_fee_bps), errors="coerce").fillna(policy.roundtrip_fee_bps)
    base_net = pd.to_numeric(ledger.get("net_pnl_bps", 0.0), errors="coerce").fillna(0.0)
    ledger["cost_bps"] = base_cost + float(policy.quote_transfer_surcharge_bps)
    ledger["net_pnl_bps_before_btcusdc_surcharge"] = base_net
    ledger["net_pnl_bps"] = base_net - float(policy.quote_transfer_surcharge_bps)
    ledger["equity_bps"] = ledger["net_pnl_bps"].cumsum()
    return ledger.reset_index(drop=True)


def _fold_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if "fold" not in trades.columns:
        return pd.DataFrame(rows)
    for fold, grp in trades.groupby("fold", sort=True):
        pnl = pd.to_numeric(grp["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append({
            "fold": int(fold),
            "trades": int(len(grp)),
            "win_rate": float((pnl > 0).mean()) if len(grp) else 0.0,
            "mean_net_pnl_bps": float(pnl.mean()) if len(grp) else 0.0,
            "total_net_pnl_bps": float(pnl.sum()),
            "min_trade_net_pnl_bps": float(pnl.min()) if len(grp) else 0.0,
        })
    return pd.DataFrame(rows)


def _block_metrics(trades: pd.DataFrame, *, blocks: int) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    n = len(trades)
    for i in range(blocks):
        start = int(np.floor(i * n / blocks))
        end = int(np.floor((i + 1) * n / blocks))
        if end <= start:
            continue
        grp = trades.iloc[start:end]
        pnl = pd.to_numeric(grp["net_pnl_bps"], errors="coerce").fillna(0.0)
        rows.append({
            "block": i + 1,
            "trades": int(len(grp)),
            "win_rate": float((pnl > 0).mean()) if len(grp) else 0.0,
            "mean_net_pnl_bps": float(pnl.mean()) if len(grp) else 0.0,
            "total_net_pnl_bps": float(pnl.sum()),
        })
    return pd.DataFrame(rows)


def _drawdown_bps(pnl: pd.Series) -> float:
    eq = pd.to_numeric(pnl, errors="coerce").fillna(0.0).cumsum()
    dd = eq - eq.cummax()
    return float(dd.min()) if len(dd) else 0.0


def _bootstrap_summary(pnl: np.ndarray, *, scenarios: int = 10000, seed: int = 26026) -> dict[str, object]:
    if pnl.size == 0:
        return {"scenarios": scenarios, "mean_p05_bps": 0.0, "total_p05_bps": 0.0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(pnl), size=(scenarios, len(pnl)))
    samples = pnl[idx]
    totals = samples.sum(axis=1)
    means = samples.mean(axis=1)
    return {
        "scenarios": int(scenarios),
        "mean_p01_bps": float(np.percentile(means, 1)),
        "mean_p05_bps": float(np.percentile(means, 5)),
        "total_p01_bps": float(np.percentile(totals, 1)),
        "total_p05_bps": float(np.percentile(totals, 5)),
        "positive_total_rate": float((totals > 0).mean()),
    }


def _missed_trade_stress(trades: pd.DataFrame, *, probabilities: list[float], scenarios: int = 10000, seed: int = 26027) -> pd.DataFrame:
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).to_numpy(float)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    n = len(pnl)
    for prob in probabilities:
        keep = rng.random((scenarios, n)) >= float(prob)
        totals = (keep * pnl).sum(axis=1)
        rows.append({
            "miss_probability": float(prob),
            "scenarios": int(scenarios),
            "mean_kept_trades": float(keep.sum(axis=1).mean()),
            "min_total_bps": float(totals.min()),
            "p01_total_bps": float(np.percentile(totals, 1)),
            "p05_total_bps": float(np.percentile(totals, 5)),
            "median_total_bps": float(np.percentile(totals, 50)),
            "mean_total_bps": float(totals.mean()),
            "positive_scenario_rate": float((totals > 0).mean()),
        })
    return pd.DataFrame(rows)


def _extra_cost_reserve(trades: pd.DataFrame, *, extra_values: list[float]) -> pd.DataFrame:
    base = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    rows: list[dict[str, object]] = []
    for extra in extra_values:
        net = base - float(extra)
        rows.append({
            "extra_cost_bps_per_trade": float(extra),
            "trades": int(len(net)),
            "mean_net_pnl_bps": float(net.mean()) if len(net) else 0.0,
            "total_net_pnl_bps": float(net.sum()),
            "win_rate": float((net > 0).mean()) if len(net) else 0.0,
        })
    return pd.DataFrame(rows)


def _stress_from_v24(v24_run_dir: Path, policy: BTCUSDCContractPolicy) -> pd.DataFrame:
    path = v24_run_dir / "btc_adaptive_fee_latency_stress.csv"
    if not path.exists():
        return pd.DataFrame()
    stress = pd.read_csv(path)
    trades = pd.to_numeric(stress.get("trades", 0), errors="coerce").fillna(0.0)
    stress["btcusdc_quote_surcharge_bps"] = float(policy.quote_transfer_surcharge_bps)
    stress["total_net_pnl_bps"] = pd.to_numeric(stress["total_net_pnl_bps"], errors="coerce").fillna(0.0) - trades * float(policy.quote_transfer_surcharge_bps)
    stress["mean_net_pnl_bps"] = np.where(trades > 0, stress["total_net_pnl_bps"] / trades, 0.0)
    stress["account_return_pct_at_policy_leverage"] = stress["total_net_pnl_bps"] * float(policy.normal_leverage) / 100.0
    return stress


def _account_stress_summary(stress: pd.DataFrame, missed: pd.DataFrame, extra: pd.DataFrame, *, policy: BTCUSDCContractPolicy, gate: BTCUSDCContractGate) -> dict[str, object]:
    extreme = pd.DataFrame()
    if not stress.empty:
        extreme = stress.loc[
            np.isclose(pd.to_numeric(stress.get("taker_fee_bps_per_side", 0.0), errors="coerce"), 10.0)
            & np.isclose(pd.to_numeric(stress.get("latency_sec", 0.0), errors="coerce"), 5.0)
        ]
    extreme_total = float(pd.to_numeric(extreme.get("total_net_pnl_bps", pd.Series([0.0])), errors="coerce").iloc[0]) if not extreme.empty else 0.0
    miss_row = missed.loc[np.isclose(pd.to_numeric(missed.get("miss_probability", 0), errors="coerce"), float(gate.missed_trade_probability))]
    miss_p05 = float(miss_row.iloc[0]["p05_total_bps"]) if not miss_row.empty else 0.0
    extra_row = extra.loc[np.isclose(pd.to_numeric(extra.get("extra_cost_bps_per_trade", 0), errors="coerce"), float(gate.extra_cost_gate_bps))]
    extra_total = float(extra_row.iloc[0]["total_net_pnl_bps"]) if not extra_row.empty else 0.0
    lev = float(policy.normal_leverage)
    return {
        "normal_leverage": lev,
        "extreme_10bps_side_5s_notional_total_bps": extreme_total,
        "extreme_10bps_side_5s_account_return_pct": extreme_total * lev / 100.0,
        "missed_trade_probability": float(gate.missed_trade_probability),
        "missed_trade_p05_notional_total_bps": miss_p05,
        "missed_trade_p05_account_return_pct": miss_p05 * lev / 100.0,
        "extra_cost_gate_bps": float(gate.extra_cost_gate_bps),
        "extra_cost_notional_total_bps": extra_total,
        "extra_cost_account_return_pct": extra_total * lev / 100.0,
    }


def run_btcusdc_contract_lock(
    *,
    v24_run_dir: str | Path,
    out_dir: str | Path,
    policy: BTCUSDCContractPolicy | None = None,
    gate: BTCUSDCContractGate | None = None,
    btcusdc_ledger: str | Path | None = None,
    clean: bool = False,
    write_data_plan: bool = True,
    data_start: str = "2024-01-01",
    data_end: str = "2026-06-10",
    max_loss_count: int = 5,
) -> dict[str, object]:
    """Run the frozen BTC model in BTCUSDC transfer mode.

    If a real BTCUSDC trade ledger is supplied, it will be used directly.  If no
    ledger is available, the function performs a conservative transfer run from
    the frozen V24 BTC ledger, subtracting a BTCUSDC quote-market surcharge and
    generating the BTCUSDC public-data download plan needed for true validation.
    """

    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    v24 = Path(v24_run_dir)
    policy = policy or BTCUSDCContractPolicy()
    gate = gate or BTCUSDCContractGate()

    summary = _load_v24_summary(v24)
    source_ledger_path = Path(btcusdc_ledger) if btcusdc_ledger else v24 / "btc_adaptive_exit_trade_ledger.csv"
    if not source_ledger_path.exists():
        raise FileNotFoundError(f"missing source ledger: {source_ledger_path}")
    true_data = btcusdc_ledger is not None
    source = pd.read_csv(source_ledger_path)
    trades = _prepare_btcusdc_ledger(source, policy, true_data=true_data)
    trades.to_csv(out / "btcusdc_contract_trade_ledger.csv", index=False)

    fold_metrics = _fold_metrics(trades)
    fold_metrics.to_csv(out / "btcusdc_fold_metrics.csv", index=False)
    blocks5 = _block_metrics(trades, blocks=5)
    blocks10 = _block_metrics(trades, blocks=10)
    blocks5.to_csv(out / "btcusdc_equal_trade_blocks_5.csv", index=False)
    blocks10.to_csv(out / "btcusdc_equal_trade_blocks_10.csv", index=False)

    stress = _stress_from_v24(v24, policy)
    stress.to_csv(out / "btcusdc_fee_latency_stress.csv", index=False)
    missed = _missed_trade_stress(trades, probabilities=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    missed.to_csv(out / "btcusdc_missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_values=[0, 0.5, 1, 2, 3, 5, 7.5, 10, 12, 14, 16, 18])
    extra.to_csv(out / "btcusdc_extra_cost_reserve.csv", index=False)

    account = _account_path(trades, policy.to_adaptive_policy())
    account.to_csv(out / "btcusdc_account_path.csv", index=False)

    inj = _loss_injection_table(
        trades,
        policy=policy.to_adaptive_policy(),
        gate=type("_Gate", (), {"synthetic_loss_bps": gate.synthetic_loss_bps, "synthetic_loss_count": gate.promoted_synthetic_loss_count})(),
        max_loss_count=max_loss_count,
    )
    inj.to_csv(out / "btcusdc_synthetic_loss_survival.csv", index=False)

    leverage = _leverage_scenarios(
        trades=trades,
        leverage_values=[1, 2, 3, 5, 6, 7, 8, 8.5, 9, 10],
        fee_roundtrip_bps=float(policy.roundtrip_fee_bps + policy.quote_transfer_surcharge_bps),
        maintenance_margin_bps=float(gate.maintenance_margin_bps),
        shock_buffer_bps=float(gate.shock_buffer_bps),
    )
    leverage.to_csv(out / "btcusdc_leverage_scenarios.csv", index=False)

    account_stress = _account_stress_summary(stress, missed, extra, policy=policy, gate=gate)
    pd.DataFrame([account_stress]).to_csv(out / "btcusdc_account_stress_summary.csv", index=False)

    data_plan: dict[str, object] = {}
    if write_data_plan:
        data_plan = write_btc_contract_data_plan(
            out / "btcusdc_data_plan",
            spec=BtcContractDataSpec(symbol=str(policy.symbol), start_date=data_start, end_date=data_end, intervals=("1s", "5s", "15s", "1m", "5m", "15m"), include_klines=True, include_agg_trades=True, include_trades=True),
            root="data/external",
        )

    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0)
    selected_lev = leverage.loc[np.isclose(pd.to_numeric(leverage["leverage"], errors="coerce"), float(policy.normal_leverage))]
    selected_lev_row = selected_lev.iloc[0].to_dict() if not selected_lev.empty else {}
    promoted_inj = inj.loc[inj["loss_count"].astype(int) == int(gate.promoted_synthetic_loss_count)]
    promoted_row = promoted_inj.iloc[0].to_dict() if not promoted_inj.empty else {}
    checks = {
        "source_v24_gate_passed": _gate_passed(summary) or true_data,
        "trade_count": int(len(trades)) >= int(gate.min_trades),
        "win_rate": float((pnl > 0).mean()) >= float(gate.min_win_rate) if len(pnl) else False,
        "total_net_pnl": float(pnl.sum()) >= float(gate.min_total_net_pnl_bps),
        "mean_net_pnl": float(pnl.mean()) >= float(gate.min_mean_net_pnl_bps) if len(pnl) else False,
        "no_loss_account_return": float(account["account_return_pct"].sum()) >= float(gate.min_no_loss_account_return_pct),
        "extreme_10bps_5s_account_return": float(account_stress["extreme_10bps_side_5s_account_return_pct"]) >= float(gate.min_extreme_10bps_5s_account_return_pct),
        "missed_trade_account_return": float(account_stress["missed_trade_p05_account_return_pct"]) >= float(gate.min_missed_trade_p05_account_return_pct),
        "extra_cost_account_return": float(account_stress["extra_cost_account_return_pct"]) >= float(gate.min_extra_cost_account_return_pct),
        "synthetic_loss_return": float(promoted_row.get("min_total_account_return_pct", 0.0)) >= float(gate.min_promoted_loss_return_pct),
        "synthetic_loss_drawdown": float(promoted_row.get("worst_max_drawdown_pct", -999.0)) >= float(gate.min_promoted_loss_drawdown_pct),
        "leverage_buffer": bool(selected_lev_row.get("passes_shock_buffer", False)),
        "uses_promoted_leverage_cap": np.isclose(float(policy.normal_leverage), float(gate.max_promoted_leverage)),
        "data_manifest_written": (not gate.require_data_manifest) or bool(data_plan.get("rows", 0)),
    }

    aggregate = {
        "data_mode": "true_btcusdc_ledger" if true_data else "transfer_proxy_from_frozen_btc_ledger",
        "true_btcusdc_data_run_completed": bool(true_data),
        "btcusdc_transfer_proxy_completed": not bool(true_data),
        "symbol": str(policy.symbol),
        "source_symbol": str(policy.source_symbol),
        "trades": int(len(trades)),
        "selected_trade_win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "notional_total_net_pnl_bps": float(pnl.sum()),
        "notional_mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "notional_median_net_pnl_bps": float(pnl.median()) if len(pnl) else 0.0,
        "notional_min_trade_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
        "notional_max_drawdown_bps": _drawdown_bps(pnl),
        "quote_transfer_surcharge_bps": float(policy.quote_transfer_surcharge_bps),
        "taker_fee_bps_per_side": float(policy.taker_fee_bps_per_side),
        "maker_fee_bps_per_side": float(policy.maker_fee_bps_per_side),
        "roundtrip_fee_bps": float(policy.roundtrip_fee_bps),
        "normal_leverage": float(policy.normal_leverage),
        "emergency_leverage": float(policy.emergency_leverage),
        "emergency_trades": int(policy.emergency_trades),
        "account_return_pct_no_compounding": float(account["account_return_pct"].sum()) if not account.empty else 0.0,
        "account_max_drawdown_pct": float(account["drawdown_pct"].min()) if not account.empty and "drawdown_pct" in account else 0.0,
        "bootstrap": _bootstrap_summary(pnl.to_numpy(float)),
        "fold_min_total_net_pnl_bps": float(fold_metrics["total_net_pnl_bps"].min()) if not fold_metrics.empty else 0.0,
        "fold_min_mean_net_pnl_bps": float(fold_metrics["mean_net_pnl_bps"].min()) if not fold_metrics.empty else 0.0,
        "blocks5_min_total_net_pnl_bps": float(blocks5["total_net_pnl_bps"].min()) if not blocks5.empty else 0.0,
        "blocks10_min_total_net_pnl_bps": float(blocks10["total_net_pnl_bps"].min()) if not blocks10.empty else 0.0,
        "extreme_10bps_side_5s_account_return_pct": float(account_stress["extreme_10bps_side_5s_account_return_pct"]),
        "missed_trade_p05_account_return_pct": float(account_stress["missed_trade_p05_account_return_pct"]),
        "extra_cost_account_return_pct": float(account_stress["extra_cost_account_return_pct"]),
        "promoted_synthetic_loss_count": int(gate.promoted_synthetic_loss_count),
        "promoted_loss_min_account_return_pct": float(promoted_row.get("min_total_account_return_pct", 0.0)),
        "promoted_loss_worst_drawdown_pct": float(promoted_row.get("worst_max_drawdown_pct", 0.0)),
        "liquidation_buffer_bps_before_safety_shock": float(selected_lev_row.get("approx_liquidation_buffer_bps_before_safety_shock", 0.0)),
        "shock_buffer_bps": float(gate.shock_buffer_bps),
        "data_plan_rows": int(data_plan.get("rows", 0)) if data_plan else 0,
        "gate": {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]},
    }

    result = {
        "version": "v26_btcusdc_contract_lock",
        "v24_run_dir": str(v24),
        "out_dir": str(out),
        "policy": policy.to_dict(),
        "gate_config": gate.to_dict(),
        "source_v24_aggregate": summary.get("aggregate", {}),
        "data_plan": {k: v for k, v in data_plan.items() if k not in {"public_data_manifest", "binance_um_daily_urls", "sources"}},
        "aggregate": aggregate,
        "caveat": "Without a real BTCUSDC order-book/trade ledger, this run is a BTCUSDC transfer/stress proxy. The package writes the BTCUSDC public-data manifest and accepts a real BTCUSDC ledger for a true run.",
    }
    payload = _v23_jsonable(result)
    (out / "summary_v26.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(out / "REPORT_V26.md", payload, trades, fold_metrics, blocks5, blocks10, stress, missed, extra, account, inj, leverage, account_stress, data_plan)
    _write_report(out / "REPORT.md", payload, trades, fold_metrics, blocks5, blocks10, stress, missed, extra, account, inj, leverage, account_stress, data_plan)
    (out / "DONE_V26.marker").write_text("ok\n", encoding="utf-8")
    return payload


def _write_report(
    path: Path,
    result: dict[str, object],
    trades: pd.DataFrame,
    fold_metrics: pd.DataFrame,
    blocks5: pd.DataFrame,
    blocks10: pd.DataFrame,
    stress: pd.DataFrame,
    missed: pd.DataFrame,
    extra: pd.DataFrame,
    account: pd.DataFrame,
    inj: pd.DataFrame,
    leverage: pd.DataFrame,
    account_stress: dict[str, object],
    data_plan: dict[str, object],
) -> None:
    agg = result["aggregate"]
    lines = [
        "# V26 BTCUSDC Contract Lock",
        "",
        "V26 runs the frozen BTC contract rule in BTCUSDC mode. If no real BTCUSDC ledger is supplied, it performs a conservative transfer run from the frozen BTC ledger, subtracts a BTCUSDC quote-market surcharge, and writes the BTCUSDC data plan needed for a true BTCUSDC replay.",
        "",
        "## Policy",
        "",
        "```json",
        json.dumps(result["policy"], indent=2),
        "```",
        "",
        "## Aggregate result",
        "",
        "```json",
        json.dumps(_v23_jsonable(agg), indent=2),
        "```",
        "",
        "## Account stress summary",
        "",
        pd.DataFrame([account_stress]).to_csv(index=False).strip(),
        "",
        "## Fold metrics",
        "",
        fold_metrics.to_csv(index=False).strip(),
        "",
        "## 5 equal-trade blocks",
        "",
        blocks5.to_csv(index=False).strip(),
        "",
        "## 10 equal-trade blocks",
        "",
        blocks10.to_csv(index=False).strip(),
        "",
        "## Fee/latency stress",
        "",
        stress.to_csv(index=False).strip(),
        "",
        "## Missed-trade stress",
        "",
        missed.to_csv(index=False).strip(),
        "",
        "## Extra-cost reserve",
        "",
        extra.to_csv(index=False).strip(),
        "",
        "## Synthetic loss survival",
        "",
        inj.to_csv(index=False).strip(),
        "",
        "## BTCUSDC leverage scenarios",
        "",
        leverage.to_csv(index=False).strip(),
        "",
        "## BTCUSDC trade ledger",
        "",
        trades[[c for c in ["timestamp", "symbol", "data_mode", "fold", "signal", "net_pnl_bps", "btcusdc_quote_surcharge_bps", "take_profit_bps", "exit_reason"] if c in trades.columns]].to_csv(index=False).strip(),
        "",
        "## Account path",
        "",
        account[[c for c in ["timestamp", "fold", "signal", "net_pnl_bps", "leverage", "account_return_pct", "equity_return_pct", "drawdown_pct"] if c in account.columns]].to_csv(index=False).strip(),
        "",
        "## BTCUSDC data plan",
        "",
        f"Rows: {int(data_plan.get('rows', 0)) if data_plan else 0}",
        f"Manifest: {data_plan.get('manifest_path', '') if data_plan else ''}",
        f"Download commands: {data_plan.get('download_commands', '') if data_plan else ''}",
        "",
        "## Caveat",
        "",
        str(result.get("caveat", "")),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
