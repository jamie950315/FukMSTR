from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .profit_lock import _jsonable


@dataclass(frozen=True)
class DeploymentLockGate:
    """V18 deployment-readiness gate for a frozen V17 run.

    This audit intentionally does not tune or regenerate entry signals. It consumes the
    already-frozen V17 trade ledger and asks whether the ledger still looks viable under
    clock-time slicing, missed-fill stress, extra-cost reserve, and combined execution
    failure stress.
    """

    min_trades: int = 20
    min_total_net_pnl_bps: float = 0.0
    min_mean_net_pnl_bps: float = 0.0
    require_v17_gate_passed: bool = True
    require_trade_integrity: bool = True
    horizon_sec: float = 90.0
    min_clock_block_count: int = 10
    min_clock_block_min_total_bps: float = 0.0
    miss_trade_gate_probability: float = 0.50
    miss_trade_min_p01_total_bps: float = 0.0
    miss_trade_min_p05_total_bps: float = 0.0
    combined_miss_probability: float = 0.50
    combined_extra_cost_bps: float = 3.0
    combined_min_p05_total_bps: float = 0.0
    extra_cost_gate_bps: float = 10.0
    extra_cost_min_total_bps: float = 0.0
    require_v17_severe_stress_positive: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_deployment_lock_certificate(
    *,
    v17_run_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float = 90.0,
    miss_probabilities: list[float] | None = None,
    extra_cost_bps_values: list[float] | None = None,
    combined_miss_probabilities: list[float] | None = None,
    combined_extra_cost_bps_values: list[float] | None = None,
    clock_block_counts: list[int] | None = None,
    random_scenarios: int = 10000,
    seed: int = 18018,
    gate: DeploymentLockGate | None = None,
    clean: bool = False,
) -> dict[str, object]:
    run = Path(v17_run_dir)
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    miss_probabilities = _dedupe_float(miss_probabilities or [0.05, 0.10, 0.20, 0.30, 0.40, 0.50])
    extra_cost_bps_values = _dedupe_float(extra_cost_bps_values or [0.0, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0])
    combined_miss_probabilities = _dedupe_float(combined_miss_probabilities or [0.10, 0.20, 0.30, 0.40, 0.50])
    combined_extra_cost_bps_values = _dedupe_float(combined_extra_cost_bps_values or [1.0, 2.0, 3.0, 5.0])
    clock_block_counts = sorted({int(x) for x in (clock_block_counts or [3, 4, 5, 6, 8, 10, 12])})
    gate = gate or DeploymentLockGate(horizon_sec=float(horizon_sec))

    bt_path = run / "execution_lock_oof_backtest.csv"
    if not bt_path.exists():
        raise FileNotFoundError(f"missing V17 trade ledger: {bt_path}")
    backtest = pd.read_csv(bt_path)
    if "timestamp" not in backtest.columns:
        raise ValueError("execution_lock_oof_backtest.csv must contain a timestamp column")
    backtest["timestamp"] = pd.to_datetime(backtest["timestamp"], utc=True, format="mixed")
    backtest = backtest.sort_values("timestamp").reset_index(drop=True)
    traded_mask = pd.to_numeric(backtest.get("traded", 0), errors="coerce").fillna(0).astype(int) == 1
    trades = backtest.loc[traded_mask].copy().sort_values("timestamp").reset_index(drop=True)
    if trades.empty:
        raise ValueError("V17 trade ledger contains no traded rows")
    trades["net_pnl_bps"] = pd.to_numeric(trades["net_pnl_bps"], errors="coerce")
    trades.to_csv(out / "frozen_v17_trade_ledger.csv", index=False)

    v17_summary = _load_json(run / "summary.json")
    v17_gate_passed = bool((((v17_summary.get("aggregate") or {}).get("gate") or {}).get("passed"))) if v17_summary else False
    severe_stress = _load_severe_stress(run / "execution_lock_severe_stress.csv")

    base = _base_metrics(trades)
    integrity = _trade_integrity(backtest, trades, horizon_sec=float(horizon_sec))
    clock = _clock_time_blocks(backtest, trades, block_counts=clock_block_counts)
    clock.to_csv(out / "clock_time_block_stability.csv", index=False)
    miss = _missed_trade_stress(trades, miss_probabilities=miss_probabilities, scenarios=random_scenarios, seed=seed)
    miss.to_csv(out / "missed_trade_stress.csv", index=False)
    extra = _extra_cost_reserve(trades, extra_cost_bps_values=extra_cost_bps_values)
    extra.to_csv(out / "extra_cost_reserve.csv", index=False)
    combined = _combined_execution_failure_stress(
        trades,
        miss_probabilities=combined_miss_probabilities,
        extra_cost_bps_values=combined_extra_cost_bps_values,
        scenarios=random_scenarios,
        seed=seed + 99,
    )
    combined.to_csv(out / "combined_execution_failure_stress.csv", index=False)

    aggregate = _aggregate(
        base=base,
        integrity=integrity,
        v17_gate_passed=v17_gate_passed,
        severe_stress=severe_stress,
        clock=clock,
        miss=miss,
        extra=extra,
        combined=combined,
        gate=gate,
    )
    result: dict[str, object] = {
        "v17_run_dir": str(run),
        "out_dir": str(out),
        "horizon_sec": float(horizon_sec),
        "random_scenarios": int(random_scenarios),
        "seed": int(seed),
        "base_metrics": base,
        "trade_integrity": integrity,
        "v17_gate_passed": v17_gate_passed,
        "v17_severe_stress": severe_stress,
        "clock_block_counts": [int(x) for x in clock_block_counts],
        "miss_probabilities": [float(x) for x in miss_probabilities],
        "extra_cost_bps_values": [float(x) for x in extra_cost_bps_values],
        "combined_miss_probabilities": [float(x) for x in combined_miss_probabilities],
        "combined_extra_cost_bps_values": [float(x) for x in combined_extra_cost_bps_values],
        "aggregate": aggregate,
        "gate_config": gate.to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(_jsonable(result), indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, clock, miss, extra, combined)
    (out / "DONE.marker").write_text("ok\n", encoding="utf-8")
    return _jsonable(result)


def _dedupe_float(values: list[float]) -> list[float]:
    out: list[float] = []
    seen: set[float] = set()
    for value in values:
        v = round(float(value), 12)
        if v not in seen:
            seen.add(v)
            out.append(float(value))
    return out


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_severe_stress(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"available": False, "all_positive": False, "cells": 0}
    df = pd.read_csv(path)
    if df.empty:
        return {"available": True, "all_positive": False, "cells": 0}
    mean = pd.to_numeric(df.get("mean_net_pnl_bps", 0), errors="coerce").fillna(0.0)
    total = pd.to_numeric(df.get("total_net_pnl_bps", 0), errors="coerce").fillna(0.0)
    worst_total_idx = int(total.idxmin())
    worst_mean_idx = int(mean.idxmin())
    return {
        "available": True,
        "cells": int(len(df)),
        "all_positive": bool((mean > 0.0).all() and (total > 0.0).all()),
        "min_mean_net_pnl_bps": float(mean.min()),
        "min_total_net_pnl_bps": float(total.min()),
        "worst_total_cell": _jsonable(df.loc[worst_total_idx].to_dict()),
        "worst_mean_cell": _jsonable(df.loc[worst_mean_idx].to_dict()),
    }


def _base_metrics(trades: pd.DataFrame) -> dict[str, object]:
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    equity = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    drawdown = equity - peak
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    return {
        "trades": int(len(pnl)),
        "hit_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
        "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "median_net_pnl_bps": float(np.median(pnl)) if len(pnl) else 0.0,
        "total_net_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
        "min_trade_net_pnl_bps": float(pnl.min()) if len(pnl) else 0.0,
        "max_trade_net_pnl_bps": float(pnl.max()) if len(pnl) else 0.0,
        "max_drawdown_bps": float(drawdown.min()) if len(drawdown) else 0.0,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if abs(losses.sum()) > 0 else float("inf"),
        "positive_trades": int((pnl > 0.0).sum()),
        "negative_trades": int((pnl < 0.0).sum()),
    }


def _trade_integrity(backtest: pd.DataFrame, trades: pd.DataFrame, horizon_sec: float) -> dict[str, object]:
    trade_ts = pd.to_datetime(trades["timestamp"], utc=True, format="mixed")
    gaps = trade_ts.diff().dt.total_seconds().dropna().to_numpy(dtype=float)
    min_gap = float(gaps.min()) if len(gaps) else float("inf")
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce")
    signals = pd.to_numeric(trades.get("signal", 0), errors="coerce").fillna(0).astype(int)
    return {
        "event_timestamps_monotonic": bool(pd.to_datetime(backtest["timestamp"], utc=True, format="mixed").is_monotonic_increasing),
        "trade_timestamps_monotonic": bool(trade_ts.is_monotonic_increasing),
        "traded_rows_have_finite_pnl": bool(np.isfinite(pnl.to_numpy(dtype=float)).all()),
        "traded_rows_have_nonzero_signal": bool((signals != 0).all()),
        "min_trade_gap_sec": min_gap if np.isfinite(min_gap) else None,
        "non_overlap_slot_reserved": bool(min_gap + 1e-9 >= float(horizon_sec)) if np.isfinite(min_gap) else True,
        "horizon_sec": float(horizon_sec),
    }


def _clock_time_blocks(backtest: pd.DataFrame, trades: pd.DataFrame, *, block_counts: list[int]) -> pd.DataFrame:
    start = pd.to_datetime(backtest["timestamp"], utc=True, format="mixed").min()
    end = pd.to_datetime(backtest["timestamp"], utc=True, format="mixed").max()
    rows: list[dict[str, object]] = []
    for blocks in block_counts:
        if blocks <= 0 or start == end:
            continue
        edges = pd.date_range(start=start, end=end, periods=int(blocks) + 1)
        labels = pd.cut(pd.to_datetime(trades["timestamp"], utc=True, format="mixed"), bins=edges, labels=False, include_lowest=True)
        tmp = trades.copy()
        tmp["clock_block"] = labels
        grouped = tmp.groupby("clock_block", dropna=False)["net_pnl_bps"].agg(["count", "sum", "mean"]).reset_index()
        with_trades = grouped.loc[grouped["count"] > 0]
        rows.append({
            "block_count_requested": int(blocks),
            "blocks_with_trades": int(len(with_trades)),
            "positive_blocks_with_trades": int((with_trades["sum"] > 0.0).sum()) if not with_trades.empty else 0,
            "all_blocks_with_trades_positive": bool((with_trades["sum"] > 0.0).all()) if not with_trades.empty else False,
            "min_block_total_bps": float(with_trades["sum"].min()) if not with_trades.empty else 0.0,
            "median_block_total_bps": float(with_trades["sum"].median()) if not with_trades.empty else 0.0,
            "total_net_pnl_bps": float(with_trades["sum"].sum()) if not with_trades.empty else 0.0,
        })
    return pd.DataFrame(rows)


def _missed_trade_stress(trades: pd.DataFrame, *, miss_probabilities: list[float], scenarios: int, seed: int) -> pd.DataFrame:
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, object]] = []
    scenarios = int(scenarios)
    for miss in miss_probabilities:
        keep = rng.random((scenarios, len(pnl))) >= float(miss)
        kept = keep.sum(axis=1).astype(float)
        sums = keep.astype(float) @ pnl
        rows.append(_scenario_row({"miss_probability": float(miss), "extra_cost_bps": 0.0}, sums, kept))
    return pd.DataFrame(rows)


