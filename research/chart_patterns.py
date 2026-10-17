"""Causal chart-pattern features built from confirmed swing events."""

import math
from numbers import Real

import pandas as pd

from .structure_features import confirmed_swing_points


EVENT_COLUMNS = [
    "pattern_id",
    "pattern_type",
    "first_pivot_time",
    "first_pivot_price",
    "middle_pivot_time",
    "middle_pivot_price",
    "second_pivot_time",
    "second_pivot_price",
    "formation_time",
    "available_at",
    "confirmation_status",
]


def detect_double_top_bottom(
    candles: pd.DataFrame,
    *,
    timeframe: str,
    left_bars: int,
    right_bars: int,
    price_tolerance_fraction: float,
    min_separation_bars: int,
    max_separation_bars: int,
) -> pd.DataFrame:
    """Emit every qualifying adjacent H-L-H or L-H-L confirmed swing triple.

    The first and second extrema must be within the supplied relative
    tolerance (absolute price difference divided by their mean). Their pivot
    index separation is inclusive of the supplied minimum and maximum. The
    intervening confirmed swing must be strictly below both tops or above
    both bottoms. A neckline break is not required: ``shape_confirmed`` means
    only that all three swings and geometric conditions are confirmed.
    """
    if (
        isinstance(price_tolerance_fraction, bool)
        or not isinstance(price_tolerance_fraction, Real)
        or not math.isfinite(float(price_tolerance_fraction))
        or not 0 <= float(price_tolerance_fraction) < 1
    ):
        raise ValueError("price_tolerance_fraction must be finite in [0, 1)")
    for name, value in (
        ("min_separation_bars", min_separation_bars),
        ("max_separation_bars", max_separation_bars),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if max_separation_bars < min_separation_bars:
        raise ValueError("max_separation_bars must be at least the minimum")

    swings = confirmed_swing_points(
        candles, timeframe=timeframe, left_bars=left_bars, right_bars=right_bars
    )
    swing_events = []
    for row_idx in range(len(swings)):
        # Stable within-row ordering for rare candles that qualify as both.
        for side, price_column, time_column in (
            ("high", "swing_high_price", "swing_high_pivot_time"),
            ("low", "swing_low_price", "swing_low_pivot_time"),
        ):
            price = swings[price_column].iloc[row_idx]
            if pd.notna(price):
                swing_events.append({
                    "side": side,
                    "price": float(price),
                    "pivot_time": swings[time_column].iloc[row_idx],
                    "pivot_index": row_idx - right_bars,
                    "available_at": swings["available_at"].iloc[row_idx],
                })

    output = []
    for end_idx in range(2, len(swing_events)):
        first, middle, second = swing_events[end_idx - 2:end_idx + 1]
        if not first["pivot_index"] < middle["pivot_index"] < second["pivot_index"]:
            continue
        sides = (first["side"], middle["side"], second["side"])
        if sides == ("high", "low", "high"):
            pattern_type = "double_top"
            middle_is_valid = middle["price"] < min(first["price"], second["price"])
        elif sides == ("low", "high", "low"):
            pattern_type = "double_bottom"
            middle_is_valid = middle["price"] > max(first["price"], second["price"])
        else:
            continue

        separation = second["pivot_index"] - first["pivot_index"]
        mean_extreme = (first["price"] + second["price"]) / 2.0
        difference_fraction = abs(first["price"] - second["price"]) / mean_extreme
        if not (
            min_separation_bars <= separation <= max_separation_bars
            and difference_fraction <= price_tolerance_fraction
            and middle_is_valid
        ):
            continue

        pattern_id = ":".join((
            pattern_type,
            first["pivot_time"].isoformat(),
            middle["pivot_time"].isoformat(),
            second["pivot_time"].isoformat(),
        ))
        output.append({
            "pattern_id": pattern_id,
            "pattern_type": pattern_type,
            "first_pivot_time": first["pivot_time"],
            "first_pivot_price": first["price"],
            "middle_pivot_time": middle["pivot_time"],
            "middle_pivot_price": middle["price"],
            "second_pivot_time": second["pivot_time"],
            "second_pivot_price": second["price"],
            "formation_time": second["pivot_time"],
            "available_at": second["available_at"],
            "confirmation_status": "shape_confirmed",
        })

    return pd.DataFrame(output, columns=EVENT_COLUMNS)
