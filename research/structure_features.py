"""Causal swing-point events with explicit confirmation delays."""

import numpy as np
import pandas as pd


def _validate_window(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def confirmed_swing_points(
    candles: pd.DataFrame,
    *,
    left_bars: int,
    right_bars: int,
) -> pd.DataFrame:
    """Emit strict swing highs/lows only when their right side is observable.

    A candidate at index `p` is a high (low) only when its high (low) is
    strictly greater (less) than all `left_bars` preceding and `right_bars`
    following candles. It is emitted on row `p + right_bars`, with that row's
    `available_at`; the separate pivot timestamp records where the price
    extremum occurred. Tied extrema are not classified as swings.
    """
    _validate_window("left_bars", left_bars)
    _validate_window("right_bars", right_bars)
    required = {"timestamp", "available_at", "high", "low"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Candle frame missing columns: {sorted(missing)}")

    frame = candles.copy()
    if frame.empty:
        raise ValueError("Candle frame is empty")
    for column in ("timestamp", "available_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
        if frame[column].isna().any() or frame[column].duplicated().any():
            raise ValueError(f"{column} timestamps must be valid and unique")
        if not frame[column].is_monotonic_increasing:
            raise ValueError(f"{column} timestamps must be ordered")
    if (frame["available_at"] <= frame["timestamp"]).any():
        raise ValueError("available_at must follow the candle timestamp")

    prices = frame[["high", "low"]].apply(pd.to_numeric, errors="raise").astype(float)
    if not np.isfinite(prices.to_numpy(dtype=float)).all():
        raise ValueError("Swing high/low inputs must be finite")
    if (prices <= 0).any().any() or (prices["high"] < prices["low"]).any():
        raise ValueError("Candle high/low values must be positive and ordered")

    high_pivot_times = [pd.NaT] * len(frame)
    high_pivot_prices = [float("nan")] * len(frame)
    low_pivot_times = [pd.NaT] * len(frame)
    low_pivot_prices = [float("nan")] * len(frame)
    result = pd.DataFrame(
        {
            "available_at": frame["available_at"],
            "swing_high_pivot_time": high_pivot_times,
            "swing_high_price": high_pivot_prices,
            "swing_low_pivot_time": low_pivot_times,
            "swing_low_price": low_pivot_prices,
        },
        index=frame.index,
    )

    first_confirmable = left_bars + right_bars
    for confirm_idx in range(first_confirmable, len(frame)):
        pivot_idx = confirm_idx - right_bars
        neighbor_indices = list(range(pivot_idx - left_bars, pivot_idx)) + list(
            range(pivot_idx + 1, confirm_idx + 1)
        )
        neighbor_high = prices["high"].iloc[neighbor_indices]
        neighbor_low = prices["low"].iloc[neighbor_indices]
        pivot_high = prices["high"].iloc[pivot_idx]
        pivot_low = prices["low"].iloc[pivot_idx]

        if pivot_high > neighbor_high.max():
            high_pivot_times[confirm_idx] = frame["timestamp"].iloc[pivot_idx]
            high_pivot_prices[confirm_idx] = pivot_high
        if pivot_low < neighbor_low.min():
            low_pivot_times[confirm_idx] = frame["timestamp"].iloc[pivot_idx]
            low_pivot_prices[confirm_idx] = pivot_low

    result["swing_high_pivot_time"] = pd.to_datetime(
        high_pivot_times, utc=True
    )
    result["swing_low_pivot_time"] = pd.to_datetime(
        low_pivot_times, utc=True
    )
    result["swing_high_price"] = high_pivot_prices
    result["swing_low_price"] = low_pivot_prices

    return result
