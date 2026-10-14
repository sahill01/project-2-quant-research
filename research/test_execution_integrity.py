from __future__ import annotations

import pandas as pd

from research.backtester import BacktestConfig, run_backtest


def make_test_data() -> pd.DataFrame:
    """
    Small deterministic dataset designed specifically to test
    execution timing.

    Candle timestamps represent candle OPEN times.
    """

    timestamps = pd.date_range(
        "2026-01-01 00:00",
        periods=5,
        freq="1h",
        tz="UTC",
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "available_at": timestamps + pd.Timedelta(hours=1),

            "open": [
                100.0,
                110.0,
                120.0,
                130.0,
                140.0,
            ],

            "high": [
                105.0,
                115.0,
                125.0,
                135.0,
                145.0,
            ],

            "low": [
                95.0,
                105.0,
                115.0,
                125.0,
                135.0,
            ],

            "close": [
                102.0,
                112.0,
                122.0,
                132.0,
                142.0,
            ],

            "volume": [
                1000.0,
                1000.0,
                1000.0,
                1000.0,
                1000.0,
            ],
        }
    )


def make_config() -> BacktestConfig:
    return BacktestConfig(
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_pct=0.0,
        allocation_fraction=1.0,
    )


def test_entry_occurs_on_next_open():
    """
    Signal on candle 0 should execute on candle 1 OPEN.

    Candle 0:
        close = 102

    Candle 1:
        open = 110

    Therefore the entry price must be 110,
    NOT 102.
    """

    df = make_test_data()

    signal = pd.Series(
        [1, 1, 1, 1, 0],
        index=df.index,
        dtype=int,
    )

    equity_df, trades_df = run_backtest(
        df,
        signal,
        make_config(),
    )

    assert len(trades_df) == 1

    trade = trades_df.iloc[0]

    assert trade["entry_price"] == 110.0

    assert trade["entry_time"] == df.loc[1, "timestamp"]

    print("PASS: signal executes at next candle open")


def test_no_execution_at_signal_candle_close():
    """
    Explicitly prove that the strategy cannot enter at the
    signal candle's closing price.
    """

    df = make_test_data()

    signal = pd.Series(
        [1, 1, 1, 1, 0],
        index=df.index,
        dtype=int,
    )

    _, trades_df = run_backtest(
        df,
        signal,
        make_config(),
    )

    trade = trades_df.iloc[0]

    assert trade["entry_price"] != df.loc[0, "close"]

    print("PASS: no execution at signal candle close")


def test_zero_slippage_and_zero_fee_are_exact():
    """
    With zero fees and zero slippage, execution price should
    exactly equal the relevant candle OPEN.
    """

    df = make_test_data()

    signal = pd.Series(
        [1, 1, 0, 0, 0],
        index=df.index,
        dtype=int,
    )

    _, trades_df = run_backtest(
        df,
        signal,
        make_config(),
    )

    trade = trades_df.iloc[0]

    assert trade["entry_price"] == 110.0
    assert trade["exit_price"] == 130.0

    print("PASS: zero-cost execution prices are exact")


def test_slippage_direction():
    """
    Slippage should work against the trader:

        BUY  -> higher price
        SELL -> lower price
    """

    df = make_test_data()

    config = BacktestConfig(
        initial_capital=1000.0,
        fee_rate=0.0,
        slippage_pct=0.01,
        allocation_fraction=1.0,
    )

    signal = pd.Series(
        [1, 1, 0, 0, 0],
        index=df.index,
        dtype=int,
    )

    _, trades_df = run_backtest(
        df,
        signal,
        config,
    )

    trade = trades_df.iloc[0]

    # Long entry at 110 with 1% adverse slippage.
    assert trade["entry_price"] == 111.1

    # Long exit at 120 with 1% adverse slippage.
    assert trade["exit_price"] == 128.7

    print("PASS: slippage direction is adverse")


def test_final_candle_does_not_create_new_entry():
    """
    A signal on the final candle has no next candle on which
    to execute, so it must not create a new trade.
    """

    df = make_test_data()

    signal = pd.Series(
        [0, 0, 0, 0, 1],
        index=df.index,
        dtype=int,
    )

    _, trades_df = run_backtest(
        df,
        signal,
        make_config(),
    )

    assert len(trades_df) == 0

    print("PASS: final candle cannot create a new entry")


def test_equity_timestamps_match_candle_availability():
    df = make_test_data()

    signal = pd.Series(
        [1, 1, 0, 0, 0],
        index=df.index,
        dtype=int,
    )

    equity_df, trades_df = run_backtest(
        df,
        signal,
        make_config(),
    )

    # Every equity observation must be timestamped when that
    # candle has closed and its OHLCV data is available.
    assert (
        equity_df["timestamp"].reset_index(drop=True)
        == df["available_at"].reset_index(drop=True)
    ).all()

    assert (
        equity_df["available_at"].reset_index(drop=True)
        == df["available_at"].reset_index(drop=True)
    ).all()

    # Entry at candle 1 open; exit at candle 3 open.
    assert trades_df.iloc[0]["entry_time"] == df.iloc[1]["timestamp"]
    assert trades_df.iloc[0]["exit_time"] == df.iloc[3]["timestamp"]

    # The final observation reflects the fully closed position.
    assert equity_df.iloc[-1]["position"] == 0
    assert (
        equity_df.iloc[-1]["mark_to_market_equity"]
        == equity_df.iloc[-1]["realized_equity"]
    )

    print("PASS: equity timestamps match candle availability")


def main():
    print("=" * 60)
    print("EXECUTION TIMELINE INTEGRITY TESTS")
    print("=" * 60)

    test_entry_occurs_on_next_open()
    test_no_execution_at_signal_candle_close()
    test_zero_slippage_and_zero_fee_are_exact()
    test_slippage_direction()
    test_final_candle_does_not_create_new_entry()
    test_equity_timestamps_match_candle_availability()

    print("=" * 60)
    print("ALL EXECUTION INTEGRITY TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()