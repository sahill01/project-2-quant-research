from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.data_loader import load_ohlcv, default_dataset_path
from research.strategies import (
    ema_crossover_signal,
    donchian_breakout_signal,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"


def compare_signal_prefix(
    full_signals: pd.Series,
    prefix_signals: pd.Series,
    cutoff_position: int,
) -> None:
    """
    Compare strategy signals generated using:

        1. Full dataset
        2. Historical prefix only

    Signals before the cutoff must be identical.
    """

    full_prefix = full_signals.iloc[:cutoff_position + 1]
    prefix = prefix_signals.iloc[:cutoff_position + 1]

    # Both series should represent the same historical candles.
    assert len(full_prefix) == len(prefix), (
        "Signal lengths differ before cutoff."
    )

    # Compare signal values.
    pd.testing.assert_series_equal(
        full_prefix.reset_index(drop=True),
        prefix.reset_index(drop=True),
        check_names=False,
        check_dtype=False,
    )


def load_test_data() -> pd.DataFrame:
    path = default_dataset_path(
        DATA_DIR,
        symbol="BTCUSD",
        timeframe="4h",
        days_back=730,
    )

    return load_ohlcv(
        path=path,
        timeframe="4h",
    )


def test_ema_prefix_invariance():
    """
    Adding future candles must not change historical EMA signals.
    """

    df = load_test_data()

    cutoff_position = len(df) // 2

    # Run strategy on the complete dataset.
    full_signals = ema_crossover_signal(
        df,
        fast=20,
        slow=50,
    )

    # Run strategy using only historical data up to cutoff.
    prefix_df = df.iloc[:cutoff_position + 1].copy()

    prefix_signals = ema_crossover_signal(
        prefix_df,
        fast=20,
        slow=50,
    )

    compare_signal_prefix(
        full_signals,
        prefix_signals,
        cutoff_position,
    )

    print("PASS: EMA prefix invariance")


def test_donchian_prefix_invariance():
    """
    Adding future candles must not change historical
    Donchian breakout signals.
    """

    df = load_test_data()

    cutoff_position = len(df) // 2

    # Run strategy on the complete dataset.
    full_signals = donchian_breakout_signal(
        df,
        period=20,
    )

    # Run strategy using only historical data up to cutoff.
    prefix_df = df.iloc[:cutoff_position + 1].copy()

    prefix_signals = donchian_breakout_signal(
        prefix_df,
        period=20,
    )

    compare_signal_prefix(
        full_signals,
        prefix_signals,
        cutoff_position,
    )

    print("PASS: Donchian prefix invariance")


def main():
    print("=" * 60)
    print("PREFIX INVARIANCE TESTS")
    print("=" * 60)

    test_ema_prefix_invariance()
    test_donchian_prefix_invariance()

    print("=" * 60)
    print("ALL PREFIX INVARIANCE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()