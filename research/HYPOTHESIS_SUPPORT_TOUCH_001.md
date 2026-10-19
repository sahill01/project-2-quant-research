# HYP-SUPPORT-TOUCH-001 — support touches by originating swing structure

> **DRAFT — NOT APPROVED FOR EVALUATION**
>
> This document proposes a falsifiable descriptive event study. It is not an
> approved experiment, trading signal, or strategy. No historical outcomes
> have been calculated for this proposal. All unresolved decisions below must
> be settled explicitly before outcome data are accessed.

> **Infrastructure note:** `research/event_study.py` now supplies synthetic-
> tested mechanics for cohort construction, candidate outcomes, temporal
> partition safeguards, and descriptive summaries, plus an approval-gated
> stage-bounded runner and verified artifact bundle. That implementation
> does not resolve or approve the scientific choices in this draft. No actual
> dataset was passed to its outcome calculator or runner.

## Proposal

**Market rationale.** A support zone is anchored to a confirmed local low,
while its `higher_low`/`lower_low` label records that low's position relative
to the previous confirmed low. Comparing later touches by this origin label
tests whether the structure context distinguishes touch outcomes. This is a
plausible descriptive contrast only; neither persistence nor predictive value
is assumed.

**Research question.** After a later touch of a confirmed support zone, does
the subsequent outcome differ according to whether the zone originated from
a confirmed higher low or lower low?

**Candidate hypothesis.** For an outcome scalar `Y_H` defined at a future
horizon `H` that has not yet been selected, the mean outcome for support-zone
touch events whose originating confirmed swing is labelled `higher_low` is
greater than the mean outcome for otherwise eligible support-zone touch
events whose originating confirmed swing is labelled `lower_low`:

`H1: E[Y_H | higher_low-origin support touch] - E[Y_H | lower_low-origin support touch] > 0`.

**Null hypothesis.**

`H0: E[Y_H | higher_low-origin support touch] - E[Y_H | lower_low-origin support touch] <= 0`.

These hypotheses define a direction, not an effect-size threshold or an
approved statistical test. **Proposed outcome measure, pending explicit
approval:** forward close-to-close return

`Y_H = (C_future / C_anchor) - 1`.

`C_anchor` is the close of the touch-event candle, whose touch becomes
observable only at that candle's `available_at`. `C_future` is the close
selected at a horizon `H` that remains unresolved. No numerical horizon or
future-close sampling rule is selected here. Event eligibility, origin labels,
joins, and features must use information available no later than the touch
candle close; future candles may be used only to calculate the outcome after
eligibility is frozen.

**Candidate baseline.** The comparison cohort is later `touched` events for
`support` zones originating from a confirmed swing low labelled
`lower_low`. The primary contrast excludes initial and equal lows, resistance
zones, creation events, and broken events. Whether this is a sufficient
control, or needs matching or stratification, remains unresolved. It is a
feature-event comparison, not Buy & Hold or a trading strategy comparison.

## Event population and feature definition

Candidate local population: the validated BTCUSD, ETHUSD, and SOLUSD OHLCV
files at 15m, 1h, 4h, and 1d. These files cover approximately 730 days. Each
asset/timeframe would initially be kept identifiable; pooling, which subsets
belong in the primary family, and the development/validation/holdout periods
are unresolved. The data are sufficient to exercise the existing feature
pipeline, but the number and independence of eligible events and adequacy for
inference have not been assessed.

An eligible event is defined from existing feature outputs as follows:

1. `confirmed_market_structure()` emits a swing low with a low-side structure
   label `higher_low` or `lower_low`.
2. `confirmed_swing_zones()` creates a distinct `support` zone from that
   confirmed swing low.
3. On a later observed candle, the same zone emits `event == "touched"`.
   The zone feature gives a close-confirmed `broken` event precedence over a
   wick intersection on the same candle, so such a candle is not a touch.
4. The touch is the event anchor for any future approved outcome. OHLC only
   establishes that the candle range intersected the zone; it does not reveal
   when inside the candle the touch occurred.

