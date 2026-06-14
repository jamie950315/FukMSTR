from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from .config import AppConfig
from .pipeline import run_train


def run_feature_ablation(
    *,
    book_path: str | Path,
    trades_path: str | Path | None,
    base_config_path: str | Path | None,
    out_dir: str | Path,
    horizon_sec: float,
    threshold_bps: float,
    model_type: str = "logistic",
    edge_threshold: float = 0.5,
    clean: bool = False,
) -> dict[str, object]:
    """Run feature-family ablations with identical label/model settings."""
    out = Path(out_dir)
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    variants = [
        ("01_base_lob", {"add_order_flow_features": False, "add_depth_shape_features": False, "add_multi_level_microprice": True, "add_lagged_features": True}),
        ("02_plus_ofi", {"add_order_flow_features": True, "add_depth_shape_features": False, "add_multi_level_microprice": True, "add_lagged_features": True}),
        ("03_plus_shape", {"add_order_flow_features": False, "add_depth_shape_features": True, "add_multi_level_microprice": True, "add_lagged_features": True}),
        ("04_no_lags", {"add_order_flow_features": True, "add_depth_shape_features": True, "add_multi_level_microprice": True, "add_lagged_features": False}),
        ("05_all_features", {"add_order_flow_features": True, "add_depth_shape_features": True, "add_multi_level_microprice": True, "add_lagged_features": True}),
    ]

    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for name, switches in variants:
        run_dir = out / name
        cfg = AppConfig.from_yaml(base_config_path)
        cfg.labels.horizon_sec = float(horizon_sec)
        cfg.labels.threshold_bps = float(threshold_bps)
        cfg.model.type = str(model_type)
        cfg.backtest.signal_edge_threshold = float(edge_threshold)
        for key, value in switches.items():
            setattr(cfg.features, key, value)
        cfg_path = run_dir / "config.yaml"
        run_dir.mkdir(parents=True, exist_ok=True)
        cfg.to_yaml(cfg_path)
        try:
            summary = run_train(book_path=book_path, trades_path=trades_path, config_path=cfg_path, out_dir=run_dir)
            metrics = summary.get("metrics", {}) if isinstance(summary.get("metrics"), dict) else {}
            bt = summary.get("backtest", {}) if isinstance(summary.get("backtest"), dict) else {}
            strict = summary.get("backtest_non_overlap", {}) if isinstance(summary.get("backtest_non_overlap"), dict) else {}
            row = {
                "variant": name,
                "feature_count": summary.get("feature_count"),
                "rows_total": summary.get("rows_total"),
                "accuracy": metrics.get("accuracy"),
                "balanced_accuracy": metrics.get("balanced_accuracy"),
                "macro_f1": metrics.get("macro_f1"),
                "majority_accuracy_valid": metrics.get("majority_accuracy_valid"),
                "accuracy_lift_vs_majority": metrics.get("accuracy_lift_vs_majority"),
                "event_trades": bt.get("trades"),
                "event_hit_rate": bt.get("hit_rate"),
                "event_mean_net_pnl_bps": bt.get("mean_net_pnl_bps"),
                "event_total_net_pnl_bps": bt.get("total_net_pnl_bps"),
                "strict_trades": strict.get("trades"),
                "strict_hit_rate": strict.get("hit_rate"),
                "strict_mean_net_pnl_bps": strict.get("mean_net_pnl_bps"),
                "strict_total_net_pnl_bps": strict.get("total_net_pnl_bps"),
                "run_dir": str(run_dir),
            }
            row["rank_score"] = _rank(row)
            rows.append(row)
        except Exception as exc:
            failures.append({"variant": name, "run_dir": str(run_dir), "error": repr(exc)})

    leaderboard = pd.DataFrame(rows)
    if not leaderboard.empty:
        leaderboard = leaderboard.sort_values(["rank_score", "strict_total_net_pnl_bps"], ascending=[False, False]).reset_index(drop=True)
        leaderboard.insert(0, "rank", range(1, len(leaderboard) + 1))
    leaderboard.to_csv(out / "ablation_leaderboard.csv", index=False)
    result = {
        "book_path": str(book_path),
        "trades_path": str(trades_path) if trades_path else None,
        "variants_requested": len(variants),
        "variants_completed": int(len(rows)),
        "failures": failures,
        "best": leaderboard.head(1).to_dict(orient="records")[0] if not leaderboard.empty else None,
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_ablation_report(out / "REPORT.md", result, leaderboard)
    return result


def write_ablation_report(path: str | Path, result: dict[str, object], leaderboard: pd.DataFrame) -> None:
    lines = [
        "# Feature Ablation Report",
        "",
        f"Book path: `{result.get('book_path')}`",
        f"Variants completed: {result.get('variants_completed')} / {result.get('variants_requested')}",
        "",
        "## Leaderboard",
        "",
    ]
    if leaderboard.empty:
        lines.append("No completed variants.")
    else:
        cols = [
            "rank",
            "variant",
            "feature_count",
            "balanced_accuracy",
            "macro_f1",
            "event_mean_net_pnl_bps",
            "event_total_net_pnl_bps",
            "strict_mean_net_pnl_bps",
            "strict_total_net_pnl_bps",
            "rank_score",
        ]
        lines.append(leaderboard[cols].to_markdown(index=False))
    if result.get("failures"):
        lines.extend(["", "## Failures", "", "```json", json.dumps(result["failures"], indent=2), "```"])
    lines.extend([
        "",
        "## Notes",
        "",
        "Ablation results should be read together with walk-forward validation. A feature family that helps one chronological split may still be unstable across market regimes.",
        "",
    ])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _rank(row: dict[str, object]) -> float:
    def f(key: str) -> float:
        try:
            return float(row.get(key) or 0.0)
        except Exception:
            return 0.0
    return (f("balanced_accuracy") - 1.0 / 3.0) + 0.25 * f("macro_f1") + 0.02 * max(min(f("strict_mean_net_pnl_bps"), 5.0), -5.0)
