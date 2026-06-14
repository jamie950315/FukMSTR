import pandas as pd

from lob_microprice_lab.kline_guard import KlineGuardSpec
from lob_microprice_lab.profit_success_fast import _family_specs, _stability


def test_profit_success_fast_stability_tracks_pair_blocks_and_loo():
    frame = pd.DataFrame(
        {
            "traded": [1] * 10,
            "net_pnl_bps": [1.0] * 10,
            "fold": [1] * 5 + [2] * 5,
        }
    )
    out = _stability(frame)
    assert out["positive_equal_trade_blocks_5"] == 5
    assert out["positive_equal_trade_blocks_10"] == 10
    assert out["equal_trade_block_5_min_total_bps"] > 0
    assert out["equal_trade_block_10_min_total_bps"] > 0
    assert out["leave_one_fold_out_min_total_bps"] == 5.0


def test_profit_success_fast_family_specs_dedupes_selected_candidate_tags():
    selected = KlineGuardSpec(
        edge_threshold=0.1,
        kline_alpha=0.125,
        ofi_col="ofi_sum_l5_norm",
        ofi_quantile=0.9,
        kline_col="kline_15s_rv_6_bps",
        kline_quantile=0.0,
        kline_operator=">=",
        directional=True,
    )
    specs = _family_specs(
        selected,
        alphas=[0.0, 0.125],
        ofi_cols=["ofi_sum_l5_norm"],
        ofi_qs=[0.9],
        k_cols=["kline_15s_rv_6_bps"],
        k_qs=[0.0],
    )
    selected_rows = [row for row in specs if row[0] == 0.125 and row[1].to_dict() == selected.to_dict()]
    assert len(selected_rows) == 1
    tags = set(selected_rows[0][2])
    assert {"selected_only", "alpha_family", "ofi_family", "kline_family"}.issubset(tags)
