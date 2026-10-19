# Decision register — SUPPORT_TOUCH_001

> **DRAFT — NOT APPROVED FOR EVALUATION.** This register records suggested
> defaults and code contracts. It is not an approval record and does not
> authorize outcome calculation.

## Proposed defaults for review

| Topic | Proposed default | Reason / caveat | Current enforcement |
|---|---|---|---|
| Primary contrast | Preserve `E[Y_H|higher_low] - E[Y_H|lower_low] > 0`; null is `<= 0`. Lower-low support touches remain the comparator. | Directly preserves SUPPORT_TOUCH_001; observational, not causal. | `EventStudySpec` stores estimand/cohorts; `event_study_runner._validate_scientific_contract()` restricts the estimand and cohort labels. User must approve the design. |
| Primary population | BTCUSD 4h only; ETHUSD/SOLUSD 4h separately exploratory; no pooling or other timeframes in the primary family. | Narrow family avoids broad multiplicity and asset-exchangeability assumptions; less general. | Scope fields and exact identities are validated by `run_event_study()`. Selection not scientifically approved. |
| Candidate outcome | `Y_24h=(C_future/C_anchor)-1`; anchor is touch-candle close. | Interpretable one-day forward close return; not executable P&L and not outcome-selected. | `OutcomeRule` and `calculate_forward_close_outcomes()` implement formula mechanics; 24h is not code default or approved. |
| Horizon/endpoint | Fixed 24 elapsed hours, exact close only. | Keeps clock horizon stable; missing exact endpoint causes exclusion. An observed-bar horizon would vary in elapsed time across gaps. | Both conventions exist; runner validates rule equals spec. Candidate convention/value needs approval. |
| Missing data | No fill; exclude if expected candles or exact endpoint are missing; retain exclusion reason. Incomplete right-edge events excluded. | Avoids synthetic prices and outcome-dependent sampling; may reduce sample and induce regularity selection. | `OutcomeRule` supports gap/incomplete policies; synthetic tests cover mechanics. No default is enforced. |
| Event eligibility/time | Later support-zone `touched` event only, origin low label exactly `higher_low` or `lower_low`; touch observed at candle close `available_at`; `C_anchor` is that candle close. | Keeps the intended cohort contrast and avoids look-ahead at pivot time. | `prepare_support_touch_events()` performs causal origin join and eligibility; runner filters by availability. |
| Origin join | `zone_id` plus `pivot_time` to `swing_low_pivot_time`; read `swing_low_structure` only after confirmation availability. Require origin/creation availability <= touch availability. | Identity uses historical pivot; observability uses availability. | Implemented by `prepare_support_touch_events()` and covered synthetically. |
| Feature parameters | Freeze one `left_bars`, `right_bars`, and `zone_width_fraction` before outcomes; use the same values across 4h assets if secondary replication is retained. No parameter search. | Comparability and fewer researcher degrees of freedom. Numeric choices need non-outcome rationale. | Runner requires exactly the three keys, but no scientific values are approved. **Blocker:** values need approval. |
| Repeats/overlap | Retain repeated touches and overlapping zones as separate events; report events, zones and blocks; model dependence. | Dropping events changes the target population; rows are not independent. | Builder retains repeated events; summary reports event/zone counts. No uncertainty method. |
| Chronology | Timestamp-derived UTC 50%/25%/25% development/validation/holdout, half-open windows; assign by `available_at`. | Straightforward chronological allocation; 730 days may be too short after warm-up/exclusions. | `TemporalSplit` validates order; runner stage-bounds data. Boundaries and adequacy not derived. **Blocker:** approve and verify without outcomes. |
| Purge/embargo | Candidate embargo no shorter than nominal outcome horizon, with every included endpoint strictly inside its assigned stage. | Edge exclusion reduces boundary dependence; with missing candles, observed-bar horizons can take longer than nominal elapsed span, so endpoint containment remains decisive. | Runner now enforces embargo >= nominal horizon and stage-bounds OHLCV/outcomes. The proposed magnitude and split are not approved. |
| Comparator/confounding | No matching in primary; report pre-touch prior 24h return, trailing 24h range/volatility, zone age, prior touch count and calendar month; interpret association only. | Higher/lower labels encode different price paths. Descriptors show imbalance but do not remove residual confounding; matching changes the target population. | Runner does not produce these descriptors or adjust. This is an explicit limit; adjusted analysis needs a newly registered estimand. |
| Sample adequacy | Require (a) minimum distinct origin zones and occupied time blocks in each cohort, (b) synthetic simulation validation of interval coverage/error over a declared dependence range, and (c) holdout interval half-width within an approved precision target tied to MME. Failure => defer. | Raw count ignores concentration; no numeric cutoff is justified here. | Runner reports raw events/zones only; no cluster/precision gate. **Blocker.** |
| Uncertainty | No inferential method is implementation-ready. A two-way zone/time procedure may be considered only after its exact algorithm, assumptions, finite-cluster behavior, and synthetic operating characteristics are specified. | A product-weight “crossed bootstrap” is not self-validating: zones span time blocks, events share windows, blocks can be serially dependent, and sparse dimensions can invalidate resampling. | `summarize_event_contrast()` is descriptive only. **Blocker:** no interval estimator will be implemented until an inferential design is defensible and approved. |
| Multiplicity | Exactly one primary confirmatory test: BTCUSD 4h, one event definition, parameter set, 24h outcome and contrast. ETH/SOL and sensitivity analyses are descriptive/exploratory; any inferential secondary family needs approved correction. | Limits winner selection; exploratory results cannot rescue primary result. | `validate_test_family()` checks membership, not correction or exploratory labeling. **Blocker** for secondary inference. |
| Advance/reject/defer | With approved `delta_min>0`: advance if adequate and holdout lower bound > `delta_min`; evidence against practical effect if upper bound < `delta_min`; reject directional H1 only if upper bound <= 0; otherwise inconclusive/defer. | Separates a small positive association from practically meaningful support. Adequacy failure always defers. | `classify_registered_decision()` does not construct intervals or assess adequacy and has no distinct practical-effect category. **Blocker:** approval and implementation. |
| Sensitivity | Prelist only; e.g. one-touch-per-zone and separately reported ETH/SOL 4h; never use to rescue primary. | Checks robustness without post hoc optimization. | No sensitivity governance is enforced by runner. Must be registered before outcomes. |

