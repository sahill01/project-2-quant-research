# Validation and Paper-Trading Readiness Plan

## Current data constraint

Local data covers 730 days for BTCUSD, ETHUSD and SOLUSD at 15m, 1h, 4h and
1d. Existing files have regular cadence and aligned timestamps. The loader
checks UTC interval boundaries for minute/hour/day candles; weekly boundaries
remain unchecked until a source-specific week anchor is defined. It is
adequate for validating the data, feature and backtest pipelines,
but is too limited to support a broad predictive claim or representative
coverage of market regimes. There is no verified local history beyond that
span. Delta's public historical-candles API documentation specifies a
2,000-candle response limit, but does not establish retention depth. No
exchange request was made.

## Required predictive experiment design

Before feature/signal implementation, record and approve one hypothesis with:

1. A market rationale and a falsifiable expected effect.
2. Exact feature and signal formulas and their `available_at` timing.
3. Fixed entry, exit, fee, slippage and sizing assumptions matching the
   approved baseline unless an explicit change is approved.
4. A baseline comparison and failure/rejection conditions.
5. Time-ordered training and validation windows plus a later untouched
   holdout. Freeze the full configuration before the holdout is opened.
6. Multiple assets, time periods and regimes, plus cost and execution
   uncertainty sensitivity.
7. Predeclared sample-size rationale and reporting metrics. Avoid selecting
   a winner using holdout outcomes.
8. A reproducible manifest with code/data hashes, configuration, timestamps,
   test results and rejection decisions.

## Proposed descriptive tests for market-structure features

These are hypotheses to preregister, not approved signals. No test below
changes feature definitions or implies that an event should be traded. Use
the event's `available_at` as the observation anchor; `pivot_time` and
`formation_time` describe earlier geometry and must not be used as if the
information was known then.

### Hypotheses and falsifiable outcomes

For each event, define forward close return as
`close_at_available_plus_H / close_at_available - 1`, where `H` is a
predeclared horizon after availability. Because candle gaps are allowed, the
horizon convention itself remains unresolved and requires approval:

- A fixed number of observed bars preserves an observation-count horizon, but
  the elapsed clock time varies when candles are missing.
- A fixed elapsed-time horizon gives a stable clock duration, but requires a
  documented sampling rule when no candle closes exactly at the target time
  (for example, which eligible close is selected or whether the event is
  excluded).

No numeric horizon or missing-candle sampling rule is chosen here. The exact
horizon(s), asset/timeframe set, comparison cohorts, minimum sample rationale,
and economically meaningful effect sizes are unresolved and require approval
before data access. An observation may support a hypothesis only if the
predeclared directional conditional return contrast is positive in its
expected direction and its uncertainty is consistent with the registered
criterion. A contrast that is zero, opposite, or too uncertain rejects or
defers it according to the criteria below; no horizon may be selected after
looking at holdout outcomes.

| Feature hypothesis | Observable comparison | Expected direction; falsifier |
|---|---|---|
| Confirmed market structure | At each close, compare outcomes when the latest confirmed high label is `higher_high` and latest confirmed low label is `higher_low` against the corresponding `lower_low`/`lower_high` state and a predeclared unconditional cohort. | Bullish-state forward returns should exceed bearish-state returns. No stable contrast or a reversed contrast rejects the directional claim. Initial/equal/mixed states remain separately described. |
| Support/resistance lifecycle | Compare returns after a support or resistance `touched` event and after a `broken` event with matched no-event observations. Match only on information known at the event's availability. | Support touch and resistance break are expected to have positive directional outcomes; resistance touch and support break negative. Reversed or absent differences reject the respective subhypothesis. These four contrasts are recorded separately. |
| Bullish engulfing | Outcomes after `bullish_engulfing` versus eligible no-pattern candles. | Positive directional contrast; zero or negative contrast rejects it. |
| Bearish engulfing | Outcomes after `bearish_engulfing` versus eligible no-pattern candles. | Negative directional contrast; zero or positive contrast rejects it. |
| Hammer | Outcomes after `hammer` versus eligible no-pattern candles. | Positive directional contrast; zero or negative contrast rejects it. The test does not add trend context absent from the detector. |
| Shooting star | Outcomes after `shooting_star` versus eligible no-pattern candles. | Negative directional contrast; zero or positive contrast rejects it. The test does not add trend context absent from the detector. |
| Double top | Outcomes anchored at the event's `available_at`, not its earlier formation candle, versus eligible no-pattern observations. | Negative directional contrast; zero or positive contrast rejects it. A neckline-break subgroup is a separate future hypothesis, not part of `shape_confirmed`. |
| Double bottom | Outcomes anchored at `available_at` versus eligible no-pattern observations. | Positive directional contrast; zero or negative contrast rejects it. |

