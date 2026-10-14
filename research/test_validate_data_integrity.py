"""Regression tests for the standalone historical data validator."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from validate_data import validate_file


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
        "open": [100.0, 100.0],
        "high": [101.0, 101.0],
        "low": [99.0, 99.0],
        "close": [100.0, 100.0],
        "volume": [1.0, 2.0],
    })


def validate_synthetic(frame: pd.DataFrame, timeframe: str = "1h"):
    with TemporaryDirectory() as directory:
        path = Path(directory) / "synthetic.csv"
        frame.to_csv(path, index=False)
        with redirect_stdout(StringIO()):
            return validate_file(path, "SYN", timeframe)


def test_infinite_values_in_every_numeric_ohlcv_column_are_rejected():
    for column in ("open", "high", "low", "close", "volume"):
        frame = sample_frame()
        frame.loc[1, column] = float("inf")
        errors, _ = validate_synthetic(frame)
        assert any("infinite numeric OHLCV" in error for error in errors), (
            column, errors
        )


def test_regular_finite_dataset_passes():
    errors, warnings = validate_synthetic(sample_frame())
    assert errors == []
    assert warnings == []


def test_consistently_offset_candles_fail_alignment_validation():
    frame = sample_frame()
    frame["timestamp"] = [
        "2026-01-01T00:30:00Z", "2026-01-01T01:30:00Z"
    ]
    errors, _ = validate_synthetic(frame)
    assert any("not aligned to UTC 1h" in error for error in errors)


def test_invalid_timeframes_return_validation_errors_without_crashing():
    frame = sample_frame()
    for timeframe in ("0h", "-1h", "", "1.5h"):
        errors, _ = validate_synthetic(frame, timeframe)
        assert errors, timeframe


def main():
    tests = [
        test_infinite_values_in_every_numeric_ohlcv_column_are_rejected,
        test_regular_finite_dataset_passes,
        test_consistently_offset_candles_fail_alignment_validation,
        test_invalid_timeframes_return_validation_errors_without_crashing,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
