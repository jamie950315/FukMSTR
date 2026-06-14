from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .btc_contract_data import BtcContractDataSpec, write_btc_contract_data_plan


@dataclass(frozen=True)
class BtcLeverageSpec:
    """Leverage assumptions for BTC perpetual contract research.

    This is intentionally exchange-agnostic.  Binance leverage brackets are account- and
    notional-dependent, so users should replace maintenance_margin_rate with their own
    bracket value before trading live.
    """

    starting_equity_usdt: float = 1000.0
    risk_fraction: float = 1.0
    maintenance_margin_rate: float = 0.005
    fee_buffer_bps: float = 8.0
    max_drawdown_pct: float = 5.0
    min_liquidation_buffer_bps: float = 500.0
    safety_multiple_vs_observed_loss: float = 10.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BtcContractGate:
    min_trades: int = 10
    min_win_rate: float = 0.80
    min_total_net_bps: float = 100.0
    min_bootstrap_p05_bps: float = 0.0
    min_fold_total_bps: float = 0.0
    max_selected_leverage: float = 5.0
    max_equity_drawdown_pct: float = 5.0
    min_liquidation_buffer_bps: float = 500.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _drawdown_pct(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak * 100.0
    return float(dd.min())


def _profit_factor(arr: np.ndarray) -> float:
    gp = float(arr[arr > 0].sum())
    gl = float(-arr[arr < 0].sum())
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def approximate_liquidation_buffer_bps(leverage: float, maintenance_margin_rate: float, fee_buffer_bps: float = 0.0) -> float:
    """Approximate adverse price move before liquidation, in bps of notional.

    For isolated USDT-margined contracts this is a simple safety proxy:
    1/leverage minus maintenance margin minus a fee buffer.  Actual exchange liquidation
    price also depends on wallet balance, position mode, brackets, funding, and exact venue rules.
    """
    lev = float(leverage)
    if lev <= 0:
        raise ValueError("leverage must be positive")
    return float(max(0.0, (1.0 / lev - float(maintenance_margin_rate)) * 10000.0 - float(fee_buffer_bps)))


def evaluate_leverage_grid(
    trades: pd.DataFrame,
    *,
    leverage_values: list[float] | tuple[float, ...] = (1, 2, 3, 5, 10, 15, 20),
    spec: BtcLeverageSpec | None = None,
) -> pd.DataFrame:
    spec = spec or BtcLeverageSpec()
    pnl_bps = pd.to_numeric(trades.get("net_pnl_bps", 0.0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    if len(pnl_bps) == 0:
        raise ValueError("trade ledger contains no trades")
    worst_loss = float(min(0.0, pnl_bps.min()))
    rows: list[dict[str, object]] = []
    for lev in leverage_values:
        lev = float(lev)
        equity = float(spec.starting_equity_usdt)
        equity_path = []
        trade_returns_pct = []
        for bps in pnl_bps:
            # Notional = equity * risk_fraction * leverage.  PnL = notional * bps/10000.
            pnl_usdt = equity * float(spec.risk_fraction) * lev * float(bps) / 10000.0
            equity += pnl_usdt
            equity_path.append(equity)
            trade_returns_pct.append(pnl_usdt / max(equity - pnl_usdt, 1e-12) * 100.0)
        equity_arr = np.asarray(equity_path, dtype=float)
        ret_arr = np.asarray(trade_returns_pct, dtype=float)
        buffer_bps = approximate_liquidation_buffer_bps(lev, spec.maintenance_margin_rate, spec.fee_buffer_bps)
        safety_ratio = float(buffer_bps / max(abs(worst_loss), 1e-12)) if worst_loss < 0 else float("inf")
        pass_safety = (
            _drawdown_pct(equity_arr) >= -float(spec.max_drawdown_pct)
            and buffer_bps >= float(spec.min_liquidation_buffer_bps)
            and safety_ratio >= float(spec.safety_multiple_vs_observed_loss)
            and float(equity_arr[-1]) > float(spec.starting_equity_usdt)
        )
        rows.append({
            "leverage": lev,
            "trades": int(len(pnl_bps)),
            "start_equity_usdt": float(spec.starting_equity_usdt),
            "end_equity_usdt": float(equity_arr[-1]),
            "total_return_pct": float((equity_arr[-1] / spec.starting_equity_usdt - 1.0) * 100.0),
            "mean_trade_return_pct": float(ret_arr.mean()),
            "median_trade_return_pct": float(np.median(ret_arr)),
            "worst_trade_return_pct": float(ret_arr.min()),
            "max_drawdown_pct": _drawdown_pct(equity_arr),
            "profit_factor_on_margin": _profit_factor(ret_arr),
            "approx_liquidation_buffer_bps": buffer_bps,
            "observed_worst_final_loss_bps": worst_loss,
            "liquidation_buffer_to_observed_loss_ratio": safety_ratio,
            "passes_leverage_safety_gate": bool(pass_safety),
        })
    return pd.DataFrame(rows)


def recommend_leverage(grid: pd.DataFrame, *, preferred_max_leverage: float = 5.0) -> dict[str, object]:
    safe = grid.loc[grid["passes_leverage_safety_gate"].astype(bool)].copy()
    if safe.empty:
        best = grid.sort_values(["total_return_pct", "max_drawdown_pct"], ascending=[False, False]).iloc[0]
        return {"recommended_leverage": None, "reason": "no leverage passed the safety gate", "best_observed_leverage": float(best["leverage"])}
    capped = safe.loc[safe["leverage"] <= float(preferred_max_leverage)]
    selected = capped.sort_values("total_return_pct", ascending=False).iloc[0] if not capped.empty else safe.sort_values("leverage").iloc[0]
    max_safe = safe.sort_values("leverage", ascending=False).iloc[0]
    return {
        "recommended_leverage": float(selected["leverage"]),
        "max_grid_leverage_passing_safety_gate": float(max_safe["leverage"]),
        "recommended_total_return_pct": float(selected["total_return_pct"]),
        "recommended_max_drawdown_pct": float(selected["max_drawdown_pct"]),
        "reason": "recommended leverage is capped for stability because this ledger does not contain full intratrade adverse-excursion depth data",
    }


def bootstrap_p05(values: np.ndarray, *, iterations: int = 5000, seed: int = 20020) -> float:
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0:
        return 0.0
    draws = rng.choice(arr, size=(int(iterations), len(arr)), replace=True).sum(axis=1)
    return float(np.quantile(draws, 0.05))


def run_btc_contract_leverage_research(
    *,
    v19_run_dir: str | Path,
    out_dir: str | Path,
    leverage_values: list[float] | None = None,
    leverage_spec: BtcLeverageSpec | None = None,
    gate: BtcContractGate | None = None,
    data_spec: BtcContractDataSpec | None = None,
    clean: bool = False,
) -> dict[str, object]:
    v19 = Path(v19_run_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    leverage_spec = leverage_spec or BtcLeverageSpec()
    gate = gate or BtcContractGate()
    leverage_values = leverage_values or [1, 2, 3, 5, 10, 15, 20]

    ledger_path = v19 / "real_fee_lock_trade_ledger.csv"
    if not ledger_path.exists():
        raise FileNotFoundError(f"missing V19 trade ledger: {ledger_path}")
    trades = pd.read_csv(ledger_path)
    pnl = pd.to_numeric(trades.get("net_pnl_bps", 0.0), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    folds = pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int)

    grid = evaluate_leverage_grid(trades, leverage_values=leverage_values, spec=leverage_spec)
    grid.to_csv(out / "btc_leverage_grid.csv", index=False)
    recommendation = recommend_leverage(grid, preferred_max_leverage=gate.max_selected_leverage)

    fold_df = pd.DataFrame({"fold": folds, "net_pnl_bps": pnl}).groupby("fold", as_index=False).agg(
        trades=("net_pnl_bps", "size"),
        total_net_pnl_bps=("net_pnl_bps", "sum"),
        mean_net_pnl_bps=("net_pnl_bps", "mean"),
    )
    fold_df.to_csv(out / "btc_fold_metrics_recheck.csv", index=False)

    base_metrics = {
        "trades": int(len(pnl)),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "median_net_pnl_bps": float(np.median(pnl)) if len(pnl) else 0.0,
        "total_net_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
        "bootstrap_total_p05_bps": bootstrap_p05(pnl),
        "worst_fold_total_bps": float(fold_df["total_net_pnl_bps"].min()) if len(fold_df) else 0.0,
        "worst_fold_mean_bps": float(fold_df["mean_net_pnl_bps"].min()) if len(fold_df) else 0.0,
        "profit_factor": _profit_factor(pnl),
        "max_drawdown_bps": float((np.cumsum(pnl) - np.maximum.accumulate(np.cumsum(pnl))).min()) if len(pnl) else 0.0,
    }

    data_plan = write_btc_contract_data_plan(out_dir=out / "btc_data_plan", spec=data_spec or BtcContractDataSpec())

    rec_lev = recommendation.get("recommended_leverage")
    selected_row = None
    if rec_lev is not None:
        selected = grid.loc[grid["leverage"] == float(rec_lev)]
        selected_row = selected.iloc[0].to_dict() if not selected.empty else None
    checks = {
        "enough_trades": base_metrics["trades"] >= gate.min_trades,
        "win_rate": base_metrics["win_rate"] >= gate.min_win_rate,
        "total_net_pnl": base_metrics["total_net_pnl_bps"] >= gate.min_total_net_bps,
        "bootstrap_positive": base_metrics["bootstrap_total_p05_bps"] >= gate.min_bootstrap_p05_bps,
        "fold_total_positive": base_metrics["worst_fold_total_bps"] >= gate.min_fold_total_bps,
        "recommended_leverage_exists": rec_lev is not None,
        "recommended_leverage_drawdown": bool(selected_row and float(selected_row["max_drawdown_pct"]) >= -gate.max_equity_drawdown_pct),
        "recommended_leverage_buffer": bool(selected_row and float(selected_row["approx_liquidation_buffer_bps"]) >= gate.min_liquidation_buffer_bps),
    }
    gate_result = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}

    result = {
        "source_v19_run_dir": str(v19),
        "out_dir": str(out),
        "base_metrics_real_fee": base_metrics,
        "leverage_spec": leverage_spec.to_dict(),
        "leverage_grid_csv": str(out / "btc_leverage_grid.csv"),
        "recommendation": recommendation,
        "selected_recommended_leverage_row": selected_row,
        "data_plan": data_plan,
        "gate": gate_result,
        "gate_config": gate.to_dict(),
        "limitations": [
            "Current bundled sample is still one Deribit BTC-PERPETUAL L2 sample, not a Binance multi-day BTCUSDT futures validation set.",
            "Leverage grid uses realized trade PnL; it does not prove intratrade liquidation safety without full path adverse-excursion data.",
            "Maker fee is zero but maker fills are not promoted without queue/fill data.",
        ],
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, grid)
    (out / "DONE.marker").write_text("ok\n", encoding="utf-8")
    return result


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, tuple):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _write_report(path: Path, result: dict[str, object], grid: pd.DataFrame) -> None:
    m = result["base_metrics_real_fee"]
    rec = result["recommendation"]
    sel = result.get("selected_recommended_leverage_row") or {}
    lines = [
        "# Research V20 - BTC contract data and leverage lock",
        "",
        "V20 keeps the V19 real-fee BTC direction policy frozen and adds BTC contract data acquisition plus leverage-aware sizing checks.",
        "",
        "## Real-fee signal result",
        "",
        f"- Trades: {m['trades']}",
        f"- Win rate: {m['win_rate']:.2%}",
        f"- Mean net PnL: {m['mean_net_pnl_bps']:.4f} bps/trade",
        f"- Total net PnL: {m['total_net_pnl_bps']:.4f} bps",
        f"- Bootstrap total p05: {m['bootstrap_total_p05_bps']:.4f} bps",
        f"- Worst fold total: {m['worst_fold_total_bps']:.4f} bps",
        "",
        "## Leverage recommendation",
        "",
        f"- Recommended leverage: {rec.get('recommended_leverage')}",
        f"- Max grid leverage passing safety gate: {rec.get('max_grid_leverage_passing_safety_gate')}",
        f"- Recommended total return on margin: {sel.get('total_return_pct', 0.0):.4f}%",
        f"- Recommended max drawdown on margin: {sel.get('max_drawdown_pct', 0.0):.4f}%",
        f"- Approx liquidation buffer: {sel.get('approx_liquidation_buffer_bps', 0.0):.4f} bps",
        "",
        "The recommendation is deliberately capped because this sample does not contain enough full intratrade adverse-excursion and maker queue data to prove aggressive live leverage.",
        "",
        "## Leverage grid",
        "",
        grid.to_markdown(index=False),
        "",
        "## BTC contract data plan",
        "",
        f"- Manifest rows: {result['data_plan']['rows']}",
        f"- Manifest CSV: `{result['data_plan']['manifest_csv']}`",
        f"- Download script: `{result['data_plan']['download_script']}`",
        "",
        "Use the manifest downloader outside this sandbox to fetch Binance USD-M BTCUSDT futures klines and aggTrades, then run the existing K-line and real-fee workflow on those independent days.",
        "",
        "## Gate",
        "",
        f"- Passed: {result['gate']['passed']}",
        f"- Failed checks: {result['gate']['failed_checks']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
