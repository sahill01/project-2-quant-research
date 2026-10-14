"""Synthetic differential check against a test-only accounting reference.

The reference below uses direct scalar formulas and does not import production
fill, fee, sizing, trade-accounting, or valuation helpers.
"""

import numpy as np
import pandas as pd

from research.backtester import BacktestConfig, run_backtest


def _synthetic_candles():
    opens = [100.0, 103.0, 98.0, 96.0, 101.0, 105.0]
    closes = [101.0, 99.0, 97.0, 102.0, 104.0, 103.0]
    timestamps = pd.date_range(
        "2026-02-01T00:00:00Z", periods=len(opens), freq="1h"
    )
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "open": opens,
        "high": [max(o, c) + 1.0 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 1.0 for o, c in zip(opens, closes)],
        "close": closes,
        "volume": [100.0] * len(opens),
    })


def _reference_simulation(candles, signals, config):
    """Independent scalar model of the declared one-position execution rules."""
    cash = float(config.initial_capital)
    held_side = 0
    quantity = 0.0
    entry_fill = None
    entry_time = None
    entry_notional = 0.0
    entry_fee = 0.0
    trade_rows = []
    equity_rows = []

    def order_fill(reference_price, order_side):
        multiplier = (
            1.0 + config.slippage_pct
            if order_side == 1
            else 1.0 - config.slippage_pct
        )
        return float(reference_price) * multiplier

    def close_held_position(fill_price, fill_time):
        nonlocal cash, held_side, quantity, entry_fill, entry_time
        nonlocal entry_notional, entry_fee
        gross = (fill_price - entry_fill) * quantity * held_side
        exit_fee = abs(fill_price * quantity) * config.fee_rate
        total_fees = entry_fee + exit_fee
        net = gross - total_fees
        cash += gross - exit_fee
        trade_rows.append({
            "entry_time": entry_time,
            "exit_time": fill_time,
            "side": "LONG" if held_side == 1 else "SHORT",
            "entry_price": entry_fill,
            "exit_price": fill_price,
            "qty": quantity,
            "entry_notional": entry_notional,
            "pnl_before_fees": gross,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "total_fees": total_fees,
            "net_pnl": net,
            "return_on_entry_notional_pct": net / entry_notional * 100.0,
        })
        held_side = 0
        quantity = 0.0
        entry_fill = None
        entry_time = None
        entry_notional = 0.0
        entry_fee = 0.0

    for index, candle in candles.iterrows():
        if index > 0:
            target_side = int(signals.iloc[index - 1])
            if target_side != held_side:
                market_open = float(candle["open"])
                if held_side:
                    close_fill = order_fill(market_open, -held_side)
                    close_held_position(close_fill, candle["timestamp"])
                if target_side:
                    entry_fill = order_fill(market_open, target_side)
                    entry_notional = max(
                        cash * config.allocation_fraction, 0.0
                    )
                    quantity = entry_notional / entry_fill
                    entry_fee = entry_notional * config.fee_rate
                    cash -= entry_fee
                    held_side = target_side
                    entry_time = candle["timestamp"]

        if index == len(candles) - 1 and held_side:
            terminal_fill = order_fill(float(candle["close"]), -held_side)
            close_held_position(terminal_fill, candle["available_at"])

        if held_side:
            marked = cash + (
                float(candle["close"]) - entry_fill
            ) * quantity * held_side
            estimated_exit = order_fill(float(candle["close"]), -held_side)
            estimated_gross = (
                estimated_exit - entry_fill
            ) * quantity * held_side
            estimated_fee = abs(estimated_exit * quantity) * config.fee_rate
            liquidation = cash + estimated_gross - estimated_fee
        else:
            marked = cash
            liquidation = cash

        equity_rows.append({
            "timestamp": candle["available_at"],
            "available_at": candle["available_at"],
            "realized_equity": cash,
            "mark_to_market_equity": marked,
            "net_liquidation_equity": liquidation,
            "position": held_side,
        })

    return pd.DataFrame(equity_rows), pd.DataFrame(trade_rows)


def _assert_frames_match(actual, expected, *, name):
    assert actual.columns.tolist() == expected.columns.tolist(), name
    assert len(actual) == len(expected), name
    for column in actual.columns:
        if column in {"timestamp", "available_at", "entry_time", "exit_time", "side"}:
            assert actual[column].tolist() == expected[column].tolist(), (
                name, column, actual[column].tolist(), expected[column].tolist()
            )
        else:
            left = pd.to_numeric(actual[column]).to_numpy(dtype=float)
            right = pd.to_numeric(expected[column]).to_numpy(dtype=float)
            assert np.isfinite(left).all() and np.isfinite(right).all(), (name, column)
            assert np.allclose(left, right, atol=1e-9, rtol=0.0), (
                name, column, left.tolist(), right.tolist()
            )


def test_backtest_matches_independent_synthetic_reference():
    candles = _synthetic_candles()
    config = BacktestConfig(
        initial_capital=500.0,
        fee_rate=0.0017,
        slippage_pct=0.003,
        allocation_fraction=0.8,
    )
    scenarios = {
        "flat": [0, 0, 0, 0, 0, 0],
        "long_then_flat": [1, 1, 0, 0, 0, 0],
        "short_then_flat": [-1, -1, 0, 0, 0, 0],
        # Enters long, reverses short, reverses long, then closes at final close.
        "both_reversals_and_terminal_close": [1, 1, -1, -1, 1, 1],
    }

    for name, values in scenarios.items():
        signals = pd.Series(values, dtype=int)
        actual_equity, actual_trades = run_backtest(candles, signals, config)
        expected_equity, expected_trades = _reference_simulation(
            candles, signals, config
        )
        _assert_frames_match(actual_equity, expected_equity, name=f"{name}/equity")
        _assert_frames_match(actual_trades, expected_trades, name=f"{name}/trades")

        assert actual_equity.iloc[-1]["position"] == 0, name
        assert actual_equity.iloc[-1]["realized_equity"] == actual_equity.iloc[-1][
            "mark_to_market_equity"
        ], name
        assert actual_equity.iloc[-1]["realized_equity"] == actual_equity.iloc[-1][
            "net_liquidation_equity"
        ], name

    reversal_trades = run_backtest(
        candles,
        pd.Series(scenarios["both_reversals_and_terminal_close"], dtype=int),
        config,
    )[1]
    assert reversal_trades["side"].tolist() == ["LONG", "SHORT", "LONG"]
    assert reversal_trades.iloc[-1]["exit_time"] == candles.iloc[-1]["available_at"]


def main():
    test_backtest_matches_independent_synthetic_reference()
    print("PASS: test_backtest_matches_independent_synthetic_reference")


if __name__ == "__main__":
    main()