## Decisions supported by existing implementation contracts

These are mechanical facts, not scientific endorsements:

- `confirmed_swing_points()` uses strict left/right extrema and emits on the
  confirmation row, with the historical pivot timestamp kept separate.
- `confirmed_market_structure()` labels a confirmed low against the preceding
  confirmed low on that side. Initial/equal labels are not higher/lower labels.
- `confirmed_swing_zones()` creates a support zone at confirmation, starts
  lifecycle checks on later candles, retains repeated touches and overlapping
  zones, and gives a close-confirmed break precedence over touch.
- Loader and feature APIs use candle open `timestamp` and declared-timeframe
  close `available_at`; gaps do not redefine duration. Normalized lifecycle
  `event_time` identifies source-candle open, `available_at` its close, and
  `pivot_time` identifies the origin. Zone source rows remain in `payload`.
- The runner verifies the approved `EventStudySpec`, source/data hashes and
  stage before `load_ohlcv_before()` parses OHLCV values. It loads only the
  stage prefix for calculations; timestamp ordering is scanned across the
  full CSV.
- The manifest and runner separate `computation_status=completed` from
  `scientific_status=not_assessed`. Completion is not scientific acceptance.

## Explicit user approval required before evaluation

1. Accept or amend the primary population and exploratory asset designation.
2. Approve numeric swing-window and zone-width settings.
3. Approve the proposed outcome formula, 24-hour horizon, exact endpoint,
   and missing/incomplete-window rules—or specify alternatives.
4. Approve retaining repeated/overlapping events and select the dependence
   estimator, resampling unit/block rule, interval/confidence level, and
   adequate-block criterion.
5. Approve the chronological allocation and exact timestamp boundaries,
   holdout access gate, purge policy, and horizon-linked embargo.
6. Approve the no-matching primary comparison and descriptive confounder
   reporting, or specify a pre-event matching/adjustment plan.
7. Approve minimum sample/effective-block rationale and minimum meaningful
   effect.
8. Approve multiplicity family/correction, and the advance/reject/defer
   criteria.
9. Approve whether sensitivity analyses are descriptive only and their
   finite registered set.

Approval must be explicit and versioned. This file leaves all choices
unresolved; it creates no `EventStudyApproval`, manifest, partition freeze, or
execution authorization.

## Milestone 4E — synthetic dependence stress (not market evidence)

