"""Synthetic checks for fixed fee/slippage sensitivity scenarios."""

import pandas as pd

from research.run_cross_asset_cost_sensitivity import (
    cost_scenarios,
    evaluate_case,
)


def test_cost_scenarios_change_only_fees_and_slippage():
    cases = cost_scenarios(0.00059, 0.0002)
    assert [case["scenario"] for case in cases] == [
        "zero_cost", "configured", "double_fee", "double_slippage", "double_both"
    ]
    assert cases[0]["fee_rate"] == cases[0]["slippage_pct"] == 0.0
    assert cases[1]["fee_rate"] == 0.00059
    assert cases[1]["slippage_pct"] == 0.0002
    assert cases[2]["fee_rate"] == 2 * cases[1]["fee_rate"]
    assert cases[2]["slippage_pct"] == cases[1]["slippage_pct"]
    assert cases[3]["fee_rate"] == cases[1]["fee_rate"]
    assert cases[3]["slippage_pct"] == 2 * cases[1]["slippage_pct"]
    assert cases[4]["fee_rate"] == 2 * cases[1]["fee_rate"]
    assert cases[4]["slippage_pct"] == 2 * cases[1]["slippage_pct"]


def test_cost_case_matches_independent_long_fill_and_fee_calculation():
    timestamps = pd.date_range("2026-01-01", periods=4, freq="4h", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=4),
        "open": [100.0, 110.0, 120.0, 130.0],
        "high": [105.0, 115.0, 125.0, 135.0],
        "low": [95.0, 105.0, 115.0, 125.0],
        "close": [102.0, 112.0, 122.0, 132.0],
        "volume": [1000.0] * 4,
    })
    signal = pd.Series([1, 1, 0, 0])
    scenario = {"scenario": "synthetic", "fee_rate": 0.01, "slippage_pct": 0.02}

    result = evaluate_case(
        frame, signal, scenario, asset="SYN", strategy="long_test"
    )

    # Independently model next-open entry, next-open close, adverse fills,
    # equity-based allocation and one fee on each execution.
    entry_fill = 110.0 * (1 + scenario["slippage_pct"])
    exit_fill = 130.0 * (1 - scenario["slippage_pct"])
    entry_notional = 50.0 * 0.95
    quantity = entry_notional / entry_fill
    entry_fee = entry_notional * scenario["fee_rate"]
    exit_fee = exit_fill * quantity * scenario["fee_rate"]
    gross_pnl = (exit_fill - entry_fill) * quantity
    expected_equity = 50.0 - entry_fee + gross_pnl - exit_fee

    assert abs(result["final_equity"] - expected_equity) < 1e-10
    assert abs(result["final_realized_equity"] - expected_equity) < 1e-10
    assert abs(result["total_fees"] - entry_fee - exit_fee) < 1e-10
    assert result["trades"] == 1
    assert result["time_in_market_pct"] > 0


def test_double_cost_scenario_is_more_costly_than_base_on_synthetic_trade():
    timestamps = pd.date_range("2026-01-01", periods=4, freq="4h", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=4),
        "open": [100.0, 110.0, 120.0, 130.0],
        "high": [105.0, 115.0, 125.0, 135.0],
        "low": [95.0, 105.0, 115.0, 125.0],
        "close": [102.0, 112.0, 122.0, 132.0],
        "volume": [1000.0] * 4,
    })
    signal = pd.Series([1, 1, 0, 0])
    scenarios = cost_scenarios(0.001, 0.001)
    base = evaluate_case(frame, signal, scenarios[1], asset="SYN", strategy="long")
    double_both = evaluate_case(
        frame, signal, scenarios[4], asset="SYN", strategy="long"
    )
    assert double_both["total_fees"] > base["total_fees"]
    assert double_both["final_equity"] < base["final_equity"]


def main():
    tests = [
        test_cost_scenarios_change_only_fees_and_slippage,
        test_cost_case_matches_independent_long_fill_and_fee_calculation,
        test_double_cost_scenario_is_more_costly_than_base_on_synthetic_trade,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