The origin join is `zone_id`/`pivot_time` to the structure row's
`swing_low_pivot_time`, then the low-side label `swing_low_structure` from
that source structure row. Structure classification is relative to the
previous confirmed swing low on that side. The proposal uses only the two
explicit labels above; it does not relabel `initial_low` or `equal_low`.

## Causal timestamps and decision-time fields

The loader treats `timestamp` as candle **open** and derives
`available_at = timestamp + declared timeframe`, the candle **close**. It
validates the explicit timeframe rather than inferring candle duration from
timestamp gaps. Missing candles are allowed by the feature contract and are
not synthesized.

In normalized `assemble_feature_dataset().events` rows:

- `event_time` is the open timestamp of the candle anchoring that event. For
  structure it is the swing-confirmation candle; for a zone touch/break it is
  the lifecycle-event candle; for chart geometry it is the formation candle.
- `available_at` is when the required information is complete: the close of
  the anchor candle for these events, or the later confirmation-candle close
  when a chart pattern needs swing confirmation.
- `pivot_time` is the historical candle open where the originating swing
  occurred. It is an identity/geometry field, not the time the swing became
  known.
- `formation_time` records candlestick/chart geometry only. It is null for
  structure and zone lifecycle records; it is not the origin pivot field.
- `payload` retains the source-layer row. For zone rows, that source schema's
  `event_time` is the lifecycle candle close; the normalized row maps the
  lifecycle candle to its open in `event_time` and retains the source value in
  `payload`.

The first point at which a **zone-touch event** and its originating structure
label can both be used is the touch candle's `available_at`. The structure
label itself is only known at the confirmation candle's `available_at`.
`confirmed_swing_zones()` creates a zone only at that confirmation close and
starts lifecycle checks on a later observed candle. Consequently, for a
valid origin join, structure availability and zone creation availability
precede the later touch availability. Any eventual as-of join must use
`available_at` and enforce those inequalities; joining at `pivot_time` or
using `event_time` as if the event were already known would leak information.
No intrabar ordering or touch time is inferred.

At an eventual approved decision point, the relevant available inputs are the
touch event type, zone type and bounds, zone identifier and origin pivot,
source payload, and the confirmed low-side structure label. The feature
assembler's candle-aligned structure columns are also available at their
row's close. No future candle, later zone state, outcome, or trade result may
be used to define eligibility.

## Outcome, missing bars, and dependence

The candidate forward close-to-close return formula is stated above, but both
the horizon and the exact rule that selects `C_future` remain unresolved. In
particular, approval is needed between:

- **Fixed observed-bar count:** preserves the number of observations, while
  elapsed clock duration varies across gaps. `H` would count observed
  candles after the touch candle; a missing interval does not create a
  synthetic candle.
- **Fixed elapsed time:** preserves clock duration, while requiring a rule
  for selecting an observed close when no candle closes exactly at the target
  time, or excluding the event. The eligible-close rule must be predeclared,
  not selected based on the resulting return.

The missing-candle policy is unresolved. It must address both a gap between
event availability and the target observation and gaps inside a future
outcome window. No rows will be forward-filled by this proposal.

Overlapping-event treatment is unresolved. Repeated touches of one zone,
simultaneous touches of overlapping zones, and outcome windows sharing future
candles can make observations dependent or duplicate exposure to the same
price movement. Possible approaches include retaining all events with a
dependence-aware analysis, event clustering/exclusion, or a predeclared
deduplication rule. No approach is selected.

## Why the hypothesis may fail; bias controls

The contrast may be absent or reversed; support-zone labels may not contain
incremental information; the result may depend on asset, timeframe, market
regime, zone-width choice, pivot confirmation settings, or a small set of
episodes; and a close-confirmed swing label may arrive too late to distinguish
subsequent touches. OHLC touch observations do not establish fillability or
the order of within-candle events. A descriptive result would not establish a
tradable effect after costs.

Leakage risks include treating the earlier `pivot_time` as the observation
time, joining a touch to a structure label before its confirmation
`available_at`, using a zone's later `broken` or touched state in an earlier
snapshot, or defining an outcome from a candle at/before event availability.
Selection risks include choosing assets, timeframes, pivot/zone parameters,
outcome horizons, subgroups, matching variables, or success criteria after
seeing outcomes, and treating repeated/overlapping events as independent.
Use only as-of feature state and freeze all such choices before any approved
outcome evaluation.

