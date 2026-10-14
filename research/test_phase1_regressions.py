"""Synthetic regression tests for Phase 1 backtester audit findings.

Run with: python -m research.test_phase1_regressions
"""

import math

import pandas as pd

from research.backtester import BacktestConfig, run_backtest, summarize
from research import period_diagnostics


def make_bars(opens, closes=None):
    timestamps = pd.date_range(
        "2026-01-01", periods=len(opens), freq="1h", tz="UTC"
    )
    closes = closes if closes is not None else opens
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "open": opens,
        "high": [max(o, c) for o, c in zip(opens, closes)],
        "low": [min(o, c) for o, c in zip(opens, closes)],
        "close": closes,
        "volume": [1.0] * len(opens),
    })


def config(capital=50.0, fee=0.0, slippage=0.0, allocation=1.0):
    return BacktestConfig(capital, fee, slippage, allocation)


def close(actual, expected, tol=1e-9):
    assert abs(float(actual) - float(expected)) <= tol, (
        f"expected {expected}, got {actual}"
    )


def synthetic_trades(pnls):
    return pd.DataFrame({"net_pnl": pnls})


def test_summary_initial_capital_is_drawdown_peak():
    """Invariant: the $50 initial balance is part of the drawdown peak path."""
    equity = pd.DataFrame({"mark_to_market_equity": [49.0, 48.0]})
    result = summarize(equity, synthetic_trades([]), 50.0)
    close(result["max_drawdown_pct"], -4.0)
    close(result["final_equity"], 48.0)
    close(result["total_return_pct"], -4.0)


def test_summary_trade_metric_cases():
    """Invariant: summary trade statistics match ledger wins and losses."""
    equity = pd.DataFrame({"mark_to_market_equity": [50.0, 60.0]})

    cases = [
        ([], 0.0, 0.0, 0.0),
        ([2.0, 3.0], 100.0, 2.5, math.inf),
        ([-2.0, -4.0], 0.0, -3.0, 0.0),
        ([3.0, -1.0], 50.0, 1.0, 3.0),
    ]
    for pnls, win_rate, average, factor in cases:
        result = summarize(equity, synthetic_trades(pnls), 50.0)
        close(result["final_equity"], 60.0)
        close(result["total_return_pct"], 20.0)
        close(result["win_rate_pct"], win_rate)
        close(result["avg_trade_net_pnl"], average)
        if math.isinf(factor):
            assert math.isinf(result["profit_factor"])
        else:
            close(result["profit_factor"], factor)


def test_open_mark_is_gross_of_exit_costs_for_long_and_short():
    """Invariant: preserve gross MTM while distinguishing net liquidation value."""
    bars = make_bars([100.0, 110.0, 120.0], [100.0, 112.0, 125.0])
    cfg = config(capital=1000.0, fee=0.01, slippage=0.01)

    for side in (1, -1):
        equity, _ = run_backtest(bars, pd.Series([side, side, side]), cfg)
        row = equity.iloc[1]
        raw_close = 112.0
        entry = 110.0 * (1.01 if side == 1 else 0.99)
        qty = 1000.0 / entry
        entry_fee = 10.0
        gross_mtm = 1000.0 - entry_fee + side * (raw_close - entry) * qty
        liquidation = raw_close * (0.99 if side == 1 else 1.01)
        gross_liquidation_pnl = side * (liquidation - entry) * qty
        exit_fee = liquidation * qty * 0.01
        net_liquidation = 1000.0 - entry_fee + gross_liquidation_pnl - exit_fee

        close(row["mark_to_market_equity"], gross_mtm)
        assert abs(float(row["mark_to_market_equity"]) - net_liquidation) > 1e-6
        assert row["position"] == side


def expected_trade(entry_side, entry_open, exit_open, capital, fee, slip):
    entry_price = entry_open * (1 + slip if entry_side == 1 else 1 - slip)
    qty = capital / entry_price
    entry_fee = capital * fee
    exit_side = -entry_side
    exit_price = exit_open * (1 + slip if exit_side == 1 else 1 - slip)
    pnl = entry_side * (exit_price - entry_price) * qty
    exit_fee = exit_price * qty * fee
    return entry_price, exit_price, qty, entry_fee, exit_fee, pnl - entry_fee - exit_fee


