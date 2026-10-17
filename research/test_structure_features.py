"""Causality tests for confirmed swing-point feature events."""

import pandas as pd

from research.structure_features import (
    confirmed_market_structure,
    confirmed_swing_points,
)


def swing_candles() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=8, freq="1h")
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "high": [10.0, 12.0, 15.0, 13.0, 14.0, 11.0, 10.0, 9.0],
        "low": [8.0, 9.0, 10.0, 8.5, 9.0, 6.0, 7.0, 8.0],
    })


def swings(frame: pd.DataFrame) -> pd.DataFrame:
    return confirmed_swing_points(
        frame, timeframe="1h", left_bars=1, right_bars=2
    )


def structure_candles() -> pd.DataFrame:
    timestamps = pd.date_range("2026-02-01T00:00:00Z", periods=9, freq="1h")
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "high": [10.0, 12.0, 11.0, 15.0, 12.0, 14.0, 11.0, 14.0, 10.5],
        "low": [8.0, 7.0, 9.0, 8.0, 10.0, 8.0, 11.0, 6.0, 9.0],
    })


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
        confirmed_swing_points(
            frame, timeframe="1h", left_bars=0, right_bars=2
        )
    except ValueError as error:
        assert "positive integer" in str(error)
    else:
        raise AssertionError("Invalid swing confirmation window was accepted")

    unavailable = frame.copy()
    unavailable.loc[0, "available_at"] = unavailable.loc[0, "timestamp"]
    try:
        swings(unavailable)
    except ValueError as error:
        assert "candle duration" in str(error)
    else:
        raise AssertionError("Candle was marked available at its open")


def test_structure_labels_compare_only_confirmed_same_side_swings():
    frame = structure_candles()
    result = confirmed_market_structure(
        frame, timeframe="1h", left_bars=1, right_bars=1
    )
    event_rows = [2, 4, 6, 8]

    assert result.loc[event_rows, "swing_high_structure"].tolist() == [
        "initial_high", "higher_high", "lower_high", "equal_high"
    ]
    assert result.loc[event_rows, "swing_low_structure"].tolist() == [
        "initial_low", "higher_low", "equal_low", "lower_low"
    ]
    for row in event_rows:
        assert result.loc[row, "available_at"] == frame.loc[row, "available_at"]
        assert result.loc[row, "swing_high_pivot_time"] == frame.loc[row - 1, "timestamp"]
        assert result.loc[row, "swing_low_pivot_time"] == frame.loc[row - 1, "timestamp"]


def test_structure_is_prefix_invariant_and_unconfirmed_tail_stays_empty():
    frame = structure_candles()
    full = confirmed_market_structure(
        frame, timeframe="1h", left_bars=1, right_bars=1
    )
    prefix = confirmed_market_structure(
        frame.iloc[:6], timeframe="1h", left_bars=1, right_bars=1
    )
    pd.testing.assert_frame_equal(
        full.iloc[:6].reset_index(drop=True),
        prefix.reset_index(drop=True),
        check_freq=False,
    )

    insufficient = confirmed_market_structure(
        frame.iloc[:2], timeframe="1h", left_bars=1, right_bars=1
    )
    assert insufficient["swing_high_structure"].isna().all()
    assert insufficient["swing_low_structure"].isna().all()

    changed_future = frame.copy()
    changed_future.loc[6:, ["high", "low"]] = [
        [100.0, 90.0], [120.0, 80.0], [110.0, 85.0]
    ]
    changed = confirmed_market_structure(
        changed_future, timeframe="1h", left_bars=1, right_bars=1
    )
    pd.testing.assert_frame_equal(
        full.iloc[:6].reset_index(drop=True),
        changed.iloc[:6].reset_index(drop=True),
        check_freq=False,
    )


def test_explicit_timeframe_rejects_premature_or_inconsistent_availability():
    frame = swing_candles()
    accepted = swings(frame)
    assert accepted.loc[4, "available_at"] == frame.loc[4, "timestamp"] + pd.Timedelta(hours=1)

    missing_candle_gap = frame.copy()
    missing_candle_gap.loc[4:, "timestamp"] += pd.Timedelta(hours=1)
    missing_candle_gap.loc[4:, "available_at"] += pd.Timedelta(hours=1)
    gap_result = swings(missing_candle_gap)
    assert gap_result.loc[4, "available_at"] == (
        missing_candle_gap.loc[4, "timestamp"] + pd.Timedelta(hours=1)
    )

    premature = frame.copy()
    premature.loc[4, "available_at"] = premature.loc[4, "timestamp"] + pd.Timedelta(minutes=1)
    try:
        swings(premature)
    except ValueError as error:
        assert "candle duration" in str(error)
    else:
        raise AssertionError("Premature swing input availability was accepted")

    inconsistent = frame.copy()
    inconsistent.loc[4, "available_at"] += pd.Timedelta(minutes=1)
    try:
        confirmed_market_structure(
            inconsistent, timeframe="1h", left_bars=1, right_bars=2
        )
    except ValueError as error:
        assert "candle duration" in str(error)
    else:
        raise AssertionError("Inconsistent structure availability was accepted")


def main():
    tests = [
        test_swing_point_is_emitted_at_confirmation_not_pivot_time,
        test_future_perturbation_cannot_change_already_confirmed_swings,
        test_equal_extrema_and_invalid_windows_are_not_confirmed,
        test_structure_labels_compare_only_confirmed_same_side_swings,
        test_structure_is_prefix_invariant_and_unconfirmed_tail_stays_empty,
        test_explicit_timeframe_rejects_premature_or_inconsistent_availability,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
