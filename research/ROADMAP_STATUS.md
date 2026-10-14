# Project 2 Roadmap Status

Status date: 2026-10-15

This report records engineering and descriptive research work completed after
the BTCUSD/ETHUSD/SOLUSD 4h cross-asset baseline run. The historical results
are limited to the existing 730-day sample and are not evidence of future
profitability.

## Completed work

### Phase 1 — Infrastructure audit

- `load_ohlcv` now fails closed for empty files, duplicate timestamps,
  nonnumeric/non-finite OHLCV values and malformed prices/volume. Valid input
  rows are still sorted by timestamp and `available_at` remains candle open
  plus timeframe.
- Timeframe parsing now rejects zero, negative and malformed intervals;
  previously `0h` made candle data available at its open and `-1h` made it
  available before the open. Positive weekly intervals retain the documented
  source-anchor alignment exemption. `validate_data.py` now uses the same
  parser, so invalid timeframe input produces a validation error rather than
  crashing in its separate minutes conversion. Out-of-range positive values
  are also normalized to `ValueError` rather than leaking pandas overflow
  exceptions.
- The backtester validates discrete signals in `{-1, 0, 1}` before integer
  conversion and rejects booleans before Python can coerce them to 0/1.
  Missing signals retain the existing flat default.
- The downloader now rejects empty chunks instead of returning partial
  history, rejects malformed, duplicate, out-of-chunk and misaligned candles,
  and refuses to overwrite an existing dataset. Persistent CSV output paths
  now use exclusive creation with preflight checks, including the shared
  backtest saver and baseline/diagnostic writers. Mocked tests only; no
  network request or baseline/diagnostic writer run was made.
- The standalone `validate_data.py` validator now rejects infinite OHLCV
  values. A synthetic reproduction previously returned `STATUS: PASS` for
  infinite volume; regression tests cover infinity in each numeric column.
- The loader and validator reject off-boundary minute/hour/day timestamps.
  Weekly alignment is left unchecked and explicitly warned about until a week
  anchor is configured. Existing configured datasets pass the alignment test.
- `data_quality.py` provides a standalone, synthetic-tested freshness check
  that requires explicit `now` and `max_age` inputs, rejects naive/future/stale
  timestamps, and chooses no policy default. It also reports exact missing
  candle counts for interval-multiple gaps and flags irregular spacings
  separately, without accepting, rejecting, or filling them. It is not
  connected to the loader, downloader, or active backtester. A current audit
  found zero gap or irregular-step rows in all 12 local datasets; this does
  not establish a future gap policy.
- The causal as-of join rejects invalid timestamps, duplicate feature
  availability keys and invalid feature-column requests before selecting
  rows, preventing order-dependent selection among ambiguous feature values.
- Read-only cadence/alignment audit of the 12 local datasets found regular
  intervals, UTC timeframe-aligned timestamps, and matching timestamps across
  assets within each timeframe. The validator reported zero errors or gap
  warnings. This describes current files; future gap acceptance remains an
  explicit data policy.
- No strategy rules, active position sizing, fee/slippage settings, execution
  behavior, or equity-column semantics were changed.

### Phase 2 — Descriptive diagnostics

`run_cross_asset_diagnostics.py` analyzes the saved nine-combination
cross-asset ledgers without rerunning a backtest. Version 2 outputs are in
`research/results/cross_asset_diagnostics_v2/` and include trade-side gross
and net P&L, fees, holding duration, profit concentration, drawdown episodes,
quarterly account returns, exit-quarter trade P&L/fees, and valuation
discounts. Each diagnostic manifest includes hashes of its input files.

The quarterly account-return series are calculated independently for
mark-to-market and net-liquidation equity; closed-trade P&L and fees are
attributed to trade exit quarter and are kept separate. For all nine
asset-strategy combinations, quarterly closed-trade net P&L sums reconcile to
the trade ledger. Diagnostic version 1's quarterly NLE fields were found
incorrect due to shared return state; version 1 is retained, marked
superseded, and version 2 contains the correction. Version 1 trade and
drawdown-episode outputs were not implicated.

The separate `run_cross_asset_regime_diagnostics.py` output in
`research/results/cross_asset_regime_diagnostics_v1/` classifies intervals by
90-day trailing trend and 30-day realized volatility. Per-asset volatility
thresholds use only the first 365 days; the prior close's regime labels the
next close-to-close equity change. The output contains both equity series and
all nine asset-strategy combinations; regime contributions reconcile to each
series' first-to-final equity change. This is descriptive attribution, not
strategy evaluation. Some regime/asset cells have very few intervals, so
cell-level results are particularly unstable.

