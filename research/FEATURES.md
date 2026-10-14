# Causal descriptive candle features

`features.py` contains reusable descriptive calculations only. It does not
produce entry/exit signals, select parameters, or connect to the backtester.
Every window is an explicit function argument; no feature window is selected
as a trading rule.

For each fully closed candle *t*, the output carries that candle's
`available_at`. All values below are available no earlier than that timestamp:

- `log_return`: `ln(close[t]) - ln(close[t-1])`.
- `momentum_return`: `close[t] / close[t-momentum_window] - 1`.
- `realized_volatility`: population standard deviation (`ddof=0`) of the most
  recent `volatility_window` one-candle log returns, including candle *t*.
- `atr`: simple mean of the most recent `atr_window` true ranges, including
  candle *t*. True range is the maximum of high-low, absolute high-previous
  close, and absolute low-previous close. The first candle uses high-low.
- `atr_pct`: `100 * atr / close[t]`.
- `relative_volume`: current candle volume divided by the mean volume of the
  preceding `volume_window` candles. A zero prior mean yields NaN, not infinity.
- Candle geometry: signed `candle_body_pct`, total `candle_range_pct`, and
  upper/lower wick percentages. Body is relative to open; range and wicks are
  relative to close.
- `prior_range_high` and `prior_range_low`: maximum high and minimum low over
  the preceding `structure_window` candles, excluding the current candle.
  `distance_to_prior_high_pct` and `distance_to_prior_low_pct` express the
  current close's distance from those levels. These are measurements, not
  breakout conditions.

Rolling warm-up values remain NaN. Input candles must have valid ordered,
unique availability timestamps and finite OHLCV values with valid OHLC
relationships. Every lookback is a required explicit argument. Synthetic
tests check independent arithmetic, exact availability, prefix invariance,
future perturbation resistance and invalid input handling. Passing these tests
establishes calculation behavior only; it does not establish predictive value
or approve any signal definition.

`structure_features.py` separately emits strict swing-high and swing-low
events. Each candidate must exceed/fall below every neighbor in its explicit
left/right windows; tied extrema do not qualify. An event is written only on
the confirmation candle after all right-side candles are closed. The output
keeps the pivot timestamp and the later confirmation `available_at` separate.
These events do not define how a level should be traded or retested.
