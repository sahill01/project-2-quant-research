"""Exact-value and causality tests for strategy-neutral candle features."""

import numpy as np
import pandas as pd

from research.causality import causal_asof_join
from research.features import causal_descriptive_features


def candles() -> pd.DataFrame:
    return pd.DataFrame({
        "available_at": pd.date_range("2026-01-01T01:00:00Z", periods=6, freq="1h"),
        "open": [100.0, 100.0, 105.0, 110.0, 108.0, 112.0],
        "high": [102.0, 106.0, 111.0, 112.0, 114.0, 115.0],
        "low": [99.0, 98.0, 104.0, 107.0, 107.0, 111.0],
        "close": [100.0, 105.0, 110.0, 108.0, 112.0, 114.0],
        "volume": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
    })


def features(frame: pd.DataFrame) -> pd.DataFrame:
    return causal_descriptive_features(
        frame,
        volatility_window=2,
        atr_window=2,
        volume_window=2,
        momentum_window=2,
        structure_window=2,
    )


def test_feature_values_match_independent_formulas_and_availability():
    frame = candles()
    result = features(frame)

    expected_log_return = np.log(110.0 / 105.0)
    returns = np.array([np.log(105.0 / 100.0), expected_log_return])
    expected_volatility = returns.std(ddof=0)
    true_ranges = np.array([8.0, 7.0])  # bars 1 and 2
    expected_atr = true_ranges.mean()
    expected_relative_volume = 30.0 / np.mean([10.0, 20.0])

    assert result["available_at"].tolist() == frame["available_at"].tolist()
    assert pd.isna(result.loc[0, "log_return"])
    assert abs(result.loc[2, "log_return"] - expected_log_return) < 1e-12
    assert abs(result.loc[2, "realized_volatility"] - expected_volatility) < 1e-12
    assert abs(result.loc[2, "atr"] - expected_atr) < 1e-12
    assert abs(result.loc[2, "atr_pct"] - expected_atr / 110.0 * 100) < 1e-12
    assert abs(result.loc[2, "relative_volume"] - expected_relative_volume) < 1e-12
    assert abs(result.loc[2, "momentum_return"] - 0.1) < 1e-12
    assert result.loc[2, "prior_range_high"] == 106.0
    assert result.loc[2, "prior_range_low"] == 98.0
    assert abs(result.loc[2, "distance_to_prior_high_pct"] - (110 / 106 - 1) * 100) < 1e-12
    assert abs(result.loc[2, "distance_to_prior_low_pct"] - (110 / 98 - 1) * 100) < 1e-12
    assert abs(result.loc[2, "candle_body_pct"] - (110 - 105) / 105 * 100) < 1e-12
    assert abs(result.loc[2, "candle_range_pct"] - (111 - 104) / 110 * 100) < 1e-12
    assert abs(result.loc[2, "upper_wick_pct"] - 1 / 110 * 100) < 1e-12
    assert abs(result.loc[2, "lower_wick_pct"] - 1 / 110 * 100) < 1e-12


def test_features_are_prefix_invariant_and_future_perturbations_do_not_leak():
    frame = candles()
    cutoff = 3
    full = features(frame)
    prefix = features(frame.iloc[:cutoff + 1].copy())
    pd.testing.assert_frame_equal(
        full.iloc[:cutoff + 1].reset_index(drop=True),
        prefix.reset_index(drop=True),
        check_freq=False,
    )

    changed_future = frame.copy()
    changed_future.loc[
        cutoff + 1:, ["open", "high", "low", "close", "volume"]
    ] *= 100
    changed = features(changed_future)
    pd.testing.assert_frame_equal(
        full.iloc[:cutoff + 1].reset_index(drop=True),
        changed.iloc[:cutoff + 1].reset_index(drop=True),
        check_freq=False,
    )


def test_feature_rows_join_only_after_their_available_at_boundary():
    feature_frame = features(candles())
    decisions = pd.DataFrame({
        "decision_time": pd.to_datetime(
            ["2026-01-01T03:59:00Z", "2026-01-01T04:00:00Z"], utc=True
        )
    })
    joined = causal_asof_join(
        decisions,
        feature_frame,
        feature_columns=["momentum_return", "prior_range_high"],
    )
    assert joined["available_at"].tolist() == pd.to_datetime(
        ["2026-01-01T03:00:00Z", "2026-01-01T04:00:00Z"], utc=True
    ).tolist()
    assert joined.loc[0, "prior_range_high"] == feature_frame.loc[2, "prior_range_high"]
    assert joined.loc[1, "prior_range_high"] == feature_frame.loc[3, "prior_range_high"]
    assert (joined["available_at"] <= joined["decision_time"]).all()


def test_asof_join_preserves_unsorted_decision_row_order():
    decisions = pd.DataFrame({
        "decision_time": pd.to_datetime([
            "2026-01-01T02:00:00Z",
            "2026-01-01T01:00:00Z",
            "2026-01-01T01:30:00Z",
        ], utc=True),
        "row_id": ["later", "earlier", "middle"],
    })
    feature_frame = pd.DataFrame({
        "available_at": pd.to_datetime([
            "2026-01-01T00:00:00Z", "2026-01-01T01:15:00Z"
        ], utc=True),
        "value": [10, 20],
    })
    joined = causal_asof_join(
        decisions, feature_frame, feature_columns=["value"]
    )
    assert joined["row_id"].tolist() == ["later", "earlier", "middle"]
    assert joined["value"].tolist() == [20, 10, 20]


def test_invalid_window_order_and_nonfinite_candles_are_rejected():
    frame = candles()
    try:
        causal_descriptive_features(
            frame,
            volatility_window=0,
            atr_window=2,
            volume_window=2,
            momentum_window=2,
            structure_window=2,
        )
    except ValueError as error:
        assert "positive integer" in str(error)
    else:
        raise AssertionError("Invalid feature window was accepted")

    unordered = frame.iloc[::-1].reset_index(drop=True)
    try:
        features(unordered)
    except ValueError as error:
        assert "available_at" in str(error)
    else:
        raise AssertionError("Unordered candle availability was accepted")

    nonfinite = frame.copy()
    nonfinite.loc[3, "volume"] = float("inf")
    try:
        features(nonfinite)
    except ValueError as error:
        assert "finite" in str(error)
    else:
        raise AssertionError("Non-finite candle input was accepted")


def test_zero_prior_volume_baseline_is_undefined_not_infinite():
    frame = candles()
    frame["volume"] = 0.0
    result = features(frame)
    assert result["relative_volume"].isna().all()
    assert not np.isinf(result.drop(columns="available_at").to_numpy()).any()


def main():
    tests = [
        test_feature_values_match_independent_formulas_and_availability,
        test_features_are_prefix_invariant_and_future_perturbations_do_not_leak,
        test_feature_rows_join_only_after_their_available_at_boundary,
        test_asof_join_preserves_unsorted_decision_row_order,
        test_invalid_window_order_and_nonfinite_candles_are_rejected,
        test_zero_prior_volume_baseline_is_undefined_not_infinite,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
