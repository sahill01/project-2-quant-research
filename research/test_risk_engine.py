"""Synthetic arithmetic tests for the unconnected risk engine."""

import numpy as np

from research.risk_engine import (
    PlannedTradeRisk,
    drawdown_limit_reached,
    plan_trade_risk,
    remaining_portfolio_risk_budget,
    size_for_stop_risk,
)


def test_long_fee_and_slippage_aware_position_size():
    plan = plan_trade_risk(1, 100.0, 90.0, 0.01, 0.02)
    expected_entry = 102.0
    expected_stop = 88.2
    expected_risk_per_unit = (expected_entry - expected_stop) + (
        expected_entry + expected_stop
    ) * 0.01
    assert plan.entry_fill == expected_entry
    assert plan.stop_fill == expected_stop
    assert abs(plan.risk_per_unit - expected_risk_per_unit) < 1e-12
    assert abs(size_for_stop_risk(1000.0, 10.0, plan) - 10.0 / expected_risk_per_unit) < 1e-12


def test_short_adverse_fills_and_caps_round_down_quantity():
    plan = plan_trade_risk(-1, 100.0, 110.0, 0.01, 0.02)
    expected_entry = 98.0
    expected_stop = 112.2
    expected_risk_per_unit = (expected_stop - expected_entry) + (
        expected_entry + expected_stop
    ) * 0.01
    assert plan.entry_fill == expected_entry
    assert plan.stop_fill == expected_stop
    assert abs(plan.risk_per_unit - expected_risk_per_unit) < 1e-12
    quantity = size_for_stop_risk(
        1000.0, 10.0, plan, max_notional=500.0,
        quantity_step=0.1, minimum_quantity=0.1,
    )
    assert quantity <= 500.0 / expected_entry
    assert abs(quantity / 0.1 - round(quantity / 0.1)) < 1e-12


def test_portfolio_budget_and_drawdown_guard_use_explicit_limits():
    assert remaining_portfolio_risk_budget(1000, 0.01, 5, 0.02) == 10
    assert remaining_portfolio_risk_budget(1000, 0.01, 15, 0.02) == 5
    assert remaining_portfolio_risk_budget(1000, 0.01, 25, 0.02) == 0
    assert drawdown_limit_reached(900, 1000, 0.1)
    assert not drawdown_limit_reached(901, 1000, 0.1)


def test_invalid_stops_and_risk_values_are_rejected():
    for args in ((1, 100.0, 105.0, 0.01, 0.0), (-1, 100.0, 95.0, 0.01, 0.0)):
        try:
            plan_trade_risk(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("Stop on a profit side was accepted as risk")


def test_boolean_and_noninteger_sides_are_rejected():
    for side in (True, False, 1.0, -1.0):
        try:
            plan_trade_risk(side, 100.0, 90.0, 0.001, 0.001)
        except ValueError as error:
            assert "side must be" in str(error)
        else:
            raise AssertionError(f"Invalid side {side!r} was accepted")


def test_numpy_integer_sides_remain_supported():
    for side in (np.int64(1), np.int32(-1)):
        stop = 90.0 if side == 1 else 110.0
        plan = plan_trade_risk(side, 100.0, stop, 0.001, 0.001)
        assert plan.side == side


def test_manually_constructed_nonfinite_trade_risk_is_rejected():
    for risk_per_unit, entry_fill in ((float("nan"), 100.0), (float("inf"), 100.0), (1.0, float("nan")), (1.0, 0.0)):
        malformed_plan = PlannedTradeRisk(
            side=1,
            entry_reference=100.0,
            stop_reference=90.0,
            entry_fill=entry_fill,
            stop_fill=90.0,
            fee_rate=0.0,
            risk_per_unit=risk_per_unit,
        )
        try:
            size_for_stop_risk(1000.0, 10.0, malformed_plan, max_notional=500.0)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed planned risk produced a quantity")


def main():
    tests = [
        test_long_fee_and_slippage_aware_position_size,
        test_short_adverse_fills_and_caps_round_down_quantity,
        test_portfolio_budget_and_drawdown_guard_use_explicit_limits,
        test_invalid_stops_and_risk_values_are_rejected,
        test_boolean_and_noninteger_sides_are_rejected,
        test_numpy_integer_sides_remain_supported,
        test_manually_constructed_nonfinite_trade_risk_is_rejected,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