The fixed cost-sensitivity run in
`research/results/cross_asset_cost_sensitivity_v1/` evaluates zero cost,
configured cost, double fee only, double slippage only, and double both.
Configured-cost metrics reconciled to the saved nine-row cross-asset summary
before output was written. At double both costs, final equity was lower than
configured in all nine combinations; the largest absolute decrease was
$14.40 for ETH Donchian 20, whose trade count remained 281. This measures the
existing rules under cost perturbations and does not select or tune a strategy.
The fee-only and slippage-only cases keep the other cost at its configured
value; the two sensitivities should not be assumed additive because position
quantity depends on the evolving account equity in the existing engine.

Descriptively, EMA 20/50 returned +50.52% on BTCUSD, -31.62% on ETHUSD and
+85.16% on SOLUSD over this sample. Its side-level result varied by asset:
ETH's net losses were concentrated on shorts, while SOL's long and short
contributions were both positive. These are historical descriptions, not a
validated edge or a basis for selecting a preferred strategy. Some observed
drawdowns remained unrecovered at the sample end.

### Phase 3 — Hypothesis specification

`hypothesis_spec.py` and `HYPOTHESIS_TEMPLATE.md` provide a validated
documentation schema for rationale, exact feature/signal definitions,
availability timing, entry/exit assumptions, expected effects, failure
conditions, baselines, validation/sample-size plans, confounders and costs.
`features.py` now provides causal, signal-neutral log return, realized
volatility, ATR, ATR percentage, relative volume, multi-period momentum,
candle geometry, and distances to prior-window highs/lows with explicit window
arguments and `available_at` metadata. Independent synthetic tests verify
formulas, warm-up behavior, timestamp availability and prefix/future
perturbation invariance, including as-of-join behavior immediately before and
at a feature availability boundary. `structure_features.py` emits strict
swing-point events only on the later confirmation candle and keeps pivot time
distinct from confirmation availability. These primitives are not connected
to a strategy and have no tested predictive value.

### Phase 4 — Evidence-testing tools and data availability

`experiment_protocol.py` provides UTC chronological partitions based on
`available_at`, config fingerprints, an explicit config-freeze check before
holdout access, no-clobber run manifests with data/source hashes, and
append-only research-log entries with rejection reasons. Holdout freeze now
requires the versioned config to declare its hypothesis `APPROVED`; this is a
caller attestation, not independent proof of approval. The freeze/open API
fingerprints the current config object each time, so changing nested
parameters or approval status after freezing prevents holdout access.
Manifests also require experiment-specific source files from the caller and
hash them with the core engine files, so the runner/feature implementation
can be recorded. The manifest writer rejects an empty input-data file list;
otherwise it could create a nominally reproducible run with no input hashes.
Config fingerprints also reject NaN and infinite values so their canonical
payload remains valid JSON. A CSV schema audit found five engineering-log rows with unquoted commas;
their quoting was repaired without changing their text or order. The log now
parses as 42 unique-ID data rows with the declared 12 columns.
Availability partitioning now also rejects an empty source frame; otherwise
empty train, validation and holdout partitions passed the assignment check
vacuously. A synthetic regression covers this failure case.

The causal as-of join restores the caller's decision-row order after its
time-sorted merge. An unsorted synthetic decision frame previously returned
sorted rows, risking misalignment with labels or metadata held separately;
the regression checks original order and the independently expected match for
each row.

`result_io.py` stages every CSV in a no-clobber batch before publishing any
destination. A serialization or commit failure rolls back destinations
created by that call and removes temporary files; rollback checks file identity
so it does not remove a concurrent replacement. Synthetic tests cover a
failure on the second serialization and a destination appearing during commit;
they verify no partial batch remains and the concurrent file is preserved.

`experiment_metrics.py` reports continuous-account returns, seeded drawdowns,
exposure, and trade statistics for UTC train/validation/holdout windows.
Closed-trade P&L is assigned by exit time; entry and exit fee events are
reported at their respective event times to avoid conflating period cash
costs with whole-trade attribution. It does not access holdout partitions;
callers must use the freeze gate before producing or supplying holdout ledgers.

The local inventory contains 12 datasets: BTCUSD, ETHUSD and SOLUSD at 15m,
1h, 4h and 1d, each with 730 days of regular candles. No additional local
history was found. `fetch_data.py` is configured to request 730 days; its
chunking implementation could request other spans if explicitly configured,
but no longer retention or additional history was established. The public
Delta candle documentation describes a 2,000-candle maximum per request; it
does not establish historical retention depth. No external or exchange
request was made. `DATA_HISTORY_OPTIONS.md` records Delta, alternate-venue
archive and licensed-vendor paths, their limitations, and validation gates.
Longer history therefore remains a data prerequisite, not an assumed
capability.