def test_reversals_and_terminal_close_reconcile():
    """Invariant: reversals close then reopen at the next open; last position closes at final close."""
    bars = make_bars(
        [100.0, 110.0, 120.0, 130.0, 140.0],
        [102.0, 112.0, 122.0, 132.0, 150.0],
    )
    fee, slip = 0.01, 0.01

    for first_side, reverse_side in ((1, -1), (-1, 1)):
        signals = pd.Series([first_side, reverse_side, reverse_side,
                             reverse_side, reverse_side])
        equity, trades = run_backtest(
            bars, signals, config(1000.0, fee, slip, 1.0)
        )
        assert len(trades) == 2
        assert trades["side"].tolist() == (
            ["LONG", "SHORT"] if first_side == 1 else ["SHORT", "LONG"]
        )

        expected_capital = 1000.0
        for idx, (side, entry_open, exit_open, entry_time, exit_time) in enumerate([
            (first_side, 110.0, 120.0, bars.iloc[1]["timestamp"], bars.iloc[2]["timestamp"]),
            (reverse_side, 120.0, 150.0, bars.iloc[2]["timestamp"], bars.iloc[-1]["available_at"]),
        ]):
            entry_price, exit_price, qty, entry_fee, exit_fee, net = expected_trade(
                side, entry_open, exit_open, expected_capital, fee, slip
            )
            trade = trades.iloc[idx]
            close(trade["entry_price"], entry_price)
            close(trade["exit_price"], exit_price)
            close(trade["qty"], qty)
            close(trade["entry_fee"], entry_fee)
            close(trade["exit_fee"], exit_fee)
            close(trade["net_pnl"], net)
            assert trade["entry_time"] == entry_time
            assert trade["exit_time"] == exit_time
            expected_capital += net

        close(equity.iloc[-1]["realized_equity"], expected_capital)
        close(equity.iloc[-1]["mark_to_market_equity"], expected_capital)
        assert equity.iloc[-1]["position"] == 0
        close(trades["net_pnl"].sum(), expected_capital - 1000.0)


def test_quarterly_equity_returns_and_exit_attribution(tmp_path, monkeypatch):
    """Invariant: equity return is quarter-end account change; trade P&L/fees follow exit quarter."""
    equity = pd.DataFrame({
        "timestamp": ["2026-01-01T00:00:00Z", "2026-03-31T23:00:00Z",
                      "2026-04-01T00:00:00Z", "2026-06-30T23:00:00Z"],
        "mark_to_market_equity": [50.0, 60.0, 61.0, 66.0],
    })
    trades = pd.DataFrame({
        "entry_time": ["2026-03-31T20:00:00Z"],
        "exit_time": ["2026-04-01T02:00:00Z"],
        "net_pnl": [4.0],
        "total_fees": [1.0],
    })
    equity.to_csv(tmp_path / "synthetic_equity.csv", index=False)
    trades.to_csv(tmp_path / "synthetic_trades.csv", index=False)
    monkeypatch.setattr(period_diagnostics, "BASELINE_DIR", tmp_path)

    q1, q2 = period_diagnostics.analyze_quarter("synthetic")
    close(q1["return_pct"], 20.0)
    close(q1["net_pnl_closed_trades"], 0.0)
    close(q1["fees_on_closed_trades"], 0.0)
    close(q2["return_pct"], 10.0)
    close(q2["net_pnl_closed_trades"], 4.0)
    close(q2["fees_on_closed_trades"], 1.0)
    assert q1["trades_closed"] == 0
    assert q2["trades_closed"] == 1


def main():
    tests = [
        test_summary_initial_capital_is_drawdown_peak,
        test_summary_trade_metric_cases,
        test_open_mark_is_gross_of_exit_costs_for_long_and_short,
        test_reversals_and_terminal_close_reconcile,
        test_quarterly_equity_returns_and_exit_attribution,
    ]
    failures = []
    for test in tests:
        try:
            if test is test_quarterly_equity_returns_and_exit_attribution:
                import tempfile
                from pathlib import Path
                with tempfile.TemporaryDirectory() as directory:
                    class MonkeyPatch:
                        @staticmethod
                        def setattr(obj, name, value):
                            setattr(obj, name, value)
                    test(Path(directory), MonkeyPatch())
            else:
                test()
            print(f"PASS: {test.__name__}")
        except AssertionError as error:
            failures.append((test.__name__, error))
            print(f"FAIL: {test.__name__}: {error}")
    if failures:
        raise AssertionError(f"{len(failures)} regression test(s) failed")


if __name__ == "__main__":
    main()
