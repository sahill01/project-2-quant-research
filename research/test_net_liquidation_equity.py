"""Synthetic checks for estimated net liquidation equity."""

import pandas as pd

from research.backtester import BacktestConfig, run_backtest


FEE = 0.01
SLIPPAGE = 0.01
CAPITAL = 1000.0


def make_bars(opens, closes):
    timestamps = pd.date_range(
        "2026-02-01", periods=len(opens), freq="1h", tz="UTC"
    )
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "open": opens,
        "high": [max(o, c) for o, c in zip(opens, closes)],
        "low": [min(o, c) for o, c in zip(opens, closes)],
        "close": closes,
        "volume": [1.0] * len(opens),
    })


def run(bars, signals):
    config = BacktestConfig(
        initial_capital=CAPITAL,
        fee_rate=FEE,
        slippage_pct=SLIPPAGE,
        allocation_fraction=1.0,
    )
    return run_backtest(bars, pd.Series(signals, dtype=int), config)


def close(actual, expected):
    assert abs(float(actual) - float(expected)) < 1e-9, (
        f"expected {expected}, got {actual}"
    )


def independent_valuation(side, entry_open, raw_close, capital):
    """Recompute from raw inputs and documented adverse fill directions."""
    entry_price = entry_open * (1 + SLIPPAGE if side == 1 else 1 - SLIPPAGE)
    qty = capital / entry_price
    entry_fee = capital * FEE
    account_equity = capital - entry_fee
    exit_price = raw_close * (1 - SLIPPAGE if side == 1 else 1 + SLIPPAGE)
    gross_pnl = side * (exit_price - entry_price) * qty
    exit_fee = abs(exit_price * qty) * FEE
    net_liquidation = account_equity + gross_pnl - exit_fee
    mark = account_equity + side * (raw_close - entry_price) * qty
    return mark, net_liquidation, qty, entry_price, exit_price, entry_fee, exit_fee


def test_open_long_and_short_with_costs():
    """Open-position valuations use adverse exit fills and one exit fee."""
    bars = make_bars(
        [100.0, 110.0, 120.0, 130.0],
        [100.0, 112.0, 122.0, 125.0],
    )

    for side in (1, -1):
        equity, _ = run(bars, [side] * len(bars))
        mark, net, *_ = independent_valuation(side, 110.0, 112.0, CAPITAL)
        close(equity.iloc[1]["mark_to_market_equity"], mark)
        close(equity.iloc[1]["net_liquidation_equity"], net)
        assert equity.iloc[1]["position"] == side
        assert abs(mark - net) > 1e-6


def test_flat_valuation_equals_realized_equity():
    """No position means no estimated close costs are applied."""
    bars = make_bars([100.0, 110.0, 120.0], [101.0, 111.0, 121.0])
    equity, trades = run(bars, [0, 0, 0])
    assert trades.empty
    assert (equity["position"] == 0).all()
    pd.testing.assert_series_equal(
        equity["net_liquidation_equity"],
        equity["realized_equity"],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        equity["mark_to_market_equity"],
        equity["realized_equity"],
        check_names=False,
    )


def test_flat_after_closed_trade_keeps_realized_equity_without_extra_fees():
    """Closed trade fees are booked once and flat valuations stay realized."""
    bars = make_bars(
        [100.0, 110.0, 120.0, 130.0, 140.0],
        [100.0, 112.0, 122.0, 132.0, 142.0],
    )
    equity, trades = run(bars, [1, 0, 0, 0, 0])

    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["entry_time"] == bars.iloc[1]["timestamp"]
    assert trade["exit_time"] == bars.iloc[2]["timestamp"]
    close(trade["total_fees"], trade["entry_fee"] + trade["exit_fee"])
    close(trade["net_pnl"], trade["pnl_before_fees"] - trade["total_fees"])

    flat_rows = equity[equity["position"] == 0]
    assert len(flat_rows) >= 2
    pd.testing.assert_series_equal(
        flat_rows["mark_to_market_equity"].reset_index(drop=True),
        flat_rows["realized_equity"].reset_index(drop=True),
        check_names=False,
    )
    pd.testing.assert_series_equal(
        flat_rows["net_liquidation_equity"].reset_index(drop=True),
        flat_rows["realized_equity"].reset_index(drop=True),
        check_names=False,
    )
    close(equity.iloc[-1]["realized_equity"], CAPITAL + trade["net_pnl"])


def test_final_liquidation_matches_both_valuations():
    """Terminal close realizes the same costs estimated by net liquidation."""
    bars = make_bars(
        [100.0, 110.0, 120.0, 130.0],
        [100.0, 112.0, 122.0, 150.0],
    )

    for side in (1, -1):
        equity, trades = run(bars, [side] * len(bars))
        last = equity.iloc[-1]
        trade = trades.iloc[-1]
        assert last["position"] == 0
        close(last["mark_to_market_equity"], last["realized_equity"])
        close(last["net_liquidation_equity"], last["realized_equity"])

        mark, net, qty, entry_price, exit_price, entry_fee, exit_fee = (
            independent_valuation(side, 110.0, 150.0, CAPITAL)
        )
        del mark, net
        gross_pnl = side * (exit_price - entry_price) * qty
        expected_final = CAPITAL - entry_fee + gross_pnl - exit_fee
        close(trade["entry_price"], entry_price)
        close(trade["exit_price"], exit_price)
        close(trade["entry_fee"], entry_fee)
        close(trade["exit_fee"], exit_fee)
        close(trade["net_pnl"], gross_pnl - entry_fee - exit_fee)
        close(last["realized_equity"], expected_final)


def test_reversal_values_new_open_position():
    """At a reversal, valuation belongs to the newly opened side after closing the old trade."""
    bars = make_bars(
        [100.0, 110.0, 120.0, 130.0, 140.0],
        [100.0, 112.0, 122.0, 132.0, 150.0],
    )
    equity, trades = run(bars, [1, -1, -1, -1, -1])
    assert len(trades) == 2
    assert trades.iloc[0]["side"] == "LONG"
    assert trades.iloc[0]["exit_time"] == bars.iloc[2]["timestamp"]
    assert equity.iloc[2]["position"] == -1

    first_net = float(trades.iloc[0]["net_pnl"])
    capital_after_first = CAPITAL + first_net
    entry_price = 120.0 * (1 - SLIPPAGE)
    qty = capital_after_first / entry_price
    entry_fee = capital_after_first * FEE
    account_equity = capital_after_first - entry_fee
    estimated_exit = 122.0 * (1 + SLIPPAGE)
    gross_pnl = entry_price - estimated_exit
    exit_fee = estimated_exit * qty * FEE
    expected_net_liquidation = account_equity + (gross_pnl * qty) - exit_fee
    close(equity.iloc[2]["net_liquidation_equity"], expected_net_liquidation)


def main():
    tests = [
        test_open_long_and_short_with_costs,
        test_flat_valuation_equals_realized_equity,
        test_flat_after_closed_trade_keeps_realized_equity_without_extra_fees,
        test_final_liquidation_matches_both_valuations,
        test_reversal_values_new_open_position,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
