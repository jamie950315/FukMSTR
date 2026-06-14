from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .data_schema import timestamps_to_ns
from .fixed_template import _build_template_pool, candidate_signature, load_ensemble_fold_predictions
from .selective import (
    SelectiveCandidate,
    backtest_fixed_signals_taker_bidask_non_overlapping,
    backtest_selective_taker_bidask_non_overlapping,
    fixed_signal_robust_gate,
    shift_null_fixed_signals,
    stress_fixed_signals,
    summarize_shift_null,
)
from .stress import block_bootstrap_pnl


@dataclass(frozen=True)
class SequentialGateConfig:
    min_oof_trades: int = 20
    min_periods_with_trades: int = 3
    min_oof_mean_net_bps: float = 0.0
    min_period_mean_net_bps: float = 0.0
    min_bootstrap_p05_bps: float = 0.0
    max_shift_null_p_mean: float = 0.10
    max_shift_null_p_total: float = 0.10
    require_stress_gate: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PeriodSpec:
    period_id: int
    fold: int
    segment: int
    start_timestamp: str
    end_timestamp: str
    rows: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


RANKING_POLICIES = {"source_rank", "past_total", "past_mean", "past_rank_score", "past_lower_bound"}
COLD_START_POLICIES = {"source_rank", "no_trade"}


