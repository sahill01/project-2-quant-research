"""Independent synthetic tests for objective candle-pattern geometry."""

import pandas as pd

from research.candlestick_patterns import detect_candlestick_patterns


def candles(rows):
    timestamps = pd.date_range(
        "2026-04-01T00:00:00Z", periods=len(rows), freq="1h"
    )
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "open": [row[0] for row in rows],
        "high": [row[1] for row in rows],
        "low": [row[2] for row in rows],
        "close": [row[3] for row in rows],
    })


def ids(frame):
    return detect_candlestick_patterns(frame, timeframe="1h")


def test_engulfing_patterns_use_opposite_real_bodies_and_containment():
    frame = candles([
        (12.0, 13.0, 9.0, 10.0),  # bearish body [10, 12]
        (9.0, 14.0, 8.0, 13.0),   # bullish body [9, 13]
        (10.0, 13.0, 9.0, 12.0),  # bullish body, no bearish reversal
        (13.0, 14.0, 8.0, 9.0),   # bearish body [9, 13]
    ])
    result = ids(frame)

    assert result["pattern_id"].tolist() == [
        "bullish_engulfing", "bearish_engulfing"
    ]
    assert result["candle_time"].tolist() == [
        frame.loc[1, "timestamp"], frame.loc[3, "timestamp"]
    ]
    assert result.loc[0, "available_at"] == frame.loc[1, "available_at"]
    assert result.loc[1, "available_at"] == frame.loc[3, "available_at"]


def test_hammer_and_shooting_star_meet_inclusive_wick_boundaries():
    # Each candle has body=1 and range=4; long wick is exactly 2x body,
    # short wick is exactly 1x body.
    frame = candles([
        (10.0, 12.0, 8.0, 11.0),  # lower wick 2, upper wick 1
        (10.5, 11.0, 10.0, 10.2),  # bearish, but neither wick pattern
        (11.0, 13.0, 9.0, 10.0),   # upper wick 2, lower wick 1
    ])
    result = ids(frame)

    assert result["pattern_id"].tolist() == ["hammer", "shooting_star"]
    assert result["available_at"].tolist() == [
        frame.loc[0, "available_at"], frame.loc[2, "available_at"]
    ]


def test_negative_examples_doji_and_zero_range_are_excluded():
    frame = candles([
        (10.0, 11.0, 9.0, 10.0),   # doji-like
        (10.0, 10.0, 10.0, 10.0),  # zero range
        (10.0, 12.0, 9.0, 11.0),   # lower/upper wick are too short
        (11.5, 13.0, 9.0, 10.5),  # opposite candle but does not engulf
    ])
    assert ids(frame).empty


def test_body_ratio_boundary_and_missing_engulfing_history():
    frame = candles([
        (10.0, 11.0, 1.0, 11.0),  # body/range exactly 0.10; excluded
    ])
    assert ids(frame).empty

    single = candles([(10.0, 11.0, 9.0, 10.8)])
    assert ids(single).empty


def test_pattern_events_are_prefix_invariant_and_future_independent():
    frame = candles([
        (12.0, 13.0, 9.0, 10.0),
        (9.0, 14.0, 8.0, 13.0),
        (10.0, 11.0, 9.0, 10.8),
        (10.0, 13.0, 7.0, 11.0),  # hammer
        (11.0, 12.0, 10.0, 10.5),
    ])
    full = ids(frame)
    cutoff = frame.loc[3, "available_at"]
    prefix = ids(frame.iloc[:4].copy())
    expected = full[full["available_at"] <= cutoff].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected, prefix)

    perturbed = frame.copy()
    perturbed.loc[4, ["open", "high", "low", "close"]] = [
        20.0, 30.0, 19.0, 29.0
    ]
    changed = ids(perturbed)
    actual = changed[changed["available_at"] <= cutoff].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected, actual)
    pd.testing.assert_frame_equal(full, ids(frame))


def test_invalid_inputs_and_timestamps_fail_closed():
    valid = candles([(10.0, 12.0, 8.0, 11.0)])
    for invalid_column, invalid_value in (("high", float("inf")), ("low", 12.0)):
        malformed = valid.copy()
        malformed.loc[0, invalid_column] = invalid_value
        try:
            ids(malformed)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid {invalid_column} input was accepted")

    unavailable = valid.copy()
    unavailable.loc[0, "available_at"] = unavailable.loc[0, "timestamp"]
    try:
        ids(unavailable)
    except ValueError as error:
        assert "available_at" in str(error)
    else:
        raise AssertionError("Open-time availability was accepted")

    unordered = pd.concat(
        [valid, candles([(10.0, 12.0, 8.0, 11.0)])], ignore_index=True
    )
    unordered.at[1, "timestamp"] = unordered.at[0, "timestamp"]
    unordered.at[1, "available_at"] = unordered.at[0, "available_at"]
    try:
        ids(unordered)
    except ValueError as error:
        assert "timestamps" in str(error)
    else:
        raise AssertionError("Duplicate timestamps were accepted")


def test_explicit_timeframe_accepts_close_and_rejects_early_availability():
    frame = candles([(10.0, 12.0, 8.0, 11.0)])
    result = ids(frame)
    assert result.loc[0, "available_at"] == frame.loc[0, "timestamp"] + pd.Timedelta(hours=1)

    premature = frame.copy()
    premature.loc[0, "available_at"] += pd.Timedelta(minutes=-59)
    try:
        detect_candlestick_patterns(premature, timeframe="1h")
    except ValueError as error:
        assert "candle duration" in str(error)
    else:
        raise AssertionError("Premature candle-pattern availability was accepted")

    inconsistent = frame.copy()
    inconsistent.loc[0, "available_at"] += pd.Timedelta(minutes=1)
    try:
        detect_candlestick_patterns(inconsistent, timeframe="1h")
    except ValueError as error:
        assert "candle duration" in str(error)
    else:
        raise AssertionError("Inconsistent candle timing was accepted")


def main():
    tests = [
        test_engulfing_patterns_use_opposite_real_bodies_and_containment,
        test_hammer_and_shooting_star_meet_inclusive_wick_boundaries,
        test_negative_examples_doji_and_zero_range_are_excluded,
        test_body_ratio_boundary_and_missing_engulfing_history,
        test_pattern_events_are_prefix_invariant_and_future_independent,
        test_invalid_inputs_and_timestamps_fail_closed,
        test_explicit_timeframe_accepts_close_and_rejects_early_availability,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