The fixed synthetic design and mechanics are recorded in
`SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md`; reusable code and deterministic
tests are in `dependence_simulation.py` and
`test_dependence_simulation.py`. Results are in the initial default-named V1
report/CSV and separately suffixed V2 report/CSV artifacts. They use generated
event rows only. V1 exposed a
degenerate moving-block interval with five periods; V1 artifacts are retained
unchanged, and V2 adds a four-zone/four-occupied-six-period-block mechanical
support gate. This toy floor is not a real-data adequacy threshold.

Conditional findings (300 synthetic replicates per effect/scenario; Monte
Carlo standard errors are in the V2 CSV):

- Calendar moving blocks failed under persistent repeated zones and unequal
  zone sizes: null coverage was 0.780 (MCSE 0.024) and 0.730 (0.026), with
  false-positive rates 0.220 and 0.270. They also undercovered in the combined
  serial/overlap/shared-shock scenario (0.860, MCSE 0.020). A time-only block
  resampler does not cover persistent within-zone dependence across blocks.
- Zone-cluster resampling was near nominal in several generated cases, but
  did not provide a universal solution: it ignores common calendar shocks by
  construction, and its null coverage was 0.933 (MCSE 0.014) in the combined
  shared-shock scenario. It remains an unapproved candidate, not a pass.
- Product-weight crossed resampling was conservative in these cases (null
  rejection 0.000–0.020; interval coverage 0.980–1.000) and had substantially
  wider intervals and lower power. That does not validate its assumptions or
  establish that it is suitable for the event-weighted estimand.
- IID event resampling behaved acceptably only in the independent baseline;
  it undercovered with repeated zones (0.807), concentrated zone sizes
  (0.790), and serial/shared dependence (0.887). It remains only a negative
  control.
- V2 returned inconclusive for all procedures in the few-zone and few-block
  scenarios. Its support gate reports raw counts and Kish concentration
  summaries; Kish values and interval widths are descriptive. No real-data
  concentration or precision cutoff was selected. Differential cohort
  missingness was generated independently of outcome within each cohort; the
  simulation therefore does not cover outcome-dependent missingness.

No method passes as a generally defensible primary procedure. The synthetic
results reject simple time-only and IID procedures under some declared
dependence structures, but cannot identify actual market dependence or
support an inferential choice. A time-and-zone procedure remains unresolved;
the product-weight candidate is not selected merely because its intervals
were conservative here. User approval is still required for the inferential
sampling assumptions, block rule, adequacy support and precision criteria,
and missingness/exclusion interpretation. The hypothesis remains
**DRAFT — NOT APPROVED FOR EVALUATION**.

### Independent 4F audit closure

The generator's superpopulation contrast is `delta`: it adds the fixed
alternative only to the higher-low cohort while leaving synthetic row
structure, zone/time shocks, event noise, and cohort-specific MCAR missingness
unchanged. AR shocks start without burn-in, and the five-period fixture wraps
six-period windows; both are documented synthetic limitations. Calendar
anchor-block weights do not fully preserve dependence when a future window
crosses a block boundary. Zone bootstrap omits common time-shock variation;
product weights are not presumed to be a valid crossed-cluster method.

V1/V2 omitted invalid-draw fractions from reported metrics. V3 adds those
fractions and separates support-gate from bootstrap-failure inconclusives;
V1/V2 outputs are preserved. All V3 bootstrap draws were finite in the fixed
matrix. The minimum support gate remains only a mechanical floor; concentration
and interval-width thresholds are unapproved. No candidate uncertainty method
is approved or selected. This is an engineering audit outcome, not an
evaluation of SUPPORT_TOUCH_001.

## Remaining implementation blockers

- No dependence-aware confidence interval or effective-block adequacy check.
- No code enforcement for the proposed fixed population, feature values,
  adjustment plan, multiplicity correction, or scientific decision gates.
- The existing bundle verifier validates recorded hashes and artifact
  consistency; it does not authenticate the approver or independently rehash
  current source files. Hash-based local approval is an accidental-misuse
  safeguard, not a tamper-proof security boundary.
- The existing runner is mechanically stage-gated but should not be used on
  project OHLCV until all choices and blockers are resolved and explicitly
  approved.

## Milestone 4B independent challenge

### Estimand and objections

The primary contrast estimates the difference in arithmetic mean 24-hour
close returns across eligible **touch events** in the declared BTCUSD 4h
period, with each event weighted equally. Thus, a frequently touched zone
contributes more than a zone touched once. The population is conditional on a
confirmed support zone being created, later touched, and originating from a
low labeled `higher_low` or `lower_low`. It is an observational association;
it cannot establish causality, incremental information beyond recent trend,
fillability, or trading profitability.

Strongest objections:

