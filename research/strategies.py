import numpy as np
import pandas as pd


def buy_and_hold_signal(df: pd.DataFrame) -> pd.Series:
    return pd.Series(1, index=df.index, dtype=int)


def ema_crossover_signal(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
) -> pd.Series:
    fast_ema = df["close"].ewm(span=fast, adjust=False).mean()
    slow_ema = df["close"].ewm(span=slow, adjust=False).mean()

    signal = pd.Series(
        np.where(fast_ema > slow_ema, 1, -1),
        index=df.index,
        dtype=int,
    )

    signal.iloc[:slow] = 0
    return signal


def donchian_breakout_signal(
    df: pd.DataFrame,
    period: int = 20,
) -> pd.Series:
    # Shift means the threshold uses only prior candles.
    upper = df["high"].rolling(period).max().shift(1)
    lower = df["low"].rolling(period).min().shift(1)

    signal = pd.Series(0, index=df.index, dtype=int)
    signal.loc[df["close"] > upper] = 1
    signal.loc[df["close"] < lower] = -1

    return signal
