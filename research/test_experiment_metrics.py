"""Synthetic checks for time-window backtest metrics and attribution."""

import pandas as pd

from research.experiment_metrics import metrics_by_temporal_split
from research.experiment_protocol import TemporalSplit, TimeWindow


def synthetic_split():
    return TemporalSplit(
        train=TimeWindow("2026-01-01T01:00:00Z", "2026-01-01T03:00:00Z"),
        validation=TimeWindow("2026-01-01T03:00:00Z", "2026-01-01T05:00:00Z"),
        holdout=TimeWindow("2026-01-01T05:00:00Z", "2026-01-01T07:00:00Z"),
    )


def synthetic_ledgers():
    times = pd.date_range("2026-01-01", periods=7, freq="1h", tz="UTC")
    equity = pd.DataFrame({
        "available_at": times,
        "position": [0, 1, 1, 1, 0, 1, 0],
        "realized_equity": [50.0, 48.0, 51.0, 45.0, 55.0, 55.0, 50.0],
        "mark_to_market_equity": [50.0, 48.0, 51.0, 45.0, 55.0, 55.0, 50.0],
        "net_liquidation_equity": [50.0, 47.0, 50.0, 44.0, 55.0, 55.0, 50.0],
    })
    trades = pd.DataFrame({
        "entry_time": pd.to_datetime([
            "2026-01-01T02:30:00Z", "2026-01-01T03:30:00Z"
        ], utc=True),
        "exit_time": pd.to_datetime([
            "2026-01-01T03:30:00Z", "2026-01-01T05:30:00Z"
        ], utc=True),
        "pnl_before_fees": [5.0, -2.0],
        "entry_fee": [0.5, 0.2],
        "exit_fee": [0.5, 0.2],
        "total_fees": [1.0, 0.4],
        "net_pnl": [4.0, -2.4],
    })
    return equity, trades


def test_period_returns_and_drawdowns_use_prior_equity_as_start_peak():
    equity, trades = synthetic_ledgers()
    report = metrics_by_temporal_split(equity, trades, synthetic_split())
    train = report.loc[report.period == "train"].iloc[0]
    validation = report.loc[report.period == "validation"].iloc[0]
    holdout = report.loc[report.period == "holdout"].iloc[0]

    assert train.starting_equity_mark_to_market == 50.0
    assert train.ending_equity_mark_to_market == 51.0
    assert abs(train.max_drawdown_pct_mark_to_market + 4.0) < 1e-10
    assert abs(train.max_drawdown_dollars_mark_to_market + 2.0) < 1e-10
    assert abs(validation.total_return_pct_mark_to_market - (55 / 51 - 1) * 100) < 1e-10
    assert abs(validation.max_drawdown_pct_mark_to_market - (45 / 51 - 1) * 100) < 1e-10
    assert abs(validation.max_drawdown_dollars_mark_to_market + 6.0) < 1e-10
    assert holdout.total_return_pct_mark_to_market < 0
    assert abs(holdout.max_drawdown_dollars_mark_to_market + 5.0) < 1e-10


def test_closed_trade_pnl_and_entry_exit_fee_event_attribution_are_separate():
    equity, trades = synthetic_ledgers()
    report = metrics_by_temporal_split(equity, trades, synthetic_split())
    train = report.loc[report.period == "train"].iloc[0]
    validation = report.loc[report.period == "validation"].iloc[0]
    holdout = report.loc[report.period == "holdout"].iloc[0]

    assert train.closed_trades_by_exit_time == 0
    assert train.closed_trade_net_pnl_by_exit_time == 0.0
    assert train.entry_fees_paid_by_entry_time == 0.5
    assert validation.closed_trades_by_exit_time == 1
    assert validation.closed_trade_net_pnl_by_exit_time == 4.0
    assert validation.closed_trade_entry_fees_by_exit_time == 0.5
    assert validation.closed_trade_exit_fees_by_exit_time == 0.5
    assert validation.entry_fees_paid_by_entry_time == 0.2
    assert validation.exit_fees_paid_by_exit_time == 0.5
    assert holdout.closed_trades_by_exit_time == 1
    assert holdout.closed_trade_net_pnl_by_exit_time == -2.4
    assert holdout.entry_fees_paid_by_entry_time == 0.0
    assert holdout.exit_fees_paid_by_exit_time == 0.2


def test_invalid_trade_accounting_and_missing_period_observation_fail():
    equity, trades = synthetic_ledgers()
    bad_trades = trades.copy()
    bad_trades.loc[0, "total_fees"] = 2.0
    try:
        metrics_by_temporal_split(equity, bad_trades, synthetic_split())
    except ValueError as error:
        assert "fee totals" in str(error)
    else:
        raise AssertionError("Invalid fee accounting was accepted")

    empty_period_split = TemporalSplit(
        train=TimeWindow("2026-01-01T00:30:00Z", "2026-01-01T00:45:00Z"),
        validation=synthetic_split().validation,
        holdout=synthetic_split().holdout,
    )
    try:
        metrics_by_temporal_split(equity, trades, empty_period_split)
    except ValueError as error:
        assert "No equity observations" in str(error)
    else:
        raise AssertionError("A split window with no equity rows was accepted")

    zero_start = equity.copy()
    zero_start.loc[0, "mark_to_market_equity"] = 0.0
    zero_start.loc[1, "mark_to_market_equity"] = 0.0
    try:
        metrics_by_temporal_split(zero_start, trades, synthetic_split())
    except ValueError as error:
        assert "non-positive starting" in str(error)
    else:
        raise AssertionError("Percentage return from zero starting equity was accepted")

    reversed_trade = trades.copy()
    reversed_trade.loc[0, "exit_time"] = pd.Timestamp("2026-01-01T01:30:00Z")
    try:
        metrics_by_temporal_split(equity, reversed_trade, synthetic_split())
    except ValueError as error:
        assert "precede entry" in str(error)
    else:
        raise AssertionError("Trade exit before entry was accepted")


def main():
    tests = [
        test_period_returns_and_drawdowns_use_prior_equity_as_start_peak,
        test_closed_trade_pnl_and_entry_exit_fee_event_attribution_are_separate,
        test_invalid_trade_accounting_and_missing_period_observation_fail,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
