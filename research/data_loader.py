from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "timestamp", "open", "high", "low", "close", "volume"
]


def timeframe_to_timedelta(timeframe: str) -> pd.Timedelta:
    if not isinstance(timeframe, str) or len(timeframe) < 2:
        raise ValueError(f"Invalid timeframe: {timeframe!r}")
    unit = timeframe[-1]
    try:
        value = int(timeframe[:-1])
    except ValueError as error:
        raise ValueError(f"Invalid timeframe: {timeframe!r}") from error
    if value <= 0:
        raise ValueError("Timeframe interval must be positive")

    if unit not in {"m", "h", "d", "w"}:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    try:
        if unit == "m":
            return pd.Timedelta(minutes=value)
        if unit == "h":
            return pd.Timedelta(hours=value)
        if unit == "d":
            return pd.Timedelta(days=value)
        return pd.Timedelta(weeks=value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"Timeframe interval is out of range: {timeframe}") from error


def validate_candle_availability(
    timestamps: pd.Series,
    available_at: pd.Series,
    timeframe: str,
) -> tuple[pd.Series, pd.Series]:
    """Validate open timestamps and exact close availability for a timeframe.

    Timestamp gaps are allowed: the explicit timeframe, not adjacent rows,
    defines when each candle closes.
    """
    interval = timeframe_to_timedelta(timeframe)
    opens = pd.to_datetime(timestamps, utc=True, errors="raise")
    availability = pd.to_datetime(available_at, utc=True, errors="raise")
    for name, values in (("timestamp", opens), ("available_at", availability)):
        if values.isna().any() or values.duplicated().any():
            raise ValueError(f"{name} timestamps must be valid and unique")
        if not values.is_monotonic_increasing:
            raise ValueError(f"{name} timestamps must be ordered")

    expected = opens + interval
    if not availability.equals(expected):
        raise ValueError(
            f"available_at must equal timestamp plus the {timeframe} candle duration"
        )
    return opens, availability


def validate_timestamp_alignment(
    timestamps: pd.Series,
    timeframe: str,
) -> None:
    """Require minute/hour/day candle opens to align to UTC interval edges.

    Weekly candles are intentionally exempt until the data source's week
    anchor is configured explicitly.
    """
    interval = timeframe_to_timedelta(timeframe)
    if timeframe.endswith("w"):
        return
    misaligned = timestamps.dt.floor(interval) != timestamps
    if misaligned.any():
        raise ValueError(
            f"Dataset contains {int(misaligned.sum())} timestamps not aligned "
            f"to UTC {timeframe} candle boundaries."
        )


def _validate_ohlcv_frame(
    df: pd.DataFrame, timeframe: str, *, sort_timestamps: bool
) -> pd.DataFrame:
    if df.empty:
        raise ValueError("Dataset is empty.")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce"
    )

    if df["timestamp"].isna().any():
        raise ValueError("Dataset contains NaN/invalid timestamps.")

    validate_timestamp_alignment(df["timestamp"], timeframe)

    if df["timestamp"].duplicated().any():
        raise ValueError("Dataset contains duplicate timestamps.")

    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df[REQUIRED_COLUMNS].isna().any().any():
        raise ValueError("Dataset contains NaN/invalid values.")

    numeric_values = df[["open", "high", "low", "close", "volume"]].to_numpy(
        dtype=float
    )
    if not np.isfinite(numeric_values).all():
        raise ValueError("Dataset contains non-finite numeric values.")

    df = df[REQUIRED_COLUMNS]
    if sort_timestamps:
        df = df.sort_values("timestamp")
    df = df.reset_index(drop=True)

    if not df["timestamp"].is_monotonic_increasing:
        raise ValueError("Timestamps are not ordered.")

    timeframe_delta = timeframe_to_timedelta(timeframe)
    df["available_at"] = df["timestamp"] + timeframe_delta

    invalid = (
        (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (df["volume"] < 0)
    )

    if invalid.any():
        raise ValueError(
            f"Dataset contains {int(invalid.sum())} invalid OHLCV rows."
        )

    return df


def load_ohlcv(path: str | Path, timeframe: str) -> pd.DataFrame:
    # timestamp is candle OPEN time.
    # available_at is when the fully closed candle becomes known.
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    return _validate_ohlcv_frame(
        pd.read_csv(path), timeframe, sort_timestamps=True
    )


def load_ohlcv_before(
    path: str | Path,
    timeframe: str,
    available_before: str | pd.Timestamp,
) -> pd.DataFrame:
    """Load and validate only candles closing before an authorized boundary.

    The CSV timestamp column is streamed to locate the prefix and verify
    chronological order. OHLCV values are materialized only for that prefix,
    which keeps later partition prices out of the returned frame. The bounded
    loader does not sort the source.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    boundary = pd.Timestamp(available_before)
    if boundary.tzinfo is None:
        raise ValueError("Availability boundary must include a timezone")
    boundary = boundary.tz_convert("UTC")
    interval = timeframe_to_timedelta(timeframe)
    row_count = 0
    previous = None
    boundary_reached = False
    iterator = pd.read_csv(path, usecols=["timestamp"], chunksize=1)
    try:
        for chunk in iterator:
            timestamp = pd.to_datetime(
                chunk["timestamp"].iloc[0], utc=True, errors="coerce"
            )
            if pd.isna(timestamp):
                raise ValueError("Dataset contains NaN/invalid timestamps.")
            validate_timestamp_alignment(pd.Series([timestamp]), timeframe)
            if previous is not None and timestamp <= previous:
                raise ValueError("Stage-bounded dataset timestamps must be strictly increasing.")
            previous = timestamp
            if timestamp + interval >= boundary:
                boundary_reached = True
            elif not boundary_reached:
                row_count += 1
    finally:
        iterator.close()

    prefix = pd.read_csv(path, nrows=row_count)
    return (
        _validate_ohlcv_frame(prefix, timeframe, sort_timestamps=False),
        boundary_reached,
    )


def default_dataset_path(
    data_dir: str | Path,
    symbol: str,
    timeframe: str,
    days_back: int,
) -> Path:
    return Path(data_dir) / f"{symbol}_{timeframe}_{days_back}d.csv"
