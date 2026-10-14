from config_research import (
    BASELINE_ALLOCATION,
    DAYS_BACK,
    DATA_DIR,
    DONCHIAN_PERIOD,
    EFFECTIVE_TAKER_FEE,
    EMA_FAST,
    EMA_SLOW,
    INITIAL_CAPITAL,
    RESULTS_DIR,
    SLIPPAGE_PCT,
    SYMBOL,
    TIMEFRAME,
)
from data_loader import default_dataset_path, load_ohlcv
from backtester import BacktestConfig, run_backtest, save_results, summarize
from strategies import (
    buy_and_hold_signal,
    donchian_breakout_signal,
    ema_crossover_signal,
)
from result_io import assert_paths_available


def run_one(name, df, signal, config):
    equity, trades = run_backtest(df, signal, config)
    summary = summarize(equity, trades, config.initial_capital)
    save_results(equity, trades, RESULTS_DIR, name)

    print(f"\n=== {name} ===")
    for key, value in summary.items():
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")
        else:
            print(f"{key}: {value}")

    return summary


def main():
    strategy_names = ("buy_hold", "ema_crossover", "donchian_breakout")
    assert_paths_available([
        RESULTS_DIR / f"{name}_{kind}.csv"
        for name in strategy_names
        for kind in ("equity", "trades")
    ])
    path = default_dataset_path(
        DATA_DIR, SYMBOL, TIMEFRAME, DAYS_BACK
    )

    print(f"Loading: {path}")

    df = load_ohlcv(path, TIMEFRAME)

    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        fee_rate=EFFECTIVE_TAKER_FEE,
        slippage_pct=SLIPPAGE_PCT,
        allocation_fraction=BASELINE_ALLOCATION,
    )

    print(
        f"Dataset: {SYMBOL} {TIMEFRAME} | "
        f"{df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}"
    )
    print(f"Candles: {len(df):,}")
    print(f"Fee: {EFFECTIVE_TAKER_FEE:.6%}")
    print(f"Slippage: {SLIPPAGE_PCT:.6%}")

    run_one(
        "buy_hold",
        df,
        buy_and_hold_signal(df),
        config,
    )

    run_one(
        "ema_crossover",
        df,
        ema_crossover_signal(df, EMA_FAST, EMA_SLOW),
        config,
    )

    run_one(
        "donchian_breakout",
        df,
        donchian_breakout_signal(df, DONCHIAN_PERIOD),
        config,
    )

    print(f"\nResults saved to: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