def run_sequential_template_audit(
    *,
    ensemble_dir: str | Path,
    out_dir: str | Path,
    horizon_sec: float,
    cost_bps: float = 1.5,
    latency_sec: float = 0.5,
    edge_thresholds: list[float] | None = None,
    signed_columns: list[str] | None = None,
    spread_quantiles: list[float] | None = None,
    vol_modes: list[str] | None = None,
    template_source: str = "first_fold",
    min_source_trades: int = 4,
    top_k_templates: int = 80,
    period_sec: float = 0.0,
    ranking_policy: str = "past_lower_bound",
    cold_start_policy: str = "source_rank",
    warmup_periods: int = 1,
    min_history_trades: int = 4,
    min_history_periods: int = 1,
    lower_bound_z: float = 1.645,
    min_lower_bound_bps: float = 0.0,
    stress_cost_bps_values: list[float] | None = None,
    stress_latency_sec_values: list[float] | None = None,
    shift_null_runs: int = 80,
    gate_config: SequentialGateConfig | None = None,
    clean: bool = False,
) -> dict[str, object]:
    """Run an online/prequential template-selection audit.

    The template family is fixed before validation.  At each validation period, the selector may only
    use earlier validation periods plus the source ranking to choose the next template.  This is a
    single-day emulator for the future multi-session workflow that should eventually use real days.
    """
    if ranking_policy not in RANKING_POLICIES:
        raise ValueError(f"ranking_policy must be one of {sorted(RANKING_POLICIES)}")
    if cold_start_policy not in COLD_START_POLICIES:
        raise ValueError(f"cold_start_policy must be one of {sorted(COLD_START_POLICIES)}")
    if min_history_trades < 0:
        raise ValueError("min_history_trades must be non-negative")
    if min_history_periods < 0:
        raise ValueError("min_history_periods must be non-negative")

    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    edge_thresholds = edge_thresholds or [0.1, 0.2, 0.3, 0.5, 0.7]
    spread_quantiles = spread_quantiles or [1.0]
    vol_modes = vol_modes or ["none"]
    stress_cost_bps_values = stress_cost_bps_values or [1.5, 3.0, 5.0]
    stress_latency_sec_values = stress_latency_sec_values or [0.0, 0.5, 1.0, 2.0]
    gate_config = gate_config or SequentialGateConfig()

    folds = load_ensemble_fold_predictions(ensemble_dir)
    templates = _build_template_pool(
        folds,
        template_source=template_source,
        edge_thresholds=edge_thresholds,
        signed_columns=signed_columns,
        spread_quantiles=spread_quantiles,
        vol_modes=vol_modes,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
        min_source_trades=min_source_trades,
        top_k_templates=top_k_templates,
    )
    if not templates:
        raise ValueError("no templates available for sequential audit")

    periods = _make_periods(folds, period_sec=period_sec)
    if not periods:
        raise ValueError("no validation periods generated")

    period_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    ledger_by_template_period: dict[tuple[str, int], pd.DataFrame] = {}

    template_metadata = []
    for source_rank, candidate in enumerate(templates, start=1):
        sig = candidate_signature(candidate)
        template_metadata.append({"source_rank": int(source_rank), "template_signature": sig, "candidate_json": json.dumps(candidate.to_dict(), sort_keys=True), **candidate.to_dict()})

    for period in periods:
        period_rows.append(period["spec"].to_dict())
        frame = period["frame"]
        for source_rank, candidate in enumerate(templates, start=1):
            sig = candidate_signature(candidate)
            bt, metrics = backtest_selective_taker_bidask_non_overlapping(
                frame,
                candidate=candidate,
                cost_bps=cost_bps,
                horizon_sec=horizon_sec,
                latency_sec=latency_sec,
            )
            bt.insert(0, "period_id", int(period["spec"].period_id))
            bt.insert(1, "source_rank", int(source_rank))
            bt["fold"] = int(period["spec"].fold)
            bt["segment"] = int(period["spec"].segment)
            bt["template_signature"] = sig
            bt["candidate_json"] = json.dumps(candidate.to_dict(), sort_keys=True)
            ledger_by_template_period[(sig, int(period["spec"].period_id))] = bt
            pnl = _trade_pnl(bt)
            metric_rows.append(
                {
                    "period_id": int(period["spec"].period_id),
                    "fold": int(period["spec"].fold),
                    "segment": int(period["spec"].segment),
                    "source_rank": int(source_rank),
                    "template_signature": sig,
                    "candidate_json": json.dumps(candidate.to_dict(), sort_keys=True),
                    "trades": int(metrics.get("trades", 0)),
                    "hit_rate": float(metrics.get("hit_rate", 0.0)),
                    "mean_net_pnl_bps": float(metrics.get("mean_net_pnl_bps", 0.0)),
                    "total_net_pnl_bps": float(metrics.get("total_net_pnl_bps", 0.0)),
                    "max_drawdown_bps": float(metrics.get("max_drawdown_bps", 0.0)),
                    "std_net_pnl_bps": float(pnl.std(ddof=0)) if len(pnl) else 0.0,
                    **_candidate_fields(candidate),
                }
            )

    periods_df = pd.DataFrame(period_rows)
    template_df = pd.DataFrame(template_metadata)
    metrics_df = pd.DataFrame(metric_rows)
    periods_df.to_csv(out / "periods.csv", index=False)
    template_df.to_csv(out / "template_family.csv", index=False)
    metrics_df.to_csv(out / "period_template_metrics.csv", index=False)

    selections: list[dict[str, object]] = []
    selected_ledgers: list[pd.DataFrame] = []
    oracle_ledgers: list[pd.DataFrame] = []
    source_rank1_ledgers: list[pd.DataFrame] = []

    for period_index, period in enumerate(periods, start=1):
        pid = int(period["spec"].period_id)
        history_metrics = metrics_df[metrics_df["period_id"].astype(int) < pid]
        selected_sig, reason, score = _select_template_for_period(
            templates=templates,
            metrics=history_metrics,
            ranking_policy=ranking_policy,
            cold_start_policy=cold_start_policy,
            warmup_periods=warmup_periods,
            period_index=period_index,
            min_history_trades=min_history_trades,
            min_history_periods=min_history_periods,
            lower_bound_z=lower_bound_z,
            min_lower_bound_bps=min_lower_bound_bps,
        )
        period_metrics = metrics_df[metrics_df["period_id"].astype(int) == pid].copy()
        oracle_row = _rank_period_candidates(period_metrics).head(1)
        oracle_sig = str(oracle_row.iloc[0]["template_signature"]) if not oracle_row.empty else ""
        source_sig = candidate_signature(templates[0])

        selected_bt = _ledger_for_selection(
            ledger_by_template_period=ledger_by_template_period,
            signature=selected_sig,
            period_id=pid,
            fallback_frame=period["frame"],
            period_spec=period["spec"],
        )
        selected_ledgers.append(selected_bt)
        oracle_ledgers.append(_ledger_for_selection(ledger_by_template_period=ledger_by_template_period, signature=oracle_sig, period_id=pid, fallback_frame=period["frame"], period_spec=period["spec"]))
        source_rank1_ledgers.append(_ledger_for_selection(ledger_by_template_period=ledger_by_template_period, signature=source_sig, period_id=pid, fallback_frame=period["frame"], period_spec=period["spec"]))

        selected_period_metrics = _metrics_for_signature(period_metrics, selected_sig)
        source_period_metrics = _metrics_for_signature(period_metrics, source_sig)
        oracle_period_metrics = _metrics_for_signature(period_metrics, oracle_sig)
        selections.append(
            {
                "period_id": pid,
                "fold": int(period["spec"].fold),
                "segment": int(period["spec"].segment),
                "selected_template_signature": selected_sig,
                "selected_source_rank": _source_rank_for_sig(template_df, selected_sig),
                "selection_reason": reason,
                "selection_score": float(score) if score is not None and np.isfinite(score) else None,
                "selected_trades": int(selected_period_metrics.get("trades", 0)),
                "selected_mean_net_pnl_bps": float(selected_period_metrics.get("mean_net_pnl_bps", 0.0)),
                "selected_total_net_pnl_bps": float(selected_period_metrics.get("total_net_pnl_bps", 0.0)),
                "source_rank1_trades": int(source_period_metrics.get("trades", 0)),
                "source_rank1_mean_net_pnl_bps": float(source_period_metrics.get("mean_net_pnl_bps", 0.0)),
                "source_rank1_total_net_pnl_bps": float(source_period_metrics.get("total_net_pnl_bps", 0.0)),
                "oracle_template_signature": oracle_sig,
                "oracle_source_rank": _source_rank_for_sig(template_df, oracle_sig),
                "oracle_trades": int(oracle_period_metrics.get("trades", 0)),
                "oracle_mean_net_pnl_bps": float(oracle_period_metrics.get("mean_net_pnl_bps", 0.0)),
                "oracle_total_net_pnl_bps": float(oracle_period_metrics.get("total_net_pnl_bps", 0.0)),
            }
        )

    selected_oof = pd.concat(selected_ledgers, ignore_index=True) if selected_ledgers else pd.DataFrame()
    oracle_oof = pd.concat(oracle_ledgers, ignore_index=True) if oracle_ledgers else pd.DataFrame()
    source_oof = pd.concat(source_rank1_ledgers, ignore_index=True) if source_rank1_ledgers else pd.DataFrame()
    selections_df = pd.DataFrame(selections)

    selected_oof.to_csv(out / "selected_online_oof_backtest.csv", index=False)
    oracle_oof.to_csv(out / "oracle_period_oof_backtest.csv", index=False)
    source_oof.to_csv(out / "source_rank1_oof_backtest.csv", index=False)
    selections_df.to_csv(out / "online_selections.csv", index=False)

    selected_summary = _ledger_summary(selected_oof, periods_df)
    oracle_summary = _ledger_summary(oracle_oof, periods_df)
    source_summary = _ledger_summary(source_oof, periods_df)

    selected_repriced, selected_metrics = backtest_fixed_signals_taker_bidask_non_overlapping(
        selected_oof,
        cost_bps=cost_bps,
        horizon_sec=horizon_sec,
        latency_sec=latency_sec,
    )
    selected_repriced.to_csv(out / "selected_online_repriced_backtest.csv", index=False)
    selected_summary.update({f"repriced_{k}": v for k, v in selected_metrics.items() if isinstance(v, (int, float, str))})

    stress = stress_fixed_signals(
        selected_oof,
        horizon_sec=horizon_sec,
        cost_bps_values=stress_cost_bps_values,
        latency_sec_values=stress_latency_sec_values,
    )
    stress.to_csv(out / "selected_online_stress.csv", index=False)
    stress_gate = fixed_signal_robust_gate(stress, min_trades=max(1, min_history_trades))

    shift_null = shift_null_fixed_signals(
        selected_oof,
        horizon_sec=horizon_sec,
        cost_bps=cost_bps,
        latency_sec=latency_sec,
        shifts=shift_null_runs,
    )
    shift_null.to_csv(out / "selected_online_shift_null.csv", index=False)
    shift_summary = summarize_shift_null(selected_metrics, shift_null)

    trade_pnl = _trade_pnl(selected_oof)
    bootstrap = block_bootstrap_pnl(trade_pnl, iterations=800, block_size=10, seed=11100)
    gate = _evaluate_sequential_gate(selected_summary, bootstrap, shift_summary, stress_gate, gate_config)
    regret = _regret_summary(selected_summary, oracle_summary, source_summary)

    result = {
        "source_ensemble_dir": str(ensemble_dir),
        "horizon_sec": float(horizon_sec),
        "cost_bps": float(cost_bps),
        "latency_sec": float(latency_sec),
        "template_source": template_source,
        "templates_tested": int(len(templates)),
        "periods": int(len(periods_df)),
        "period_sec": float(period_sec),
        "ranking_policy": ranking_policy,
        "cold_start_policy": cold_start_policy,
        "warmup_periods": int(warmup_periods),
        "min_history_trades": int(min_history_trades),
        "min_history_periods": int(min_history_periods),
        "lower_bound_z": float(lower_bound_z),
        "min_lower_bound_bps": float(min_lower_bound_bps),
        "selected_online": selected_summary,
        "source_rank1": source_summary,
        "period_oracle": oracle_summary,
        "regret": regret,
        "bootstrap": bootstrap,
        "shift_null": shift_summary,
        "stress_gate": stress_gate,
        "gate_config": gate_config.to_dict(),
        "gate": gate,
        "out_dir": str(out),
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    _write_report(out / "REPORT.md", result, selections_df, stress, shift_null)
    return result


def _make_periods(folds: list[tuple[int, pd.DataFrame, pd.DataFrame]], *, period_sec: float) -> list[dict[str, object]]:
    periods: list[dict[str, object]] = []
    period_id = 0
    for fold_num, _calib, validation in folds:
        frame = validation.copy().sort_values("timestamp").reset_index(drop=True)
        if frame.empty:
            continue
        if period_sec <= 0:
            period_id += 1
            periods.append({"spec": _period_spec(period_id, int(fold_num), 1, frame), "frame": frame})
            continue
        ts_ns = timestamps_to_ns(frame["timestamp"])
        start = int(ts_ns[0])
        span = int(float(period_sec) * 1_000_000_000)
        if span <= 0:
            raise ValueError("period_sec must be positive or 0")
        segment = 0
        cursor = start
        stop = int(ts_ns[-1])
        while cursor <= stop:
            segment += 1
            right = cursor + span
            mask = (ts_ns >= cursor) & (ts_ns < right)
            part = frame.loc[mask].copy().reset_index(drop=True)
            if len(part) > 0:
                period_id += 1
                periods.append({"spec": _period_spec(period_id, int(fold_num), segment, part), "frame": part})
            cursor = right
    return periods


def _period_spec(period_id: int, fold: int, segment: int, frame: pd.DataFrame) -> PeriodSpec:
    return PeriodSpec(
        period_id=int(period_id),
        fold=int(fold),
        segment=int(segment),
        start_timestamp=str(frame["timestamp"].iloc[0]),
        end_timestamp=str(frame["timestamp"].iloc[-1]),
        rows=int(len(frame)),
    )


def _select_template_for_period(
    *,
    templates: list[SelectiveCandidate],
    metrics: pd.DataFrame,
    ranking_policy: str,
    cold_start_policy: str,
    warmup_periods: int,
    period_index: int,
    min_history_trades: int,
    min_history_periods: int,
    lower_bound_z: float,
    min_lower_bound_bps: float,
) -> tuple[str, str, float | None]:
    if ranking_policy == "source_rank":
        return candidate_signature(templates[0]), "source_rank_policy", 0.0
    if period_index <= max(0, int(warmup_periods)) or metrics.empty:
        if cold_start_policy == "source_rank":
            return candidate_signature(templates[0]), "cold_start_source_rank", 0.0
        return "", "cold_start_no_trade", None

    rows: list[dict[str, object]] = []
    for source_rank, candidate in enumerate(templates, start=1):
        sig = candidate_signature(candidate)
        hist = metrics[metrics["template_signature"] == sig]
        stats = _history_stats(hist, lower_bound_z=lower_bound_z)
        if stats["trades"] < min_history_trades or stats["periods_with_trades"] < min_history_periods:
            score = -math.inf
        elif ranking_policy == "past_total":
            score = stats["total"]
        elif ranking_policy == "past_mean":
            score = stats["mean"]
        elif ranking_policy == "past_rank_score":
            score = stats["mean"] + 0.003 * stats["total"] + 0.10 * stats["hit_rate"] - 0.01 * abs(stats["max_drawdown"]) + 0.002 * min(stats["trades"], 300)
        elif ranking_policy == "past_lower_bound":
            score = stats["lower_bound"]
        else:
            score = -math.inf
        rows.append({"signature": sig, "source_rank": source_rank, "score": float(score), **stats})

    ranked = sorted(rows, key=lambda r: (r["score"], -float(r["source_rank"])), reverse=True)
    if not ranked or not np.isfinite(float(ranked[0]["score"])):
        return "", "insufficient_history_no_trade", None
    if ranking_policy == "past_lower_bound" and float(ranked[0]["score"]) < float(min_lower_bound_bps):
        return "", "lower_bound_gate_no_trade", float(ranked[0]["score"])
    return str(ranked[0]["signature"]), ranking_policy, float(ranked[0]["score"])


def _history_stats(hist: pd.DataFrame, *, lower_bound_z: float = 1.645) -> dict[str, float]:
    if hist.empty:
        return {"trades": 0.0, "periods_with_trades": 0.0, "mean": 0.0, "total": 0.0, "hit_rate": 0.0, "std": 0.0, "lower_bound": -math.inf, "max_drawdown": 0.0}
    trades = pd.to_numeric(hist.get("trades", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    totals = pd.to_numeric(hist.get("total_net_pnl_bps", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    total_trades = float(trades.sum())
    total_pnl = float(totals.sum())
    mean = total_pnl / total_trades if total_trades > 0 else 0.0
    # Approximate trade-level variance from period means/stds.
    weighted_var_num = 0.0
    wins = 0.0
    for _, row in hist.iterrows():
        n = float(row.get("trades", 0.0) or 0.0)
        if n <= 0:
            continue
        std = float(row.get("std_net_pnl_bps", 0.0) or 0.0)
        m = float(row.get("mean_net_pnl_bps", 0.0) or 0.0)
        weighted_var_num += n * (std * std + (m - mean) ** 2)
        wins += n * float(row.get("hit_rate", 0.0) or 0.0)
    std = math.sqrt(max(weighted_var_num / total_trades, 0.0)) if total_trades > 0 else 0.0
    lower = mean - float(lower_bound_z) * std / math.sqrt(total_trades) if total_trades > 0 else -math.inf
    # Drawdown over period totals is coarse but useful for ranking.
    eq = totals.cumsum().to_numpy(dtype=float)
    dd = float((eq - np.maximum.accumulate(eq)).min()) if len(eq) else 0.0
    return {
        "trades": total_trades,
        "periods_with_trades": float((trades > 0).sum()),
        "mean": float(mean),
        "total": float(total_pnl),
        "hit_rate": float(wins / total_trades) if total_trades > 0 else 0.0,
        "std": float(std),
        "lower_bound": float(lower),
        "max_drawdown": float(dd),
    }


def _rank_period_candidates(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return metrics
    m = metrics.copy()
    m["oracle_rank_score"] = (
        m["mean_net_pnl_bps"].astype(float).clip(-20, 20)
        + 0.003 * m["total_net_pnl_bps"].astype(float).clip(-2000, 2000)
        + 0.10 * m["hit_rate"].astype(float)
        - 0.01 * m["max_drawdown_bps"].astype(float).abs().clip(0, 1000)
        + 0.002 * m["trades"].astype(float).clip(0, 300)
    )
    return m.sort_values(["trades", "oracle_rank_score", "total_net_pnl_bps"], ascending=[False, False, False]).reset_index(drop=True)


def _ledger_for_selection(
    *,
    ledger_by_template_period: dict[tuple[str, int], pd.DataFrame],
    signature: str,
    period_id: int,
    fallback_frame: pd.DataFrame,
    period_spec: PeriodSpec,
) -> pd.DataFrame:
    if signature and (signature, period_id) in ledger_by_template_period:
        out = ledger_by_template_period[(signature, period_id)].copy()
        out["selection_active"] = 1
        return out
    out = fallback_frame.copy().reset_index(drop=True)
    out.insert(0, "period_id", int(period_id))
    out["fold"] = int(period_spec.fold)
    out["segment"] = int(period_spec.segment)
    out["source_rank"] = np.nan
    out["template_signature"] = ""
    out["candidate_json"] = ""
    out["signal"] = 0
    out["traded"] = 0
    out["gross_pnl_bps"] = 0.0
    out["cost_bps"] = 0.0
    out["net_pnl_bps"] = 0.0
    out["equity_bps"] = 0.0
    out["selection_active"] = 0
    return out


def _metrics_for_signature(period_metrics: pd.DataFrame, signature: str) -> dict[str, float]:
    if not signature or period_metrics.empty:
        return {"trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    row = period_metrics[period_metrics["template_signature"] == signature]
    if row.empty:
        return {"trades": 0.0, "hit_rate": 0.0, "mean_net_pnl_bps": 0.0, "total_net_pnl_bps": 0.0}
    r = row.iloc[0]
    return {
        "trades": float(r.get("trades", 0.0) or 0.0),
        "hit_rate": float(r.get("hit_rate", 0.0) or 0.0),
        "mean_net_pnl_bps": float(r.get("mean_net_pnl_bps", 0.0) or 0.0),
        "total_net_pnl_bps": float(r.get("total_net_pnl_bps", 0.0) or 0.0),
    }


def _source_rank_for_sig(template_df: pd.DataFrame, signature: str) -> int | None:
    if not signature or template_df.empty:
        return None
    row = template_df[template_df["template_signature"] == signature]
    if row.empty:
        return None
    return int(row.iloc[0]["source_rank"])


def _trade_pnl(frame: pd.DataFrame) -> pd.Series:
    if frame.empty or "traded" not in frame.columns or "net_pnl_bps" not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame.loc[frame["traded"].astype(int) == 1, "net_pnl_bps"], errors="coerce").dropna()


def _ledger_summary(ledger: pd.DataFrame, periods: pd.DataFrame) -> dict[str, object]:
    pnl = _trade_pnl(ledger)
    periods_with_trades = 0
    if not ledger.empty and "period_id" in ledger.columns and "traded" in ledger.columns:
        periods_with_trades = int(ledger.loc[ledger["traded"].astype(int) == 1, "period_id"].nunique())
    return {
        "periods": int(len(periods)),
        "periods_with_trades": periods_with_trades,
        "trades": int(len(pnl)),
        "total_net_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
        "mean_net_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "median_net_pnl_bps": float(pnl.median()) if len(pnl) else 0.0,
        "hit_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "std_net_pnl_bps": float(pnl.std(ddof=0)) if len(pnl) else 0.0,
        "max_drawdown_bps": _max_drawdown(pnl),
        **_period_trade_summary(ledger),
        "profit_factor": _profit_factor(pnl),
    }


def _period_trade_summary(ledger: pd.DataFrame) -> dict[str, object]:
    if ledger.empty or "period_id" not in ledger.columns or "traded" not in ledger.columns or "net_pnl_bps" not in ledger.columns:
        return {
            "period_trades_min": 0,
            "period_mean_net_pnl_bps_min": 0.0,
            "period_total_net_pnl_bps_min": 0.0,
            "periods_positive_total": 0,
        }
    trades = ledger[ledger["traded"].astype(int) == 1].copy()
    if trades.empty:
        return {
            "period_trades_min": 0,
            "period_mean_net_pnl_bps_min": 0.0,
            "period_total_net_pnl_bps_min": 0.0,
            "periods_positive_total": 0,
        }
    grouped = trades.groupby("period_id")["net_pnl_bps"].agg(["count", "mean", "sum"]).reset_index()
    return {
        "period_trades_min": int(grouped["count"].min()) if len(grouped) else 0,
        "period_mean_net_pnl_bps_min": float(grouped["mean"].min()) if len(grouped) else 0.0,
        "period_total_net_pnl_bps_min": float(grouped["sum"].min()) if len(grouped) else 0.0,
        "periods_positive_total": int((grouped["sum"] > 0).sum()) if len(grouped) else 0,
    }


def _max_drawdown(pnl: pd.Series) -> float:
    if len(pnl) == 0:
        return 0.0
    equity = pnl.cumsum().to_numpy(dtype=float)
    return float((equity - np.maximum.accumulate(equity)).min())


def _profit_factor(pnl: pd.Series) -> float:
    if len(pnl) == 0:
        return 0.0
    gains = float(pnl[pnl > 0].sum())
    losses = float(-pnl[pnl < 0].sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _evaluate_sequential_gate(
    summary: dict[str, object],
    bootstrap: dict[str, object],
    shift_summary: dict[str, object],
    stress_gate: dict[str, object],
    gate_config: SequentialGateConfig,
) -> dict[str, object]:
    checks = {
        "enough_oof_trades": float(summary.get("trades", 0)) >= gate_config.min_oof_trades,
        "enough_periods_with_trades": float(summary.get("periods_with_trades", 0)) >= gate_config.min_periods_with_trades,
        "positive_oof_mean": float(summary.get("mean_net_pnl_bps", -999.0)) > gate_config.min_oof_mean_net_bps,
        "positive_period_min_mean": float(summary.get("period_mean_net_pnl_bps_min", -999.0)) > gate_config.min_period_mean_net_bps,
        "positive_bootstrap_p05": float(bootstrap.get("mean_p05_bps", -999.0)) > gate_config.min_bootstrap_p05_bps,
        "shift_null_mean_ok": float(shift_summary.get("p_null_mean_ge_actual", 1.0)) <= gate_config.max_shift_null_p_mean,
        "shift_null_total_ok": float(shift_summary.get("p_null_total_ge_actual", 1.0)) <= gate_config.max_shift_null_p_total,
        "stress_gate_ok": bool(stress_gate.get("passed")) if gate_config.require_stress_gate else True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {"passed": not failed, "failed_checks": failed, "checks": checks}


def _regret_summary(selected: dict[str, object], oracle: dict[str, object], source: dict[str, object]) -> dict[str, float]:
    selected_total = float(selected.get("total_net_pnl_bps", 0.0))
    oracle_total = float(oracle.get("total_net_pnl_bps", 0.0))
    source_total = float(source.get("total_net_pnl_bps", 0.0))
    return {
        "oracle_minus_selected_total_bps": float(oracle_total - selected_total),
        "selected_minus_source_rank1_total_bps": float(selected_total - source_total),
        "oracle_minus_source_rank1_total_bps": float(oracle_total - source_total),
    }


def _candidate_fields(candidate: SelectiveCandidate) -> dict[str, object]:
    return {
        "edge_threshold": float(candidate.edge_threshold),
        "direction_mode": candidate.direction_mode,
        "signed_col": candidate.signed_col,
        "signed_mode": candidate.signed_mode,
        "signed_abs_threshold": float(candidate.signed_abs_threshold or 0.0),
        "spread_max_bps": candidate.spread_max_bps,
        "vol_col": candidate.vol_col,
        "vol_mode": candidate.vol_mode,
        "vol_min": candidate.vol_min,
        "vol_max": candidate.vol_max,
    }


def _write_report(path: str | Path, result: dict[str, object], selections: pd.DataFrame, stress: pd.DataFrame, shift_null: pd.DataFrame) -> None:
    lines = [
        "# Research V11 Sequential Template Audit",
        "",
        "This report tests whether a frozen template family can be selected online using only earlier validation periods.",
        "It is stricter than validation-ranked oracle selection and closer to the intended multi-session workflow.",
        "",
        "## Settings",
        "",
        "```json",
        json.dumps({k: result.get(k) for k in ["source_ensemble_dir", "horizon_sec", "cost_bps", "latency_sec", "templates_tested", "periods", "period_sec", "ranking_policy", "cold_start_policy", "warmup_periods", "min_history_trades", "min_history_periods", "lower_bound_z", "min_lower_bound_bps"]}, indent=2),
        "```",
        "",
        "## Online selected summary",
        "",
        "```json",
        json.dumps(result.get("selected_online", {}), indent=2),
        "```",
        "",
        "## Comparators",
        "",
        "```json",
        json.dumps({"source_rank1": result.get("source_rank1", {}), "period_oracle": result.get("period_oracle", {}), "regret": result.get("regret", {})}, indent=2),
        "```",
        "",
        "## Bootstrap / null / gate",
        "",
        "```json",
        json.dumps({"bootstrap": result.get("bootstrap", {}), "shift_null": result.get("shift_null", {}), "stress_gate": result.get("stress_gate", {}), "gate": result.get("gate", {})}, indent=2),
        "```",
        "",
        "## Period selections",
        "",
    ]
    show_cols = [
        "period_id",
        "fold",
        "segment",
        "selection_reason",
        "selected_source_rank",
        "selection_score",
        "selected_trades",
        "selected_mean_net_pnl_bps",
        "selected_total_net_pnl_bps",
        "source_rank1_total_net_pnl_bps",
        "oracle_source_rank",
        "oracle_total_net_pnl_bps",
    ]
    lines.append(selections[[c for c in show_cols if c in selections.columns]].to_markdown(index=False) if not selections.empty else "No selections.")
    lines.extend(["", "## Stress sweep", ""])
    stress_cols = ["cost_bps", "latency_sec", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps", "max_drawdown_bps"]
    lines.append(stress[[c for c in stress_cols if c in stress.columns]].to_markdown(index=False) if not stress.empty else "No stress rows.")
    lines.extend(["", "## Shift null distribution", ""])
    null_cols = ["shift_rows", "trades", "hit_rate", "mean_net_pnl_bps", "total_net_pnl_bps"]
    lines.append(shift_null[[c for c in null_cols if c in shift_null.columns]].head(20).to_markdown(index=False) if not shift_null.empty else "No null rows.")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "A pass requires online-selected trades to remain positive after bootstrap, shifted-signal null, and cost/latency stress.  The period oracle is diagnostic only because it chooses the best template after seeing each period.",
        "",
    ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")
