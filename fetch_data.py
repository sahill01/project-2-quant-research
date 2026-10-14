"""
Project 2 — Historical Market Data Downloader

Downloads public historical OHLCV data from Delta Exchange.

No API key is required.

The downloader is intentionally separated from the backtester so that
the backtesting engine remains independent of the data source.
"""

import os
import time
import numpy as np
import requests
import pandas as pd

from config import (
    DATA_SOURCE,
    SYMBOLS,
    TIMEFRAMES,
    DAYS_BACK,
)
from research.data_loader import (
    timeframe_to_timedelta,
    validate_timestamp_alignment,
)
from research.result_io import write_csv_batch_no_clobber

DELTA_BASE_URL = "https://api.india.delta.exchange"

OUTPUT_DIR = "data/raw"


# ============================================================
# RESOLUTION HELPERS
# ============================================================

def resolution_to_seconds(resolution):
    return int(timeframe_to_timedelta(resolution).total_seconds())


# ============================================================
# FETCH CANDLES
# ============================================================

def fetch_candles(symbol, resolution, days_back):
    """
    Download historical OHLCV candles.

    Delta returns a maximum of 2000 candles per request,
    so the downloader requests the data in chunks.
    """

    end_time = int(time.time())
    start_time = end_time - days_back * 86400

    chunk_seconds = 1900 * resolution_to_seconds(resolution)

    all_rows = []
    cursor_end = end_time

    print(
        f"\nDownloading {symbol} | {resolution} | "
        f"{days_back} days"
    )

    while cursor_end > start_time:

        cursor_start = max(
            start_time,
            cursor_end - chunk_seconds
        )

        params = {
            "resolution": resolution,
            "symbol": symbol,
            "start": cursor_start,
            "end": cursor_end,
        }

        response = requests.get(
            f"{DELTA_BASE_URL}/v2/history/candles",
            params=params,
            timeout=20,
        )

        response.raise_for_status()

        payload = response.json()

        if not payload.get("success", True):
            raise RuntimeError(
                f"Delta API error: {payload}"
            )

        rows = payload.get("result", [])

        if not rows:
            raise RuntimeError(
                f"Empty candle response for {symbol} {resolution} "
                f"chunk {cursor_start}..{cursor_end}; refusing partial history."
            )

        response_times = pd.to_numeric(
            pd.Series([row.get("time") for row in rows]),
            errors="coerce",
        )
        if response_times.isna().any() or not np.isfinite(
            response_times.to_numpy(dtype=float)
        ).all():
            raise ValueError(
                f"Malformed candle timestamps in {symbol} {resolution} response"
            )
        outside_chunk = (
            (response_times < cursor_start) | (response_times > cursor_end)
        )
        if outside_chunk.any():
            raise ValueError(
                f"Candle timestamp outside requested chunk {cursor_start}.."
                f"{cursor_end} for {symbol} {resolution}"
            )

        all_rows.extend(rows)

        cursor_end = cursor_start - 1

        # Avoid hammering the public endpoint.
        time.sleep(0.2)

    if not all_rows:
        raise ValueError(
            f"No data returned for {symbol} {resolution}"
        )

    df = pd.DataFrame(all_rows)

    df = df.rename(
        columns={
            "time": "timestamp"
        }
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        unit="s",
        utc=True,
    )
    validate_timestamp_alignment(df["timestamp"], resolution)

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

    df = df[
        ["timestamp", "open", "high", "low", "close", "volume"]
    ]
    if df.isna().any().any():
        raise ValueError(f"Malformed candle fields in {symbol} {resolution} response")
    if df["timestamp"].duplicated().any():
        raise ValueError(f"Duplicate candle timestamps in {symbol} {resolution} response")
    numeric = df[["open", "high", "low", "close", "volume"]].to_numpy(float)
    if not np.isfinite(numeric).all():
        raise ValueError(f"Non-finite candle values in {symbol} {resolution} response")
    invalid = (
        (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (df["volume"] < 0)
    )
    if invalid.any():
        raise ValueError(f"Invalid OHLCV rows in {symbol} {resolution} response")
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


# ============================================================
# SAVE DATASET
# ============================================================

def save_dataset(df, symbol, timeframe):

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    filename = (
        f"{symbol}_{timeframe}_{DAYS_BACK}d.csv"
    )

    filepath = os.path.join(
        OUTPUT_DIR,
        filename,
    )

    write_csv_batch_no_clobber([(df, filepath)])

    print(
        f"Saved {len(df):,} candles → {filepath}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if DATA_SOURCE != "delta":
        raise NotImplementedError(
            f"Data source '{DATA_SOURCE}' "
            f"is not implemented yet."
        )

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            try:

                df = fetch_candles(
                    symbol=symbol,
                    resolution=timeframe,
                    days_back=DAYS_BACK,
                )

                save_dataset(
                    df,
                    symbol,
                    timeframe,
                )

            except Exception as exc:

                print(
                    f"ERROR: {symbol} {timeframe}: {exc}"
                )


if __name__ == "__main__":
    main()