def _combined_execution_failure_stress(
    trades: pd.DataFrame,
    *,
    miss_probabilities: list[float],
    extra_cost_bps_values: list[float],
    scenarios: int,
    seed: int,
) -> pd.DataFrame:
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, object]] = []
    scenarios = int(scenarios)
    for miss in miss_probabilities:
        keep = rng.random((scenarios, len(pnl))) >= float(miss)
        kept = keep.sum(axis=1).astype(float)
        keep_float = keep.astype(float)
        for extra in extra_cost_bps_values:
            adjusted = pnl - float(extra)
            sums = keep_float @ adjusted
            rows.append(_scenario_row({"miss_probability": float(miss), "extra_cost_bps": float(extra)}, sums, kept))
    return pd.DataFrame(rows).sort_values(["miss_probability", "extra_cost_bps"]).reset_index(drop=True)


def _scenario_row(prefix: dict[str, object], sums: np.ndarray, kept: np.ndarray) -> dict[str, object]:
    q = np.percentile(sums, [1, 5, 10, 50])
    row = dict(prefix)
    row.update({
        "scenarios": int(len(sums)),
        "mean_kept_trades": float(kept.mean()) if len(kept) else 0.0,
        "min_total_bps": float(sums.min()) if len(sums) else 0.0,
        "p01_total_bps": float(q[0]),
        "p05_total_bps": float(q[1]),
        "p10_total_bps": float(q[2]),
        "median_total_bps": float(q[3]),
        "mean_total_bps": float(sums.mean()) if len(sums) else 0.0,
        "positive_scenario_rate": float((sums > 0.0).mean()) if len(sums) else 0.0,
    })
    return row


