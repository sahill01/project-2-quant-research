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

`experiment_protocol.py` now separates intended specification, actual input
and implementation provenance, outputs, and validation/approval metadata in
the versioned manifest. It records the hypothesis ID/version, config and
hypothesis fingerprints, dataset IDs/hashes/observed timestamp ranges and
timeframe, core and caller-supplied source hashes, code revision when Git is
available, feature-pipeline version, execution/cost assumptions, random
seeds, runtime versions, artifact hashes, and validation metadata. Experiment
IDs are path-safe and unique within an output root; existing run directories
are never overwritten. The manifest starts as `configured_not_run`. Finalized
manifests use `evaluation_completed` only when computation status is
`completed`; a separate scientific status records `not_assessed`,
`criteria_met`, `criteria_not_met`, or `inconclusive`. These labels do not
define or imply acceptance thresholds. `verify_experiment_manifest()` checks
schema/status consistency, artifact containment, uniqueness, existence, and
SHA-256 values. Hashes first captured at finalization cannot prove that an
artifact was unchanged before finalization.

Holdout freeze and holdout-inclusive `experiment_metrics.py` reports require
a `PreregistrationApproval` record created from an approved config and
hypothesis, an approver identity/note/time, fully resolved decision fields,
and hashes of the current data and implementation files. The record is
rechecked against the current config, hypothesis, data, and code at use time.
An `APPROVED` string alone, Boolean, or caller-provided digest is insufficient.
This is a deliberate local audit contract and stale-input safeguard, not an
identity service or security boundary: Python callers can forge local records
or bypass APIs and access private data. Frozen partitions also bind the exact
approval record, canonical source-frame content fingerprint, partition
boundaries, and copied partition contents. The frame fingerprint detects
content changes; it does not prove the frame originated from the approved
source files.

`ResearchDecisions` explicitly leaves unanswered methodology fields as
`None`, empty values, and common unresolved placeholders (`UNRESOLVED`, `TBD`,
`TODO`, `TO BE DETERMINED`, or `PENDING`, case-insensitively) block approval.
Placeholder-like words in ordinary explanatory text do not by themselves
make a field unresolved. No
numeric horizon, missing-candle policy, sample threshold, effect-size or
uncertainty criterion, matching method, or split design is supplied by the
infrastructure. Synthetic tests use fixture-only values and are not research
choices. Manifests require at least one data file and experiment-specific
source file; strict canonical JSON rejects non-finite config values. The
append-only research log continues to record experiment IDs and outcomes or
rejection reasons.

Reproducibility tests (`python -m research.test_experiment_protocol`,
`python -m research.test_hypothesis_spec`, and
`python -m research.test_experiment_metrics`) exercise synthetic fixtures and
temporary directories only. They do not run an evaluation. The repository has
no single approved predictive-evaluation command; baseline and diagnostic
scripts produce descriptive historical outputs and are not preregistration
gates. Any future predictive runner must first require a resolved approval
record and the holdout gate. Reproducibility establishes repeatability and
auditability, not scientific validity, profitability, or statistical support.

`experiment_metrics.py` summarizes precomputed ledgers over those windows,
using the last equity observation before each window as its starting account
value and drawdown peak. It keeps closed-trade exit-time attribution separate
from fee event-time attribution. Holdout-inclusive summaries require the
current approval and an `EvaluationProvenance` record that fingerprints the
exact supplied ledgers and split. This detects later ledger substitution or
mutation, but cannot prove that a caller initially derived those strategy
ledgers from the approved source data or implementation; that remains a
caller responsibility because the feature-only event-study runner does not
own the strategy-ledger derivation boundary. A local
Python API cannot prevent deliberate private-attribute access, copying data
before freeze, or forged records.
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

## Feature-only event-study infrastructure (Milestone 3)

