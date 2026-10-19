"""Fail-fast tests for malformed OHLCV input files."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from research.data_loader import load_ohlcv, load_ohlcv_before


COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": ["2026-01-01T00:00:00Z"],
        "open": [100.0],
        "high": [105.0],
        "low": [95.0],
        "close": [102.0],
        "volume": [1.0],
    })


def assert_rejected(frame: pd.DataFrame, message: str) -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.csv"
        frame.to_csv(path, index=False)
        try:
            load_ohlcv(path, "4h")
        except ValueError as error:
            assert message in str(error), str(error)
        else:
            raise AssertionError(f"Expected ValueError containing {message!r}")


def test_empty_dataset_is_rejected():
    assert_rejected(pd.DataFrame(columns=COLUMNS), "Dataset is empty")


def test_non_finite_ohlcv_is_rejected():
    frame = valid_frame()
    frame.loc[0, "high"] = float("inf")
    assert_rejected(frame, "non-finite")


def test_duplicate_timestamps_are_rejected_instead_of_dropped():
    frame = valid_frame()
    duplicate = frame.copy()
    duplicate.loc[0, "close"] = 99.0
    assert_rejected(
        pd.concat([frame, duplicate], ignore_index=True),
        "duplicate timestamps",
    )


def test_timestamps_off_utc_timeframe_grid_are_rejected():
    frame = valid_frame()
    frame["timestamp"] = ["2026-01-01T00:30:00Z"]
    assert_rejected(frame, "not aligned to UTC 4h")


def test_nonpositive_and_malformed_timeframes_are_rejected():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "valid.csv"
        valid_frame().to_csv(path, index=False)
        for timeframe in (
            "0h", "-1h", "", "h", "1.5h", "999999999999999999999999w"
        ):
            try:
                load_ohlcv(path, timeframe)
            except ValueError:
                pass
            else:
                raise AssertionError(
                    f"Invalid timeframe {timeframe!r} was accepted"
                )


def test_valid_dataset_is_preserved():
    frame = valid_frame()
    with TemporaryDirectory() as directory:
        path = Path(directory) / "valid.csv"
        frame.to_csv(path, index=False)
        loaded = load_ohlcv(path, "4h")
    assert len(loaded) == 1
    assert loaded.loc[0, "close"] == 102.0
    assert loaded.loc[0, "available_at"] == pd.Timestamp(
        "2026-01-01T04:00:00Z"
    )


def test_stage_bounded_loader_rejects_out_of_order_timestamp_after_boundary():
    frame = pd.DataFrame({
        "timestamp": [
            "2026-01-01T00:00:00Z",
            "2026-01-01T02:00:00Z",  # First candle at the exclusive boundary.
            "2026-01-01T01:00:00Z",  # Would otherwise be silently omitted.
        ],
        "open": [100.0, 100.0, 100.0],
        "high": [105.0, 105.0, 105.0],
        "low": [95.0, 95.0, 95.0],
        "close": [102.0, 102.0, 102.0],
        "volume": [1.0, 1.0, 1.0],
    })
    with TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.csv"
        frame.to_csv(path, index=False)
        try:
            load_ohlcv_before(path, "1h", "2026-01-01T03:00:00Z")
        except ValueError as error:
            assert "strictly increasing" in str(error)
        else:
            raise AssertionError("Out-of-order timestamp after boundary was ignored")


def main() -> None:
    tests = [
        test_empty_dataset_is_rejected,
        test_non_finite_ohlcv_is_rejected,
        test_duplicate_timestamps_are_rejected_instead_of_dropped,
        test_timestamps_off_utc_timeframe_grid_are_rejected,
        test_nonpositive_and_malformed_timeframes_are_rejected,
        test_valid_dataset_is_preserved,
        test_stage_bounded_loader_rejects_out_of_order_timestamp_after_boundary,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
