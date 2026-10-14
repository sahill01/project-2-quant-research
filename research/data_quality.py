"""Caller-configured timestamp freshness checks for research data."""

import pandas as pd


def inspect_timestamp_gaps(timestamps, *, expected_interval) -> pd.DataFrame:
    """Report missing-candle counts and irregular spacing without a policy choice.

    Exact multiples of the expected interval report the number of missing
    candles. Non-multiple spacings are marked irregular and their missing count
    is left undefined. The function neither fills nor rejects gaps.
    """
    try:
        interval = pd.Timedelta(expected_interval)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("expected_interval must be a finite positive duration") from error
    if pd.isna(interval) or interval <= pd.Timedelta(0):
        raise ValueError("expected_interval must be a finite positive duration")

    values = pd.Series(timestamps)
    if values.empty:
        raise ValueError("At least one timestamp is required")
    parsed = pd.to_datetime(values, utc=True, errors="coerce")
    if parsed.isna().any():
        raise ValueError("Cadence timestamps must be valid")
    if parsed.duplicated().any():
        raise ValueError("Cadence timestamps must be unique")
    if not parsed.is_monotonic_increasing:
        raise ValueError("Cadence timestamps must be ordered")

    rows = []
    for idx in range(1, len(parsed)):
        elapsed = parsed.iloc[idx] - parsed.iloc[idx - 1]
        if elapsed == interval:
            continue
        multiple = elapsed.value % interval.value == 0
        missing_count = elapsed.value // interval.value - 1 if multiple else pd.NA
        rows.append({
            "previous_timestamp": parsed.iloc[idx - 1],
            "next_timestamp": parsed.iloc[idx],
            "observed_interval": elapsed,
            "is_exact_interval_multiple": multiple,
            "missing_candle_count": missing_count,
        })

    result = pd.DataFrame(rows, columns=[
        "previous_timestamp",
        "next_timestamp",
        "observed_interval",
        "is_exact_interval_multiple",
        "missing_candle_count",
    ])
    if not result.empty:
        result["missing_candle_count"] = pd.array(
            result["missing_candle_count"], dtype="Int64"
        )
    return result


def validate_latest_available_at(
    latest_available_at,
    *,
    now,
    max_age,
) -> pd.Timedelta:
    """Return data age or fail if caller-supplied freshness limits are violated.

    Both timestamps must include a timezone. No clock or age policy is chosen
    implicitly, and this helper is not wired into data loading or trading.
    """
    latest = pd.Timestamp(latest_available_at)
    observed_now = pd.Timestamp(now)
    if pd.isna(latest) or pd.isna(observed_now):
        raise ValueError("Freshness timestamps must be valid")
    if latest.tzinfo is None or observed_now.tzinfo is None:
        raise ValueError("Freshness timestamps must include a timezone")
    latest = latest.tz_convert("UTC")
    observed_now = observed_now.tz_convert("UTC")

    try:
        age_limit = pd.Timedelta(max_age)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("max_age must be a finite non-negative duration") from error
    if pd.isna(age_limit) or age_limit < pd.Timedelta(0):
        raise ValueError("max_age must be a finite non-negative duration")

    age = observed_now - latest
    if age < pd.Timedelta(0):
        raise ValueError("Latest available_at timestamp is in the future")
    if age > age_limit:
        raise ValueError(f"Data is stale: age {age} exceeds maximum {age_limit}")
    return age
