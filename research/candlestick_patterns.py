"""Objective causal candlestick geometry events; no trading signals."""

import numpy as np
import pandas as pd

from .data_loader import validate_candle_availability


DOJI_BODY_FRACTION = 0.10
EVENT_COLUMNS = ["pattern_id", "candle_time", "available_at"]
PATTERN_ORDER = (
    "bullish_engulfing",
    "bearish_engulfing",
    "hammer",
    "shooting_star",
)


def detect_candlestick_patterns(
    candles: pd.DataFrame, *, timeframe: str
) -> pd.DataFrame:
    """Return one event row per detected pattern on each fully closed candle.

    Engulfing uses the prior candle's real body and requires opposite candle
    colors. Hammer and shooting-star labels use only the current candle's
    body and wick ratios. A real body must exceed 10% of its candle range;
    zero-range and doji-like candles are excluded.
    """
    required = {"timestamp", "available_at", "open", "high", "low", "close"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Candle frame missing columns: {sorted(missing)}")
    if candles.empty:
        raise ValueError("Candle frame is empty")

    frame = candles.copy()
    frame["timestamp"], frame["available_at"] = validate_candle_availability(
        frame["timestamp"], frame["available_at"], timeframe
    )

    prices = frame[["open", "high", "low", "close"]].apply(
        pd.to_numeric, errors="raise"
    ).astype(float)
    values = prices.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (prices <= 0).any().any():
        raise ValueError("OHLC inputs must be finite and positive")
    invalid_ohlc = (
        (prices["high"] < prices[["open", "close"]].max(axis=1))
        | (prices["low"] > prices[["open", "close"]].min(axis=1))
        | (prices["high"] < prices["low"])
    )
    if invalid_ohlc.any():
        raise ValueError("Candle OHLC relationships are invalid")

    rows = []
    for idx in range(len(frame)):
        candle = prices.iloc[idx]
        body = abs(candle["close"] - candle["open"])
        candle_range = candle["high"] - candle["low"]
        body_is_valid = (
            candle_range > 0
            and body / candle_range > DOJI_BODY_FRACTION
        )
        detected = []

        if idx > 0 and body_is_valid:
            previous = prices.iloc[idx - 1]
            previous_body = abs(previous["close"] - previous["open"])
            previous_range = previous["high"] - previous["low"]
            previous_body_is_valid = (
                previous_range > 0
                and previous_body / previous_range > DOJI_BODY_FRACTION
            )
            current_body_low = min(candle["open"], candle["close"])
            current_body_high = max(candle["open"], candle["close"])
            previous_body_low = min(previous["open"], previous["close"])
            previous_body_high = max(previous["open"], previous["close"])
            if previous_body_is_valid:
                if (
                    previous["close"] < previous["open"]
                    and candle["close"] > candle["open"]
                    and current_body_low <= previous_body_low
                    and current_body_high >= previous_body_high
                ):
                    detected.append("bullish_engulfing")
                if (
                    previous["close"] > previous["open"]
                    and candle["close"] < candle["open"]
                    and current_body_low <= previous_body_low
                    and current_body_high >= previous_body_high
                ):
                    detected.append("bearish_engulfing")

        if body_is_valid:
            upper_wick = candle["high"] - max(candle["open"], candle["close"])
            lower_wick = min(candle["open"], candle["close"]) - candle["low"]
            if lower_wick >= 2.0 * body and upper_wick <= body:
                detected.append("hammer")
            if upper_wick >= 2.0 * body and lower_wick <= body:
                detected.append("shooting_star")

        for pattern_id in PATTERN_ORDER:
            if pattern_id in detected:
                rows.append({
                    "pattern_id": pattern_id,
                    "candle_time": frame["timestamp"].iloc[idx],
                    "available_at": frame["available_at"].iloc[idx],
                })

    return pd.DataFrame(rows, columns=EVENT_COLUMNS)