### Outcomes and baselines

The primary descriptive outcome is the predeclared forward-return
distribution (mean, median, quantiles and uncertainty) at every registered
horizon, with directional hit rate reported as a secondary summary rather
than a trading objective. Where OHLC makes it meaningful, also report
maximum favorable and adverse excursion from the first post-availability
bar through the horizon. All outcome windows begin after the event becomes
available. A descriptive event study has no position, execution, fee, or
equity accounting and is not a backtest.

Compare feature cohorts with unconditional and carefully matched no-event
observations from the same asset, timeframe and chronological period. For
context, report unchanged Buy & Hold, EMA 20/50 and Donchian 20 baseline
metrics on exactly the same asset/timeframe/date range; existing saved
baseline files remain untouched and are not regenerated for this protocol.
Such strategy-level context does not establish that a feature caused a
baseline's result. If a separately approved rule is later tested as a full
strategy, report turnover, exposure, fees, slippage, drawdown and both
mark-to-market and net-liquidation equity under the existing semantics.

### Leakage, dependence and reproducibility controls

- Compute every feature on chronologically ordered data with the declared
  timeframe. Require `available_at == timestamp + timeframe`; do not infer a
  duration from missing-candle gaps. A pivot/formation is eligible only at
  its later feature `available_at`.
- Split by availability into development (training plus validation) and an
  untouched later holdout. Freeze the versioned configuration and approved
  hypothesis before opening the holdout through `experiment_protocol.py`.
  The existing 730-day data is engineering/pipeline evidence only until a
  suitable history and approved split plan exist.
- Events and forward windows can overlap. Predeclare an event-clustering or
  dependence-aware uncertainty method; do not count repeated or overlapping
  observations as independent. For matched cohorts, define matching variables
  using information available at the anchor close only.
- Register all eight feature families, the four separate zone contrasts,
  horizons, assets, subgroups and outcome metrics before evaluation. Preserve
  null and rejected results in the research log; use an approved multiple-
  testing adjustment or designate a small primary family before analysis.
- Never choose thresholds, horizons, assets, regimes or variants based on
  holdout performance. Any revision after validation creates a new version
  and requires a fresh untouched holdout.
- Record hypothesis ID/version, feature code hashes, data-file hashes and
  ranges, explicit timeframe, configuration fingerprint, sample counts,
  exclusions, tests, outcome definitions, uncertainty method and rejection
  decision in a no-clobber experiment manifest and append-only log.

### Decision and approval criteria

Advance a hypothesis only when its preregistered outcome is directionally
consistent in the development and validation data, sample-size rationale is
met, uncertainty and multiple-testing treatment satisfy the approved plan,
and the result survives the registered asset/period and observation-dependence
checks. Reject it if the registered effect is absent or reversed under the
approved decision rule. Defer it when history, event count, data quality or
uncertainty is insufficient. Numerical effect-size, confidence, minimum
sample, cross-asset consistency and multiplicity thresholds are intentionally
left undecided; they require approval before any predictive experiment.

Passing this protocol would justify only the next research gate. It would not
approve strategy integration, a preferred strategy, paper trading, or live
execution.

The existing split/manifest utilities enforce basic chronology, availability
column coverage, fingerprint matching, output no-clobber behavior, and an
explicit `APPROVED` hypothesis-status declaration before holdout freeze. The
status is a caller attestation, not independent proof of user approval. A
manifest requires the caller to provide experiment-specific source files and
hashes them alongside the core backtester, loader, strategies and protocol.
The caller must include every feature and runner file that affects the
experiment. These utilities do not decide suitable date windows, sample
sufficiency or a strategy. The manifest writer also rejects an empty input
data-file list so a configured run cannot appear reproducible without data
hashes. Configuration fingerprints use strict JSON serialization and reject
NaN and infinite values instead of encoding Python's non-standard JSON tokens.