## Decisions supported by existing code

- The structure API requires explicit `timeframe`, `left_bars`, and
  `right_bars`; strict pivots are emitted only after the configured right
  confirmation bars close. Tied extrema are not strict swings.
- Market-structure labels compare each confirmed high/low only with the
  previous confirmed swing on the same side.
- The zone API requires an explicit timeframe and zone-width fraction. It
  creates separate fixed-width zones from confirmed pivots, does not merge
  overlaps, checks later candles, records repeated touches, and makes a
  close-confirmed break terminal. Break takes precedence over touch on the
  same candle.
- The feature assembler preserves source rows in `payload`, separates
  lifecycle/formation and availability timestamps, and sorts same-close
  events by a fixed layer order for bookkeeping. That ordering is not
  intrabar chronology.
- The loader/API contract accepts missing-candle gaps without inferring a new
  timeframe. The dataset inspection found the configured files readable with
  aligned close availability; this is a data-integrity observation only.
- The experiment schema has fields for the hypothesis, null/baseline,
  event definition, outcome horizon, missing bars, overlap, chronological
  windows, matching, sample rationale, effect size, uncertainty/multiple
  testing, and decision rules. It requires resolved decisions and approval
  before an approval record can be created.

## Decisions awaiting explicit approval

The following are not selected or resolved by this draft:

1. Forward-return horizon and exact outcome calculation.
2. Fixed observed-bar count versus fixed elapsed-time horizon and sampling.
3. Missing-candle policy.
4. Overlapping-event treatment.
5. Chronological development, validation, and untouched holdout windows.
6. Matching or control-selection methodology.
7. Minimum sample requirement and its rationale.
8. Minimum meaningful effect-size threshold.
9. Uncertainty and multiple-testing criteria, including the primary test
   family.
10. Advancement, rejection, and deferral rules.

Also unresolved before a reproducible study are the exact asset/timeframe
family, swing left/right confirmation bars, zone width, any stratification,
and whether the candidate lower-low touch cohort is the sole comparator or
additional contemporaneous controls are needed. None may be selected by
examining historical outcomes.

The template's trade signal, entry/exit, execution, and transaction-cost
fields are not applicable to this descriptive feature event study as drafted;
there is no proposed position or strategy. This does not waive costs if a
separate strategy hypothesis is later proposed.

## Mapping to the existing specification schema

The document corresponds to `HypothesisSpec` version 1 under candidate ID
`HYP-SUPPORT-TOUCH-001`: the rationale, feature/event definition,
availability, expected contrast, failure conditions, comparator, confounders,
and limitations are described above. There is no trading signal, entry/exit,
or execution rule. The `ResearchDecisions` fields for horizon/calculation,
missing candles, overlap, chronological windows, matching, sample rationale,
effect size, uncertainty/multiple testing, and advance/reject/defer remain
unresolved; the event and null/comparator are proposals, not approval records.
No `HypothesisSpec`, `ExperimentConfig`, manifest, or
`PreregistrationApproval` is instantiated or written by this draft.

## Feasibility and next gate

The existing APIs can construct the event cohorts without changing their
schemas or adding a parallel pipeline. A causal join is feasible through the
zone's origin `pivot_time`/`zone_id`, the source structure row, and explicit
`available_at` checks. The existing synthetic tests cover confirmation
delays, prefix/future perturbation invariance, lifecycle creation/touch/break,
payload and timestamp semantics, as-of zone snapshots, missing-candle gaps,
and deterministic assembly. Dataset loading was checked for format, OHLCV
validity, timestamp ordering/alignment, and availability consistency, without
calculating outcomes.

This establishes engineering feasibility only. It does not establish enough
eligible observations, independence, power, predictive value, or suitability
for a strategy. The next gate is user review of the unresolved design choices
above. Do not create an experiment config, set an approval status, create a
`PreregistrationApproval`, expose or analyze forward outcomes, or run an
evaluation until those choices are explicitly approved and the required
specification is complete.

