"""
Project 2 — Repeated-trade accounting integrity test.

Purpose:
- Verify entry/exit fees are handled correctly across multiple trades.
- Verify entry_fee state is reset between trades.
- Verify trade-level net P&L reconciles to final account equity.

Run from the project root:
    python -m research.test_accounting_repeated_trades
"""

import pandas as pd

from research.backtester import BacktestConfig, run_backtest


def make_data():
    # Signals are acted on at the NEXT candle open.
    # Three independent long trades:
    #   signal 0 -> entry candle 1 @ 100
    #   signal 1 -> exit  candle 2 @ 110
    #   signal 2 -> entry candle 3 @ 100
    #   signal 3 -> exit  candle 4 @ 110
    #   signal 4 -> entry candle 5 @ 100
    #   signal 5 -> exit  candle 6 @ 110
    timestamps = pd.date_range(
        "2026-01-01",
        periods=7,
        freq="4h",
        tz="UTC",
    )

    opens = [100.0, 100.0, 110.0, 100.0, 110.0, 100.0, 110.0]

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": [p for p in opens],
            "low": [p for p in opens],
            "close": [p for p in opens],
            "volume": [1.0] * len(opens),
        }
    )
    df["available_at"] = df["timestamp"] + pd.Timedelta(hours=4)
    return df


def test_repeated_long_trades():
    df = make_data()

    signal = pd.Series(
        [1, 0, 1, 0, 1, 0, 0],
        dtype=int,
    )

    config = BacktestConfig(
        initial_capital=100.0,
        fee_rate=0.01,
        slippage_pct=0.0,
        allocation_fraction=1.0,
    )

    equity_df, trades_df = run_backtest(df, signal, config)

    assert len(trades_df) == 3, (
        f"Expected 3 trades, got {len(trades_df)}"
    )

    # Independent expected account evolution.
    # Each trade is 100 -> 110 with 1% entry and exit fees.
    expected_equity = 100.0
    expected_entry_fees = []

    for _ in range(3):
        notional = expected_equity
        qty = notional / 100.0

        entry_fee = notional * 0.01
        exit_fee = (110.0 * qty) * 0.01
        gross_pnl = (110.0 - 100.0) * qty

        expected_entry_fees.append(entry_fee)
        expected_equity -= entry_fee
        expected_equity += gross_pnl - exit_fee

    actual_final = float(equity_df["realized_equity"].iloc[-1])

    assert abs(actual_final - expected_equity) < 1e-9, (
        f"Final equity mismatch: expected {expected_equity}, "
        f"got {actual_final}"
    )

    actual_trade_net = float(trades_df["net_pnl"].sum())
    expected_trade_net = expected_equity - 100.0

    assert abs(actual_trade_net - expected_trade_net) < 1e-9, (
        f"Trade P&L mismatch: expected {expected_trade_net}, "
        f"got {actual_trade_net}"
    )

    assert "entry_fee" in trades_df.columns, (
        "Trade records must expose entry_fee explicitly."
    )

    for actual, expected in zip(
        trades_df["entry_fee"],
        expected_entry_fees,
    ):
        assert abs(float(actual) - expected) < 1e-9, (
            f"Entry fee mismatch: expected {expected}, got {actual}"
        )

    assert all(trades_df["entry_fee"].iloc[i] != trades_df["entry_fee"].iloc[i + 1]
               for i in range(len(trades_df) - 1)), (
        "Entry fees should change with account equity; possible fee-state leak."
    )


def main():
    print("=" * 60)
    print("REPEATED-TRADE ACCOUNTING INTEGRITY TEST")
    print("=" * 60)

    test_repeated_long_trades()

    print("PASS: repeated trades reconcile")
    print("PASS: entry fee resets between trades")
    print("PASS: trade-level P&L reconciles to final equity")
    print("=" * 60)
    print("REPEATED-TRADE ACCOUNTING TEST PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
