"""
Project 2 — First Baseline Experiments.

BTCUSD / 4H / 730 days.

Strategies:
1. Execution-aware buy & hold
2. EMA 20/50
3. Donchian 20

No parameter optimization.
All strategies use the same capital, fees, slippage, and execution convention.

Run from the project root:
    python -m research.run_baselines_v1
"""

from pathlib import Path

import pandas as pd

from config import (
    DAYS_BACK,
    EFFECTIVE_TAKER_FEE,
    INITIAL_CAPITAL,
    SLIPPAGE_PCT,
)
from research.backtester import (
    BacktestConfig,
    run_backtest,
    save_results,
    summarize,
)
from research.data_loader import default_dataset_path, load_ohlcv
from research.strategies import (
    buy_and_hold_signal,
    donchian_breakout_signal,
    ema_crossover_signal,
)
from research.result_io import assert_paths_available, write_csv_batch_no_clobber


SYMBOL = "BTCUSD"
TIMEFRAME = "4h"
RESULTS_DIR = Path("research/results/baselines")


def run_one(name, df, signal, config):
    equity_df, trades_df = run_backtest(df, signal, config)

    metrics = summarize(
        equity_df,
        trades_df,
        config.initial_capital,
    )

    metrics["strategy"] = name
    metrics["symbol"] = SYMBOL
    metrics["timeframe"] = TIMEFRAME
    metrics["days_back"] = DAYS_BACK
    metrics["fee_rate"] = config.fee_rate
    metrics["slippage_pct"] = config.slippage_pct
    metrics["allocation_fraction"] = config.allocation_fraction
    metrics["total_fees"] = (
        float(trades_df["total_fees"].sum())
        if not trades_df.empty
        else 0.0
    )

    # Fraction of recorded bars spent in a position.
    metrics["time_in_market_pct"] = (
        float((equity_df["position"] != 0).mean() * 100)
        if not equity_df.empty
        else 0.0
    )

    save_results(
        equity_df,
        trades_df,
        RESULTS_DIR,
        name,
    )

    return metrics


def main():
    strategy_names = ("buy_hold", "ema_20_50", "donchian_20")
    assert_paths_available([
        *(
            RESULTS_DIR / f"{name}_{kind}.csv"
            for name in strategy_names
            for kind in ("equity", "trades")
        ),
        RESULTS_DIR / "baseline_summary.csv",
    ])
    print("=" * 72)
    print("PROJECT 2 — FIRST BASELINE EXPERIMENT")
    print("=" * 72)
    print(f"Market:       {SYMBOL}")
    print(f"Timeframe:    {TIMEFRAME}")
    print(f"History:      {DAYS_BACK} days")
    print(f"Capital:      ${INITIAL_CAPITAL:.2f}")
    print(f"Fee rate:     {EFFECTIVE_TAKER_FEE:.6f}")
    print(f"Slippage:     {SLIPPAGE_PCT:.6f}")
    print("Allocation:   95%")
    print("Execution:    signal -> next candle OPEN")
    print("=" * 72)

    path = default_dataset_path(
        "data/raw",
        SYMBOL,
        TIMEFRAME,
        DAYS_BACK,
    )

    df = load_ohlcv(path, TIMEFRAME)

    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        fee_rate=EFFECTIVE_TAKER_FEE,
        slippage_pct=SLIPPAGE_PCT,
        allocation_fraction=0.95,
    )

    experiments = {
        "buy_hold": buy_and_hold_signal(df),
        "ema_20_50": ema_crossover_signal(
            df,
            fast=20,
            slow=50,
        ),
        "donchian_20": donchian_breakout_signal(
            df,
            period=20,
        ),
    }

    results = []

    for name, signal in experiments.items():
        print(f"\nRunning: {name}")
        results.append(
            run_one(
                name,
                df,
                signal,
                config,
            )
        )

    results_df = pd.DataFrame(results)

    write_csv_batch_no_clobber([
        (results_df, RESULTS_DIR / "baseline_summary.csv"),
    ])

    display_columns = [
        "strategy",
        "final_equity",
        "total_return_pct",
        "max_drawdown_pct",
        "trades",
        "win_rate_pct",
        "profit_factor",
        "avg_trade_net_pnl",
        "total_fees",
        "time_in_market_pct",
    ]

    print("\n" + "=" * 72)
    print("BASELINE SUMMARY")
    print("=" * 72)
    print(
        results_df[display_columns].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nSaved baseline outputs to:")
    print(RESULTS_DIR)


if __name__ == "__main__":
    main()
