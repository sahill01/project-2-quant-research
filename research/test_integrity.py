from __future__ import annotations

import pandas as pd

from research.causality import add_available_at, causal_asof_join

def test_available_at():
    """
    Verify that candle information is not considered available
    until the candle has closed.
    """

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 08:00",
                    "2026-01-01 12:00",
                ],
                utc=True,
            ),
            "close": [100, 110],
        }
    )

    result = add_available_at(df, "4h")

    expected = pd.to_datetime(
        [
            "2026-01-01 12:00",
            "2026-01-01 16:00",
        ],
        utc=True,
    )

    assert result["available_at"].tolist() == expected.tolist()

    print("PASS: available_at enforcement")


def test_causal_multitimeframe_join():
    """
    Verify that higher-timeframe candles become available only
    after they have closed.

    4H candles:

        04:00 -> available at 08:00
        08:00 -> available at 12:00

    Therefore:

        07:59 -> no 4H candle available
        08:00 -> 04:00 candle available
        11:45 -> 04:00 candle available
        12:00 -> 08:00 candle available
        12:15 -> 08:00 candle available
    """

    higher_tf = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 04:00",
                    "2026-01-01 08:00",
                ],
                utc=True,
            ),
            "close": [95, 110],
        }
    )

    higher_tf = add_available_at(higher_tf, "4h")

    decisions = pd.DataFrame(
        {
            "decision_time": pd.to_datetime(
                [
                    "2026-01-01 07:59",
                    "2026-01-01 08:00",
                    "2026-01-01 11:45",
                    "2026-01-01 12:00",
                    "2026-01-01 12:15",
                ],
                utc=True,
            )
        }
    )

    result = causal_asof_join(
        decisions,
        higher_tf,
        feature_columns=["close"],
    )

    # Before the first 4H candle closes, nothing is available.
    assert pd.isna(result.loc[0, "close"])

    # At 08:00, the 04:00 candle becomes available.
    assert result.loc[1, "close"] == 95

    # At 11:45, the latest available candle is still the 04:00 candle.
    assert result.loc[2, "close"] == 95

    # At 12:00, the 08:00 candle becomes available.
    assert result.loc[3, "close"] == 110

    # At 12:15, the 08:00 candle remains the latest available candle.
    assert result.loc[4, "close"] == 110

    print("PASS: causal multi-timeframe join")


def test_no_future_feature_leakage():
    """
    Stronger check:
    every joined feature must have been available at or before
    the decision timestamp.
    """

    higher_tf = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 08:00",
                    "2026-01-01 12:00",
                ],
                utc=True,
            ),
            "close": [110, 120],
        }
    )

    higher_tf = add_available_at(higher_tf, "4h")

    decisions = pd.DataFrame(
        {
            "decision_time": pd.to_datetime(
                [
                    "2026-01-01 11:59",
                    "2026-01-01 12:00",
                    "2026-01-01 15:00",
                ],
                utc=True,
            )
        }
    )

    result = causal_asof_join(
        decisions,
        higher_tf,
        feature_columns=["close"],
    )

    available_times = result["available_at"]

    for decision_time, available_at in zip(
        result["decision_time"],
        available_times,
    ):
        if pd.notna(available_at):
            assert available_at <= decision_time

    print("PASS: no future feature leakage")


def test_invalid_or_ambiguous_feature_availability_is_rejected():
    decisions = pd.DataFrame({
        "decision_time": pd.to_datetime(["2026-01-01T12:00:00Z"], utc=True)
    })
    valid_features = pd.DataFrame({
        "available_at": pd.to_datetime(["2026-01-01T08:00:00Z"], utc=True),
        "value": [1.0],
    })

    for features, message in (
        (pd.concat([valid_features, valid_features], ignore_index=True), "unique"),
        (pd.DataFrame({"available_at": ["invalid"], "value": [1.0]}), "valid"),
    ):
        try:
            causal_asof_join(decisions, features, feature_columns=["value"])
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("Invalid/ambiguous feature availability was accepted")

    for columns, message in ((["missing"], "Missing feature"), (["value", "value"], "unique")):
        try:
            causal_asof_join(decisions, valid_features, feature_columns=columns)
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("Invalid feature-column request was accepted")
    print("PASS: invalid/ambiguous feature availability rejected")


def main():
    print("=" * 60)
    print("RESEARCH INTEGRITY TESTS")
    print("=" * 60)

    test_available_at()
    test_causal_multitimeframe_join()
    test_no_future_feature_leakage()
    test_invalid_or_ambiguous_feature_availability_is_rejected()

    print("=" * 60)
    print("ALL INTEGRITY TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
