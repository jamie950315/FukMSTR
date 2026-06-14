from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v115_btcusdc_v112_contrarian_sizing"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V115_BTCUSDC_V112_CONTRARIAN_SIZING_RESULTS.md"
V114_LEDGER = ROOT / "runs" / "research_v114_btcusdc_v112_guard_sweep" / "v114_selected_guard_trade_ledger.csv"

TARGET_IMPROVEMENT_RATE = 0.05
MAX_MONTH_DEGRADATION = 0.05
CONTRARIAN_WINDOW = 720
CONTRARIAN_AMP = 0.5
CONTRARIAN_SCALE_BPS = 800.0
MIN_POSITION_WEIGHT = 0.2
MAX_POSITION_WEIGHT = 2.0


def _max_drawdown_bps(pnl: pd.Series) -> float:
    equity = pd.to_numeric(pnl, errors="coerce").fillna(0.0).cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max()) if len(drawdown) else 0.0


def _aligned_prior_return_bps(signal: pd.Series, prior_ret_bps: pd.Series) -> pd.Series:
    signal_numeric = pd.to_numeric(signal, errors="coerce").fillna(0.0)
    prior_numeric = pd.to_numeric(prior_ret_bps, errors="coerce").fillna(0.0)
    return pd.Series(np.where(signal_numeric >= 0.0, prior_numeric, -prior_numeric), index=prior_ret_bps.index)


def _contrarian_position_weights(
    signal: pd.Series,
    prior_ret_bps: pd.Series,
    *,
    amp: float = CONTRARIAN_AMP,
    scale_bps: float = CONTRARIAN_SCALE_BPS,
    min_weight: float = MIN_POSITION_WEIGHT,
    max_weight: float = MAX_POSITION_WEIGHT,
) -> pd.Series:
    aligned = _aligned_prior_return_bps(signal, prior_ret_bps)
    raw = 1.0 - float(amp) * np.tanh(aligned / float(scale_bps))
    raw = pd.Series(raw, index=prior_ret_bps.index).clip(float(min_weight), float(max_weight))
    prior_mean = raw.expanding(min_periods=1).mean().shift(1).fillna(1.0)
    weights = (raw / prior_mean).clip(float(min_weight), float(max_weight))
    return weights.astype(float)


def _monthly_pnl(frame: pd.DataFrame, pnl_col: str, months: pd.Index | None = None) -> pd.Series:
    monthly = frame.groupby("month", sort=True)[pnl_col].sum()
    if months is not None:
        monthly = monthly.reindex(months, fill_value=0.0)
    return monthly


def _sizing_summary(weighted: pd.DataFrame, baseline_monthly: pd.Series) -> dict[str, object]:
    weighted_monthly = _monthly_pnl(weighted, "weighted_net_pnl_bps", baseline_monthly.index)
    baseline_total = float(baseline_monthly.sum())
    weighted_total = float(weighted_monthly.sum())
    target_total = baseline_total * (1.0 + TARGET_IMPROVEMENT_RATE)
    month_floor = baseline_monthly * (1.0 - MAX_MONTH_DEGRADATION)
    month_deltas = weighted_monthly - baseline_monthly
    failed_months = weighted_monthly.loc[weighted_monthly < month_floor]
    return {
        "trade_count": int(len(weighted)),
        "baseline_total_net_pnl_bps": baseline_total,
        "target_total_net_pnl_bps": float(target_total),
        "weighted_total_net_pnl_bps": weighted_total,
        "improvement_bps": float(weighted_total - baseline_total),
        "improvement_rate": float(weighted_total / baseline_total - 1.0) if baseline_total > 0.0 else math.nan,
        "five_percent_target_met": bool(weighted_total >= target_total),
        "month_guard_passed": bool((weighted_monthly >= month_floor).all()),
        "selected_gate_passed": bool(weighted_total >= target_total and (weighted_monthly >= month_floor).all()),
        "win_rate": float((weighted["weighted_net_pnl_bps"] > 0.0).mean()) if len(weighted) else 0.0,
        "max_drawdown_bps": _max_drawdown_bps(weighted["weighted_net_pnl_bps"]),
        "position_weight_mean": float(weighted["position_weight"].mean()) if len(weighted) else 0.0,
        "position_weight_min": float(weighted["position_weight"].min()) if len(weighted) else 0.0,
        "position_weight_max": float(weighted["position_weight"].max()) if len(weighted) else 0.0,
        "worst_month_delta_bps": float(month_deltas.min()) if len(month_deltas) else 0.0,
        "worst_month_degradation_rate": float((month_deltas / baseline_monthly).min()) if len(month_deltas) else 0.0,
        "failed_months": ";".join(failed_months.index.astype(str).tolist()),
        "month_positive_count": int((weighted_monthly > 0.0).sum()),
        "month_count": int(len(weighted_monthly)),
        "april_2026_net_pnl_bps": float(weighted_monthly.loc["2026-04"]) if "2026-04" in weighted_monthly.index else math.nan,
    }


