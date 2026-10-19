# Project 2 Roadmap Status

Status date: 2026-10-20

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
distinct from confirmation availability. `confirmed_market_structure` now
classifies each event against only the previous confirmed swing on that same
side, labeling initial, higher, lower and equal highs/lows on the confirmation
row. Synthetic tests cover all classifications, prefix and future-perturbation
invariance, and insufficient history. These primitives are not connected to a
strategy and have no tested predictive value.

`candlestick_patterns.py` provides four deterministic geometric events:
bullish/bearish real-body engulfing, hammer, and shooting star. It excludes
zero-range and doji-like candles (body/range at most 0.10); engulfing also
requires one valid opposing-color prior candle. Events carry the source candle
open timestamp and its close availability. Synthetic tests cover positive and
negative cases, ratio boundaries, invalid inputs, prefix invariance and future
perturbation. These labels have no trend context and no tested predictive
value.

`chart_patterns.py` adds double-top and double-bottom geometry events from
consecutive confirmed swing triples. The intervening confirmed trough/peak
must lie strictly beyond both extrema; endpoint similarity uses a caller
tolerance fraction of their mean price, and separation uses inclusive candle
index bounds. No neckline break is required, so `shape_confirmed` denotes
only geometric formation. Availability is the close of the candle that
confirms the second extremum. Overlapping qualifying triples are all emitted
with timestamp-derived deterministic IDs. Tests cover both shapes, threshold
boundaries, delayed swing confirmation, overlapping candidates and causal
prefix/future invariance. This is feature detection only.

`support_resistance.py` derives fixed-width support/resistance zones from
those confirmed swings without rerunning pivot detection. Its event ledger
records zone creation at confirmation availability, then wick-touch events or
terminal close-confirmed breaks on later candles. Zones remain distinct when
they overlap and retain their origin pivot and creation timestamps. Synthetic
tests cover both zone types, lifecycle precedence, repeated touches,
overlaps, deterministic output, insufficient history and prefix/future
perturbation invariance. These are feature semantics, not trading rules or
evidence of predictive value.

All four feature layers now require an explicit candle timeframe and validate
`available_at == timestamp + timeframe`; gaps in the data do not alter that
contract. A candle may qualify as both a high and low swing; both are retained
at the same pivot time, while chart sequencing keeps the stable high-then-low
order and never treats them as two temporally ordered pivots.

`feature_pipeline.py` assembles the standalone APIs into separate candle
features, a normalized provenance-preserving event ledger, and per-close
zone-state snapshots. Its same-close sort is deterministic but not an
intrabar ordering claim. Synthetic integration tests cover simultaneous
events, delayed availability, missing candles, as-of state stability,
invalid inputs, deterministic repeats, and insufficient swing history.

### Stages 5–8 — Reference validation and research readiness

TA-Lib and pandas-ta-classic are not installed in the project environment.
Source/documentation review and deterministic Project 2-only synthetic cases
show meaningful definition differences, so neither dependency was added.
TA-Lib uses adaptive candle settings for hammer/shooting-star and has a
previous-real-body gap condition for shooting star; pandas-ta-classic's native
patterns are TA-Lib-oriented, so they are not a fully independent reference.
Runtime library comparison remains unperformed.

The feature assembler passed synthetic end-to-end prefix extension and future
perturbation checks, including event availability, fixed zone boundaries,
as-of touch/break state, duplicate/unsorted/malformed input rejection,
explicit timeframe mismatch rejection, valid missing-candle gaps,
same-close deterministic ordering, and dual-pivot non-sequencing. It does not
validate predictive value. `VALIDATION_AND_READINESS_PLAN.md` now specifies
eight falsifiable descriptive feature families, separate support/resistance
contrasts, return/excursion outcomes, baseline context, overlap and
multiple-testing controls, holdout freeze/reproducibility steps, and decision
gates. Horizon, sample-size, effect-size, uncertainty and multiplicity
thresholds remain undecided and require approval before predictive evaluation.

### Phase 4 — Evidence-testing tools and data availability

`experiment_protocol.py` provides UTC chronological partitions, strict
canonical configuration fingerprints, no-clobber manifests, and append-only
research-log entries. Approval is now a structured local review record bound
to hypothesis ID/version, the full hypothesis and config snapshots, and
current hashes of input data plus core/caller-supplied implementation files.
Holdout freeze and holdout-inclusive metrics reject a status string alone and
revalidate approval invariants and source hashes at use time. Frozen partitions
bind the approval record, split boundaries, frame-content fingerprint, and
copied partition contents. Metrics require a ledger-content provenance record;
it detects later substitution but cannot prove the caller derived the ledgers
from the approved files. All preregistration decision fields must be resolved
before an approval record can be created; common unresolved placeholders are
recognized without treating placeholder-like words inside normal prose as
unresolved. Methodology choices remain explicit and are not given defaults.

