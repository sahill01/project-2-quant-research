"""Synthetic checks for causal regime construction and attribution timing."""

import pandas as pd

from research.run_cross_asset_regime_diagnostics import (
    attribute_equity_changes,
    build_regimes,
)


def test_regime_labels_use_only_trailing_data_and_calibration_window():
    timestamps = pd.date_range(
        "2026-01-01", periods=15, freq="4h", tz="UTC"
    )
    close = [100, 101, 102, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112]
    market = pd.DataFrame({"available_at": timestamps, "close": close})
    params = {
        "trend_lookback_days": 1,
        "volatility_lookback_days": 1,
        "calibration_days": 1,
    }
    original, threshold, calibration_end = build_regimes(market, **params)

    changed_future = market.copy()
    changed_future.loc[10:, "close"] = [150, 90, 160, 80, 170]
    revised, revised_threshold, _ = build_regimes(changed_future, **params)

    assert threshold == revised_threshold
    assert calibration_end == timestamps[6]
    assert original.loc[:6, "regime"].eq("CALIBRATION").all()
    assert original.loc[7:9, "regime"].equals(revised.loc[7:9, "regime"])
    assert original.loc[7, "regime"] == "UP_LOW_VOL"


def test_equity_changes_are_attributed_to_prior_close_regime_and_reconcile():
    timestamps = pd.date_range(
        "2026-01-01", periods=4, freq="4h", tz="UTC"
    )
    regimes = pd.DataFrame({
        "available_at": timestamps,
        "regime": ["CALIBRATION", "UP_LOW_VOL", "DOWN_HIGH_VOL", "CALIBRATION"],
    })
    equity = pd.DataFrame({
        "timestamp": timestamps,
        "position": [0, 1, 1, 0],
        "realized_equity": [50.0, 50.0, 50.0, 54.0],
        "mark_to_market_equity": [50.0, 52.0, 51.0, 54.0],
        "net_liquidation_equity": [50.0, 51.0, 50.0, 54.0],
    })
    rows = attribute_equity_changes(
        equity,
        regimes,
        asset="SYN",
        strategy="synthetic",
        volatility_threshold=0.5,
        calibration_end=timestamps[0],
    )
    result = {
        (row["equity_series"], row["regime"]): row["equity_pnl_dollars"]
        for row in rows
    }
    # The first two deltas use the regimes available at t0 and t1; the
    # following delta uses the regime available at t2.
    assert result[("mark_to_market_equity", "CALIBRATION")] == 2.0
    assert result[("mark_to_market_equity", "UP_LOW_VOL")] == -1.0
    assert result[("mark_to_market_equity", "DOWN_HIGH_VOL")] == 3.0
    assert result[("net_liquidation_equity", "CALIBRATION")] == 1.0
    assert result[("net_liquidation_equity", "UP_LOW_VOL")] == -1.0
    assert result[("net_liquidation_equity", "DOWN_HIGH_VOL")] == 4.0
    assert sum(
        row["equity_pnl_dollars"] for row in rows
        if row["equity_series"] == "mark_to_market_equity"
    ) == 4.0


def test_equity_attribution_rejects_timestamp_mismatch_and_open_final_position():
    timestamps = pd.date_range(
        "2026-01-01", periods=2, freq="4h", tz="UTC"
    )
    regimes = pd.DataFrame({
        "available_at": timestamps,
        "regime": ["CALIBRATION", "CALIBRATION"],
    })
    equity = pd.DataFrame({
        "timestamp": timestamps + pd.Timedelta(minutes=1),
        "position": [0, 0],
        "realized_equity": [50.0, 50.0],
        "mark_to_market_equity": [50.0, 50.0],
        "net_liquidation_equity": [50.0, 50.0],
    })
    try:
        attribute_equity_changes(
            equity, regimes, asset="SYN", strategy="test",
            volatility_threshold=0.1, calibration_end=timestamps[0],
        )
    except ValueError as error:
        assert "do not align" in str(error)
    else:
        raise AssertionError("Mismatched market/equity timestamps were accepted")

    equity["timestamp"] = timestamps
    equity.loc[1, "position"] = 1
    try:
        attribute_equity_changes(
            equity, regimes, asset="SYN", strategy="test",
            volatility_threshold=0.1, calibration_end=timestamps[0],
        )
    except ValueError as error:
        assert "Final position" in str(error)
    else:
        raise AssertionError("Open final position was accepted")


def main():
    tests = [
        test_regime_labels_use_only_trailing_data_and_calibration_window,
        test_equity_changes_are_attributed_to_prior_close_regime_and_reconcile,
        test_equity_attribution_rejects_timestamp_mismatch_and_open_final_position,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
