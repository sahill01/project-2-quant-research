"""Synthetic causality tests for swing-based double-top/bottom events."""

import pandas as pd

from research.chart_patterns import detect_double_top_bottom
from research.structure_features import confirmed_swing_points


def candles(highs, lows):
    timestamps = pd.date_range(
        "2026-05-01T00:00:00Z", periods=len(highs), freq="1h"
    )
    opens = [(high + low) / 2.0 for high, low in zip(highs, lows)]
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": opens,
        "volume": [1.0] * len(highs),
    })


def double_top_frame():
    return candles(
        [12.0, 15.0, 13.0, 14.9, 12.0],
        [10.0, 11.0, 8.0, 10.0, 9.0],
    )


def double_bottom_frame():
    return candles(
        [12.0, 13.0, 16.0, 13.0, 14.0],
        [10.0, 5.0, 8.0, 5.1, 9.0],
    )


def detect(
    frame,
    *,
    right_bars=1,
    tolerance=0.02,
    minimum=2,
    maximum=2,
):
    return detect_double_top_bottom(
        frame,
        timeframe="1h",
        left_bars=1,
        right_bars=right_bars,
        price_tolerance_fraction=tolerance,
        min_separation_bars=minimum,
        max_separation_bars=maximum,
    )


def test_valid_double_top_and_bottom_use_confirmed_swings():
    top_frame = double_top_frame()
    top = detect(top_frame)
    assert len(top) == 1
    assert top.loc[0, "pattern_type"] == "double_top"
    assert top.loc[0, "first_pivot_price"] == 15.0
    assert top.loc[0, "middle_pivot_price"] == 8.0
    assert top.loc[0, "second_pivot_price"] == 14.9
    assert top.loc[0, "formation_time"] == top_frame.loc[3, "timestamp"]
    assert top.loc[0, "available_at"] == top_frame.loc[4, "available_at"]
    assert top.loc[0, "confirmation_status"] == "shape_confirmed"

    bottom_frame = double_bottom_frame()
    bottom = detect(bottom_frame)
    assert len(bottom) == 1
    assert bottom.loc[0, "pattern_type"] == "double_bottom"
    assert bottom.loc[0, "first_pivot_price"] == 5.0
    assert bottom.loc[0, "middle_pivot_price"] == 16.0
    assert bottom.loc[0, "second_pivot_price"] == 5.1
    assert bottom.loc[0, "available_at"] == bottom_frame.loc[4, "available_at"]


def test_tolerance_and_separation_boundaries_are_inclusive():
    frame = double_top_frame()
    tolerance_at_boundary = abs(15.0 - 14.9) / ((15.0 + 14.9) / 2.0)
    exact = detect(frame, tolerance=tolerance_at_boundary)
    assert len(exact) == 1
    assert detect(frame, tolerance=tolerance_at_boundary - 1e-6).empty

    assert len(detect(frame, minimum=2, maximum=2)) == 1
    assert detect(frame, minimum=3, maximum=4).empty
    assert detect(frame, minimum=1, maximum=1).empty


def test_second_extremum_is_not_available_until_its_swing_confirms():
    frame = double_top_frame()
    with_two_right_bars = candles(
        [12.0, 15.0, 13.0, 14.9, 12.0, 11.0],
        [10.0, 11.0, 8.0, 10.0, 9.0, 9.5],
    )
    assert detect(with_two_right_bars.iloc[:5], right_bars=2).empty
    result = detect(with_two_right_bars, right_bars=2)
    assert len(result) == 1
    assert result.loc[0, "formation_time"] == frame.loc[3, "timestamp"]
    assert result.loc[0, "available_at"] == with_two_right_bars.loc[5, "available_at"]
    assert result.loc[0, "available_at"] > result.loc[0, "formation_time"]


def test_overlapping_candidates_are_both_reported_with_stable_ids():
    frame = candles(
        [12.0, 15.0, 13.0, 14.9, 12.0, 15.1, 11.0],
        [10.0, 11.0, 8.0, 10.0, 9.0, 11.0, 9.0],
    )
    first = detect(frame, tolerance=0.02, minimum=2, maximum=2)
    second = detect(frame, tolerance=0.02, minimum=2, maximum=2)

    assert first["pattern_type"].tolist() == ["double_top", "double_top"]
    assert first["pattern_id"].is_unique
    assert first["pattern_id"].tolist() == second["pattern_id"].tolist()
    assert first.loc[0, "second_pivot_time"] == first.loc[1, "first_pivot_time"]


def test_prefix_invariance_future_perturbation_and_insufficient_history():
    frame = double_top_frame()
    full = detect(frame)
    assert detect(frame.iloc[:4].copy()).empty
    prefix = detect(frame.iloc[:5].copy())
    pd.testing.assert_frame_equal(full, prefix)

    changed = frame.copy()
    changed.loc[4, ["open", "high", "low", "close"]] = [
        20.0, 21.0, 19.0, 20.5
    ]
    assert detect(changed).empty
    pd.testing.assert_frame_equal(full, detect(frame))


def test_invalid_tolerances_and_separation_rules_are_rejected():
    frame = double_top_frame()
    for tolerance in (-0.01, 1.0, float("nan"), True):
        try:
            detect(frame, tolerance=tolerance)
        except ValueError as error:
            assert "price_tolerance_fraction" in str(error)
        else:
            raise AssertionError(f"Invalid tolerance {tolerance!r} was accepted")

    for minimum, maximum in ((0, 2), (2, 1), (1, True)):
        try:
            detect(frame, minimum=minimum, maximum=maximum)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid separation range was accepted")


def test_dual_pivot_is_reported_on_both_sides_but_not_ordered_as_two_candles():
    frame = candles([10.0, 20.0, 11.0], [8.0, 1.0, 9.0])
    swings = confirmed_swing_points(
        frame, timeframe="1h", left_bars=1, right_bars=1
    )
    assert swings.loc[2, "swing_high_price"] == 20.0
    assert swings.loc[2, "swing_low_price"] == 1.0
    assert swings.loc[2, "swing_high_pivot_time"] == frame.loc[1, "timestamp"]
    assert swings.loc[2, "swing_low_pivot_time"] == frame.loc[1, "timestamp"]
    # The chart scanner's stable same-row order is high then low, but its
    # strict pivot-index ordering forbids treating one candle as two swings.
    assert detect(frame, minimum=1, maximum=2).empty


def test_chart_api_rejects_availability_before_declared_candle_close():
    frame = double_top_frame()
    frame.loc[2, "available_at"] -= pd.Timedelta(minutes=59)
    try:
        detect(frame)
    except ValueError as error:
        assert "candle duration" in str(error)
    else:
        raise AssertionError("Premature chart-pattern availability was accepted")


def main():
    tests = [
        test_valid_double_top_and_bottom_use_confirmed_swings,
        test_tolerance_and_separation_boundaries_are_inclusive,
        test_second_extremum_is_not_available_until_its_swing_confirms,
        test_overlapping_candidates_are_both_reported_with_stable_ids,
        test_prefix_invariance_future_perturbation_and_insufficient_history,
        test_invalid_tolerances_and_separation_rules_are_rejected,
        test_dual_pivot_is_reported_on_both_sides_but_not_ordered_as_two_candles,
        test_chart_api_rejects_availability_before_declared_candle_close,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
