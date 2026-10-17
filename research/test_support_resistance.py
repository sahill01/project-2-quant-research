"""Synthetic causality and lifecycle tests for swing-derived zones."""

import pandas as pd

from research.support_resistance import confirmed_swing_zones


def candles(highs, lows, closes=None):
    timestamps = pd.date_range(
        "2026-03-01T00:00:00Z", periods=len(highs), freq="1h"
    )
    if closes is None:
        closes = [min(h, max(l, 9.5)) for h, l in zip(highs, lows)]
    opens = [min(h, max(l, c)) for h, l, c in zip(highs, lows, closes)]
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    })


def resistance_example():
    return candles(
        [10.0, 15.0, 12.0, 15.1, 15.1, 15.3, 14.0],
        [9.0, 9.0, 9.0, 14.8, 14.8, 14.9, 9.0],
        [9.5, 9.5, 9.5, 15.0, 15.0, 15.2, 10.0],
    )


def run(frame, width=0.02):
    return confirmed_swing_zones(
        frame,
        timeframe="1h",
        left_bars=1,
        right_bars=1,
        zone_width_fraction=width,
    )


def test_zone_is_created_at_confirmation_with_fixed_price_range():
    frame = resistance_example()
    result = run(frame)
    zone_id = f"resistance:{frame.loc[1, 'timestamp'].isoformat()}"
    creation = result[(result["zone_id"] == zone_id) & (result["event"] == "created")]

    assert len(creation) == 1
    row = creation.iloc[0]
    assert row["pivot_time"] == frame.loc[1, "timestamp"]
    assert row["created_at"] == frame.loc[2, "available_at"]
    assert row["event_time"] == frame.loc[2, "available_at"]
    assert row["created_at"] != row["pivot_time"]
    assert abs(row["lower_bound"] - 14.85) < 1e-12
    assert abs(row["upper_bound"] - 15.15) < 1e-12
    assert not (result["zone_id"].eq(zone_id) & (result["event_time"] < row["created_at"])).any()


def test_wick_touches_repeat_once_per_zone_and_candle():
    frame = resistance_example()
    result = run(frame)
    zone_id = f"resistance:{frame.loc[1, 'timestamp'].isoformat()}"
    target = result[result["zone_id"] == zone_id]

    assert target["event"].tolist() == ["created", "touched", "touched", "broken"]
    assert target["touch_count"].tolist() == [0, 1, 2, 2]
    assert target["event_time"].is_unique


def test_support_break_is_terminal_and_precedes_touch_counting():
    frame = candles(
        [15.0] * 7,
        [8.0, 8.0, 8.0, 5.0, 8.0, 4.7, 8.0],
        [10.0, 10.0, 10.0, 10.0, 10.0, 4.8, 10.0],
    )
    result = run(frame)
    zone_id = f"support:{frame.loc[3, 'timestamp'].isoformat()}"
    target = result[result["zone_id"] == zone_id]

    assert target["event"].tolist() == ["created", "broken"]
    assert target.iloc[-1]["state"] == "broken"
    assert target.iloc[-1]["touch_count"] == 0


def test_overlapping_zones_remain_distinct_and_execution_is_deterministic():
    frame = candles(
        [10.0, 15.0, 12.0, 10.0, 15.1, 11.0, 10.0],
        [8.0] * 7,
        [9.0] * 7,
    )
    first = confirmed_swing_zones(
        frame, timeframe="1h", left_bars=1, right_bars=1,
        zone_width_fraction=0.03
    )
    second = confirmed_swing_zones(
        frame, timeframe="1h", left_bars=1, right_bars=1,
        zone_width_fraction=0.03
    )
    pd.testing.assert_frame_equal(first, second)

    created = first[first["event"] == "created"]
    zones = created[created["zone_type"] == "resistance"]
    assert len(zones) >= 2
    first_zone, second_zone = zones.iloc[0], zones.iloc[1]
    assert first_zone["zone_id"] != second_zone["zone_id"]
    assert max(first_zone["lower_bound"], second_zone["lower_bound"]) <= min(
        first_zone["upper_bound"], second_zone["upper_bound"]
    )


def test_prefix_invariance_future_perturbation_and_insufficient_history():
    frame = resistance_example()
    full = run(frame)
    prefix = run(frame.iloc[:5].copy())
    cutoff = frame.loc[4, "available_at"]
    pd.testing.assert_frame_equal(
        full[full["event_time"] <= cutoff].reset_index(drop=True),
        prefix.reset_index(drop=True),
    )

    changed = frame.copy()
    changed.loc[5:, ["open", "high", "low", "close"]] = [
        [20.0, 25.0, 19.0, 24.0], [21.0, 26.0, 20.0, 25.0]
    ]
    perturbed = run(changed)
    pd.testing.assert_frame_equal(
        full[full["event_time"] <= cutoff].reset_index(drop=True),
        perturbed[perturbed["event_time"] <= cutoff].reset_index(drop=True),
    )

    assert run(frame.iloc[:2].copy()).empty


def test_invalid_width_and_ohlc_are_rejected():
    frame = resistance_example()
    for width in (0.0, 2.0, float("nan"), True):
        try:
            run(frame, width)
        except ValueError as error:
            assert "zone_width_fraction" in str(error)
        else:
            raise AssertionError(f"Invalid zone width {width!r} was accepted")

    malformed = frame.copy()
    malformed.loc[0, "close"] = malformed.loc[0, "high"] + 1.0
    try:
        run(malformed)
    except ValueError as error:
        assert "OHLC relationships" in str(error)
    else:
        raise AssertionError("Invalid OHLC relationship was accepted")


def test_zone_api_rejects_availability_before_declared_candle_close():
    frame = resistance_example()
    frame.loc[2, "available_at"] -= pd.Timedelta(minutes=59)
    try:
        run(frame)
    except ValueError as error:
        assert "candle duration" in str(error)
    else:
        raise AssertionError("Premature zone availability was accepted")


def main():
    tests = [
        test_zone_is_created_at_confirmation_with_fixed_price_range,
        test_wick_touches_repeat_once_per_zone_and_candle,
        test_support_break_is_terminal_and_precedes_touch_counting,
        test_overlapping_zones_remain_distinct_and_execution_is_deterministic,
        test_prefix_invariance_future_perturbation_and_insufficient_history,
        test_invalid_width_and_ohlc_are_rejected,
        test_zone_api_rejects_availability_before_declared_candle_close,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