- Higher-low/lower-low labels encode different recent price paths. Trend,
  volatility, regime, zone age, touch count, overlap density, and data gaps
  may differ. Recommend no outcome-selected matching in the primary; report
  pre-touch prior 24h return, trailing 24h range/volatility, zone age, prior
  touch count, and calendar month by cohort. These describe imbalance, not
  eliminate confounding. Month stratification is a sensitivity because it
  changes weighting.
- Repeated touches, multiple zones per candle, and shared 24h endpoints make
  rows dependent. Retention is compatible with an event-weighted estimand but
  IID event-level uncertainty is invalid.
- Exact-endpoint/gap exclusions may be informative. Report the eligible
  denominator and outcome exclusions by cohort and calendar period; do not
  impute. No future zone state should affect earlier eligibility.
- Event count can be concentrated in a few zones or periods. A raw count
  alone does not establish independent evidence.
- Horizon, parameters, covariates, gap policy, subgroup and threshold choices
  are researcher degrees of freedom. Freeze them before outcome access and
  retain all exclusions/deviations.

### Candidate uncertainty and adequacy procedure

Recommend a crossed cluster bootstrap for the event-weighted mean difference:
resample origin-zone clusters and contiguous UTC calendar-week blocks,
combine their multiplicity weights for events, and recompute the contrast.
This targets within-zone repeat dependence and common shocks/overlapping
windows within time blocks. It assumes adequate numbers of independent zones
and blocks, limited dependence beyond the selected block length, and a
resampling scheme suitable for this event-weighted estimand. A predeclared
nearby block-length sensitivity should be reported. Few clusters, domination
by one zone/period, sparse cohort support, or unstable results invalidate the
interval; do not fall back to IID errors. Method, block construction/length,
interval level, and synthetic coverage validation require approval; no
estimator is implemented.

Define adequacy before outcomes as all of: (1) each cohort meets approved
minimum distinct-zone and occupied-time-block requirements; (2) synthetic
dependence simulations over a declared range show acceptable interval
coverage and decision error; and (3) the holdout interval half-width meets an
approved precision target tied to the minimum meaningful effect. Numeric
cluster counts, simulation tolerances and target precision remain unresolved.
Failure of any gate means inconclusive/deferred.

### Confirmatory family and decision semantics

The confirmatory family should be exactly one BTCUSD 4h contrast using one
approved event definition, feature parameter set, 24h outcome, and estimand.
ETHUSD/SOLUSD 4h and all stratified, adjusted, or sensitivity analyses remain
descriptive/exploratory; they cannot rescue a failed primary result. Any
secondary inferential family needs pre-outcome approval and multiplicity
correction.

With approved `delta_min > 0`, advance only if adequacy passes and the
untouched holdout interval lower bound is greater than `delta_min`. An
adequate interval upper bound below `delta_min` is evidence against practical
importance; it rejects directional `H1` only when the upper bound is also
`<= 0`. Other intervals or failed gates are inconclusive/deferred. The
interval level, threshold, validation-consistency rule and exact wording need
approval and must be fingerprinted before outcomes.

### Partition, selection and leakage audit

The reviewed code validates unique ordered candle timestamps and exact
declared-close availability. The outcome calculator supports exact endpoints,
counts internal gaps, excludes gaps under the chosen policy, and records an
unavailable endpoint for incomplete windows. Partitioning uses `available_at`
in UTC half-open windows and purges/rejects outcomes whose endpoint is at or
beyond the partition end. The runner excludes configured edge-embargo events
before calculating outcomes and materializes only OHLCV before the requested
stage end.

The code does not derive/freeze 50/25/25 boundaries, require embargo >=
horizon, or enforce a separate holdout release after a locked analysis plan.
One approval can authorize several stages. The loader scans timestamp
metadata across the full CSV for ordering/boundary integrity, although it
does not materialize future OHLCV values. Local Python gates can be bypassed;
they do not prevent an operator from viewing holdout values and changing the
plan. Treat holdout protection as procedural, not a security guarantee.

Initial/equal lows, resistance, creation, breaks, and invalid origins are
predefined exclusions that define this estimand. Missing-outcome exclusions
are potential selection mechanisms and must be reported by cohort/period.
The reviewed causal join uses pivot identity while gating on availability;
no future feature leak was identified in this path. The dominant remaining
risk is confounded interpretation and selection into the touch population.

### Approval items and blockers

