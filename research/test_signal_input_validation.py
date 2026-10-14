"""Synthetic validation tests for discrete backtester signal inputs."""

import numpy as np
import pandas as pd

from research.backtester import BacktestConfig, run_backtest


def bars() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-01-01", periods=2, freq="4h", tz="UTC"
    )
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=4),
        "open": [100.0, 101.0],
        "high": [100.0, 101.0],
        "low": [100.0, 101.0],
        "close": [100.0, 101.0],
        "volume": [1.0, 1.0],
    })


def config() -> BacktestConfig:
    return BacktestConfig(100.0, 0.0, 0.0, 1.0)


def test_fractional_signal_is_rejected_before_integer_coercion():
    try:
        run_backtest(bars(), pd.Series([1.5, 0.0]), config())
    except ValueError as error:
        assert "Signals must contain only" in str(error)
    else:
        raise AssertionError("Fractional signal was silently coerced")


def test_invalid_final_signal_is_rejected_even_without_next_bar():
    try:
        run_backtest(bars(), pd.Series([0.0, -0.5]), config())
    except ValueError as error:
        assert "Signals must contain only" in str(error)
    else:
        raise AssertionError("Invalid final signal was silently ignored")


def test_boolean_values_are_not_coerced_into_position_signals():
    for values in ([True, False], [True, 0]):
        try:
            run_backtest(
                bars(), pd.Series(values, dtype=object), config()
            )
        except ValueError as error:
            assert "Signals must contain only" in str(error)
        else:
            raise AssertionError("Boolean signal was accepted as a position")


def test_numpy_integer_signals_remain_supported():
    equity, trades = run_backtest(
        bars(), pd.Series(np.array([1, 1], dtype=np.int64)), config()
    )
    assert len(trades) == 1
    assert trades.iloc[0]["side"] == "LONG"


def test_nan_signal_keeps_existing_flat_default():
    equity, trades = run_backtest(
        bars(), pd.Series([float("nan"), 0.0]), config()
    )
    assert trades.empty
    assert (equity["position"] == 0).all()


def main() -> None:
    tests = [
        test_fractional_signal_is_rejected_before_integer_coercion,
        test_invalid_final_signal_is_rejected_even_without_next_bar,
        test_boolean_values_are_not_coerced_into_position_signals,
        test_numpy_integer_signals_remain_supported,
        test_nan_signal_keeps_existing_flat_default,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
