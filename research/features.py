"""Causal, descriptive candle features; this module does not create signals."""

import numpy as np
import pandas as pd


def _validate_window(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def causal_descriptive_features(
    candles: pd.DataFrame,
    *,
    volatility_window: int,
    atr_window: int,
    volume_window: int,
    momentum_window: int,
    structure_window: int,
) -> pd.DataFrame:
    """Calculate descriptive features available at each candle close.

    All windows are explicit caller inputs. Rolling volatility and ATR include
    the current fully closed candle. Relative volume compares current volume
    with the mean of the preceding `volume_window` candles. The returned
    `available_at` is copied from the current candle and is the earliest
    decision time at which these values may be used.
    """
    for name, value in (
        ("volatility_window", volatility_window),
        ("atr_window", atr_window),
        ("volume_window", volume_window),
        ("momentum_window", momentum_window),
        ("structure_window", structure_window),
    ):
        _validate_window(name, value)

    required = {"available_at", "open", "high", "low", "close", "volume"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Candle frame missing columns: {sorted(missing)}")
    if candles.empty:
        raise ValueError("Candle frame is empty")

    available_at = pd.to_datetime(
        candles["available_at"], utc=True, errors="raise"
    )
    if (
        available_at.isna().any()
        or available_at.duplicated().any()
        or not available_at.is_monotonic_increasing
    ):
        raise ValueError("available_at timestamps must be valid, unique and ordered")

    prices = candles[["open", "high", "low", "close"]].apply(
        pd.to_numeric, errors="raise"
    ).astype(float)
    volume = pd.to_numeric(candles["volume"], errors="raise").astype(float)
    numeric = prices.assign(volume=volume).to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("Candle inputs must be finite")
    if (prices <= 0).any().any() or (volume < 0).any():
        raise ValueError("Prices must be positive and volume non-negative")
    invalid_ohlc = (
        (prices["high"] < prices[["open", "close"]].max(axis=1))
        | (prices["low"] > prices[["open", "close"]].min(axis=1))
        | (prices["high"] < prices["low"])
    )
    if invalid_ohlc.any():
        raise ValueError("Candle OHLC relationships are invalid")

    close = prices["close"]
    log_return = np.log(close).diff()
    realized_volatility = log_return.rolling(
        volatility_window, min_periods=volatility_window
    ).std(ddof=0)

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            prices["high"] - prices["low"],
            (prices["high"] - previous_close).abs(),
            (prices["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(atr_window, min_periods=atr_window).mean()
    prior_volume_mean = volume.shift(1).rolling(
        volume_window, min_periods=volume_window
    ).mean()
    prior_high = prices["high"].shift(1).rolling(
        structure_window, min_periods=structure_window
    ).max()
    prior_low = prices["low"].shift(1).rolling(
        structure_window, min_periods=structure_window
    ).min()
    candle_body_top = prices[["open", "close"]].max(axis=1)
    candle_body_bottom = prices[["open", "close"]].min(axis=1)

    return pd.DataFrame(
        {
            "available_at": available_at,
            "log_return": log_return,
            "momentum_return": close / close.shift(momentum_window) - 1.0,
            "realized_volatility": realized_volatility,
            "atr": atr,
            "atr_pct": atr / close * 100.0,
            "relative_volume": volume / prior_volume_mean.where(
                prior_volume_mean > 0
            ),
            "candle_body_pct": (close - prices["open"]) / prices["open"] * 100.0,
            "candle_range_pct": (prices["high"] - prices["low"]) / close * 100.0,
            "upper_wick_pct": (
                prices["high"] - candle_body_top
            ) / close * 100.0,
            "lower_wick_pct": (
                candle_body_bottom - prices["low"]
            ) / close * 100.0,
            "prior_range_high": prior_high,
            "prior_range_low": prior_low,
            "distance_to_prior_high_pct": (close / prior_high - 1.0) * 100.0,
            "distance_to_prior_low_pct": (close / prior_low - 1.0) * 100.0,
        },
        index=candles.index,
    )