Approval is required for primary population and event weighting; feature
parameters; 24h exact endpoint and gap policy; repeated/overlapping event
retention; crossed-cluster method, block length and interval level; adequacy
simulation/precision criteria; split boundaries and separate holdout-release
procedure; horizon-linked embargo; descriptor reporting; multiplicity
family; minimum meaningful effect; and decision rules. Inference remains
blocked until the dependence estimator, adequacy checks, embargo constraint,
and holdout-release governance are resolved. This proposal remains
**DRAFT — NOT APPROVED FOR EVALUATION**.


## Milestone 4C clarification

The former zone × calendar-week bootstrap suggestion is withdrawn as an
implementation recommendation. No crossed resampler has been specified or
validated. Repeated zone observations and time-block shocks create crossed
dependence, while serial dependence may extend across adjacent blocks. The
number and concentration of independent clusters have not been examined from
project event data. Accordingly, no confidence interval or precision gate is
implemented; synthetic tests alone cannot establish empirical coverage.

Ordinary event-study approvals now exclude the holdout stage. Holdout requires
`lock_event_study_plan()` followed by the separate
`authorize_event_study_holdout()` operation. Both bind the spec and approval
fingerprints; the runner revalidates the release and records its hash. This is
a local API safeguard, not access control against direct file or Python access.

### 4C approval decisions still open

Before any real-data outcome calculation, the owner must approve or amend:

1. BTCUSD 4h as the only primary population and ETH/SOL exploratory status.
2. The event-weighted estimand and exact endpoint/gap/incomplete-window rules.
3. Swing/zone feature values and exact chronological boundaries.
4. Repeated/overlapping event retention and a dependence estimator whose
   assumptions fit the observed design; no crossed bootstrap is currently
   selected.
5. Adequacy criteria tied to independent cluster support and uncertainty
   precision, including the simulation plan; raw counts are insufficient.
6. Interval level, multiplicity family, meaningful effect, and immutable
   advance/reject/inconclusive criteria.
7. Whether confounder reporting remains descriptive only or a separately
   defined adjusted estimand is proposed.

The draft fingerprint in `SUPPORT_TOUCH_001_PREREG_DRAFT_V1.json` identifies
only a versioned candidate specification. It does not represent owner
acceptance. Feature parameters, split, statistical rules, thresholds, and
provenance hashes remain unresolved and prevent approval.

## Milestone 4D — current recommendation and approval register

This section supersedes the 4B crossed-bootstrap candidate. The V1 draft
fingerprint is reproducible and still has `approval_status: DRAFT`, no split,
no feature settings, no inference/decision fields, and no data/source hashes.
No approved SUPPORT_TOUCH_001 specification or evaluation record was created.

### Inference-method comparison

| Candidate | Estimand / independent unit | Repeated zones and temporal dependence | Overlapping 24h outcomes | Support/failure conditions | Decision |
|---|---|---|---|---|---|
| Calendar moving-block bootstrap | Event-weighted contrast; contiguous time blocks are resampled units. | Captures common shocks and serial dependence within blocks; a zone spanning blocks is split across replicates. | Captures overlap only when dependent event windows remain together; cross-boundary windows need explicit treatment and sufficiently long blocks. | Enough blocks; weak dependence beyond block length; stable process; block length covers outcome overlap and meaningful serial dependence. Few blocks or long memory fails. | Candidate, insufficient alone for zone repeats. |
| Zone-cluster resampling | Event-weighted contrast; originating zones are resampled units. | Preserves within-zone repeats; misses common market shocks and dependence across zones. | Within-zone overlap is retained; overlap between zones is not. | Adequate independent zones in each cohort; no severe cluster-size domination; cross-zone dependence limited. | Candidate, insufficient alone for temporal dependence. |
| Two-way zone/time-block cluster robust | Event-weighted contrast; zone and time block are dependence dimensions. | Can cover dependence sharing a zone or block under multiway-cluster assumptions. Adjacent-block serial dependence is not automatic. | Events in one block share dependence; windows crossing blocks can remain correlated. | Many informative clusters in both dimensions, defensible block scheme, finite-sample correction; small or imbalanced dimensions may invalidate inference. | Candidate for review, not selected. |
| Product-weight crossed bootstrap | Same only if a specific algorithm has a validity argument. | Product weights do not automatically reproduce crossed dependence. | Cross-boundary overlapping windows are not automatically handled. | Exact scheme, support conditions, simulation coverage/error checks required. | Not recommended as currently specified. |
| IID event bootstrap | Event-weighted contrast; each touch is treated as independent. | Violates repeated-zone and temporal independence assumptions. | Treats overlapping outcomes as independent. | Independence is contradicted by event construction. | Unsuitable. |

