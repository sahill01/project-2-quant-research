"""
Project 2 — Historical Data Validation

Checks every downloaded market dataset before it is used
by the backtesting engine.

The validator checks:

1. File exists
2. Required columns exist
3. Timestamp parsing
4. Timestamp ordering
5. Duplicate candles
6. Missing candles / time gaps
7. OHLC validity
8. Negative/zero prices
9. Negative volume
10. NaN values
11. Basic dataset statistics
"""

import os
import glob
import numpy as np
import pandas as pd

from config import SYMBOLS, TIMEFRAMES, DAYS_BACK
from research.data_loader import (
    timeframe_to_timedelta,
    validate_timestamp_alignment,
)


# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIR = "data/raw"

REQUIRED_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
]


# ============================================================
# TIMEFRAME HELPERS
# ============================================================

def timeframe_to_minutes(timeframe):
    interval = timeframe_to_timedelta(timeframe)
    return int(interval.total_seconds() // 60)


# ============================================================
# VALIDATE ONE DATASET
# ============================================================

def validate_file(filepath, symbol, timeframe):

    print("\n" + "=" * 70)
    print(f"VALIDATING: {symbol} | {timeframe}")
    print(f"FILE: {filepath}")
    print("=" * 70)

    errors = []
    warnings = []

    try:
        expected_minutes = timeframe_to_minutes(timeframe)
    except ValueError as exc:
        errors.append(str(exc))
        return errors, warnings

    # --------------------------------------------------------
    # File check
    # --------------------------------------------------------

    if not os.path.exists(filepath):
        errors.append("File does not exist.")
        return errors, warnings

    # --------------------------------------------------------
    # Read CSV
    # --------------------------------------------------------

    try:
        df = pd.read_csv(filepath)
    except Exception as exc:
        errors.append(
            f"Could not read CSV: {exc}"
        )
        return errors, warnings

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        errors.append(
            f"Missing columns: {missing_columns}"
        )
        return errors, warnings

    # --------------------------------------------------------
    # Timestamp validation
    # --------------------------------------------------------

    try:
        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True,
            errors="coerce",
        )
    except Exception as exc:
        errors.append(
            f"Timestamp conversion failed: {exc}"
        )
        return errors, warnings

    invalid_timestamps = df["timestamp"].isna().sum()

    if invalid_timestamps > 0:
        errors.append(
            f"{invalid_timestamps} invalid timestamps."
        )
    elif timeframe.endswith("w"):
        warnings.append(
            "Weekly timestamp alignment was not checked because the week "
            "anchor is not configured."
        )
    else:
        try:
            validate_timestamp_alignment(df["timestamp"], timeframe)
        except ValueError as exc:
            errors.append(str(exc))

    # --------------------------------------------------------
    # Numeric conversion
    # --------------------------------------------------------

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # --------------------------------------------------------
    # NaN check
    # --------------------------------------------------------

    nan_counts = df[
        REQUIRED_COLUMNS
    ].isna().sum()

    nan_total = nan_counts.sum()

    if nan_total > 0:

        errors.append(
            f"Found {nan_total} NaN values."
        )

    numeric_values = df[numeric_columns].to_numpy(dtype=float)
    infinite_count = int(np.isinf(numeric_values).sum())
    if infinite_count > 0:
        errors.append(
            f"Found {infinite_count} infinite numeric OHLCV values."
        )

    # --------------------------------------------------------
    # Duplicate timestamp check
    # --------------------------------------------------------

    duplicate_count = (
        df["timestamp"]
        .duplicated()
        .sum()
    )

    if duplicate_count > 0:

        errors.append(
            f"Found {duplicate_count} duplicate candles."
        )

    # --------------------------------------------------------
    # Timestamp ordering
    # --------------------------------------------------------

    if not df["timestamp"].is_monotonic_increasing:

        errors.append(
            "Timestamps are not strictly increasing."
        )

    # --------------------------------------------------------
    # Expected candle interval
    # --------------------------------------------------------

    expected_delta = pd.Timedelta(
        minutes=expected_minutes
    )

    if len(df) > 1:

        deltas = (
            df["timestamp"]
            .diff()
            .dropna()
        )

        incorrect_intervals = (
            deltas != expected_delta
        )

        gap_count = incorrect_intervals.sum()

        if gap_count > 0:

            warnings.append(
                f"Found {gap_count} timestamp gaps "
                f"or irregular intervals."
            )

            largest_gap = deltas.max()

            warnings.append(
                f"Largest interval: {largest_gap}"
            )

    # --------------------------------------------------------
    # OHLC relationship checks
    # --------------------------------------------------------

    invalid_high = (
        df["high"]
        < df[
            ["open", "close"]
        ].max(axis=1)
    )

    invalid_low = (
        df["low"]
        > df[
            ["open", "close"]
        ].min(axis=1)
    )

    invalid_high_count = invalid_high.sum()
    invalid_low_count = invalid_low.sum()

    if invalid_high_count > 0:

        errors.append(
            f"{invalid_high_count} candles have "
            f"high below open/close."
        )

    if invalid_low_count > 0:

        errors.append(
            f"{invalid_low_count} candles have "
            f"low above open/close."
        )

    # --------------------------------------------------------
    # Price checks
    # --------------------------------------------------------

    price_columns = [
        "open",
        "high",
        "low",
        "close",
    ]

    for column in price_columns:

        invalid_prices = (
            df[column] <= 0
        ).sum()

        if invalid_prices > 0:

            errors.append(
                f"{column}: "
                f"{invalid_prices} zero/negative values."
            )

    # --------------------------------------------------------
    # Volume checks
    # --------------------------------------------------------

    negative_volume = (
        df["volume"] < 0
    ).sum()

    if negative_volume > 0:

        errors.append(
            f"Found {negative_volume} "
            f"negative volume values."
        )

    # --------------------------------------------------------
    # Dataset statistics
    # --------------------------------------------------------

    print(f"Candles:       {len(df):,}")

    if len(df) > 0:

        print(
            f"Start:         "
            f"{df['timestamp'].iloc[0]}"
        )

        print(
            f"End:           "
            f"{df['timestamp'].iloc[-1]}"
        )

        print(
            f"Price range:   "
            f"{df['low'].min():.6f}"
            f" → "
            f"{df['high'].max():.6f}"
        )

        print(
            f"Volume range:  "
            f"{df['volume'].min():.6f}"
            f" → "
            f"{df['volume'].max():.6f}"
        )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    if not errors:

        print("\nSTATUS: PASS")

    else:

        print("\nSTATUS: FAIL")

        for error in errors:

            print(
                f"  ERROR: {error}"
            )

    if warnings:

        print("\nWARNINGS:")

        for warning in warnings:

            print(
                f"  WARNING: {warning}"
            )

    return errors, warnings


# ============================================================
# MAIN VALIDATION
# ============================================================

def main():

    print("\n")
    print("=" * 70)
    print("PROJECT 2 — DATA VALIDATION")
    print("=" * 70)

    total_errors = 0
    total_warnings = 0
    total_files = 0

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            filename = (
                f"{symbol}_{timeframe}_"
                f"{DAYS_BACK}d.csv"
            )

            filepath = os.path.join(
                DATA_DIR,
                filename,
            )

            errors, warnings = validate_file(
                filepath,
                symbol,
                timeframe,
            )

            total_files += 1
            total_errors += len(errors)
            total_warnings += len(warnings)

    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("FINAL VALIDATION SUMMARY")
    print("=" * 70)

    print(
        f"Files checked: {total_files}"
    )

    print(
        f"Errors:        {total_errors}"
    )

    print(
        f"Warnings:      {total_warnings}"
    )

    if total_errors == 0:

        print(
            "\nOVERALL STATUS: PASS"
        )

        print(
            "The datasets are ready for the next stage."
        )

    else:

        print(
            "\nOVERALL STATUS: FAIL"
        )

        print(
            "Do NOT use these datasets for backtesting "
            "until the errors are investigated."
        )


if __name__ == "__main__":
    main()
