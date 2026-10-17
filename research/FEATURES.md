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
Swing, structure, zone, chart-pattern, and candlestick APIs require an explicit
`timeframe`. They validate that each `available_at` exactly equals the candle
open `timestamp` plus that interval. Timestamp gaps are allowed and do not
change the declared candle duration; premature or otherwise mismatched
availability fails with `ValueError` rather than being repaired.
`confirmed_market_structure` adds a separate causal classification over
those events: each confirmed high is compared with the previous confirmed
high, and each confirmed low with the previous confirmed low. The first event
of either side is labelled `initial_high` or `initial_low`; subsequent events
are labelled `higher_high`, `lower_high`, or `equal_high`, and
`higher_low`, `lower_low`, or `equal_low`. A consecutive same-side swing
replaces the prior comparison reference only after its own confirmation.
Classification appears on the confirmation row and uses that row's
`available_at`; it does not backdate knowledge to the pivot candle. Tied
neighbor extrema remain excluded from swing detection. These events do not
define how a level should be traded or retested, and they do not produce
signals.

`candlestick_patterns.py` exposes `detect_candlestick_patterns` as an event
ledger with `pattern_id`, `candle_time`, and `available_at`. An event is
available at the source candle's close; engulfing patterns inspect exactly
one preceding candle, while hammer and shooting-star patterns use only the
current candle. Body is `abs(close - open)`, range is `high - low`, upper wick
is `high - max(open, close)`, and lower wick is `min(open, close) - low`.
Candles with zero range or body/range at most 0.10 are excluded. Engulfing
requires opposite candle colors and the current real body to contain the
previous real body, including equal boundaries; it has no trend or gap rule.
A hammer requires lower wick at least twice the body and upper wick at most
the body. A shooting star requires the inverse. Wick thresholds are inclusive.
These geometry labels are not contextualized by trend and are not predictive
claims or trading signals.

`support_resistance.py` derives one fixed range zone from each confirmed
swing high or low. `confirmed_swing_zones` requires explicit swing windows
and `zone_width_fraction` (`0 < fraction < 2`); the full zone width is that
fraction of the pivot price and is centered on the pivot. Highs create
resistance zones and lows create support zones. Zones are not merged, so
overlapping candidates retain separate deterministic IDs and origin times.

The returned event ledger has `zone_id`, `zone_type`, `lower_bound`,
`upper_bound`, `pivot_time`, `created_at`, `event_time`, `event`, `state`,
and `touch_count`. A `created` event is emitted at the originating swing's
confirmation-row `available_at`. Lifecycle checks begin on the next candle.
On each later candle, a close above a resistance upper bound or below a
support lower bound emits a terminal `broken` event; this takes precedence
over touch counting. Otherwise, inclusive wick-range intersection emits one
`touched` event for that zone and candle. Consecutive intersecting candles
count separately. Untouched active zones have no per-candle ledger row.
This bar-level convention cannot determine intrabar ordering; the close-break
precedence rule makes ambiguous cases deterministic. Zone boundaries never
change after creation. The engine emits descriptive events only and is not
connected to strategies or execution.

`chart_patterns.py` exposes `detect_double_top_bottom`, which reuses
`confirmed_swing_points` and inspects consecutive confirmed swing triples.
A double top is high-low-high with the middle low strictly below both highs;
a double bottom is low-high-low with the middle high strictly above both
lows. The first and second extrema must differ by no more than
`price_tolerance_fraction`, calculated as absolute difference divided by
their arithmetic mean. Their pivot candle-index separation must fall within
the inclusive `min_separation_bars` and `max_separation_bars` bounds. These
are caller-specified geometry rules, not tuned values.

The event ledger includes a deterministic `pattern_id`, pattern type, all
three pivot timestamps and prices, `formation_time` (the second extremum's
pivot time), `available_at`, and `confirmation_status`. No neckline break is
required: `shape_confirmed` means only that the three confirmed swings meet
the geometric definition. Availability is the confirmation-close time of the
second extremum, never its earlier pivot time. Every qualifying adjacent
triple is emitted, including overlapping candidates; identity is based on
the pattern type and the three pivot timestamps. No subsequent candle
retrospectively changes a reported pattern. This is descriptive structure, not
a trade signal.

If one candle qualifies as both a strict swing high and swing low, the swing
output records both events on that candle's confirmation row with the same
pivot timestamp. The chart-pattern scanner's deterministic within-row order
is high then low. It requires strictly increasing pivot indices for a pattern
triple, so both events from one candle are never treated as two sequential
swings; their presence can interrupt an otherwise adjacent three-event
sequence. This is a deterministic representation rule, not a market-direction
interpretation.

`feature_pipeline.py` provides `assemble_feature_dataset` without replacing
the layer APIs. It returns three tables: `candle_features` has one row per
input candle and the confirmed structure columns; `events` is a long-form
ledger with stable `event_id`, layer/type, and explicit normalized times:
`event_time` is the open timestamp of the candle anchoring the event;
`available_at` is when all required information is known; `pivot_time` is the
original swing candle where applicable; and `formation_time` identifies
candlestick/chart geometry only (null for structure and zone lifecycle
events). For zone creation, touch and break, `event_time` is the lifecycle
candle, `available_at` is that candle's close, and `pivot_time` remains the
originating swing candle. The source zone row, whose `event_time` is its
availability/close timestamp, is retained unchanged in `payload`. OHLC does
not reveal an intrabar touch or break time, so none is inferred. For chart
patterns, `event_time`/`formation_time` identify the second pivot candle while
`available_at` is the later confirmation close. Structure events use the
confirmation candle as `event_time` and preserve the earlier pivot in
`pivot_time`. Events with the same `available_at` are sorted by normalized
layer in this exact order:

1. Structure
2. Candlestick
3. Chart pattern
4. Zone

Within a layer, `event_id` is the deterministic tie-breaker. This is a
bookkeeping convention only; it does not imply intrabar chronology.

`zone_states` has an as-of row per observed candle close and each zone already
created by that close. Formation and pivot timestamps may precede
`available_at`, but an event is included only at its availability time.
Missing candles remain absent
and every provided row is validated against the caller's explicit timeframe.
Zone snapshots carry state forward only from events available at or before the
snapshot close, so future touches/breaks do not rewrite earlier snapshots.
Broken zones remain in every later snapshot. With C observed candles and Z
accumulated zones, the snapshot table has O(C*Z) rows; at most two zones are
created per candle, making O(C^2) the worst-case row growth. This descriptive
assembly does not create trading decisions.
