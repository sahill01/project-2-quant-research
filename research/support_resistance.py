"""Causal support/resistance zone lifecycle features; no trading signals."""

import math
from numbers import Real

import numpy as np
import pandas as pd

from .structure_features import confirmed_swing_points


EVENT_COLUMNS = [
    "zone_id",
    "zone_type",
    "lower_bound",
    "upper_bound",
    "pivot_time",
    "created_at",
    "event_time",
    "event",
    "state",
    "touch_count",
]


def confirmed_swing_zones(
    candles: pd.DataFrame,
    *,
    timeframe: str,
    left_bars: int,
    right_bars: int,
    zone_width_fraction: float,
) -> pd.DataFrame:
    """Return a causal event ledger for fixed-width swing-derived zones.

    Each confirmed high/low creates a distinct resistance/support zone. Its
    total width is ``zone_width_fraction`` times the pivot price, centered on
    that price. Zones are never merged. The confirmation candle creates the
    zone; lifecycle checks start on the following candle.

    On later candles a close beyond the far boundary emits a terminal
    ``broken`` event (and takes precedence over a wick touch). Otherwise, an
    inclusive candle-range intersection emits one ``touched`` event for that
    zone/candle. Consecutive intersecting candles each count as a touch.
    Output is an event ledger, not a per-candle state snapshot or a signal.
    """
    if (
        isinstance(zone_width_fraction, bool)
        or not isinstance(zone_width_fraction, Real)
        or not math.isfinite(float(zone_width_fraction))
        or not 0 < float(zone_width_fraction) < 2
    ):
        raise ValueError("zone_width_fraction must be finite and between 0 and 2")

    required = {"open", "high", "low", "close"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Candle frame missing columns: {sorted(missing)}")

    swings = confirmed_swing_points(
        candles, timeframe=timeframe, left_bars=left_bars, right_bars=right_bars
    )
    ohlc = candles[["open", "high", "low", "close"]].apply(
        pd.to_numeric, errors="raise"
    ).astype(float)
    values = ohlc.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (ohlc <= 0).any().any():
        raise ValueError("OHLC inputs must be finite and positive")
    invalid = (
        (ohlc["high"] < ohlc[["open", "close"]].max(axis=1))
        | (ohlc["low"] > ohlc[["open", "close"]].min(axis=1))
        | (ohlc["high"] < ohlc["low"])
    )
    if invalid.any():
        raise ValueError("Candle OHLC relationships are invalid")

    events = []
    zones = []
    for row_idx in range(len(candles)):
        event_time = swings["available_at"].iloc[row_idx]
        candle_high = ohlc["high"].iloc[row_idx]
        candle_low = ohlc["low"].iloc[row_idx]
        candle_close = ohlc["close"].iloc[row_idx]

        # Only zones created on earlier rows are eligible for lifecycle events.
        for zone in zones:
            if zone["state"] == "broken":
                continue
            if (
                (zone["zone_type"] == "resistance" and candle_close > zone["upper_bound"])
                or (zone["zone_type"] == "support" and candle_close < zone["lower_bound"])
            ):
                zone["state"] = "broken"
                event = "broken"
            elif candle_low <= zone["upper_bound"] and candle_high >= zone["lower_bound"]:
                zone["touch_count"] += 1
                zone["state"] = "touched"
                event = "touched"
            else:
                continue
            events.append({
                **{key: zone[key] for key in (
                    "zone_id", "zone_type", "lower_bound", "upper_bound",
                    "pivot_time", "created_at",
                )},
                "event_time": event_time,
                "event": event,
                "state": zone["state"],
                "touch_count": zone["touch_count"],
            })

        # Confirmed pivots become zones only now, after earlier zones were updated.
        for side, column in (
            ("resistance", "swing_high_price"),
            ("support", "swing_low_price"),
        ):
            price = swings[column].iloc[row_idx]
            if pd.isna(price):
                continue
            pivot_time = swings[
                "swing_high_pivot_time" if side == "resistance"
                else "swing_low_pivot_time"
            ].iloc[row_idx]
            half_width = float(zone_width_fraction) / 2.0
            zone = {
                "zone_id": f"{side}:{pivot_time.isoformat()}",
                "zone_type": side,
                "lower_bound": float(price) * (1.0 - half_width),
                "upper_bound": float(price) * (1.0 + half_width),
                "pivot_time": pivot_time,
                "created_at": event_time,
                "state": "created",
                "touch_count": 0,
            }
            zones.append(zone)
            events.append({
                **{key: zone[key] for key in (
                    "zone_id", "zone_type", "lower_bound", "upper_bound",
                    "pivot_time", "created_at",
                )},
                "event_time": event_time,
                "event": "created",
                "state": "created",
                "touch_count": 0,
            })

    return pd.DataFrame(events, columns=EVENT_COLUMNS)
