"""
Backtester accounting integrity tests.

These tests verify that:
- entry fees reduce equity
- exit fees reduce equity
- trade-level net P&L includes BOTH fees
- long and short accounting are symmetric
- zero-fee accounting is exact
"""

import pandas as pd

from research.backtester import BacktestConfig, run_backtest


def make_test_data():
    timestamps = pd.date_range(
        "2026-01-01 00:00:00",
        periods=4,
        freq="1h",
        tz="UTC",
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "available_at": timestamps + pd.Timedelta(hours=1),
            "open": [100.0, 110.0, 120.0, 130.0],
            "high": [105.0, 115.0, 125.0, 135.0],
            "low": [95.0, 105.0, 115.0, 125.0],
            "close": [102.0, 112.0, 122.0, 132.0],
            "volume": [1000.0] * 4,
        }
    )


def config(fee_rate=0.0, allocation=1.0):
    return BacktestConfig(
        initial_capital=1000.0,
        fee_rate=fee_rate,
        slippage_pct=0.0,
        allocation_fraction=allocation,
    )


def assert_close(actual, expected, tolerance=1e-9):
    assert abs(actual - expected) <= tolerance, (
        f"Expected {expected}, got {actual}"
    )


def test_zero_fee_long():
    df = make_test_data()

    # Signal at candle 0 -> entry candle 1 open = 110
    # Signal at candle 2 -> exit candle 3 open = 130
    signal = pd.Series([1, 1, 0, 0], index=df.index)

    equity_curve, trades = run_backtest(
        df,
        signal,
        config(fee_rate=0.0),
    )

    trade = trades.iloc[0]

    qty = 1000.0 / 110.0
    expected_pnl = (130.0 - 110.0) * qty
    expected_equity = 1000.0 + expected_pnl

    assert_close(trade["pnl_before_fees"], expected_pnl)
    assert_close(trade["net_pnl"], expected_pnl)
    assert_close(equity_curve.iloc[-1]["realized_equity"], expected_equity)

    print("PASS: zero-fee long accounting")


def test_long_fees():
    df = make_test_data()

    signal = pd.Series([1, 1, 0, 0], index=df.index)

    fee_rate = 0.01

    equity_curve, trades = run_backtest(
        df,
        signal,
        config(fee_rate=fee_rate),
    )

    trade = trades.iloc[0]

    qty = 1000.0 / 110.0

    entry_notional = 1000.0
    entry_fee = entry_notional * fee_rate

    gross_pnl = (130.0 - 110.0) * qty

    exit_notional = 130.0 * qty
    exit_fee = exit_notional * fee_rate

    expected_net_pnl = gross_pnl - entry_fee - exit_fee
    expected_equity = 1000.0 + expected_net_pnl

    assert_close(trade["pnl_before_fees"], gross_pnl)

    # This is the important accounting test.
    assert_close(trade["net_pnl"], expected_net_pnl)

    assert_close(
        equity_curve.iloc[-1]["realized_equity"],
        expected_equity,
    )

    print("PASS: long entry + exit fees reconcile")


def test_short_fees():
    df = make_test_data()

    signal = pd.Series([-1, -1, 0, 0], index=df.index)

    fee_rate = 0.01

    equity_curve, trades = run_backtest(
        df,
        signal,
        config(fee_rate=fee_rate),
    )

    trade = trades.iloc[0]

    qty = 1000.0 / 110.0

    entry_notional = 1000.0
    entry_fee = entry_notional * fee_rate

    gross_pnl = (110.0 - 130.0) * qty

    exit_notional = 130.0 * qty
    exit_fee = exit_notional * fee_rate

    expected_net_pnl = gross_pnl - entry_fee - exit_fee
    expected_equity = 1000.0 + expected_net_pnl

    assert_close(trade["pnl_before_fees"], gross_pnl)
    assert_close(trade["net_pnl"], expected_net_pnl)

    assert_close(
        equity_curve.iloc[-1]["realized_equity"],
        expected_equity,
    )

    print("PASS: short entry + exit fees reconcile")


def test_mark_to_market():
    df = make_test_data()

    signal = pd.Series([1, 1, 1, 1], index=df.index)

    equity_curve, trades = run_backtest(
        df,
        signal,
        config(fee_rate=0.0),
    )

    # Entry happens at candle 1 open = 110.
    # Candle 1 close = 112.
    # Therefore unrealized P&L should be:
    #
    # (112 - 110) * (1000 / 110)
    qty = 1000.0 / 110.0
    expected_mtm = 1000.0 + (112.0 - 110.0) * qty

    row = equity_curve.iloc[1]

    assert_close(
        row["mark_to_market_equity"],
        expected_mtm,
    )

    print("PASS: mark-to-market equity")


def main():
    print("=" * 60)
    print("BACKTESTER ACCOUNTING INTEGRITY TESTS")
    print("=" * 60)

    tests = [
        test_zero_fee_long,
        test_long_fees,
        test_short_fees,
        test_mark_to_market,
    ]

    for test in tests:
        test()

    print("=" * 60)
    print("ALL ACCOUNTING TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()