`research/event_study.py` is a separate feature-only contract and utility
module. It does not populate the strategy-oriented `ExperimentConfig` or
`HypothesisSpec` with invented execution fields. Its `EventStudySpec` records
event/cohort semantics, source joins and availability constraints, outcome
rule, sample scope, feature parameters, missing/incomplete and overlap
policies, temporal splits, boundary handling, estimand, uncertainty,
multiplicity, decision criteria, source/data hashes, and draft/approved status.
Unresolved fields block creation of a local approval record.

The module constructs support-zone lifecycle rows and joins support origins
to confirmed swing-low labels by pivot identity, while checking origin and
creation availability against the touch close. It retains repeated and
overlapping lifecycle events. Its outcome calculator supports fixed observed
bars and fixed elapsed time with explicit endpoint, lateness, gap, and
incomplete-window choices. Its partition utility uses event `available_at`
with UTC half-open windows and can purge or reject outcome windows crossing a
boundary. Descriptive cohort counts/means do not include uncertainty or
significance claims. These paths have synthetic tests only; the calculator
has not been run on the project's OHLCV datasets.

`research/event_study_runner.py` now provides an ordinary-use execution
boundary: it verifies approval and current hashes before parsing candles,
then materializes only the candle prefix whose availability precedes the
requested stage end. It streams the timestamp column through the file to
validate chronological order while locating the boundary; OHLCV values after
the boundary are not materialized. The lower-level research outcome function
also rejects any supplied candle at or beyond the authorized stage end.
Bundle creation and verification check exact artifact identities, required
schemas, matching event/outcome IDs, stage bounds, finite included outcomes,
and count/status consistency. It stages and verifies a bundle containing the
specification, event/outcome/exclusion
ledgers, data-quality report, descriptive summary, validation record, and
manifest. Manifest status is `computation_completed` with
`scientific_status=not_assessed`; the runner does not classify the hypothesis
as passed. The approved source-hash set must include the current runner,
event-study primitives, loader, swing, and support/resistance implementations.

The runner provides a local boundary, not isolation: Python callers can read
files directly, bypass the runner, or lie about `data_role` when calling the
low-level calculator. Hashes and local approval records are not tamper-proof
and do not prove causal derivation. There is no dependence-aware uncertainty
estimator; inferential output is disabled and summaries are descriptive only.

The support-touch proposal remains **DRAFT — NOT APPROVED FOR EVALUATION**.
The outcome formula, horizon and close-selection rule, missing-candle and
incomplete-window treatment, event overlap/repetition policy, asset/timeframe
family, feature parameters, comparator/confounder plan, chronological split,
minimum-sample rationale, uncertainty method, multiplicity family,
effect-size threshold, and advance/reject/defer rules all remain subject to
explicit approval. The implementation and synthetic fixtures are engineering
evidence only, not predictive evidence or permission to calculate real-data
outcomes.

For a future approved run, the study owner resolves the specification and
authorized stage set. The runner verifies the approved spec, data hashes, and
required implementation hashes before parsing OHLCV; loads only the authorized
stage prefix; freezes the causal event cohort before calculating outcomes;
excludes embargoed events before outcome calculation; applies approved gap,
incomplete-window, and boundary policies; then publishes and verifies a
no-clobber bundle. A reviewer assesses scientific criteria separately.
Computation completion is not a scientific pass. This workflow has only been
exercised with synthetic temporary fixtures.

### Milestone 4A — SUPPORT_TOUCH_001 proposal boundary

The current decision-ready candidate recommends BTCUSD 4h as the sole
primary population, with ETHUSD/SOLUSD 4h as separate exploratory
replications, and preserves the registered higher-low versus lower-low
support-touch contrast. It proposes `Y_24h = C_future/C_anchor - 1`, with the
touch close as anchor and an exact close 24 elapsed hours later. The proposed
gap policy is no filling and exclusion of outcomes missing an expected 4h
candle, exact endpoint, or complete window. These are recommendations for
explicit owner review, not scientific defaults in code or permission to
calculate real-data outcomes.

The event is observed at the touch candle's declared close availability.
Origin structure is joined by pivot identity, but its confirmation and zone
creation availability must be no later than touch availability. `pivot_time`
is not information availability. The event-study builder and runner implement
these mechanical contracts; source inspection and synthetic tests establish
only implementation behavior.

