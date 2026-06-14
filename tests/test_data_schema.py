from __future__ import annotations

import pandas as pd

from lob_microprice_lab.data_schema import timestamps_to_ns


def test_timestamps_to_ns_returns_nanoseconds_for_string_timestamps() -> None:
    ts = pd.Series(["2020-01-01T00:00:00Z", "2020-01-01T00:00:01Z"])

    values = timestamps_to_ns(ts)

    assert values[1] - values[0] == 1_000_000_000
