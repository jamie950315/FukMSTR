from pathlib import Path

from lob_microprice_lab.diagnostics import feature_forward_scan, profile_market_data
from lob_microprice_lab.sample_data import generate_sample_data


def test_profile_and_feature_scan(tmp_path: Path):
    book, trades = generate_sample_data(tmp_path / "data", rows=350, depth=5, seed=7)
    profile = profile_market_data(book_path=book, trades_path=trades, config_path=None, out_dir=tmp_path / "profile")
    assert profile["rows_features"] > 0
    assert (tmp_path / "profile" / "market_profile.json").exists()

    scan = feature_forward_scan(
        book_path=book,
        trades_path=trades,
        config_path=None,
        out_dir=tmp_path / "scan",
        horizons_sec=[1.0],
        threshold_bps=0.5,
        top_n=5,
    )
    assert scan["feature_count"] > 0
    assert (tmp_path / "scan" / "feature_forward_scan.csv").exists()
