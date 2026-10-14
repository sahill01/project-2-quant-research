# Quant Research v1 — Foundation + Thin Backtester

Research loop:
Data -> Loader -> Strategy signal -> Event-driven backtester -> Metrics -> Research log

The old strategy/backtest files are intentionally left untouched.

Rules:
1. Signals are generated from the current closed candle.
2. Orders execute at the next candle open.
3. Fees and configurable slippage are charged.
4. One position at a time in v1.
5. No leverage/funding/liquidation/intrabar stop-target model yet.
6. `available_at` records when a closed candle becomes known.
7. Baselines are references, not optimization targets.
8. No parameter optimization in v1.

Baselines:
- Buy and Hold
- EMA crossover long/short
- Donchian breakout long/short

Run from the project root:
    python research/run_baselines.py

Default dataset:
    data/raw/BTCUSD_4h_730d.csv