`experiment_metrics.py` summarizes precomputed ledgers over those windows,
using the last equity observation before each window as its starting account
value and drawdown peak. It keeps closed-trade exit-time attribution separate
from fee event-time attribution. It does not load or reveal holdout data; the
caller remains responsible for using the freeze/open protocol before
calculating holdout metrics.
The holdout is omitted from the partition object's default representation to
avoid accidental disclosure through ordinary logging. Python callers can
still intentionally access the private attribute or serialize the object, so
this is not a security boundary.

The saved cross-asset regime diagnostic is only a retrospective decomposition
of account-equity changes. It assigns each interval to a trailing regime known
at the previous close and keeps an initial calibration year; it does not test
whether regime labels predict returns. Sparse regime cells and the short
sample preclude regime-performance claims.

Cost sensitivity is implemented as fixed fee/slippage scenarios around the
configured assumptions, with the unchanged strategy definitions. This is a
descriptive robustness check; the scenario values do not search for or select
lower-cost settings. Cost effects may interact with equity-based quantity
through the existing backtester behavior.

## Independent execution and accounting comparison protocol

A test-only scalar reference now checks synthetic ledgers in
`test_independent_accounting_reference.py`; no independent framework or
market-data comparison has been run. Before any future predictive evaluation,
compare the active backtester with a separately written reference
implementation. The reference must not import the production fill, fee,
position-sizing, trade-accounting, or equity-valuation helpers. Record both
implementations' source hashes and use a fresh output directory that refuses
existing targets.

Start with deterministic synthetic OHLCV fixtures covering: remaining flat;
opening and closing a long; opening and closing a short; long-to-short and
short-to-long reversals; nonzero fee and slippage; an open position valued at
an intermediate close; and final-candle liquidation. For each candle, compare
signal/decision time, execution time and price, side and quantity, entry/exit
fees, gross and net closed-trade P&L, realized equity, mark-to-market equity,
net liquidation equity, and terminal position state. Independently calculate
expected fills, fee amounts, and equity from the declared formulas instead of
using either engine's helper functions as the oracle.

Require exact matches for timestamps, sides, position states, trade counts,
and signal decisions. For price, quantity, fees, P&L and equity, require
absolute error <= 1e-9 in the synthetic fixtures; document any scale-dependent
tolerance before using wider-valued fixtures. Each discrepancy must be
reconciled to a declared convention (such as rounding) before comparison is
accepted. A framework comparison is supplementary: it must match execution
timing, fee/slippage inputs and position semantics, and differences must be
reported rather than normalized away.

Only after synthetic agreement should an independently generated trace be
compared on training/validation data for an approved hypothesis. Do not expose
the project holdout during this engineering check. A mismatch blocks later
predictive evaluation until its cause is fixed and the frozen configuration,
code hashes, test output and discrepancy report are recorded. This protocol
defines an engineering gate; it is not evidence that any strategy has
predictive value.

## Paper-trading gate

The current-state assessment is recorded in
`research/PAPER_TRADING_READINESS_REVIEW.md`. It finds the system not ready:
local candles are stale for operational use, the active engine models
simulated fills only, risk calculations are not enforced controls, and there
is no paper order lifecycle, independent reconciliation, or monitoring stack.
`research/data_quality.py` offers a synthetic-tested freshness check with
explicit caller-supplied time and age threshold; it is not integrated into an
operational feed and defines no default freshness policy.

Paper trading should not begin until independent review confirms all of the
following:

- causal, fresh data ingestion with explicit gap/staleness policy;
- deterministic signal generation and reproducible replay;
- complete order lifecycle, partial-fill, cancel/reject and restart recovery
  handling in a paper-only adapter;
- position and cash reconciliation against an independent ledger;
- separately approved risk limits and tested breach behavior;
- structured monitoring, alerting, audit logs and failure recovery;
- out-of-sample evidence that meets a prespecified acceptance plan, including
  costs, execution uncertainty and multiple-market conditions.

None of these statements authorizes exchange connectivity, live orders or
activation of the standalone risk module in the backtester. Paper-trading
transition remains an explicit approval gate.