## Milestone 4A — preregistration proposal addendum

> **DRAFT — NOT APPROVED FOR EVALUATION.** This addendum recommends a
> concrete candidate design for review. It does not resolve approval-gated
> choices, authorize real-data outcomes, or change the primary contrast.

The primary estimand remains the mean forward-return difference:

`E[Y_H | higher_low-origin support touch] - E[Y_H | lower_low-origin support touch]`.

The directional alternative remains `> 0`, and the null remains `<= 0`. The
lower-low-origin support-touch cohort remains the sole primary comparator.

**Recommended primary population:** BTCUSD 4h only. Keep ETHUSD 4h and
SOLUSD 4h as separate exploratory replications, not pooled confirmatory
cohorts. Other timeframes are outside this proposal. This limits the primary
test family and avoids assuming that assets or timeframes are exchangeable;
it does not imply BTC representativeness or sample adequacy.

**Recommended event rule:** retain each later source-layer `touched` event
for a `support` zone whose originating confirmed swing-low label is
`higher_low` or `lower_low`. Exclude creation, resistance, break, initial-low,
equal-low, invalid-origin, and unavailable-origin events. Retain each repeated
touch as an event and preserve its zone identity. Require origin structure
confirmation and zone creation availability no later than touch availability.
The event is observable only at the touch candle close (`available_at`),
which is also `C_anchor`. `pivot_time` is an origin key, never knowledge time.

**Recommended candidate outcome:**

`Y_24h = (C_future / C_anchor) - 1`

with `C_future` the close exactly 24 elapsed hours after the touch candle
close. Recommend exact endpoint matching; exclude the outcome if the exact
endpoint or any expected 4h candle in the interval is missing. Do not
forward-fill, substitute a nearby close, or select endpoints based on returns.
Exclude right-edge incomplete windows while retaining their event exclusion
records. The 24-hour candidate is six bars on an uninterrupted 4h grid; it is
not selected from observed performance. Horizon, endpoint, and gap policy
remain approval decisions.

**Repeated and overlapping events:** retain repeated touches and
simultaneous/overlapping-zone touches in the event population. Do not treat
rows as independent. Report event count, unique zones, and calendar-block
coverage. Recommend a calendar-block resampling interval that resamples all
events in each block, preserving clustered activity; the block construction,
length, uncertainty interval, and minimum usable blocks are not implemented
and remain engineering/scientific blockers. If these cannot be justified,
defer inferential reporting rather than use IID event-level errors.

**Chronology:** assign by event `available_at` to UTC half-open windows.
Recommend a 50%/25%/25% chronological division of available calendar
coverage for development, validation, and untouched holdout, with boundaries
computed from timestamps only. Purge outcomes whose endpoint is at or beyond
the partition end; recommend an embargo at least the approved horizon at each
boundary. The current ~730-day coverage may be inadequate after warm-up,
exclusions, and dependence. Exact boundaries and adequacy require approval;
do not shorten holdout after viewing outcomes. If evidence is insufficient,
defer and seek longer history.

**Estimation and gates:** report cohort means, their difference, counts,
unique zones, block coverage, exclusions, and data-quality rates. Use a
dependence-aware calendar-block interval, not IID event-level uncertainty.
Advance only if the untouched-holdout interval's lower bound exceeds an
approved positive minimum meaningful effect and approved sample/data-quality
criteria are met. Reject the directional hypothesis only if its upper bound
is at or below zero under an adequate design. Otherwise classify as
inconclusive/deferred. Confidence level, interval procedure, sample rationale,
minimum effect, and gate values require approval. One registered primary
contrast needs no within-primary multiplicity adjustment; inferential
secondary analyses require a predeclared family and correction. Exploratory
ETH/SOL and sensitivity results cannot rescue a failed primary result.

See [`DECISION_REGISTER_SUPPORT_TOUCH_001.md`](DECISION_REGISTER_SUPPORT_TOUCH_001.md)
for the complete decision-to-code enforcement map and approval checklist.