Version 2 manifests separate intended specification, actual input/code and
runtime provenance, outputs, and validation/approval state. They record data
identities, hashes, timestamp ranges/timeframe, source hashes, Git revision
when available, feature version, execution/cost config, random seeds, and
artifact hashes on finalization. Stable path-safe IDs, unique run directories,
and no-clobber publication prevent accidental identity collision. These local
Python controls are not an authentication/security boundary. Finalization
separates completed computation (`evaluation_completed`) from scientific
status and requires an explicit state; independent manifest verification
checks contained artifact paths and recorded hashes. Synthetic tests cover
config/spec/input/source and partition mutation, unresolved decisions,
unauthorized holdout access/metrics, manifest validation states, artifact
integrity, and no-clobber publication. No predictive experiment or holdout
evaluation was run.

A CSV schema audit found five engineering-log rows with unquoted commas;
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

The support-touch feature hypothesis is now documented as a draft, but its
methodology has not been approved and no outcomes have been evaluated. The
next gate is user review of that methodology and any missing infrastructure
design choices before a real-data evaluation is authorized. No predictive
rule should be selected or tested before that approval. Paper-trading
readiness is not established.

### Milestone 3 — Feature-only event-study infrastructure

`event_study.py` provides a versioned feature-event-study specification,
local approval/staleness checks, causal support-touch cohorts, outcome
mechanics, partition assignment, descriptive summaries, and bundle
verification. `event_study_runner.py` verifies approvals and source/data
hashes before reading stage-bounded OHLCV prefixes, freezes stage events
before calculating outcomes, and publishes a no-clobber, verified output
bundle. Stage-bound loading validates the full timestamp ordering without
materializing post-boundary OHLCV, and the lower-level research outcome API
rejects frames containing candles at or beyond the authorized stage end.
Manifest creation and verification check exact artifact identities, schemas,
matching event/outcome IDs, stage-bounded timestamps, finite included outcomes,
completion-check keys, and row counts. Synthetic tests cover both horizon
conventions, gaps, partition crossings, unauthorized stages, future-candle
exclusion, symlink/path escapes, malformed and unexpected artifacts,
reproducibility, and failed publication cleanup.

The runner reports `computation_completed` and `scientific_status=not_assessed`;
it does not perform inferential analysis or assess the hypothesis. Local
approval and runner checks reduce accidental misuse but are not a security or
process-isolation boundary. No project OHLCV was passed to the event-study
runner or outcome calculator, and no real-data event study or predictive
evaluation was run.

The support-touch hypothesis and approval package remain **DRAFT — NOT
APPROVED FOR EVALUATION**. No real-hypothesis approval record, run directory,
or real-data manifest was created. Dependence-aware uncertainty estimation
remains unimplemented, and all scientific choices listed in the approval
package remain unresolved. Synthetic fixtures and computation completion are
engineering evidence only, not proof of predictive value or permission for a
real-data evaluation.

### Milestone 4A — SUPPORT_TOUCH_001 preregistration proposal

The hypothesis and companion methodology/approval documents now contain a
decision-ready draft recommendation: BTCUSD 4h as the sole primary family;
ETHUSD and SOLUSD 4h as separate exploratory replications; the unchanged
higher-low versus lower-low support-touch contrast; and a proposed exact
24-hour close-to-close outcome. UTC chronological partitions, gap and overlap
rules, dependence-aware uncertainty, minimum evidence, multiplicity, and
decision criteria are specified as candidates, not approved values.

`DECISION_REGISTER_SUPPORT_TOUCH_001.md` maps recommendations and existing
mechanical contracts to the implementing functions and identifies open
approval decisions and engineering blockers. The dependence-aware interval
and effective-sample adequacy check are not implemented. At the time of the
Milestone 4A proposal, embargo was not validated against horizon; Milestone
4C adds that mechanical check. The event-study runner remains descriptive
and stage-gated only. No outcome, approval record, frozen real-data holdout,
or experiment manifest was created. The hypothesis remains
**DRAFT — NOT APPROVED FOR EVALUATION**.

### Milestone 4C — statistical and protocol readiness (engineering only)

Created the versioned draft specification
`SUPPORT_TOUCH_001_PREREG_DRAFT_V1.json` and recorded its `EventStudySpec`
fingerprint. The primary BTCUSD 4h, event-weighted contrast, proposed exact
24-hour outcome, and gap exclusions remain unapproved recommendations; the
split, feature settings, uncertainty procedure, adequacy thresholds, and
scientific decision criteria remain unresolved.

The runner now enforces a nominal horizon-linked embargo and stage-endpoint
containment. A separate plan-lock then holdout-release API is required for
holdout, and the release hash is recorded in its output bundle; authorization time must follow lock time. Tests use
synthetic files only. These local API controls reduce accidental misuse but
do not isolate files or prevent a process owner from bypassing Python checks.

No bootstrap interval or precision gate was implemented. The previously
suggested crossed zone × calendar-week bootstrap is not sufficiently specified
or validated for the crossed and serial dependence structure; choosing an
estimator requires further methodological review and explicit approval. No
project OHLCV outcomes, labels, or hypothesis results were calculated, no real
approval/holdout/manifest was created, and the hypothesis remains
**DRAFT — NOT APPROVED FOR EVALUATION**.