### Phase 5 — Separate risk-engine design

`risk_engine.py` contains synthetic-testable, explicit-input calculations
for adverse entry/stop fills, round-trip fees, sizing under a supplied risk
budget, notional/lot caps, remaining portfolio risk budget and a drawdown
threshold check. `RISK_ENGINE_ASSUMPTIONS.md` records its assumptions. This
module is not connected to the active backtester and chooses no policy
defaults; configured risk settings are not represented as enforced controls.
Sizing now also rejects non-finite risk-per-unit values and invalid entry
fills supplied through a manually constructed `PlannedTradeRisk`, which
otherwise could yield a non-finite quantity or bypass the notional cap.
The standalone planner also requires an integer `+1` or `-1` side and rejects
booleans and floating-point lookalikes.

### Phase 6 — Robustness and independent-validation design

Temporal split, holdout-freeze and no-clobber primitives are in place, but no
holdout evaluation or independent-framework/market-data comparison was run.
The current 730-day data remains suitable for engineering and descriptive
pipeline checks only. A predictive experiment needs a predeclared hypothesis, a
separate untouched holdout, adequate history across distinct regimes, cost
and execution sensitivity, and a prespecified evaluation/reporting plan.
`VALIDATION_AND_READINESS_PLAN.md` now specifies an event-level independent
engine check using synthetic execution/accounting cases, independent formula
oracles, exact discrete-state comparisons and a declared numeric tolerance.
`test_independent_accounting_reference.py` implements a test-only scalar
reference and compares complete synthetic trade/equity ledgers, including
reversals, costs, open-position valuations and terminal close. The test passes;
it does not constitute a second-framework or market-data comparison, and no
project holdout was accessed.

## Tests

All 23 research test modules passed with `.venv/bin/python` on 2026-10-15:

- Existing: accounting integrity, general integrity, prefix invariance,
  execution integrity, repeated-trade accounting, Phase 1 regressions and
  net-liquidation equity.
- Added: data-loader integrity, signal-input validation, downloader safety,
  cross-asset diagnostics, experiment protocol, hypothesis specification
  risk-engine calculations, causal regime attribution, cost sensitivity and
  temporal experiment metrics, standalone data validator, explicit-policy
  data-freshness checks, no-clobber result I/O, causal descriptive features,
  confirmed swing-point structure features, and independent synthetic
  accounting reference comparison.

The experiment-protocol test also covers a reproduced post-freeze config
mutation defect and a failed manifest publish that previously left an empty
run directory; manifests are now staged before no-clobber publication and
failed publication cleans up the run directory. The API and regressions were
updated and the full suite rerun.

The system Python environment does not have pandas installed; the project's
`.venv` contains the required existing dependencies. No dependencies were
added.

## Output preservation

No baseline or existing diagnostic writer was run. The 48 pre-existing
result CSVs captured before this work were rehashed afterward and all 48
matched. New diagnostic outputs were written only to the new versioned
`cross_asset_diagnostics_v1/` and `cross_asset_diagnostics_v2/` directories;
v1 is explicitly superseded due to the quarterly state bug described above.

## Remaining issues and approval gate

- Data loader tests establish rejection of empty, duplicate and malformed
  values, but do not impose a universal missing-candle policy. Existing local
  datasets had regular cadence; a future experiment should declare whether
  gaps invalidate a dataset or are permitted.
- Downloader safety tests use mocked responses. No live endpoint behavior or
  historical retention was verified.
- `available_at` is used in the partition tool and existing causality tests
  pass, but no predictive feature hypothesis has been specified or tested.
- Holdout protection is an accidental-use safeguard within this Python API,
  not a security boundary: callers can still directly access the private
  `_holdout` attribute or copy the data before freezing. The default
  partition representation now omits holdout rows to prevent accidental
  disclosure through routine logging.
- The standalone risk calculations have synthetic tests only and are not
  active controls.
- The paper-trading readiness review finds its operational and validation
  gates unmet; see `PAPER_TRADING_READINESS_REVIEW.md`.

The next work would define one specific, pre-registered market hypothesis
and its untouched validation plan before implementing research features or
signals. That is the first approval gate: no strategy/predictive rule should
be selected or tested until the user approves the exact hypothesis and
validation design. Paper-trading readiness is not established.
