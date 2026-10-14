"""Synthetic checks for cross-asset descriptive diagnostics."""

import pandas as pd

from research.run_cross_asset_diagnostics import (
    drawdown_episodes,
    quarterly_diagnostics,
    trade_diagnostics,
)


def test_drawdown_episodes_recovery_and_open_episode():
    timestamps = pd.date_range(
        "2026-01-01", periods=6, freq="1h", tz="UTC"
    )
    equity = pd.DataFrame({
        "timestamp": timestamps,
        "mark_to_market_equity": [50.0, 60.0, 55.0, 52.0, 60.0, 58.0],
    })
    episodes = drawdown_episodes(
        "SYN", "test", equity, "mark_to_market_equity"
    )
    assert len(episodes) == 2
    assert episodes[0]["recovered"] is True
    assert episodes[0]["peak_equity"] == 60.0
    assert episodes[0]["trough_equity"] == 52.0
    assert episodes[0]["recovery_time"] == timestamps[4]
    assert episodes[1]["recovered"] is False
    assert episodes[1]["trough_equity"] == 58.0
    assert pd.isna(episodes[1]["recovery_time"])


def test_quarterly_equity_returns_are_separate_from_exit_quarter_trade_pnl():
    timestamps = pd.to_datetime([
        "2026-01-01T00:00:00Z", "2026-03-31T23:00:00Z",
        "2026-04-01T00:00:00Z", "2026-06-30T23:00:00Z",
    ], utc=True)
    equity = pd.DataFrame({
        "timestamp": timestamps,
        "realized_equity": [50.0, 60.0, 61.0, 66.0],
        "position": [0, 1, 1, 0],
        "mark_to_market_equity": [50.0, 60.0, 61.0, 66.0],
        "net_liquidation_equity": [50.0, 59.0, 60.0, 66.0],
    })
    trades = pd.DataFrame({
        "entry_time": pd.to_datetime(["2026-03-31T20:00:00Z"], utc=True),
        "exit_time": pd.to_datetime(["2026-04-01T02:00:00Z"], utc=True),
        "side": ["LONG"],
        "qty": [1.0],
        "pnl_before_fees": [5.0],
        "entry_fee": [0.5],
        "exit_fee": [0.5],
        "total_fees": [1.0],
        "net_pnl": [4.0],
    })
    rows = quarterly_diagnostics({("SYN", "test"): (equity, trades)})
    q1 = rows.loc[rows["quarter_utc"] == "2026Q1"].iloc[0]
    q2 = rows.loc[rows["quarter_utc"] == "2026Q2"].iloc[0]
    assert abs(q1["return_mark_to_market_pct"] - 20.0) < 1e-9
    assert q1["closed_trades"] == 0
    assert q1["closed_trade_net_pnl"] == 0.0
    assert abs(q2["return_mark_to_market_pct"] - 10.0) < 1e-9
    assert abs(
        q2["return_net_liquidation_pct"] - (66.0 / 59.0 - 1) * 100
    ) < 1e-9
    assert q2["closed_trade_net_pnl"] == 4.0
    assert q2["entry_fees_at_exit_quarter"] == 0.5
    assert q2["exit_fees_at_exit_quarter"] == 0.5


def test_trade_diagnostics_reconcile_fees_and_report_sides():
    trades = pd.DataFrame({
        "side": ["LONG", "SHORT"],
        "entry_time": pd.to_datetime([
            "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"
        ], utc=True),
        "exit_time": pd.to_datetime([
            "2026-01-01T04:00:00Z", "2026-01-03T00:00:00Z"
        ], utc=True),
        "qty": [1.0, 1.0],
        "pnl_before_fees": [3.0, -2.0],
        "entry_fee": [0.5, 0.5],
        "exit_fee": [0.5, 0.5],
        "total_fees": [1.0, 1.0],
        "net_pnl": [2.0, -3.0],
    })
    result = trade_diagnostics({("SYN", "test"): (pd.DataFrame(), trades)})
    long_row = result.loc[result["side"] == "LONG"].iloc[0]
    short_row = result.loc[result["side"] == "SHORT"].iloc[0]
    assert long_row["net_pnl"] == 2.0
    assert short_row["net_pnl"] == -3.0
    assert long_row["total_fees"] == short_row["total_fees"] == 1.0
    assert long_row["median_duration_hours"] == 4.0
    assert short_row["median_duration_hours"] == 24.0


def main():
    tests = [
        test_drawdown_episodes_recovery_and_open_episode,
        test_quarterly_equity_returns_are_separate_from_exit_quarter_trade_pnl,
        test_trade_diagnostics_reconcile_fees_and_report_sides,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
