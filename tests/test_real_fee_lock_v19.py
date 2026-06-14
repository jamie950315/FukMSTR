from __future__ import annotations

import pandas as pd

from lob_microprice_lab.real_fee_lock import (
    FeeGuardFilterSpec,
    RealFeeSpec,
    _mask_for_filters,
    default_v19_fee_filters,
)


def test_real_fee_percent_to_bps() -> None:
    fees = RealFeeSpec(taker_fee_percent=0.0400, maker_fee_percent=0.0000)
    assert fees.taker_fee_bps_per_side == 4.0
    assert fees.maker_fee_bps_per_side == 0.0
    assert fees.taker_taker_roundtrip_bps == 8.0


def test_fee_guard_filter_transforms() -> None:
    frame = pd.DataFrame({
        "prob_edge": [0.2, -0.3, 0.1],
        "kline_15s_signal": [0.5, 0.5, -0.5],
        "raw_col": [1.0, 2.0, 3.0],
    })
    directions = pd.Series([1, -1, 1]).to_numpy()
    specs = [
        FeeGuardFilterSpec("abs", "prob_edge", ">=", 0.15),
        FeeGuardFilterSpec("signed", "kline_15s_signal", ">=", -0.6),
        FeeGuardFilterSpec("raw", "raw_col", "<=", 2.0),
    ]
    mask = _mask_for_filters(frame, directions, specs)
    assert mask.tolist() == [True, True, False]


def test_default_v19_fee_filters_are_frozen() -> None:
    filters = default_v19_fee_filters()
    assert len(filters) == 3
    assert filters[0].column == "kline_15s_signal"
    assert filters[0].transform == "signed"
    assert filters[1].column == "kline_1m_rv_3_bps"
    assert filters[2].column == "kline_1m_range_z_6"
