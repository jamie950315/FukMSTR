from pathlib import Path

import pandas as pd

from lob_microprice_lab.portfolio import combine_fixed_backtest_ledgers


def test_combine_fixed_backtest_ledgers_enforces_non_overlap(tmp_path: Path):
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    common = {
        "timestamp": [0, 10_000_000_000, 80_000_000_000],
        "traded": [1, 1, 1],
        "signal": [1, -1, 1],
        "net_pnl_bps": [2.0, -1.0, 3.0],
    }
    pd.DataFrame(common).to_csv(a, index=False)
    pd.DataFrame({**common, "timestamp": [5_000_000_000, 70_000_000_000, 90_000_000_000], "net_pnl_bps": [5.0, 4.0, -2.0]}).to_csv(b, index=False)
    result = combine_fixed_backtest_ledgers(backtest_paths=[a, b], horizon_secs=[60, 60], strategy_names=["a", "b"], out_dir=tmp_path / "out")
    summary = result["summary"]
    assert summary["proposed_trades"] == 6
    assert summary["trades"] == 2
    assert summary["total_net_pnl_bps"] == 6.0
