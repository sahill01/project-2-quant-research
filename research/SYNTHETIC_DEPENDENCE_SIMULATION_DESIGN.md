# SUPPORT_TOUCH_001 synthetic dependence simulation — design preregistration

> **SYNTHETIC — NOT MARKET EVIDENCE.** This document fixes the simulator
> design before execution. It does not approve SUPPORT_TOUCH_001, authorize
> use of project OHLCV, or establish that any resampling method is valid for
> market data.

## Purpose and estimand

Stress-test candidate confidence intervals for the event-weighted difference
in observed-case arithmetic means, `mean(Y | higher_low) - mean(Y | lower_low)`.
The generated outcome is a synthetic scalar, not a market return or a label
derived from candles. The primary simulation estimand is the generator's
population contrast among events before the declared missingness mechanism.
When missingness depends on cohort or outcome, the observed-case estimator
may target a different contrast; this is a deliberate selection-bias stress.

## Fixed simulation protocol

- Generator: two cohorts, each with its own synthetic zones; events are placed
  on integer 4-hour periods. Each event outcome equals cohort effect plus a
  zone random intercept plus the mean of six future period shocks (a synthetic
  24-hour overlapping window) plus event noise. Period shocks may be AR(1)
  and/or shared by every zone. No OHLCV or project result file is read.
- In the deliberately five-period sparse-calendar scenario, six-shock windows
  wrap circularly to keep the generated outcome defined. That synthetic edge
  convention is only a stress-fixture device and is not a market sampling rule.
- Scenario factors: independent events; repeated events per persistent zone;
  AR(1) calendar shocks; six-period overlapping windows; common shocks across
  zones; highly unequal/concentrated zone event counts; few zones; few time
  periods; cohort-differential missingness; and null or fixed nonzero cohort
  effects. Factor combinations are declared in code and the report. They are
  stress cases, not claims about actual crypto dependence.
- Illustrative synthetic scale only: unit event-noise SD; zone SD 0.5 when
  active; period-innovation SD 0.5 when active; AR coefficient 0.7 when
  active. AR paths start from a zero-mean innovation draw without burn-in, so
  marginal variance ramps toward its stationary level;
  nonzero contrast 0.25. These values are not market estimates or adequacy
  thresholds.
- Fixed RNG seeds: master seed `20261020`; each Monte Carlo replicate and
  bootstrap stream is derived deterministically from it and scenario/method
  indices. Outer repetitions: 300 per scenario/effect cell. Bootstrap draws:
  399 per dataset, percentile 95% two-sided intervals. A simulation floor of
  4 distinct zones and 4 occupied six-period blocks in each cohort is used
  only to demonstrate fail-closed mechanics; it is not an inferential minimum.
- Candidate methods: (1) circular moving calendar-block bootstrap, fixed
  length 6 periods (24h); (2) within-cohort zone-cluster bootstrap; (3)
  product-weight crossed bootstrap using independently drawn zone and calendar
  block multiplicities; (4) event IID bootstrap as a deliberately
  misspecified negative control, never an acceptable primary method.
- The calendar-block method samples circular contiguous blocks to create
  period multiplicities shared across cohorts and zones. It preserves local
  calendar dependence and overlapping events within sampled blocks, but does
  not preserve a zone's dependence across separated blocks. The zone method
  resamples whole zones within cohort and retains all their events, but does
  not preserve common calendar shocks. The product-weight method multiplies
  zone and period weights; it is included as a stress candidate, not presumed
  valid for crossed dependence. None guarantees validity under sparse support,
  long-range dependence, informative cluster sampling, or missing-not-at-random
  outcomes.
- Each method returns inconclusive when either cohort has fewer than 4
  observed zones or fewer than 4 occupied non-overlapping six-period calendar
  blocks, a bootstrap draw has zero cohort weight,
  or fewer than 90% of requested draws yield finite estimates. This is a
  mechanical simulation guard only. Report raw events, unique zones, occupied
  periods, occupied blocks, and Kish concentration summaries separately; Kish counts are
  concentration summaries, not proof of independence.

## Metrics and failure criteria

For each scenario/effect/method report point-estimate bias, empirical 95%
interval coverage, mean interval width, null false-positive rate (two-sided
interval excludes zero), power at the fixed nonzero effect, and inconclusive
frequency. Report Monte Carlo standard errors: `sqrt(p*(1-p)/R)` for rates
and sample-SD divided by `sqrt(R)` for means. Intervals and performance are
not tuned or ranked to choose the most favorable method.

Conditional failure flags are descriptive: null rejection visibly above the
nominal 5% relative to its Monte Carlo uncertainty; undercoverage; severe
interval instability; or high inconclusive rate. No universal pass cutoff is
declared. Synthetic performance cannot supply real-market minimum sample,
block length, confidence, or precision policy.

## Interpretation limits

An event-weighted contrast gives more influence to zones with more retained
touches. Unequal event counts, cohort-specific missingness, shared shocks,
serial shocks, and overlapping windows can each change bias or uncertainty.
Product-weight resampling is not automatically a valid two-way bootstrap.
The finite synthetic scenarios do not identify the actual dependence range,
cluster structure, missingness mechanism, or effective sample size in
SUPPORT_TOUCH_001. No candidate is selected as confirmatory by this exercise;
owner approval and a pre-outcome method/support policy remain required.

## Transparent implementation amendment before corrected run (V2)

The first fixed-protocol run exposed a mechanical support defect: a five-period
fixture passed a four-occupied-period floor even though the six-period moving
block resampler had only one effective calendar block and returned a
zero-width interval. Initial outputs are retained unchanged as V1. Before the
corrected V2 run, the mechanical gate was amended to require four occupied
non-overlapping six-period calendar blocks per cohort, in addition to four
zones. This is a conservative algorithm-support guard motivated directly by
the declared block length; it is not empirically calibrated, not a real-data
threshold, and does not declare any method successful. All other DGPs, seeds,
repetitions, methods, and metrics remain fixed. V2 outputs use new filenames.

## Transparent audit amendment before V3

The independent audit found that V1/V2 omitted the fraction of bootstrap
replicates with zero weight in a cohort from the result table. The code already
returned inconclusive below 90% finite draws, but could exclude up to 10% of
draws without the report exposing that count. V3 adds valid-draw counts and
fractions, and separates minimum-support from bootstrap-failure inconclusive
rates. No generator, resampling algorithm, threshold, seed, repetition count,
or scientific interpretation changed. V1 and V2 artifacts remain preserved.