Proposed dependence handling retains repeated and overlapping events but
requires time-block-aware uncertainty. No confidence interval, effective
sample-size check, or minimum-block rule is implemented. Proposed UTC
50%/25%/25% chronological windows and horizon-linked purge/embargo are not
derived or approved by the runner; the protocol validates supplied windows
and supports configured purge/embargo but does not enforce embargo >= horizon.
Until an uncertainty method and adequacy rules are approved, descriptive
cohort counts/means are the limit; inferential reporting must defer.

The decision register in `DECISION_REGISTER_SUPPORT_TOUCH_001.md` maps each
method choice to its enforcement path and lists remaining blockers. Proposal,
owner approval, authorized stage execution, and independent scientific
reporting remain separate gates. The local approval/provenance code is not
tamper-proof and is not a security boundary. No approval record, holdout
freeze, experiment manifest, result bundle, or hypothesis outcome has been
created for this proposal.

## Milestone 4C — SUPPORT_TOUCH_001 readiness boundary

The versioned candidate specification is
`research/SUPPORT_TOUCH_001_PREREG_DRAFT_V1.json`. Its fingerprint covers the
proposed `EventStudySpec`; it is explicitly a draft fingerprint, not an
approval, experiment manifest, or data/source provenance record. The
BTCUSD 4h scope, event-weighted higher-low minus lower-low contrast, proposed
24-hour exact elapsed close return, and proposed gap/incomplete-window
exclusions remain unapproved recommendations.

### Inference remains blocked

No inferential interval or precision-adequacy utility is provided. A product
of zone and calendar-time-block bootstrap weights is not automatically valid
for crossed zone/time dependence: repeated touches share zones, different
zones can share candles and overlapping forward windows, and adjacent blocks
may remain dependent. A defendable design needs its exact estimator,
resampling algorithm, support conditions in each dependence dimension,
finite-cluster behavior, confidence level, block rule, and synthetic
operating-characteristic plan specified before outcome access. Without that,
raw event counts and IID intervals cannot justify an inferential claim. The
adequacy result must be inconclusive when there are too few independent
clusters or precision is insufficient; numerical criteria remain unapproved.

### Stage and holdout safeguards

The event-study runner now fails closed for missing/invalid split boundaries,
requires the configured embargo to be at least the nominal outcome horizon,
and excludes/rejects any included outcome endpoint at or beyond its stage end.
Observed-bar horizons are converted using the explicit declared timeframe,
not observed timestamp gaps. Missing candles can make actual elapsed outcomes
longer than that nominal span, so endpoint containment remains mandatory.

The initial event-study approval cannot include `holdout`. The explicit
sequence is plan lock, then holdout-release authorization, then a holdout
runner invocation bound to the same spec and approval fingerprints. Bundle
validation records the release fingerprint. This is a procedural local API
gate, not a security boundary or proof that holdout data were never viewed;
direct file access and Python-level bypass remain possible. Development and
validation runners still materialize OHLCV only before their stage end, and
included outcomes must end within that stage.

The event-study output remains descriptive with `scientific_status` set to
`not_assessed`. No project OHLCV was used to calculate outcomes or labels.
SUPPORT_TOUCH_001 remains **DRAFT — NOT APPROVED FOR EVALUATION**.

Required scientific gates before confirmatory evaluation are a frozen
population/cohort definition, feature values, horizon and endpoint/gap rule,
chronological boundaries, horizon-linked embargo, dependence-aware inference,
precision/support adequacy, multiplicity family, effect threshold, and
advance/reject/inconclusive rules. Separate ETH/SOL replication, a
one-touch-per-zone sensitivity, and pre-event descriptive strata are optional
robustness checks; they cannot replace the primary result and require advance
registration if reported inferentially.

The process is proposal and fingerprint → explicit owner approval →
authorized stage execution → independent scientific reporting. The local
fingerprint is reproducible identification, not authentication. Approval
records bind local inputs but do not prove the operator did not inspect
holdout data or bypass the runner.