Multiway clustering and wild-cluster methods have nontrivial cluster-count
and asymptotic conditions; use of the method name does not show those
conditions are met. References: [Cameron, Gelbach & Miller (2011)](https://cameron.econ.ucdavis.edu/research/JBESpaper2009version.pdf);
[MacKinnon & Webb (2018)](https://econ.queensu.ca/faculty/mackinnon/working-papers/qed_wp_1364.pdf).

**Selection:** do not implement or report inferential intervals yet. Missing
information is the event-level concentration and dependence structure by
zone and time: distinct zones per cohort, zone event counts/lifetimes,
occupied blocks and block imbalance, same-candle/multi-zone events, overlapping
windows including those crossing block edges, and dependence duration across
blocks. These were not computed from project OHLCV. First approve a small
simulation design with plausible dependence structures and error/coverage
tolerances; then choose a method that passes that prospective stress test and
has adequate support in the later study. If none qualifies, the study remains
descriptive/inconclusive.

### Proposed adequacy gate

Keep these quantities separate: raw eligible events; included outcomes and
exclusion reasons; distinct origin zones by cohort; occupied time blocks and
events per block; estimator-specific support/concentration in each dependence
dimension; interval precision relative to an approved `delta_min`. A
Kish-style `(sum w)^2 / sum(w^2)` may describe concentration but is not a
generic count of independent observations. Require both cohorts to meet
preapproved zone and time support, no disallowed concentration, approved
simulation performance, and an interval half-width within the approved
precision target. Any failed or unevaluable gate yields `inconclusive`.
No numeric minimum counts or precision cutoff are set here; justify them by
pre-outcome simulation and scientific relevance, not holdout results.

### Recommended preregistration, pending approval

- Primary estimand: event-weighted arithmetic mean 24h close return for
  higher-low-origin touches minus lower-low-origin touches; observational
  association only.
- Primary family: one BTCUSD 4h contrast. ETHUSD/SOLUSD 4h remain separate
  descriptive/exploratory reports; no pooling and no rescue of the primary.
- Proposed eligibility: later touched support zone, origin swing-low label
  exactly higher_low or lower_low; source origin/creation availability must
  precede or equal touch availability. Anchor at the touch candle close.
- Proposed outcome: exact elapsed 24h close return, with future close
  available exactly at anchor availability + 24h. No fill or nearest-close
  substitution; exclude a missing expected 4h candle, absent endpoint, or
  incomplete right edge and report exclusions by cohort and period.
- Proposed partitions: chronological UTC half-open 50%/25%/25% of declared
  source coverage, internal boundaries snapped to first observed close
  availability at or after the calculated boundary. Record literal boundary
  timestamps before outcomes. Assign by event availability; require full
  outcome containment and purge target availability at or after stage end.
  Candidate 24h edge embargo applies on both sides. These are proposed
  values/rules, not approved split boundaries.
- Confounder diagnostics: prior 24h return/range/volatility end by touch
  candle open; zone age; prior touch count excluding current touch; calendar
  month. No matching/adjustment in the primary. Incomplete/gapped diagnostic
  windows remain missing and are reported, not filled.
- Decision proposal: after the inference and adequacy rules are selected,
  advance only when adequacy passes, validation does not clearly contradict
  the registered direction, and the holdout lower confidence bound exceeds
  approved `delta_min > 0`. Reject directional H1 only when an adequate
  holdout upper bound is `<= 0`. If the upper bound is below `delta_min` but
  above zero, report lack of practical importance without claiming H1
  rejected. All other cases or failed adequacy are inconclusive. Interval
  level, threshold and validation-consistency rule remain unresolved.

### Existing enforcement and remaining decisions

The runner enforces chronological split ordering, nominal embargo >= nominal
horizon, stage-bounded OHLCV materialization, endpoint containment, a separate
plan-lock then holdout-release sequence, and fingerprint rejection after plan
changes. The event builder enforces causal origin/zone availability. These do
not choose the dates, estimator, support thresholds or scientific criteria.
The local API is not a security boundary; holdout files can be read outside it.

Approval is still required for scope, feature settings, horizon/gaps,
repetition/overlap, split boundaries and embargo, inference method and
simulation design, adequacy thresholds, confounder reporting, multiplicity,
minimum effect, and decision rules. No estimator or adequacy gate is
implemented. No outcomes or labels were calculated, and the hypothesis stays
**DRAFT — NOT APPROVED FOR EVALUATION**.
