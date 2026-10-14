from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from .result_io import write_csv_batch_no_clobber
else:  # Support the legacy runner's top-level `import backtester` usage.
    from result_io import write_csv_batch_no_clobber


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float
    fee_rate: float
    slippage_pct: float
    allocation_fraction: float = 0.95


def apply_slippage(price: float, direction: int, slippage_pct: float) -> float:
    # +1 = buy, -1 = sell.
    if direction == 1:
        return price * (1.0 + slippage_pct)
    return price * (1.0 - slippage_pct)


def run_backtest(df, signal, config):
    # Signal on candle i is acted on at candle i+1 OPEN.
    # v1 supports one position: +1 long, -1 short, 0 flat.
    if len(df) != len(signal):
        raise ValueError("Data and signal lengths differ.")

    data = df.reset_index(drop=True).copy()
    raw_signal = signal.reset_index(drop=True)
    if raw_signal.map(lambda value: isinstance(value, (bool, np.bool_))).any():
        raise ValueError("Signals must contain only -1, 0, 1, or NaN.")
    desired = pd.to_numeric(
        raw_signal,
        errors="raise",
    ).fillna(0)
    if not desired.isin((-1, 0, 1)).all():
        raise ValueError("Signals must contain only -1, 0, 1, or NaN.")
    desired = desired.astype(int)

    equity = float(config.initial_capital)
    position = 0
    qty = 0.0
    entry_price = float("nan")
    entry_time = None
    entry_notional = 0.0
    entry_fee = 0.0

    trades = []
    equity_rows = []

    def mark_to_market(close_price):
        if position == 0:
            return equity
        if position == 1:
            return equity + (close_price - entry_price) * qty
        return equity + (entry_price - close_price) * qty

    def net_liquidation_value(close_price):
        if position == 0:
            return equity

        estimated_exit_price = apply_slippage(
            close_price,
            -position,
            config.slippage_pct,
        )
        if position == 1:
            pnl = (estimated_exit_price - entry_price) * qty
        else:
            pnl = (entry_price - estimated_exit_price) * qty

        estimated_exit_fee = (
            abs(estimated_exit_price * qty) * config.fee_rate
        )
        # Entry fee is already reflected in equity from position opening.
        return equity + pnl - estimated_exit_fee

    def close_position(exit_price, exit_time):
        nonlocal equity, position, qty, entry_price, entry_time
        nonlocal entry_notional, entry_fee

        if position == 1:
            pnl = (exit_price - entry_price) * qty
            side = "LONG"
        else:
            pnl = (entry_price - exit_price) * qty
            side = "SHORT"

        exit_notional = abs(exit_price * qty)
        exit_fee = exit_notional * config.fee_rate
        total_fees = entry_fee + exit_fee
        net_pnl = pnl - total_fees

        # Entry fee was already deducted when the position was opened.
        # Only apply P&L and exit fee here to avoid double-counting.
        equity += pnl - exit_fee

        trades.append({
            "entry_time": entry_time,
            "exit_time": exit_time,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "qty": qty,
            "entry_notional": entry_notional,
            "pnl_before_fees": pnl,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "total_fees": total_fees,
            "net_pnl": net_pnl,
            "return_on_entry_notional_pct": (
                net_pnl / entry_notional * 100
                if entry_notional else 0.0
            ),
        })

        position = 0
        qty = 0.0
        entry_price = float("nan")
        entry_time = None
        entry_notional = 0.0
        entry_fee = 0.0

    
    # Equity observations are recorded at candle close availability.
    # A signal from candle i executes at candle i+1 OPEN.
    for i in range(len(data)):
        row = data.iloc[i]

        # At this candle's open, act on the previous candle's signal.
        if i > 0:
            target = int(desired.iloc[i - 1])

            if target not in (-1, 0, 1):
                raise ValueError(
                    f"Invalid signal {target} at index {i - 1}"
                )

            if target != position:
                execution_open = float(row["open"])

                if position != 0:
                    exit_price = apply_slippage(
                        execution_open,
                        -position,
                        config.slippage_pct,
                    )
                    close_position(exit_price, row["timestamp"])

                if target != 0:
                    entry_price = apply_slippage(
                        execution_open,
                        target,
                        config.slippage_pct,
                    )

                    notional = max(
                        equity * config.allocation_fraction,
                        0.0,
                    )
                    qty = notional / entry_price
                    entry_fee = notional * config.fee_rate
                    equity -= entry_fee

                    position = target
                    entry_time = row["timestamp"]
                    entry_notional = notional

        # Final position is liquidated at the final candle close.
        # This includes exit slippage and the exit fee in final equity.
        if i == len(data) - 1 and position != 0:
            exit_price = apply_slippage(
                float(row["close"]),
                -position,
                config.slippage_pct,
            )
            close_position(exit_price, row["available_at"])

        equity_rows.append({
            "timestamp": row["available_at"],
            "available_at": row["available_at"],
            "realized_equity": equity,
            "mark_to_market_equity": (
                mark_to_market(float(row["close"]))
                if position != 0
                else equity
            ),
            "net_liquidation_equity": net_liquidation_value(
                float(row["close"])
            ),
            "position": position,
        })

    return pd.DataFrame(equity_rows), pd.DataFrame(trades)


def summarize(equity_df, trades_df, initial_capital):
    equity = equity_df["mark_to_market_equity"]

    final_equity = float(equity.iloc[-1])
    total_return = final_equity / initial_capital - 1.0

    running_max = equity.cummax().clip(lower=initial_capital)
    drawdown = equity / running_max - 1.0
    max_drawdown = float(drawdown.min())

    n_trades = len(trades_df)

    if n_trades:
        wins = trades_df.loc[trades_df["net_pnl"] > 0, "net_pnl"]
        losses = trades_df.loc[trades_df["net_pnl"] <= 0, "net_pnl"]

        win_rate = len(wins) / n_trades
        gross_profit = float(wins.sum())
        gross_loss = float(-losses.sum())
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0 else float("inf")
        )
        avg_trade = float(trades_df["net_pnl"].mean())
    else:
        win_rate = 0.0
        profit_factor = 0.0
        avg_trade = 0.0

    return {
        "initial_equity": initial_capital,
        "final_equity": final_equity,
        "total_return_pct": total_return * 100,
        "max_drawdown_pct": max_drawdown * 100,
        "trades": n_trades,
        "win_rate_pct": win_rate * 100,
        "profit_factor": profit_factor,
        "avg_trade_net_pnl": avg_trade,
    }


def save_results(equity_df, trades_df, results_dir, strategy_name):
    results_dir = Path(results_dir)
    write_csv_batch_no_clobber([
        (equity_df, results_dir / f"{strategy_name}_equity.csv"),
        (trades_df, results_dir / f"{strategy_name}_trades.csv"),
    ])
