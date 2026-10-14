"""Causality tests for confirmed swing-point feature events."""

import pandas as pd

from research.structure_features import confirmed_swing_points


def swing_candles() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=8, freq="1h")
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "high": [10.0, 12.0, 15.0, 13.0, 14.0, 11.0, 10.0, 9.0],
        "low": [8.0, 9.0, 10.0, 8.5, 9.0, 6.0, 7.0, 8.0],
    })


def swings(frame: pd.DataFrame) -> pd.DataFrame:
    return confirmed_swing_points(frame, left_bars=1, right_bars=2)


def test_swing_point_is_emitted_at_confirmation_not_pivot_time():
    frame = swing_candles()
    result = swings(frame)

    assert pd.isna(result.loc[2, "swing_high_price"])
    assert pd.isna(result.loc[3, "swing_high_price"])
    assert result.loc[4, "swing_high_price"] == 15.0
    assert result.loc[4, "swing_high_pivot_time"] == frame.loc[2, "timestamp"]
    assert result.loc[4, "available_at"] == frame.loc[4, "available_at"]

    # The low at index 5 is confirmed only after two right-side candles.
    assert result.loc[7, "swing_low_price"] == 6.0
    assert result.loc[7, "swing_low_pivot_time"] == frame.loc[5, "timestamp"]
    assert result.loc[7, "available_at"] == frame.loc[7, "available_at"]


def test_future_perturbation_cannot_change_already_confirmed_swings():
    frame = swing_candles()
    original = swings(frame)
    perturbed = frame.copy()
    perturbed.loc[5:, "high"] *= 100
    perturbed.loc[5:, "low"] *= 100
    changed = swings(perturbed)
    pd.testing.assert_frame_equal(
        original.iloc[:5].reset_index(drop=True),
        changed.iloc[:5].reset_index(drop=True),
    )


def test_equal_extrema_and_invalid_windows_are_not_confirmed():
    frame = swing_candles()
    frame.loc[3, "high"] = frame.loc[2, "high"]
    result = swings(frame)
    assert pd.isna(result.loc[4, "swing_high_price"])

    try:
        confirmed_swing_points(frame, left_bars=0, right_bars=2)
    except ValueError as error:
        assert "positive integer" in str(error)
    else:
        raise AssertionError("Invalid swing confirmation window was accepted")

    unavailable = frame.copy()
    unavailable.loc[0, "available_at"] = unavailable.loc[0, "timestamp"]
    try:
        swings(unavailable)
    except ValueError as error:
        assert "must follow" in str(error)
    else:
        raise AssertionError("Candle was marked available at its open")


def main():
    tests = [
        test_swing_point_is_emitted_at_confirmation_not_pivot_time,
        test_future_perturbation_cannot_change_already_confirmed_swings,
        test_equal_extrema_and_invalid_windows_are_not_confirmed,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