def _month_table(weighted: pd.DataFrame, baseline_monthly: pd.Series) -> pd.DataFrame:
    weighted_monthly = _monthly_pnl(weighted, "weighted_net_pnl_bps", baseline_monthly.index)
    out = pd.DataFrame(
        {
            "month": baseline_monthly.index,
            "v114_net_pnl_bps": baseline_monthly.to_numpy(float),
            "v115_weighted_net_pnl_bps": weighted_monthly.to_numpy(float),
        }
    )
    out["delta_bps"] = out["v115_weighted_net_pnl_bps"] - out["v114_net_pnl_bps"]
    out["degradation_rate"] = out["delta_bps"] / out["v114_net_pnl_bps"]
    out["month_guard_passed"] = out["v115_weighted_net_pnl_bps"] >= out["v114_net_pnl_bps"] * (
        1.0 - MAX_MONTH_DEGRADATION
    )
    return out


def _write_report(payload: dict[str, object], month_table: pd.DataFrame) -> None:
    selected = payload["selected"]
    lines = [
        "# Research V115 BTCUSDC V112 Contrarian Sizing Results",
        "",
        "## Decision",
        "",
        f"- Base ledger: `V114 short_uptrend_veto_ret30_gt_150`",
        f"- Sizing overlay: `contrarian_ret{CONTRARIAN_WINDOW}_amp{CONTRARIAN_AMP}_scale{CONTRARIAN_SCALE_BPS:g}`",
        f"- Five percent target total: `{selected['target_total_net_pnl_bps']:.6f}` bps",
        f"- V114 total: `{selected['baseline_total_net_pnl_bps']:.6f}` bps",
        f"- V115 total: `{selected['weighted_total_net_pnl_bps']:.6f}` bps",
        f"- Improvement: `{selected['improvement_rate']:.6%}`",
        f"- Target met: `{selected['five_percent_target_met']}`",
        f"- Month guard passed: `{selected['month_guard_passed']}`",
        f"- Selected gate passed: `{selected['selected_gate_passed']}`",
        f"- Trade count: `{selected['trade_count']}`",
        f"- Win rate: `{selected['win_rate']:.6%}`",
        f"- Max drawdown: `{selected['max_drawdown_bps']:.6f}` bps",
        f"- Position weight mean/min/max: `{selected['position_weight_mean']:.6f}` / `{selected['position_weight_min']:.6f}` / `{selected['position_weight_max']:.6f}`",
        f"- 2026-04 PnL: `{selected['april_2026_net_pnl_bps']:.6f}` bps",
        f"- Worst monthly degradation: `{selected['worst_month_degradation_rate']:.6%}`",
        "",
        "## Month Table",
        "",
        month_table.to_csv(index=False).strip(),
        "",
        "## Interpretation",
        "",
        "V115 keeps the V114 trade set unchanged and applies a live-feasible contrarian sizing overlay. It reduces size when the selected direction follows the prior 12-hour move, and increases size when the selected direction fades that move. The expanding normalizer uses only prior trades, so the average exposure adjustment does not use future rows. This remains a research candidate, not a live trading guarantee.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, object]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    ledger = pd.read_csv(V114_LEDGER)
    ledger["timestamp"] = pd.to_datetime(ledger["timestamp"], utc=True)
    ledger["month"] = ledger["timestamp"].dt.strftime("%Y-%m")
    ledger = ledger.sort_values("timestamp").reset_index(drop=True)
    baseline_monthly = _monthly_pnl(ledger, "net_pnl_bps")

    prior_col = f"prior_ret_{CONTRARIAN_WINDOW}_bps"
    weighted = ledger.copy()
    weighted["aligned_prior_ret_720_bps"] = _aligned_prior_return_bps(weighted["signal"], weighted[prior_col])
    weighted["position_weight"] = _contrarian_position_weights(weighted["signal"], weighted[prior_col])
    weighted["weighted_gross_pnl_bps"] = weighted["gross_pnl_bps"] * weighted["position_weight"]
    weighted["weighted_net_pnl_bps"] = weighted["net_pnl_bps"] * weighted["position_weight"]
    weighted["weighted_equity_bps"] = weighted["weighted_net_pnl_bps"].cumsum()

    month_table = _month_table(weighted, baseline_monthly)
    selected = _sizing_summary(weighted, baseline_monthly)

    ledger_path = OUT_DIR / "v115_weighted_trade_ledger.csv"
    month_path = OUT_DIR / "v115_months.csv"
    summary_path = OUT_DIR / "v115_summary.json"
    weighted.to_csv(ledger_path, index=False)
    month_table.to_csv(month_path, index=False)

    payload = {
        "version": "v115_btcusdc_v112_contrarian_sizing",
        "base_version": "v114_btcusdc_v112_guard_sweep",
        "config": {
            "contrarian_window": CONTRARIAN_WINDOW,
            "contrarian_amp": CONTRARIAN_AMP,
            "contrarian_scale_bps": CONTRARIAN_SCALE_BPS,
            "min_position_weight": MIN_POSITION_WEIGHT,
            "max_position_weight": MAX_POSITION_WEIGHT,
            "target_improvement_rate": TARGET_IMPROVEMENT_RATE,
            "max_month_degradation": MAX_MONTH_DEGRADATION,
            "normalizer": "expanding prior-trade mean of raw weights",
        },
        "selected": selected,
        "outputs": {
            "summary_json": str(summary_path),
            "weighted_trade_ledger": str(ledger_path),
            "months": str(month_path),
            "report": str(REPORT_PATH),
        },
    }
    summary_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_report(payload, month_table)
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
