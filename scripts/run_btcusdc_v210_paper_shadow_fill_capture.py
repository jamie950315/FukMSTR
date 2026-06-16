from __future__ import annotations

import argparse
import json
from pathlib import Path

from lob_microprice_lab.paper_shadow_capture import PaperShadowCaptureConfig, run_paper_shadow_fill_capture
from lob_microprice_lab.paper_trading import BinancePublicTickerSource, CsvPriceSource, CsvSignalProvider


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "research_v210_paper_shadow_fill_capture"
FILL_AUDIT_PATH = ROOT / "runs" / "research_v205_execution_validation" / "fill_audit.csv"
REPORT_PATH = ROOT / "reports" / "RESEARCH_V210_BTCUSDC_PAPER_SHADOW_FILL_CAPTURE.md"


def _write_report(payload: dict[str, object], *, report_path: Path) -> None:
    decision = payload["decision"]
    evidence = payload["evidence"]
    config = payload["config"]
    outputs = payload["outputs"]
    lines = [
        "# Research V210 BTCUSDC Paper-Shadow Fill Capture",
        "",
        "## Decision",
        "",
        f"- Status: `{decision['status']}`",
        f"- Places live orders: `{decision['places_live_orders']}`",
        f"- Failed checks: `{', '.join(decision['failed_checks']) if decision['failed_checks'] else 'none'}`",
        f"- Message: {decision['message']}",
        "",
        "## Outputs",
        "",
        f"- Fill audit CSV: `{outputs['fill_audit_csv']}`",
        "",
        "## Evidence",
        "",
        f"- Snapshot count: `{evidence['snapshot_count']}`",
        f"- Fill count: `{evidence['fill_count']}`",
        f"- Rejected count: `{evidence['rejected_count']}`",
        f"- Rejected reasons: `{', '.join(evidence['rejected_reasons']) if evidence['rejected_reasons'] else 'none'}`",
        "",
        "## Iteration Metrics",
        "",
        "| Metric | V210 |",
        "|---|---:|",
        "| Strategy thresholds changed | No |",
        "| Entry/exit logic changed | No |",
        "| Leverage logic changed | No |",
        "| New backtest return improvement claimed | No |",
        "| Places live orders | No |",
        f"| Execution mode | {config['execution_mode']} |",
        f"| Fill audit rows | {evidence['fill_count']} |",
        "",
        "## Interpretation",
        "",
        "V210 creates a path for collecting V205/V209-compatible paper-shadow fill evidence from live market snapshots and realtime signals. It does not create synthetic fills when only synthetic prices are available, and it does not place exchange orders.",
        "",
        "Real-money use remains blocked until V205, V204, and the launch preflight pass with current evidence.",
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def run(
    *,
    signal_csv: Path,
    price_csv: Path | None = None,
    out_dir: Path = OUT_DIR,
    fill_audit_path: Path = FILL_AUDIT_PATH,
    report_path: Path = REPORT_PATH,
    symbol: str = "BTCUSDC",
    market: str = "spot",
    ticks: int = 0,
    interval_sec: float = 60.0,
    no_sleep: bool = False,
    capture_id: str = "paper-shadow-capture",
    evidence_source: str = "live_capture",
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    market_source = CsvPriceSource(price_csv, symbol=symbol) if price_csv is not None else BinancePublicTickerSource(symbol=symbol, market=market)
    signal_provider = CsvSignalProvider(signal_csv, default_symbol=symbol)
    payload = run_paper_shadow_fill_capture(
        market_source=market_source,
        signal_provider=signal_provider,
        fill_audit_path=fill_audit_path,
        config=PaperShadowCaptureConfig(
            symbol=symbol,
            capture_id=capture_id,
            evidence_source=evidence_source,
        ),
        ticks=ticks,
        interval_sec=interval_sec,
        sleep=not no_sleep,
    )
    payload["outputs"]["summary_json"] = str(out_dir / "v210_paper_shadow_fill_capture_summary.json")
    payload["outputs"]["report"] = str(report_path)
    (out_dir / "v210_paper_shadow_fill_capture_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_report(payload, report_path=report_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture BTCUSDC paper-shadow fill evidence for V205/V209.")
    parser.add_argument("--signal-csv", required=True)
    parser.add_argument("--price-csv", default=None)
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--fill-audit", default=str(FILL_AUDIT_PATH))
    parser.add_argument("--symbol", default="BTCUSDC")
    parser.add_argument("--market", choices=["spot", "um-futures"], default="spot")
    parser.add_argument("--ticks", type=int, default=0)
    parser.add_argument("--interval-sec", type=float, default=60.0)
    parser.add_argument("--capture-id", default="paper-shadow-capture")
    parser.add_argument("--evidence-source", default="live_capture")
    parser.add_argument("--no-sleep", action="store_true")
    args = parser.parse_args()
    payload = run(
        signal_csv=Path(args.signal_csv),
        price_csv=Path(args.price_csv) if args.price_csv else None,
        out_dir=Path(args.out),
        fill_audit_path=Path(args.fill_audit),
        symbol=args.symbol,
        market=args.market,
        ticks=args.ticks,
        interval_sec=args.interval_sec,
        no_sleep=args.no_sleep,
        capture_id=args.capture_id,
        evidence_source=args.evidence_source,
    )
    print(json.dumps(payload["decision"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
