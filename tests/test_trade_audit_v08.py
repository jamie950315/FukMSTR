import pandas as pd

from lob_microprice_lab.trade_audit import enrich_trade_paths, side_fold_summary, summarize_trade_ledger


def test_enrich_trade_paths_adds_mfe_mae_for_trades():
    frame = pd.DataFrame(
        {
            "timestamp": [0, 500_000_000, 1_000_000_000, 1_500_000_000],
            "best_bid": [99.9, 100.0, 100.4, 100.1],
            "best_ask": [100.1, 100.2, 100.6, 100.3],
            "signal": [1, 0, 0, 0],
            "traded": [1, 0, 0, 0],
            "entry_px_taker": [100.1, None, None, None],
            "net_pnl_bps": [1.0, 0.0, 0.0, 0.0],
        }
    )
    enriched = enrich_trade_paths(frame, horizon_sec=1.0, latency_sec=0.0)
    assert enriched.loc[0, "path_mfe_gross_bps"] > 0
    assert enriched.loc[0, "path_mae_gross_bps"] < 0


def test_summarize_trade_ledger_basic_metrics():
    trades = pd.DataFrame({"traded": [1, 1, 1], "signal": [1, -1, 1], "net_pnl_bps": [2.0, -1.0, 3.0], "fold": [1, 1, 2]})
    summary = summarize_trade_ledger(trades)
    assert summary["trades"] == 3
    assert summary["long_trades"] == 2
    assert summary["short_trades"] == 1
    assert summary["total_net_pnl_bps"] == 4.0
    assert summary["max_loss_streak"] == 1


def test_side_fold_summary_groups_sides():
    trades = pd.DataFrame({"fold": [1, 1, 2], "signal": [1, -1, -1], "net_pnl_bps": [2.0, -1.0, 3.0]})
    grouped = side_fold_summary(trades)
    assert set(grouped["side"]) == {"long", "short"}
    assert grouped["trades"].sum() == 3
