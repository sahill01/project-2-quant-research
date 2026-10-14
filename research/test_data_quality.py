"""Synthetic checks for caller-configured market-data freshness."""

import pandas as pd

from research.data_quality import inspect_timestamp_gaps, validate_latest_available_at


def test_freshness_accepts_exact_limit_and_normalizes_timezones():
    age = validate_latest_available_at(
        "2026-10-15T12:00:00+02:00",
        now="2026-10-15T10:30:00Z",
        max_age="30min",
    )
    assert age == pd.Timedelta(minutes=30)


def test_freshness_rejects_stale_and_future_observations():
    cases = (
        ("2026-10-15T11:59:00Z", "2026-10-15T12:00:00Z", "30s", "stale"),
        ("2026-10-15T12:01:00Z", "2026-10-15T12:00:00Z", "30s", "future"),
    )
    for latest, now, max_age, message in cases:
        try:
            validate_latest_available_at(latest, now=now, max_age=max_age)
        except ValueError as error:
            assert message in str(error).lower()
        else:
            raise AssertionError(f"{message} data timestamp was accepted")


def test_freshness_rejects_naive_invalid_and_negative_policy_inputs():
    cases = (
        ("2026-10-15 12:00:00", "2026-10-15T12:00:00Z", "1h"),
        ("2026-10-15T12:00:00Z", "2026-10-15 12:00:00", "1h"),
        ("not-a-time", "2026-10-15T12:00:00Z", "1h"),
        ("2026-10-15T12:00:00Z", "2026-10-15T12:00:00Z", "-1s"),
    )
    for latest, now, max_age in cases:
        try:
            validate_latest_available_at(latest, now=now, max_age=max_age)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError("Invalid freshness input was accepted")


def test_gap_inspector_counts_missing_candles_and_marks_irregular_steps():
    regular = pd.to_datetime(
        ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"], utc=True
    )
    assert inspect_timestamp_gaps(regular, expected_interval="1h").empty

    with_gap = pd.to_datetime(
        ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", "2026-01-01T04:00:00Z"],
        utc=True,
    )
    report = inspect_timestamp_gaps(with_gap, expected_interval="1h")
    assert len(report) == 1
    assert bool(report.loc[0, "is_exact_interval_multiple"])
    assert report.loc[0, "missing_candle_count"] == 2

    irregular = inspect_timestamp_gaps(
        pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T01:30:00Z"], utc=True),
        expected_interval="1h",
    )
    assert not bool(irregular.loc[0, "is_exact_interval_multiple"])
    assert pd.isna(irregular.loc[0, "missing_candle_count"])


def test_gap_inspector_rejects_invalid_order_duplicates_and_interval():
    valid = pd.to_datetime(
        ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"], utc=True
    )
    invalid_cases = (
        (valid[::-1], "ordered"),
        (pd.DatetimeIndex([valid[0], valid[0]]), "unique"),
        (pd.DatetimeIndex([valid[0], pd.NaT]), "valid"),
    )
    for timestamps, message in invalid_cases:
        try:
            inspect_timestamp_gaps(timestamps, expected_interval="1h")
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("Invalid cadence timestamps were accepted")

    try:
        inspect_timestamp_gaps(valid, expected_interval="0s")
    except ValueError as error:
        assert "positive duration" in str(error)
    else:
        raise AssertionError("Nonpositive expected interval was accepted")


def main():
    tests = [
        test_freshness_accepts_exact_limit_and_normalizes_timezones,
        test_freshness_rejects_stale_and_future_observations,
        test_freshness_rejects_naive_invalid_and_negative_policy_inputs,
        test_gap_inspector_counts_missing_candles_and_marks_irregular_steps,
        test_gap_inspector_rejects_invalid_order_duplicates_and_interval,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