def _extra_cost_reserve(trades: pd.DataFrame, *, extra_cost_bps_values: list[float]) -> pd.DataFrame:
    pnl = pd.to_numeric(trades["net_pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    folds = pd.to_numeric(trades.get("fold", 0), errors="coerce").fillna(0).astype(int).to_numpy()
    rows: list[dict[str, object]] = []
    for extra in extra_cost_bps_values:
        adjusted = pnl - float(extra)
        by_fold = pd.DataFrame({"fold": folds, "pnl": adjusted}).groupby("fold")["pnl"].sum()
        rows.append({
            "extra_cost_bps_per_trade": float(extra),
            "trades": int(len(adjusted)),
            "mean_net_pnl_bps": float(adjusted.mean()) if len(adjusted) else 0.0,
            "total_net_pnl_bps": float(adjusted.sum()) if len(adjusted) else 0.0,
            "min_fold_total_net_pnl_bps": float(by_fold.min()) if len(by_fold) else 0.0,
            "positive_folds": int((by_fold > 0.0).sum()) if len(by_fold) else 0,
            "all_folds_positive": bool((by_fold > 0.0).all()) if len(by_fold) else False,
        })
    return pd.DataFrame(rows)


def _aggregate(
    *,
    base: dict[str, object],
    integrity: dict[str, object],
    v17_gate_passed: bool,
    severe_stress: dict[str, object],
    clock: pd.DataFrame,
    miss: pd.DataFrame,
    extra: pd.DataFrame,
    combined: pd.DataFrame,
    gate: DeploymentLockGate,
) -> dict[str, object]:
    clock_row = _row_for(clock, "block_count_requested", gate.min_clock_block_count)
    miss_row = _row_for(miss, "miss_probability", gate.miss_trade_gate_probability)
    combined_rows = combined.loc[
        np.isclose(pd.to_numeric(combined["miss_probability"], errors="coerce"), float(gate.combined_miss_probability))
        & np.isclose(pd.to_numeric(combined["extra_cost_bps"], errors="coerce"), float(gate.combined_extra_cost_bps))
    ]
    combined_row = combined_rows.iloc[0].to_dict() if not combined_rows.empty else {}
    extra_row = _row_for(extra, "extra_cost_bps_per_trade", gate.extra_cost_gate_bps)
    agg = {
        "trades": int(base.get("trades", 0)),
        "hit_rate": float(base.get("hit_rate", 0.0)),
        "mean_net_pnl_bps": float(base.get("mean_net_pnl_bps", 0.0)),
        "total_net_pnl_bps": float(base.get("total_net_pnl_bps", 0.0)),
        "max_drawdown_bps": float(base.get("max_drawdown_bps", 0.0)),
        "v17_gate_passed": bool(v17_gate_passed),
        "trade_integrity_passed": bool(all(bool(v) for k, v in integrity.items() if k not in {"min_trade_gap_sec", "horizon_sec"})),
        "v17_severe_stress_all_positive": bool(severe_stress.get("all_positive", False)),
        "v17_severe_stress_min_total_bps": float(severe_stress.get("min_total_net_pnl_bps", 0.0)),
        "v17_severe_stress_min_mean_bps": float(severe_stress.get("min_mean_net_pnl_bps", 0.0)),
        "clock_gate_blocks_with_trades": int(clock_row.get("blocks_with_trades", 0)),
        "clock_gate_positive_blocks": int(clock_row.get("positive_blocks_with_trades", 0)),
        "clock_gate_min_total_bps": float(clock_row.get("min_block_total_bps", 0.0)),
        "miss_gate_probability": float(gate.miss_trade_gate_probability),
        "miss_gate_p01_total_bps": float(miss_row.get("p01_total_bps", 0.0)),
        "miss_gate_p05_total_bps": float(miss_row.get("p05_total_bps", 0.0)),
        "miss_gate_positive_rate": float(miss_row.get("positive_scenario_rate", 0.0)),
        "extra_cost_gate_bps": float(gate.extra_cost_gate_bps),
        "extra_cost_gate_total_bps": float(extra_row.get("total_net_pnl_bps", 0.0)),
        "extra_cost_gate_mean_bps": float(extra_row.get("mean_net_pnl_bps", 0.0)),
        "extra_cost_gate_min_fold_total_bps": float(extra_row.get("min_fold_total_net_pnl_bps", 0.0)),
        "combined_gate_miss_probability": float(gate.combined_miss_probability),
        "combined_gate_extra_cost_bps": float(gate.combined_extra_cost_bps),
        "combined_gate_p05_total_bps": float(combined_row.get("p05_total_bps", 0.0)),
        "combined_gate_p01_total_bps": float(combined_row.get("p01_total_bps", 0.0)),
        "combined_gate_positive_rate": float(combined_row.get("positive_scenario_rate", 0.0)),
    }
    checks: dict[str, bool] = {}
    checks["enough_trades"] = int(agg["trades"]) >= int(gate.min_trades)
    checks["positive_total"] = float(agg["total_net_pnl_bps"]) > float(gate.min_total_net_pnl_bps)
    checks["positive_mean"] = float(agg["mean_net_pnl_bps"]) > float(gate.min_mean_net_pnl_bps)
    checks["v17_gate_passed"] = (not gate.require_v17_gate_passed) or bool(v17_gate_passed)
    checks["trade_integrity"] = (not gate.require_trade_integrity) or bool(agg["trade_integrity_passed"])
    checks["severe_stress_positive"] = (not gate.require_v17_severe_stress_positive) or bool(agg["v17_severe_stress_all_positive"])
    checks["clock_time_blocks_positive"] = int(agg["clock_gate_blocks_with_trades"]) >= int(gate.min_clock_block_count) and int(agg["clock_gate_positive_blocks"]) >= int(gate.min_clock_block_count) and float(agg["clock_gate_min_total_bps"]) > float(gate.min_clock_block_min_total_bps)
    checks["missed_trade_p01_positive"] = float(agg["miss_gate_p01_total_bps"]) > float(gate.miss_trade_min_p01_total_bps)
    checks["missed_trade_p05_positive"] = float(agg["miss_gate_p05_total_bps"]) > float(gate.miss_trade_min_p05_total_bps)
    checks["extra_cost_total_positive"] = float(agg["extra_cost_gate_total_bps"]) > float(gate.extra_cost_min_total_bps)
    checks["combined_failure_p05_positive"] = float(agg["combined_gate_p05_total_bps"]) > float(gate.combined_min_p05_total_bps)
    agg["gate"] = {"passed": bool(all(checks.values())), "checks": checks, "failed_checks": [k for k, v in checks.items() if not v]}
    return agg


def _row_for(df: pd.DataFrame, column: str, value: float | int) -> dict[str, object]:
    if df.empty or column not in df.columns:
        return {}
    numeric = pd.to_numeric(df[column], errors="coerce")
    rows = df.loc[np.isclose(numeric, float(value))]
    if rows.empty:
        return {}
    return rows.iloc[0].to_dict()


def _write_report(path: Path, result: dict[str, object], clock: pd.DataFrame, miss: pd.DataFrame, extra: pd.DataFrame, combined: pd.DataFrame) -> None:
    agg = result["aggregate"]
    lines = [
        "# V18 Deployment-Lock Certificate",
        "",
        "V18 does not tune the trading rule. It reads the frozen V17 trade ledger and checks whether the saved result survives practical deployment failures: missed trades, extra fees, clock-time slicing, and combined missed-trade plus extra-cost stress.",
        "",
        "## Gate and aggregate",
        "",
        "```json",
        json.dumps(_jsonable(agg), indent=2),
        "```",
        "",
        "## Plain-English use",
        "",
        "Unzip the package, enter the folder, and run `make deployment-lock-v18`. The command checks the saved V17 result without changing the trading choices.",
        "",
        "## Clock-time block stability",
        "",
        clock.to_csv(index=False).strip() if not clock.empty else "No clock block metrics.",
        "",
        "## Missed-trade stress",
        "",
        miss.to_csv(index=False).strip() if not miss.empty else "No missed-trade metrics.",
        "",
        "## Extra-cost reserve",
        "",
        extra.to_csv(index=False).strip() if not extra.empty else "No extra-cost metrics.",
        "",
        "## Combined missed-trade plus extra-cost stress",
        "",
        combined.to_csv(index=False).strip() if not combined.empty else "No combined stress metrics.",
        "",
        "## Caveat",
        "",
        "This certificate is stronger than V17 for operational robustness, but it still uses the bundled single sample. Stable live profit requires the same frozen rule to pass on independent multi-day data.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
