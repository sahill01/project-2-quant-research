"""Standalone risk calculations; deliberately not connected to backtesting.

All policy values are explicit caller inputs. This module does not choose a
risk fraction, stop policy, leverage, or exchange contract convention.
"""

from dataclasses import dataclass
import math
from numbers import Integral


@dataclass(frozen=True)
class PlannedTradeRisk:
    side: int
    entry_reference: float
    stop_reference: float
    entry_fill: float
    stop_fill: float
    fee_rate: float
    risk_per_unit: float


def _validate_rate(name: str, value: float, *, upper_exclusive: float | None = None):
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    if upper_exclusive is not None and value >= upper_exclusive:
        raise ValueError(f"{name} must be below {upper_exclusive}")


def plan_trade_risk(
    side: int,
    entry_reference: float,
    stop_reference: float,
    fee_rate: float,
    slippage_pct: float,
) -> PlannedTradeRisk:
    """Return adverse fills and round-trip fee-inclusive risk per unit."""
    if isinstance(side, bool) or not isinstance(side, Integral) or side not in (-1, 1):
        raise ValueError("side must be +1 (long) or -1 (short)")
    if not all(math.isfinite(p) and p > 0 for p in (entry_reference, stop_reference)):
        raise ValueError("Entry and stop reference prices must be finite and positive")
    _validate_rate("fee_rate", fee_rate)
    _validate_rate("slippage_pct", slippage_pct, upper_exclusive=1.0)

    if side == 1:
        entry_fill = entry_reference * (1 + slippage_pct)
        stop_fill = stop_reference * (1 - slippage_pct)
        gross_risk = entry_fill - stop_fill
    else:
        entry_fill = entry_reference * (1 - slippage_pct)
        stop_fill = stop_reference * (1 + slippage_pct)
        gross_risk = stop_fill - entry_fill

    if gross_risk <= 0:
        raise ValueError("Stop must represent a loss relative to the adverse entry fill")
    round_trip_fees_per_unit = (entry_fill + stop_fill) * fee_rate
    return PlannedTradeRisk(
        side=side,
        entry_reference=entry_reference,
        stop_reference=stop_reference,
        entry_fill=entry_fill,
        stop_fill=stop_fill,
        fee_rate=fee_rate,
        risk_per_unit=gross_risk + round_trip_fees_per_unit,
    )


def remaining_portfolio_risk_budget(
    account_equity: float,
    risk_per_trade_fraction: float,
    current_open_risk: float,
    max_portfolio_risk_fraction: float,
) -> float:
    """Cap one trade's budget by the remaining planned portfolio risk."""
    if not math.isfinite(account_equity) or account_equity < 0:
        raise ValueError("account_equity must be finite and non-negative")
    for name, value in (
        ("risk_per_trade_fraction", risk_per_trade_fraction),
        ("max_portfolio_risk_fraction", max_portfolio_risk_fraction),
    ):
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if not math.isfinite(current_open_risk) or current_open_risk < 0:
        raise ValueError("current_open_risk must be finite and non-negative")
    per_trade_budget = account_equity * risk_per_trade_fraction
    remaining_portfolio_budget = max(
        account_equity * max_portfolio_risk_fraction - current_open_risk,
        0.0,
    )
    return min(per_trade_budget, remaining_portfolio_budget)


def size_for_stop_risk(
    account_equity: float,
    risk_budget: float,
    planned_risk: PlannedTradeRisk,
    *,
    max_notional: float | None = None,
    quantity_step: float | None = None,
    minimum_quantity: float = 0.0,
) -> float:
    """Size quantity under a fee/slippage-aware stop-risk budget.

    Quantity is rounded down when a quantity step is supplied. A caller may
    provide max_notional or lot constraints from a future venue adapter.
    """
    if not math.isfinite(account_equity) or account_equity < 0:
        raise ValueError("account_equity must be finite and non-negative")
    if not math.isfinite(risk_budget) or risk_budget < 0:
        raise ValueError("risk_budget must be finite and non-negative")
    if not math.isfinite(planned_risk.risk_per_unit) or planned_risk.risk_per_unit <= 0:
        raise ValueError("planned risk per unit must be finite and positive")
    if not math.isfinite(planned_risk.entry_fill) or planned_risk.entry_fill <= 0:
        raise ValueError("planned entry fill must be finite and positive")
    if not math.isfinite(minimum_quantity) or minimum_quantity < 0:
        raise ValueError("minimum_quantity must be finite and non-negative")

    quantity = risk_budget / planned_risk.risk_per_unit
    if max_notional is not None:
        if not math.isfinite(max_notional) or max_notional < 0:
            raise ValueError("max_notional must be finite and non-negative")
        quantity = min(quantity, max_notional / planned_risk.entry_fill)
    if quantity_step is not None:
        if not math.isfinite(quantity_step) or quantity_step <= 0:
            raise ValueError("quantity_step must be finite and positive")
        quantity = math.floor(quantity / quantity_step) * quantity_step
    if quantity < minimum_quantity:
        return 0.0
    return quantity


def drawdown_limit_reached(
    current_equity: float,
    running_peak: float,
    max_drawdown_fraction: float,
) -> bool:
    """Evaluate a caller-supplied drawdown stop; does not liquidate positions."""
    if not math.isfinite(current_equity) or current_equity < 0:
        raise ValueError("current_equity must be finite and non-negative")
    if not math.isfinite(running_peak) or running_peak <= 0:
        raise ValueError("running_peak must be finite and positive")
    if not math.isfinite(max_drawdown_fraction) or not 0 <= max_drawdown_fraction <= 1:
        raise ValueError("max_drawdown_fraction must be between 0 and 1")
    drawdown_fraction = max(1.0 - current_equity / running_peak, 0.0)
    return drawdown_fraction + 1e-12 >= max_drawdown_fraction
