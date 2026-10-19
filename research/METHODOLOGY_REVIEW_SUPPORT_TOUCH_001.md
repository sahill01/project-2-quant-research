# Methodology review — HYP-SUPPORT-TOUCH-001

> **Implementation status:** the event-study contract and mechanical cohort,
> outcome, partition, and descriptive-summary utilities are present in
> `event_study.py`; `event_study_runner.py` now provides approved-stage,
> stage-bounded orchestration and a verified output bundle. Synthetic tests
> are in `test_event_study.py`. This review remains a proposal. The outcome
> formula and every scientific decision below remain unapproved; no
> project-data outcomes were calculated.

> **DRAFT — NOT APPROVED FOR EVALUATION**
>
> This is a methodology proposal for review. It does not authorize outcome
> calculation, an experiment, signal implementation, or strategy research.
> No forward returns, labels, or predictive results were calculated in
> preparing it.

## 1. Hypothesis and proposed outcome

**Question.** Among later touches of confirmed support zones, is the future
close-to-close return higher when the zone originated from a confirmed
`higher_low` than when it originated from a confirmed `lower_low`?

Let `Y_H` denote the outcome at a future horizon `H`, not yet selected. The
candidate directional hypothesis is

`H1: E[Y_H | higher_low-origin support touch] - E[Y_H | lower_low-origin support touch] > 0`.

The null is

`H0: E[Y_H | higher_low-origin support touch] - E[Y_H | lower_low-origin support touch] <= 0`.

**Proposed outcome measure, awaiting user approval:**

`Y_H = (C_future / C_anchor) - 1`.

`C_anchor` is the close of the candle on which the support-zone touch becomes
observable, at that candle's `available_at`. `C_future` is the close selected
by a still-unresolved horizon and sampling rule. No numeric horizon or close
selection is specified here. This is a feature-event outcome, not a position
return, trade P&L, or strategy result. It does not model fees, slippage, or
whether an intrabar touch was fillable.

**Proposed comparator.** Later touches of support zones whose originating
confirmed swing low has `swing_low_structure == "lower_low"`. The exposed
cohort is support-zone `touched` events from `higher_low` origins. Both
cohorts exclude initial/equal lows, resistance zones, creation events, and
same-candle broken events. The comparator is plausible but not established
as adequate: structure labels may correspond to different market regimes,
calendar periods, volatility, or zone ages. Matching/control selection is
unresolved.

The proposal is intentionally limited to one structure-conditioned support
touch contrast. It does not combine other feature families or define entries,
exits, stops, leverage, position sizing, or a trading strategy.

## 2. Population, eligibility, and causal join

The candidate local population is the 12 available asset/timeframe files:
BTCUSD, ETHUSD, and SOLUSD at 15m, 1h, 4h, and 1d. Each asset/timeframe is
identifiable in the data. Whether the formal primary family is all 12,
selected predeclared strata, or a narrower set is unresolved. Results must
not be pooled across assets or timeframes without an approved aggregation
plan. The local span is about 730 days and has not been shown to provide
adequate independent events or validation history.

An eligible event requires all of the following:

1. `confirmed_market_structure()` reports a swing low and labels it
   `higher_low` or `lower_low` against the previous confirmed low.
2. `confirmed_swing_zones()` creates a support zone from that confirmed low.
3. On a later observed candle, that same zone emits `event == "touched"`.
   The zone implementation checks close-confirmed breaks first, so a break
   on that candle takes precedence and is not a touch.
4. The event is assigned to a cohort using only the origin structure label
   that was available by the touch close.

The zone origin is identified by its `zone_id` and `pivot_time`. Join that
origin to the source structure row using
`zone.pivot_time == structure.swing_low_pivot_time`, then read
`structure.swing_low_structure`. The historical `pivot_time` is a join key,
not an observation timestamp. Enforce that structure confirmation and zone
creation availability are no later than the touch availability. Do not join
using future zone state or event outcome.

### Timestamp contract

- Loader `timestamp`: candle open.
- Loader `available_at`: candle close, computed from the declared timeframe;
  the explicit duration is used even when candles are missing.
- Normalized event `event_time`: open of the event anchor candle. For a zone
  lifecycle event this is the touch/break candle, not the zone origin candle.
- Normalized event `available_at`: close when the event's required
  information is complete. A touch is only observable at the touch candle
  close.
- `pivot_time`: historical originating swing candle open. It does not imply
  that the swing was known then.
- `formation_time`: candlestick/chart-pattern geometry timestamp; null for
  structure and zone lifecycle events.
- Zone source-layer payload: preserves the original row, where source
  `event_time` is the lifecycle candle close. The normalized event maps its
  event anchor to the candle open while retaining the source row in `payload`.

The earliest eligible observation anchor for the touch cohort and its origin
label together is the touch candle's close (`available_at`). OHLC proves only
that the candle range intersected the zone; it cannot establish the
intracandle touch time or ordering. Future candles may be consulted only for
the outcome after event eligibility and cohort assignment are frozen.

## 3. Horizon and gaps — unresolved

The return formula is proposed, but `H` and the rule for selecting
`C_future` require approval. Candidate conventions:

| Convention | Possible definition | Benefit | Cost / decision required |
|---|---|---|---|
| Fixed observed-bar count | Select a close a fixed number of observed candles after the touch candle. | Same observation count within a timeframe; gaps do not create synthetic rows. | Elapsed duration changes across gaps, and the same bar count means different clock durations across timeframes. Decide treatment when the dataset ends before the count is reached. |
| Fixed elapsed-time horizon | Target `touch available_at + H` elapsed time. | Same intended clock duration across timeframes. | A close may not exist exactly at target. Must choose prior eligible close, first close after target, nearest close subject to a tolerance, or event exclusion; these change realized duration and may create selection. |

The exact close-selection convention is a methodological requirement, not an
implementation detail. It must not use the observed return to choose a close.
Choose a horizon from a stated research timescale before outcome access; do
not select whichever horizon gives the strongest observed contrast. No
horizon value or sampling option is selected in this document.

Missing-candle policy is a separate unresolved requirement. It must cover
gaps between event availability and target, gaps within a future window,
events near the sample boundary, and whether target selection can cross a
long gap. Options include: retain events under a declared observed-bar rule;
exclude events whose elapsed-time target lacks an eligible close; or treat
them as censored under a separately specified method. Forward-filling is not
supported by the feature contract and would fabricate observations. No gap
threshold or policy is selected.

## 4. Decisions required before approval

Every item marked **Required** below must be resolved and frozen before
outcome computation. Options are alternatives for user review, not
recommendations selected by this draft.

| Decision | Status and options/trade-offs |
|---|---|
| Primary asset/timeframe family and aggregation | **Required.** Candidate family is 3 assets × 4 timeframes. Analyze each stratum separately, choose a predeclared subset, or define a pooled estimand with asset/timeframe effects. Broad coverage reduces cherry-picking but raises multiplicity and dependence; narrowing reduces tests but can create selection bias unless justified without outcomes. |
| Swing and zone parameters | **Required.** Freeze `left_bars`, `right_bars`, and `zone_width_fraction` for every selected timeframe. A single configuration aids comparability; timeframe-specific settings may better reflect sampling scale but add researcher degrees of freedom. Values must be chosen without inspecting this study's outcomes. Sensitivity variants are optional robustness checks and count toward multiplicity if interpreted inferentially. |
| Candidate outcome, horizon, and close selection | **Required.** Approve the forward close-to-close return formula and one or more horizons, plus observed-bar versus elapsed-time convention and exact target-close sampling. Multiple horizons can answer scale questions but expand the test family. |
| Missing-candle and sample-boundary policy | **Required.** Predeclare how internal gaps, target gaps, and right-censored events are retained, excluded, or treated. Exclusion is simple but may select a nonrepresentative subset; a censoring model adds assumptions. Do not fill candles. |
| Overlapping and repeated events | **Required.** Options include retain all with zone/time-clustered uncertainty; retain one touch per zone under a predeclared reset rule; decluster nearby events; or remove overlapping outcome windows. Keeping all uses more observations but requires dependence-aware inference. Exclusion reduces dependence but changes the target population and can discard overlapping-zone information. Define simultaneous touches and repeated touches in advance. |
| Chronological development, validation, and holdout windows | **Required.** Specify UTC half-open boundaries `[start, end)`, use availability time for event assignment, keep holdout later and untouched, and define treatment of outcome windows crossing boundaries (e.g. exclude/censor). A larger development period leaves less validation/holdout data; arbitrary proportions do not guarantee adequate history. Existing 730-day coverage may be insufficient for meaningful three-way separation. |
| Comparator adequacy and matching/control selection | **Required.** The proposed lower-low-origin touch cohort is simple and feature-specific. Decide whether it alone answers the contrast, whether to compare within asset/timeframe/period strata, or whether to match on pre-event factors available at the touch close (such as zone age or trailing volatility). Matching may reduce observed confounding but requires covariate definitions, calipers/weights, balance checks, and can reduce sample size; it cannot remove unmeasured confounding. A no-event cohort is a different estimand, not an automatic substitute. |
| Confounders and estimand scope | **Required.** Predeclare handling or reporting for asset, timeframe, calendar period/regime, broad trend, volatility, zone age and width, price proximity, prior touches, overlap, and swing/zone parameters. Existing OHLCV-derived candidates include trailing range/ATR percentage, realized volatility, and relative volume; these are liquidity/volatility proxies, not direct spread, depth, or executable liquidity. Decide whether the target is within-stratum association or a cross-stratum average. This remains observational and cannot establish causality. |
| Minimum sample requirement and rationale | **Required.** Set minimum eligible events in each cohort and relevant stratum, a balance/common-support rule, and whether raw event count or effective independent count matters. Options include precision-based interval width, power for a user-approved meaningful effect, or a feasibility threshold with explicit inconclusive classification. Counts selected after seeing outcomes are unacceptable; no number is proposed. |
| Uncertainty method | **Required.** Choose an interval/test for the mean contrast and account for repeated zones, shared future candles, serial dependence, and asset/timeframe strata. Cluster/bootstrap blocks, dependence-robust estimators, or a prespecified randomization method have different assumptions and small-sample behavior. The procedure and confidence level/decision interpretation need approval; none is chosen. |
| Multiple-testing family and interpretation | **Required.** Define which assets, timeframes, horizons, outcomes, parameter variants, subgroups, and robustness checks belong to the confirmatory family. Options include one primary contrast with family-wise control for secondary contrasts, hierarchical testing, or false-discovery control for explicitly exploratory families. More protection can reduce power; unadjusted parallel claims inflate false-positive risk. Keep all tested variants and null results in provenance/logs. |
| Meaningful effect-size threshold | **Required.** Choose a minimum effect of interest in return units or another approved scale, and distinguish it from the zero-effect null and statistical uncertainty. A purely directional test may identify a negligible difference. No threshold is inferred from historical results or chosen here. |
| Advance / reject / defer criteria | **Required.** Define in advance how direction, uncertainty, effect-size criterion, sample sufficiency, validation replication, multiplicity, data-quality failures, and holdout results map to each decision. Advance can require consistent development/validation evidence; reject can follow an adequately precise null/opposite result; defer can cover insufficient sample or unresolved data quality. Exact logic and holdout role remain for approval. |

### Optional robustness checks (not substitutes for required decisions)

After the primary configuration and family are frozen, possible secondary
checks include: reasonable predeclared zone-width or swing-window variants;
alternative dependence-aware uncertainty methods; per-asset/timeframe
heterogeneity; alternative but causally valid horizon conventions; placebo
anchors; and sensitivity to one-touch-per-zone versus all-touch handling.
Each check must be labelled exploratory or included in the multiplicity plan
before outcomes are viewed. These do not authorize parameter selection or
winner-picking.

## 5. Proposal, approval, execution, and reporting are separate gates

1. **Proposal (current stage):** document the estimand, event, feature timing,
   alternatives, and unresolved decisions. No outcomes are calculated.
2. **Approval:** the user reviews and resolves every required methodological
   choice and explicitly approves a frozen specification. Approval must not
   be inferred from a draft being complete or internally consistent.
3. **Execution:** only after approval, an implementation may compute events
   and outcomes under the frozen choices, preserve development/validation/
   holdout separation, and produce no-clobber artifacts. Any change to the
   choices creates a new version and may invalidate holdout independence.
4. **Reporting:** report cohort construction/exclusions, counts, estimates,
   uncertainty, multiplicity, gaps/overlap, provenance, limitations, and all
   rejected or inconclusive results. Do not turn an event-study association
   into a strategy or profitability claim.

## 6. Existing protocol fit and safeguard limits

`HypothesisSpec` and `ResearchDecisions` can record a hypothesis and block an
approval record while decision fields remain unresolved. The approval
factory requires an approved config and hypothesis, resolved decisions,
approver text/time, and hashes of data and implementation inputs. The
experiment protocol can fingerprint configurations, freeze chronological
partitions, record artifacts, and verify recorded paths/hashes. These are
useful local provenance and accidental-use controls.

The strategy-oriented experiment protocol still has a schema mismatch for
this proposed descriptive event study:
`ExperimentConfig` requires a `strategy` and nonempty `execution` settings,
while `HypothesisSpec` requires signal, entry/exit, and transaction-cost
fields. Those fields are strategy-oriented and do not naturally represent a
feature-only event study. A separate `EventStudySpec` and synthetic-tested
runner now define that contract, so no fields are filled with invented
trading assumptions. The runner enforces the support-touch event and outcome
semantics it implements; it does not implement inferential analysis or resolve
scientific approval choices.

These safeguards are not tamper-proof or an identity/security boundary.
Approver identity and approval text are local caller-supplied assertions;
Python callers or repository users can bypass or alter local files. Hashes
detect byte changes relative to captured values but do not prove who created
an input, that it was derived causally, or that it was unchanged before its
first hash. Manifest verification checks recorded artifact integrity and
structure; it does not validate scientific design, event correctness, or
prevent deliberate bypass. The existing protocol does not constitute
scientific approval.

## 7. Current limits and approval checklist

Current feature APIs can emit the necessary confirmed swing labels and later
zone lifecycle events with causal availability. Synthetic tests exercise
timing and lifecycle mechanics. This supports implementation feasibility,
not predictive sufficiency. No event counts, forward returns, outcome labels,
effect sizes, or predictive metrics were inspected or calculated for this
proposal.

Before any evaluation, user approval is required for:

1. Outcome formula and future-close rule (the formula above is only proposed).
2. Horizon value(s) and observed-bar versus elapsed-time convention.
3. Missing-candle and endpoint/censoring policy.
4. Event overlap and repeated-touch policy.
5. Primary asset/timeframe family and aggregation.
6. Swing-window and zone-width parameters.
7. Comparator adequacy, matching/control method, and pre-event covariates.
8. Chronological UTC development, validation, and untouched holdout windows.
9. Confounder/stratification plan and estimand scope.
10. Minimum sample rationale and thresholds.
11. Uncertainty method and interpretation.
12. Multiple-testing family and correction/interpretation.
13. Meaningful effect-size threshold.
14. Advance/reject/defer rules.
15. The feature-only `EventStudySpec`/runner contract is implemented and
    synthetically tested; this engineering choice is complete and does not
    require scientific approval.

No approval status, approval record, frozen holdout, experiment manifest, or
evaluation is created by this review.

## 8. Recommended defaults for review (none approved)

These recommendations are intended to make the next review concrete. Each
remains **unresolved** until the user explicitly accepts or amends it. They
are not grounds to calculate outcomes.

| Topic | Recommended default (not approved) | Rationale and alternative |
|---|---|---|
| Outcome and horizon | Retain the proposed `Y_H` endpoint-return definition and use one fixed elapsed-time horizon, with `C_anchor` the touch-candle close and `C_future` the first observed close at or after the target, subject to a predeclared maximum lateness. The maximum lateness and horizon value remain unset. | An elapsed horizon is more comparable across sampling frequencies. Fixed observed bars is simpler and avoids target sampling but spans different clock durations across assets/timeframes and gaps. If no close meets the lateness rule, exclude/censor under a frozen rule; never select the close by return. |
| Event multiplicity | Keep the stated touch-event population, but retain a `zone_id` and anchor timestamp on every row and use dependence-aware uncertainty clustered by zone and common time blocks; report the number of unique zones separately from touch rows. | First-touch-only would reduce repeated events but change the question to first retests. Treating all rows as independent would overstate precision. Simultaneous overlapping-zone touches still require an explicit clustered/deduplication policy. |
| Comparator/confounding | Use the lower-low cohort as the sole primary comparator; calculate the contrast within predeclared asset/timeframe strata and report heterogeneity. Do not match in the first study. | Matching may improve balance on measured, available covariates but increases modeling choices and can discard events. Stratification is interpretable but cannot remove unmeasured confounding; call the result an association. |
| Dataset family | Use the three assets at 4h as the candidate primary family, preserve asset-specific contrasts, and define one across-asset summary before outcomes. Treat 15m/1h/1d as optional, predeclared robustness families. | 4h aligns with the existing cross-asset baseline setup and limits the first test family. A broader 12-cell family gives more coverage but raises multiplicity and cross-timeframe dependence. This recommendation is based on study manageability, not performance. The aggregation (equal-weighted asset contrasts versus a stratified model) still needs approval. |
| Missing and invalid observations | Do not forward-fill. Rely on loader rejection of malformed, non-finite, duplicate, unordered, and timeframe-inconsistent rows. Under an elapsed horizon, retain only events with an eligible target close within the approved lateness rule; report all exclusions and reasons. | Existing validation covers input candle integrity, not event-study treatment of an otherwise valid gap or incomplete outcome window. A stricter internal-gap exclusion is possible but changes the included population and must be justified in advance. |
| Temporal evaluation | Treat the current 730-day history as exploratory/development evidence only. For confirmatory evidence, acquire/validate a longer chronological sample, assign events by `available_at`, and keep a later untouched holdout. Purge any event whose outcome window crosses a split boundary; add an embargo at least as long as the maximum outcome window if dependence/overlap calls for it. | A three-way split inside a short two-year span can leave weak samples and an unconvincing holdout. Exact boundaries and embargo duration cannot be set until the horizon is approved and the available history is established. |
| Sample sufficiency | Base the minimum on precision/power for a user-approved minimum meaningful contrast and the effective, dependence-adjusted sample, not raw touch count. If variance/effect assumptions cannot be justified independently, classify the first local study as descriptive/exploratory and defer confirmatory claims. | A fixed event-count rule alone is not a power justification. Historical pilot variance may itself be outcome access and must not be used to revise the same study's threshold after unblinding. |
| Uncertainty | Candidate default: resample contiguous calendar blocks jointly across assets, retaining all events in each block, and account for zone-level repetition; assess whether a two-way cluster/block method is supportable before preregistration. Freeze block construction and interval/test interpretation before outcomes. | Naive IID intervals are not appropriate for serially dependent and overlapping event windows. Cluster/bootstrap methods can be unstable with few effective blocks; the exact method and minimum block support remain unresolved. |
| Multiple testing | Define one primary contrast and one horizon for the primary 4h family; treat asset-specific contrasts, other timeframes, alternate horizons, and parameter variants as secondary. Use a predeclared family-wise procedure for confirmatory secondary claims; label other checks exploratory. | A small primary family improves interpretability; wider coverage raises multiplicity. The test family, correction, and error-rate interpretation still require user approval. |
| Effect and decisions | Set a nonzero minimum meaningful difference before any outcomes, separate from the zero-effect null. Advance only if the approved effect and uncertainty criteria pass in development and validation and the untouched holdout is consistent; reject only under a sufficiently precise approved rule; otherwise defer/inconclusive. | No numerical threshold, confidence level, or decision rule can be derived without a substantive decision and sample assumptions. Do not use this event-study association as a trading or profitability gate. |

## 9. Independent methodological red-team

No fatal code-contract contradiction prevents forming the proposed cohorts,
but the following risks would invalidate or materially weaken an evaluation
if left unresolved:

| Severity | Risk | Resolution before evaluation |
|---|---|---|
| **Major** | **Pseudoreplication:** repeated touches of one zone, overlapping zones on one candle, and shared future windows are not independent observations. Naive standard errors can be severely optimistic. | Approve an event-retention rule and dependence-aware inference; report unique zones, anchors, and effective blocks. Validate the method synthetically and on simulated dependence before using observed outcomes. |
| **Major** | **Confounding / over-interpretation:** higher-low and lower-low zones can arise in different trends, volatility states, periods, and zone ages. The two-cohort contrast is observational, not causal. | Predeclare the estimand, stratification or limited adjustment, covariates known at touch availability, and cautious associative wording. Do not claim that structure causes returns. |
| **Major** | **Outcome/split leakage:** pivot time predates confirmation; selecting features at pivot time, using final zone state, or allowing a forward window to cross into validation/holdout leaks information. | Join on origin identity but enforce structure/creation `available_at <= touch available_at`; use as-of zone state; assign by touch availability; purge/censor split-crossing outcomes and freeze holdout. |
| **Major** | **Short and repeated historical sample:** 730 days across crypto may provide few independent regime episodes, especially after stratification and overlap control. Three chronological partitions could be inadequate. | Establish event and effective-block counts only after an approved feasibility gate. If precision/power cannot be supported, defer confirmation and seek longer independent history; do not collapse strata post hoc. |
| **Major** | **Researcher degrees of freedom:** 12 asset/timeframe cells, horizons, swing/zone settings, matching, exclusions, and outcome summaries can produce a selected result. | Freeze a primary family, horizon, parameters, exclusions, and multiplicity plan before outcome access; version every deviation; report null and exploratory results. |
| **Minor** | **Candle-level touch is not an executable fill:** wick intersection has no intrabar order or fill guarantee, and close-to-close outcome starts at the event candle close. | Keep interpretation strictly descriptive. Any later strategy question requires a separate approved execution-aware hypothesis and cost model. |
| **Minor** | **Separate protocol schemas:** current `HypothesisSpec`/`ExperimentConfig` and metrics remain strategy-oriented, while this study uses event cohorts. | The separate `EventStudySpec` and event-study runner address the schema mismatch; do not insert fake strategy values or treat the runner as scientific approval. |

The study can estimate a descriptive conditional return contrast if its cohort,
target close, dependence, comparison, and split rules are fixed. In its
current form it cannot support a causal claim or a claim of tradability,
profitability after costs, or strategy performance.

## 10. Milestone 4A preregistration recommendation

This section proposes defaults for explicit review; none is an approval. It
preserves the directional contrast and lower-low comparator above.

### Recommended primary design

Use **BTCUSD 4h** as the only primary asset/timeframe. Keep ETHUSD 4h and
SOLUSD 4h as separately reported exploratory replications. Do not pool
assets, include other timeframes, or use those secondary results to promote
the primary hypothesis. One primary contrast limits multiplicity and avoids
assuming identical event populations across assets. It sacrifices breadth
and may produce inadequate independent evidence; the available history has
not been assessed for cohort size or power.

The event is every later source-layer `touched` event for a `support` zone
whose originating confirmed low is labeled `higher_low` or `lower_low`.
Exclude other zone/event types, initial/equal lows, unjoinable origins, and
touch candles where a break takes precedence. Preserve repeated touches,
overlapping zones, and simultaneous zone events as distinct rows. The event
becomes observable at the touch candle's `available_at`; `C_anchor` is the
touch candle close. Zone identity and origin `pivot_time` join the event to
the confirmed structure row's `swing_low_pivot_time`; read its
`swing_low_structure` label only if its confirmation `available_at` and zone
`created_at` are no later than touch availability. Never join on pivot time
as if it were availability.

Candidate outcome for approval:

`Y_24h = (C_future / C_anchor) - 1`

where `C_future` is the close exactly 24 elapsed hours after the touch close.
Recommend an exact endpoint and no forward fill or nearby-close substitution.
If the exact endpoint is absent, or any expected 4h bar between anchor and
endpoint is missing, exclude that outcome with a reason; exclude incomplete
right-edge windows. The horizon is six 4h bars only on a complete regular
grid. This is not an execution return. Twenty-four hours is a design proposal
chosen for a short, interpretable one-day response window, not empirical
evidence. A fixed observed-bar alternative has more stable bar count but
variable elapsed time over gaps; an elapsed-time endpoint preserves clock
duration but creates exclusions if exact closes are unavailable. User
approval is required for this horizon and endpoint policy.

### Decision-by-decision recommendations

| Decision | Recommended default | Rationale and failure mode | Existing enforcement / approval status |
|---|---|---|---|
| Event/cohort | Later support `touched`, origin low label exactly `higher_low` or `lower_low`; lower-low is the comparator. | Preserves the registered contrast; excluding unconfirmed or equal/initial origins avoids ambiguous cohorts. Misjoining by pivot time leaks unconfirmed labels. | `prepare_support_touch_events()` constructs this ledger and checks causal availability. The selected event definition still requires approval. |
| Observable time | Touch candle close, i.e. source `available_at`; anchor at that close. | A wick intersection has no intrabar timestamp in OHLC. Using candle open or pivot time would be premature. | Loader/features validate close availability; event builder emits availability. Runner filters by `available_at`. |
| Outcome/horizon | Forward close return at exactly 24 elapsed hours. | Interpretable one-day horizon; no data-driven horizon selection. | Formula/horizon mechanics exist in `OutcomeRule` and `calculate_forward_close_outcomes`; no scientific default is enforced. |
| Endpoint/gaps | Exact endpoint, no fill/substitution; exclude if endpoint or any expected 4h candle is missing; report exclusions. | Avoids variable exposure duration and return-dependent sampling; reduces sample and can select regular-market periods. | Outcome calculator supports exact endpoints and `exclude_if_gap`; tests use synthetic gaps. The proposed rule is not approved. |
| Incomplete window | Exclude an event if endpoint is not inside the authorized window or available sample. | Avoids right-censoring being confused with zero/negative outcome. | Calculator/runner record endpoint exclusions and purge stage crossings. |
| Repetition/overlap | Retain repeated zone touches and simultaneous overlapping-zone events, preserve zone IDs, do not assume independent rows. | Dropping events changes the estimand; retaining them requires dependence-aware uncertainty. | Cohort builder retains events; summary reports event/zone counts. No dependence estimator exists. |
| Scope | BTCUSD 4h primary; ETHUSD/SOLUSD 4h exploratory, separate; no pooling or extra timeframes. | Minimizes primary multiplicity and avoids exchangeability assumptions; costs generality. | Scope is recorded in `EventStudySpec`; runner requires exact scoped file identities. Scientific scope is not selected by code. |
| Feature settings | Recommend freeze one `left_bars`, `right_bars`, and zone-width value before any outcomes; do not search. Use a single common setting across 4h assets if secondary replication proceeds. | Parameter search invites researcher degrees of freedom; one setting aids comparability. Numeric values need an engineering rationale and approval. | Runner requires exactly these registered parameter keys; values are supplied by spec, not defaulted by code. **Blocker:** values are not finalized. |
| Chronology | Recommend 50%/25%/25% of timestamp coverage for development/validation/untouched holdout, fixed from timestamps only. | Supports chronological separation; at ~730 days each partition and warm-up may be too short. | `TemporalSplit` enforces ordered UTC windows; runner stage-bounds input. It does not derive boundaries or establish adequacy. **Blocker:** exact boundaries require approval. |
| Purge/embargo | Purge targets at or beyond partition end; embargo at least the approved horizon on both sides. | Prevents outcome windows and nearby dependent events crossing boundaries. Longer embargo reduces usable events. | Partition code supports purge/error and a configured embargo. It does not require embargo >= horizon. **Blocker:** relationship/rule needs approval and validation. |
| Confounding/control | Keep the lower-low cohort as sole primary comparator; no matching in primary; report stratified cohort characteristics known at touch time. | Matching adds model/selection choices and can reduce support; unadjusted contrast remains observational and confounded by trend, volatility, period, age, geometry and liquidity. | Current estimand is an unadjusted mean contrast. No matching or adjustment implementation. Interpretation must remain associational. |
| Sample adequacy | Require evidence planned against precision/power for the approved minimum effect and effective calendar blocks, not raw event count alone. Defer if inadequate. | Many touches can be concentrated in a few zones or periods. No universal numeric count can be responsibly inferred without effect/uncertainty assumptions. | Runner reports raw event/zone counts only; no power or adequacy gate. **Blocker:** rationale and thresholds require approval. |
| Estimation/uncertainty | Mean difference; recommend calendar-block bootstrap interval with all events in sampled blocks retained; report zone concentration and block coverage. | Preserves temporal clustering better than IID row bootstrap, but block length, resampling unit, and small-block behavior matter. | `summarize_event_contrast()` is descriptive only. No interval, cluster estimator, or bootstrap is implemented. **Engineering blocker** before inferential claims. |
| Multiplicity | One primary contrast/outcome/horizon. Treat all other asset, timeframe, horizon, parameter and subgroup analyses as exploratory; if inferential, register one family and apply a prespecified correction. | Avoids choosing among many variants. Even a single primary may be compromised if informal repeated looks are untracked. | `validate_test_family()` checks IDs against a supplied family only; no correction procedure is implemented. **Blocker:** family and criterion require approval. |
| Effect/decision | Advance only if holdout interval lower bound exceeds a positive approved minimum effect and evidence/data gates pass; reject direction only if upper bound <= 0 under adequate evidence; otherwise defer/inconclusive. | Directional significance alone may be practically negligible; failure to reject is not proof of no effect. | `classify_registered_decision()` accepts caller-supplied bounds/counts but is not an inferential method. No threshold, confidence level, or adequate-evidence rule exists. **Blocker:** approve values/rules and implement interval first. |
| Sensitivity | After the primary specification is frozen, test only prelisted alternatives (e.g. one-touch-per-zone, alternative gap policy, and 4h ETH/SOL); label exploratory. | Reveals fragility but can become implicit optimization if used to select a winner. | No sensitivity runner or multiplicity interpretation enforces this separation. Must be registered before outcomes. |

### Stage separation and approval boundary

1. **Proposal:** this document and the companion decision register describe
   recommendations and trade-offs. They cannot create authorization.
2. **Approval:** the owner explicitly accepts/amends the required choices;
   the full `EventStudySpec` is resolved and reviewed. No approval record is
   created while this draft remains unapproved or blockers remain.
3. **Execution:** only a separately authorized stage may run after approval;
   development, validation, and holdout are kept distinct, and holdout is not
   opened during design or tuning.
4. **Reporting:** computation completion is mechanical. Scientific
   interpretation, uncertainty, rejection/deferral, and claim limits are a
   separate review. The local hashes and Python guards reduce accidental
   misuse; they are not tamper-proof or a process-isolation boundary.

The exact code mapping and distinction between implementation contracts,
proposed defaults, approval decisions, and engineering blockers is recorded in
[`DECISION_REGISTER_SUPPORT_TOUCH_001.md`](DECISION_REGISTER_SUPPORT_TOUCH_001.md).

## 11. Milestone 4B independent challenge

### Estimand and strongest objections

Under the proposed BTCUSD 4h population and event rule, the unadjusted
contrast estimates the **difference between the arithmetic mean 24-hour
close returns across eligible touch events** whose origin labels are
`higher_low` and `lower_low`, during the declared observation period and
under the declared endpoint-completeness rule. It is event-weighted: every
touch contributes one row, so a zone with many touches has more weight than a
zone with one touch. It is conditional on a confirmed support zone being
created, surviving to a later touch, and having one of the two selected
labels.

This can establish an observed conditional association for that event
population if the sampling, missingness, and uncertainty rules are adequate.
It cannot establish that the swing label caused the return, that the label
adds information beyond recent trend/volatility, that all support zones or
assets behave similarly, that a wick touch could be executed, or that a
strategy earns a net return. Conditioning on zone creation and later touch
also selects a subset of market paths; the conclusion does not generalize to
all swing lows or all times.

Strongest objections and disposition:

1. **Cohort comparability:** higher-low and lower-low origins encode different
   recent price paths by definition. Their touch events may also differ in
   trend, volatility, calendar regime, zone age, width, prior touch count,
   and overlapping-zone density. This does not invalidate the descriptive
   contrast, but it invalidates a causal or incremental-predictive reading.
   Minimal primary plan: no outcome-selected matching; report pre-touch
   characteristics by cohort within the primary BTCUSD 4h sample, including
   prior 24h return, trailing 24h realized volatility/range, zone age, prior
   touch count, and month. These are measured only through touch close.
   Add a prespecified month-stratified contrast only as a sensitivity because
   it changes the target weighting and can lose common support. No such
   covariates or stratified estimate is currently produced by the runner.
2. **Touch-weighting and overlap:** repeated touches, multiple zones touched
   on one candle, and shared 24h endpoints create clustered observations.
   The stated mean difference weights each event equally, not each zone or
   time period equally. Retaining all touches is coherent with an event-level
   estimand, but naive event-level IID uncertainty is invalid.
3. **Outcome missingness:** exact endpoint and gap exclusions can be
   informative. Missing candles may cluster in volatile periods or at
   operational/data boundaries. Report the eligible event denominator,
   outcome inclusion/exclusion reason, cohort and period for exclusions, and
   compare inclusion rates using pre-event fields. Do not impute outcomes.
4. **Short and clustered sample:** nominal touch count is not independent
   evidence. A large count concentrated in a few zones or calendar periods
   cannot support a precise generalization. The current data span and number
   of independent clusters have not been assessed for outcomes or power.
5. **Researcher degrees of freedom:** horizon, feature parameters, assets,
   missingness, matching, strata, uncertainty, and decision thresholds can
   all select a result. Freeze one primary family and analysis before outcome
   access; retain all exclusions and deviations. Do not use validation or
   holdout to tune the design.

### Proposed dependence-aware uncertainty and adequacy

Candidate inference is a **crossed cluster bootstrap** for the event-weighted
mean difference: resample originating `zone_id` clusters and contiguous UTC
calendar-time blocks, form event weights from the two resampling multiplicity
vectors, and recompute the difference for each replicate. Contiguous blocks
must be longer than the 24-hour overlapping outcome window; propose a
predeclared calendar-week block as an initial candidate, while acknowledging
that week length may not capture longer market dependence. This preserves
within-zone repeated-touch dependence and common market shocks within sampled
time blocks better than IID event resampling. The interval method, block
length, boundary treatment, resample count, and confidence level still need
approval and synthetic operating-characteristic validation.

Assumptions/failure conditions: enough distinct zones and time blocks in
both cohorts; dependence is adequately represented by zone and time
clustering; dependence across time blocks is limited at the chosen block
scale; and the resampling scheme is valid for the event-weighted estimand.
If clusters are few, one zone or period dominates, cohort support is sparse,
or conclusions change materially under modest predeclared block-length
sensitivity, the interval is unreliable and the result is **inconclusive**.
No IID standard error or test is an acceptable fallback.

Define evidence adequacy before outcomes as a conjunction, not a raw event
count: (a) each cohort meets a minimum number of distinct origin zones and
occupied time blocks; (b) an approved synthetic simulation study shows the
chosen interval has acceptable coverage and decision error over a declared
range of cluster/dependence structures; and (c) the holdout interval half
width is no greater than a preapproved precision target tied to the minimum
meaningful effect. The minimum cluster counts, simulation assumptions,
coverage/error tolerances, and precision target require approval; absent any
one, inference defers. Synthetic simulations must not be calibrated by
examining the holdout outcomes.

### Multiplicity and decision semantics

The confirmatory family should contain exactly one primary contrast:
BTCUSD 4h, one approved parameter set, one 24-hour outcome, one eligible
event definition, and one estimand. ETHUSD/SOLUSD 4h, month-stratified
contrasts, covariate adjustment, alternative gap/overlap policies, and
parameter sensitivities are exploratory and descriptive. If any secondary
result is to receive an inferential claim, its full family and correction
must be approved before any outcomes; otherwise report estimates without
confirmatory language and do not use them to rescue the primary result.

Let `delta_min > 0` be an approved minimum meaningful difference. Keep the
formal directional hypothesis `H1: delta > 0` and `H0: delta <= 0` unchanged.
Use separate labels for direction and practical importance:

- **Advance to the next research gate:** evidence adequacy passes and the
  approved holdout interval lower bound is greater than `delta_min`.
- **Evidence against a practically meaningful positive effect:** adequacy
  passes and the interval upper bound is below `delta_min`. This does not by
  itself reject the directional hypothesis if the interval remains above 0.
- **Reject the directional hypothesis:** adequacy passes and the interval
  upper bound is at or below 0.
- **Inconclusive/defer:** adequacy fails, the interval spans the relevant
  threshold(s), validation contradicts the registered direction, or
  required data-quality checks fail.

The interval level, `delta_min`, validation consistency rule, adequacy gates,
and exact decision wording require approval. These rules must be fingerprinted
with the specification before outcomes; post-result changes create a new
hypothesis version and cannot reinterpret the original holdout as untouched.

### Temporal leakage and implementation challenge

Source behavior supports key mechanical controls: the runner validates the
specification and current hashes before `load_ohlcv_before()`; event
assignment uses UTC half-open windows by `available_at`; the calculator
requires endpoint availability after the anchor and rejects/excludes
endpoints at or beyond the stage end; the runner excludes events in the
configured edge embargo and stage-bounds OHLCV materialization. Synthetic
tests already exercise exact endpoints, internal gaps, endpoint absence,
duplicate/invalid event inputs, boundary crossing, and future-value exclusion.

Limits that remain: the split validates ordering but does not derive or
freeze 50/25/25 boundaries; the partition helper does not require embargo >=
horizon; the stage approval can authorize holdout alongside development, so
the API does not enforce a separate holdout release after a locked analysis
plan; and callers can bypass the runner via lower-level functions. The
timestamp-only loader scan validates ordering across the full CSV, including
future timestamps, while materializing OHLCV values only before the stage
boundary. Treat this as metadata access, not a security-isolated holdout.
An authorized operator could still inspect files or run holdout and then
change choices; provenance hashes do not prevent that behavior.

The implementation does not add retrospective eligibility based on future
zone state: zones are created at confirmation and lifecycle rows are emitted
on later candles; origin labels are joined by pivot identity with availability
inequalities. Exclusions of initial/equal lows and non-support events are
part of the explicit estimand, not post-outcome exclusions. Endpoint/gap
exclusions remain a possible selection mechanism and must be reported by
cohort and period. The strongest causal threat is interpretation beyond the
observational conditional association, not evidence of a code-level future
feature leak in the reviewed path.

### Finding classification

| Issue | Classification | Conclusion |
|---|---|---|
| Declared close availability, duplicate timestamps, strict origin confirmation, later touch lifecycle | **Resolved by an existing contract** | The loader/feature APIs validate timestamp uniqueness, order and exact timeframe availability; swing/zone features emit only after confirmation and on later lifecycle candles. |
| 24h exact close and gap handling mechanics | **Resolved by an existing contract** | Outcome code supports exact elapsed endpoints, counts internal gaps and excludes configured gaps/incomplete endpoints. The 24h/exclude choice itself is not enforced. |
| Event-weighted estimand, primary population, parameter values, horizon, exclusions, comparability plan | **A proposed scientific choice requiring approval** | The proposal needs explicit acceptance before an approved spec is possible. |
| Residual trend/regime/volatility confounding and selection into touched zones | **An unresolved methodological risk** | The primary estimate is associational; descriptors do not remove unmeasured confounding or justify causal language. |
| Dependence-aware interval and evidence-adequacy computation | **A concrete implementation blocker** | No non-IID interval or cluster/precision adequacy procedure exists. Inference must not run until designed, implemented and synthetically validated. |
| Embargo >= horizon and separate holdout release after plan lock | **A concrete implementation blocker** | Current code accepts configured embargo and stage authorization but does not enforce these governance invariants. |
| Fixed split boundaries/50-25-25 allocation, alpha/interval level, minimum effect, sample simulation limits, multiplicity correction | **A proposed scientific choice requiring approval** | Code validates supplied split ordering and test IDs but does not choose or freeze these criteria. |
| Gap-related outcome exclusion selection and multiple descriptive sensitivities | **An unresolved methodological risk** | Exclusions can be period/cohort dependent; report eligible denominators and reasons, and keep secondary analyses exploratory. |

No production defect in the exact endpoint, duplicate-timestamp, internal-gap,
or incomplete-window mechanics was found by source inspection and synthetic
checks. The blockers above concern inferential and holdout governance support,
not evidence that the registered contrast has predictive value.

The mapping, approval checklist, and unresolved engineering controls are
maintained in the companion decision register. No project OHLCV outcome was
calculated for this challenge.

## Milestone 4C — statistical and protocol readiness

### Versioned proposal fingerprint

`SUPPORT_TOUCH_001_PREREG_DRAFT_V1.json` is a versioned **DRAFT — NOT
APPROVED FOR EVALUATION** specification proposal. It records the recommended
BTCUSD 4h population, event-weighted higher-low minus lower-low contrast,
proposed exact 24-hour elapsed close return, and proposed exclusion of gapped
or incomplete windows. These remain recommendations. Its fingerprint is
`a4c6f27011234655d3691aa7134436f4fee47027701f348c413b4f5be584cc1e`, computed
with `event_study_spec_fingerprint()` over the draft `EventStudySpec`. The
spec leaves split, feature parameters, uncertainty, sample adequacy, effect
threshold, decision criteria, and provenance hashes unresolved. This is not
an approval, run manifest, data fingerprint, or evaluation record.

### Statistical readiness decision

No uncertainty estimator or precision gate is implemented. The previously
suggested product-weight zone × calendar-week bootstrap is not sufficiently
specified to defend. Events are clustered by originating zone, but zones
can span many weeks; different zones can share candles and overlapping outcome
windows; adjacent week blocks may remain serially dependent. A naive product
of independent zone and week resampling weights does not automatically give a
valid multiway cluster bootstrap, especially with few or imbalanced clusters.
A crossed cluster-robust method also needs an appropriate large-cluster
argument in each dimension and a finite-sample procedure. Those assumptions
cannot be established from synthetic mechanics tests or without inspecting
real event concentration (which is outside this milestone's permitted work).

Consequently, any future inference needs a separately specified estimator,
resampling unit/algorithm, cluster-count conditions, interval level, block
length rule, and simulation-based operating-characteristic plan before
outcomes are accessed. A precision gate must use that same estimator and must
return inconclusive when cluster support or interval precision is inadequate.
Raw event count is not evidence adequacy. No IID interval fallback is
permitted. The event-weighted contrast remains descriptive only until this
blocker is resolved and approved.

### Mechanical safeguards added

The runner now validates ordered, nonmissing split boundaries; requires the
configured embargo to be at least the nominal registered horizon (elapsed
time, or observed-bar count times the declared timeframe); and still checks
each included endpoint lies strictly before its stage end. For gapped
observed-bar windows, the realized elapsed interval can exceed the nominal
embargo, so endpoint containment is decisive and the gap policy remains
explicit. The loader materializes only candles available before the stage
end; its timestamp-integrity scan can still inspect full-file timestamp
metadata.

Ordinary approval records cannot authorize `holdout`. The local workflow now
requires `lock_event_study_plan()` and then a separate explicit
`authorize_event_study_holdout()` record bound to the specification and
approval fingerprints. The runner rechecks the release before loading OHLCV
and records the release in the bundle. Editing the specification after
release makes the bound fingerprints stale. These are accidental-misuse
controls within the Python API, not security isolation: a process with direct
filesystem/Python access can read or copy holdout data, forge local objects, or
bypass the runner. The control cannot prove that a person did not inspect
holdout data before requesting release.

No real OHLCV outcomes, labels, or hypothesis results were calculated in this
milestone. Synthetic runner tests establish only deterministic mechanics and
rejection behavior, not inferential validity or predictive value. The
hypothesis remains **DRAFT — NOT APPROVED FOR EVALUATION**.

### Candidate dependence methods considered (none selected)

- **Two-way cluster-robust variance by origin zone and time block:** handles
  non-nested dependence dimensions through an inclusion/exclusion variance
  construction under its asymptotic conditions. It needs enough informative
  clusters in both dimensions and a defensible block partition; few or highly
  unbalanced clusters can make finite-sample inference unreliable. See the
  original [multi-way clustering paper](https://cameron.econ.ucdavis.edu/research/JBESpaper2009version.pdf).
- **Wild cluster bootstrap:** can improve some cluster-robust procedures, but
  is not a generic cure for very few or severely unbalanced clusters. See
  [MacKinnon and Webb (2018)](https://econ.queensu.ca/faculty/mackinnon/working-papers/qed_wp_1364.pdf).
- **Moving/stationary time-block bootstrap:** preserves local serial dependence
  and common shocks inside sampled blocks, but does not automatically preserve
  the full lifetime dependence of a zone that appears in separated blocks.
  Block length also trades dependence capture against the number of resampled
  units.
- **Zone-only cluster bootstrap:** retains within-zone repeats, but misses
  cross-zone dependence from shared candles and overlapping outcomes.
- **Product of zone and time-block bootstrap weights:** not selected. A
  multiplicative weighting recipe needs its own justification for this
  crossed structure; “crossed” alone is not a validity argument.

These alternatives are design candidates, not recommendations for an
inferential result. Choosing among them requires a pre-outcome estimand and
assumption review, a specified simulation design spanning plausible dependence
and imbalance, and an approved minimum-cluster/precision policy. No numeric
cluster cutoff or synthetic coverage claim is made here.

### Required gates versus optional robustness checks

**Required before confirmatory evaluation:** approve one population and cohort
contrast; freeze feature parameters and eligibility/exclusion semantics; choose
the horizon and endpoint/gap rule; set UTC partition boundaries and a
horizon-linked embargo; define an uncertainty estimator and its support
requirements; define adequacy and inconclusive behavior; register the primary
test family, meaningful-effect threshold, and immutable decision rules; and
approve the descriptive confounder/exclusion reporting plan. These determine
the estimand or whether its uncertainty is interpretable.

**Optional robustness checks:** separate ETHUSD/SOLUSD 4h replications,
prelisted one-touch-per-zone sensitivity, nearby time-block choices, and
pre-event descriptive stratification. They must not replace or rescue the
primary result; if inferential claims are made for any, the family and
multiplicity procedure must be expanded and approved in advance.

Workflow gates remain separate: (1) proposal and fingerprint, (2) explicit
owner approval of the resolved specification, (3) authorized stage execution
with current provenance, and (4) independent scientific reporting. Passing
mechanical validation does not satisfy the next gate.

## Milestone 4D — final methodology proposal (still unapproved)

This section supersedes the 4B candidate-bootstrap wording and the 4C method
alternatives as the current proposal. The draft JSON fingerprint remains
unchanged because no approval values or implementation contracts were
changed. No empirical event or outcome distribution was inspected.

### Candidate inference comparison

| Candidate | Target and independent unit | Dependence / overlap coverage | Support and failure conditions | Assessment here |
|---|---|---|---|---|
| Contiguous calendar-block bootstrap | Event-weighted mean contrast; resampled unit is a contiguous time block containing events from both cohorts. | Retains common shocks and within-block overlapping 24h windows if the block construction keeps complete event windows together. Repeated events from one zone may land in different blocks, losing long-lived zone dependence. | Requires enough blocks, weak dependence across sampled blocks, a stationary-enough event process, and a block length covering horizon overlap plus relevant serial dependence. Too few blocks or dependence longer than blocks invalidates uncertainty. | Plausible for temporal dependence; does not alone solve zone dependence. |
| Origin-zone cluster resampling | Event-weighted contrast over resampled zones; unit is the originating zone, with all its observed touches retained. | Preserves repeated touches within a zone, including within-zone overlapping outcomes. It does not preserve same-time shocks or overlap between different zones. | Requires enough independent zones per cohort and tolerable zone-size imbalance. Few/dominant zones or material cross-zone market dependence invalidate ordinary cluster resampling. | Insufficient alone. |
| Two-way zone × time-block cluster-robust variance | Event-weighted contrast with event-level influence contributions; dependence clusters are zone and time block. | Can represent dependence when two events share a zone or time block. Overlapping outcomes crossing block boundaries and serial dependence between adjacent blocks are not automatically covered; blocks must be designed around the outcome horizon and residual dependence. | Large-cluster conditions in both dimensions, non-dominant clusters, a defensible time-block scheme, and an appropriate finite-sample correction are needed. Few blocks/zones, highly unequal sizes, or cross-block dependence can make it unreliable. | Candidate for further methodological review, not selected or implemented. |
| Crossed/product-weight bootstrap | Would target the same event-weighted contrast only if the specific multiway resampling algorithm is justified. | A product of zone and time weights is not by itself proof that both dependence structures or cross-boundary overlapping outcomes are handled. | Requires an identified valid procedure, adequate support in each dimension, and demonstrated operating characteristics under the event/overlap structure. | Not recommended as currently described; “crossed” is not a method specification. |
| IID event bootstrap / IID standard errors | Event-weighted contrast treating each touch as an independent draw. | Fails to preserve repeated-zone dependence, shared candle shocks, overlapping outcomes, and serial dependence. | Its independence assumption is contradicted by the event construction. | Unsuitable. |

Multiway cluster methods are established for non-nested clustering under
specific asymptotics, but this does not establish that those conditions hold
for this event ledger. Few-cluster procedures can also fail when cluster
support is very small or imbalanced. See Cameron, Gelbach & Miller,
[Robust Inference with Multi-way Clustering](https://cameron.econ.ucdavis.edu/research/JBESpaper2009version.pdf),
and MacKinnon & Webb,
[The Wild Bootstrap for Few (Treated) Clusters](https://econ.queensu.ca/faculty/mackinnon/working-papers/qed_wp_1364.pdf).

**Inference selection remains blocked.** The exact missing information is the
pre-outcome event-incidence structure needed to assess: distinct zones by
cohort; events per zone and zone lifetimes; occupied time blocks and gaps;
cohort balance by block; the rate of shared candles and overlapping 24h
windows, including windows crossing block edges; and dependence duration
across adjacent blocks. This milestone did not inspect or calculate those
project event records. Synthetic fixtures can verify code behavior but cannot
establish those empirical support conditions. Before evaluation, specify a
small set of plausible dependence scenarios independently of holdout
outcomes, compare candidate procedures in simulation, and require an
inconclusive result when no method meets its predeclared support conditions.
The simulation model, coverage/error tolerances, and method choice themselves
require approval. No estimator or IID fallback is recommended meanwhile.

### Proposed adequacy gate (no numerical cutoffs selected)

Report separately, for each cohort and partition: (1) all eligible touch
counts; (2) outcome-included counts and each exclusion reason; (3) distinct
origin-zone counts and event concentration across zones; (4) occupied temporal
block counts, counts per block, and concentration across blocks; (5) the
estimator-specific effective support in each dependence dimension; and (6)
uncertainty interval width relative to the approved minimum meaningful effect
`delta_min`.

Adequacy should be a conjunctive gate: both cohorts need the preapproved
zone and temporal support; neither dimension may be dominated beyond an
approved concentration rule; simulation evidence must meet predeclared
coverage/type-I-error criteria under the registered dependence scenarios;
and the primary interval half-width must meet a predeclared precision target
relative to `delta_min`. A concentration statistic such as
`(sum w)^2 / sum(w^2)` can describe event-weight concentration across zones or
blocks, but is not itself an estimator-independent count of independent
observations. Thresholds must be selected from a prospective design/simulation
exercise and a scientific precision rationale, never tuned to holdout
outcomes. Failure of any required gate returns **inconclusive**; do not replace
it with raw event count or IID inference.

### Recommended primary design

- **Estimand:** event-weighted arithmetic mean difference
  `E[Y_24h | higher_low-origin support touch] -
  E[Y_24h | lower_low-origin support touch]`. This is an observational
  association in the eligible touch-event population, not a causal effect or
  trading return.
- **Scope/family:** one confirmatory BTCUSD 4h contrast. Keep ETHUSD and
  SOLUSD 4h as separate descriptive/exploratory reports; no pooling and no
  secondary result may rescue the primary. One event definition and one
  feature configuration only.
- **Eligibility/anchor:** a later support-zone `touched` lifecycle row whose
  originating confirmed swing low is labeled `higher_low` or `lower_low`.
  Origin/zone creation availability must be no later than touch availability.
  The anchor close is the touch candle close; only the touch candle's
  `available_at` makes the event observable. Retain repeated touches and
  overlapping zones as separate events, with zone and timestamp identities.
- **Outcome proposal:** exact elapsed 24-hour close return
  `Y_24h=(C_future/C_anchor)-1`; `C_future` is the close whose `available_at`
  equals `anchor available_at + 24h`. No forward fill or nearest-close
  substitution. Exclude a touch if any expected 4h candle is missing, the
  exact endpoint is absent, or the right edge is incomplete; report all such
  exclusions by cohort and period. These choices remain unapproved.
- **Temporal proposal:** derive three UTC half-open windows from the complete
  declared BTCUSD 4h coverage interval: first 50% elapsed time for
  development, next 25% for validation, final 25% for holdout. Snap each
  interior boundary to the first observed candle `available_at` at or after
  its calculated timestamp; write the resulting literal UTC boundaries into
  the frozen spec before outcome access. Assign events by `available_at`.
  Require the event and its full endpoint to be inside the same partition;
  purge any endpoint `>= partition_end`. Candidate edge embargo is 24 elapsed
  hours on both sides of each partition, with the existing runner's
  `embargo >= nominal horizon` check. A missing endpoint remains excluded
  even if the timestamp embargo condition passes. Split fractions, alignment
  rule, and boundaries require approval.
- **Confounding diagnostics:** no matching or adjustment in the primary
  estimand. Report cohort distributions of prior 24h return, prior 24h
  realized range/volatility, zone age, prior touch count, and calendar month.
  Price diagnostics must end no later than the candle open of the touch candle
  (the preceding close); prior touch count excludes the current touch. If a
  trailing window is incomplete or gapped, report missingness without fill.
  These are descriptive diagnostics, not confounder control. Adjusted or
  matched estimates would be a separately registered exploratory estimand.
- **Inference and decisions:** no estimator is selected until the dependence
  blocker is resolved. Then freeze a method-specific interval, support
  thresholds, simulation plan, confidence level, multiplicity family,
  `delta_min > 0`, and decision rules in a new version before holdout access.
  Conditional proposal: advance only if adequacy passes, validation does not
  clearly contradict direction under the registered rule, and the holdout
  lower bound exceeds `delta_min`; reject directional H1 only if an adequate
  holdout upper bound is `<= 0`; if the upper bound is below `delta_min` but
  above zero, report evidence against practical importance without calling
  H1 rejected; otherwise defer/inconclusive. No numeric threshold is chosen.

### Holdout no-revision rule

Lock the complete event, feature, endpoint, gap, split, inference, adequacy,
multiplicity, effect, and decision plan before any confirmatory holdout access.
The runner's separate plan-lock/release API binds fingerprints and rejects a
changed spec after release; the release must follow lock time. If any plan
change is needed after holdout access, retire that holdout for confirmation,
create a new hypothesis/specification version, and use a genuinely untouched
future period or independently sourced sample. Do not re-label the old
holdout as untouched. These are local procedural controls, not security
isolation; a process with direct file access can bypass them.

### Status of choices

**Implementation contracts:** strict feature availability; origin confirmation
and zone creation no later than touch; UTC half-open split validation; nominal
horizon-linked embargo; stage-bounded OHLCV materialization; endpoint
containment; separate holdout release; stale fingerprint rejection. These
contracts do not decide scientific adequacy.

**Approval required:** population/family, feature parameters, outcome/gap
rules, exact split boundaries, embargo policy, estimator, block construction,
support criteria, simulation assumptions/tolerances, interval level,
confounder reporting, multiplicity, `delta_min`, and decision wording.

**Unresolved blockers:** no defensible estimator selected; no estimator-linked
adequacy implementation; no numeric cutoffs or real split boundaries; and no
real-data event support has been measured. Hypothesis status remains
**DRAFT — NOT APPROVED FOR EVALUATION**.

## Milestone 4F — independent simulation audit

### DGP and estimand audit

The implemented event outcome is
`Y_i = delta * 1(cohort_i == 0) + a_zone(i) + mean(u_zone(i),t+1..t+6) + e_i`,
where `e_i ~ N(0,1)`, zone effects are independent zero-mean normal draws
(SD 0.5 when enabled), and the six-period mean creates overlapping synthetic
outcomes for nearby anchors. The intended population contrast is the
superpopulation event-weighted mean difference: its expectation is exactly
`delta` because zone, shock, and event errors have zero mean and the cohort
generation rules are otherwise symmetric. Each replication's finite event
sample need not have contrast exactly equal to `delta`; coverage and bias are
therefore judged against the superpopulation parameter. A new synthetic test
confirms that reusing a seed and changing `delta` shifts only cohort 0's
outcomes, leaving rows, missingness, window components, and cohort 1 unchanged.

When temporal dependence is active, the implementation uses innovations
`epsilon_t ~ N(0, period_sd^2)` with `u_0=epsilon_0` and
`u_t=epsilon_t + rho*u_(t-1)`. It has no stationary burn-in, so marginal shock
variance ramps toward its stationary level. With shared shocks, one such path
is broadcast to every zone; otherwise each zone has an independent path. The
unequal-size scenario gives the first zone in each cohort eight times the
ordinary fixed event count; this makes concentration symmetric across
cohorts, not outcome-dependent. Missing outcomes are Bernoulli missing-at-
random within cohort (10% vs 40%); this changes observed sample sizes but not
the expected cohort mean. No outcome-dependent missingness or deliberate
cohort variance change is simulated. In the five-period sparse fixture, six
period outcome windows wrap circularly; this is a boundary stress convention,
not a realistic chronology.

The zones are disjoint by cohort, and each zone contributes events across
calendar periods; in the shared-shock scenario, zone and time dimensions are
crossed. In non-shared scenarios, each zone carries its own serial path.
Therefore the generator isolates repeated-zone persistence, common calendar
shocks, serial dependence and overlap, but does not represent every possible
sampling design.

### Resampling and metric audit

- **Calendar blocks:** circular six-period blocks generate period
  multiplicities shared across rows. Outcomes are not recomputed from sampled
  underlying shocks; event rows are weighted by their anchor period. A
  six-period window can cross a resampled block boundary, so dependence from
  overlapping outcomes is not perfectly kept together. The block procedure
  is a stress candidate, not a justified primary interval.
- **Zone clusters:** zones are sampled with replacement separately within
  cohort and all their events receive the same multiplicity. This retains
  within-zone persistence and observed cluster sizes. It conditions on shared
  time shocks and cannot capture uncertainty from common calendar shocks.
- **Crossed product weights:** independently generated zone and block
  multiplicities are multiplied. This is a product-weight/pigeonhole-style
  bootstrap, not a generally valid two-way cluster estimator by definition.
  The generator has crossed zones and time in the shared-shock scenario, but
  product weights can be conservative and can distort finite-sample variation.
- **IID negative control:** resamples rows within cohort and is explicitly
  excluded from any primary-method recommendation.
- Intervals are equal-tailed percentile intervals from finite bootstrap
  contrasts. Null false-positive rate and power use a two-sided rule (the
  interval excludes zero); this is a simulation diagnostic, not the proposed
  directional decision rule for SUPPORT_TOUCH_001. Point bias, coverage,
  width, rates, and their Monte Carlo standard errors are calculated over
  support-passing Monte Carlo replications. The reported standard error for a
  rate is binomial `sqrt(p*(1-p)/R)`; mean metrics use sample SD / `sqrt(R)`.

The V1/V2 code filtered non-finite bootstrap contrasts and could retain up to
10% invalid draws without publishing the count. This was a **medium-severity
reporting defect**, even though the below-90% case failed closed. V3 now
reports mean/minimum valid-draw fractions, separates support-gate and
bootstrap-failure inconclusives, and returns an explicit failure reason. A
regression tests the exact 90% boundary and the fail-closed case. In the V3
300-replication matrix every attempted draw was finite (minimum valid fraction
1.0; bootstrap-failure rate 0); sparse support still yielded 100%
inconclusive in both few-zone and few-block scenarios. V1/V2 artifacts remain
unchanged, and V3 has separate output names.

The V3 common-column metrics match V2 for identical seeds, confirming this
instrumentation amendment did not change interval estimates. V3's report is
rendered from its CSV. No candidate is selected: calendar blocks undercovered
with persistent zones and unequal cluster sizes; IID undercovered under
dependence and remains negative control; zone resampling does not handle
common shocks; crossed products were conservative here but had wider intervals
and lower power. These are conditional generator findings, not claims about
crypto market structure or method validity.

### Adequacy and finding classification

The V2/V3 support gate checks only a mechanical floor of four observed zones
and four occupied six-period blocks per cohort. It does not assert statistical
independence, concentration adequacy, or sufficient precision. Kish
concentration summaries and interval widths are reported descriptively, but
no cutoff is set. A real-data study therefore remains inconclusive until an
owner-approved concentration/support policy and precision target exist.

- **Medium — corrected:** invalid bootstrap draws were not exposed in V1/V2
  reports. V3 adds auditable counts/fractions and an explicit inconclusive
  reason.
- **Medium — unresolved design limitation:** anchor-period weighting does not
  keep all overlapping future windows together across moving-block boundaries.
  A different temporal procedure would need separate design and validation;
  this audit does not select one.
- **Low — clarified:** AR shocks use innovation-scale SD and no burn-in. The
  design document now states the transient variance behavior.
- **No defect found:** the registered difference's synthetic null/effect
  shifts cohort 0 only in expectation. Differential missingness is confined
  to cohort-specific MCAR as documented; MNAR remains outside the tested
  scope.

No scientific approval or production inference method follows from this audit.
The draft remains **DRAFT — NOT APPROVED FOR EVALUATION**.

## Milestone 4E — synthetic dependence simulation (not market evidence)

The simulation protocol was recorded in
`SYNTHETIC_DEPENDENCE_SIMULATION_DESIGN.md` before its first run. The reusable
synthetic-only harness is `dependence_simulation.py`; focused deterministic
mechanics are tested in `test_dependence_simulation.py`. V1 uses master seed
20261020, 300 Monte Carlo replications per scenario/effect, and 399 bootstrap
draws. It covered independent events, persistent zones, serial and shared
calendar shocks, six-period overlapping outcomes, unequal zone sizes, sparse
zones/periods, cohort-differential missingness, and null/effect 0.25. All
parameters are illustrative and not market estimates.

V1 exposed an implementation support defect: five periods passed a generic
four-period floor although a six-period moving-block bootstrap had only one
effective block and produced degenerate intervals. V1 files are preserved.
The V2 protocol amendment requires four zones and four occupied
non-overlapping six-period calendar blocks per cohort. V2 was rerun with the
same seeds, DGPs, repetitions, methods, and metrics; only this mechanical
support gate and filenames changed. It returned inconclusive for both sparse
zone and sparse block scenarios. This threshold is a simulation mechanics
guard only.

### Conditional findings and method status

- Calendar moving-block intervals undercovered substantially when persistent
  repeated zones were the active dependence (null coverage 0.780 ± 0.024
  Monte Carlo SE) and with unequal concentrated zone sizes (0.730 ± 0.026).
  Under combined serial, shared-shock and overlapping-window dependence,
  coverage was 0.860 ± 0.020. This exposes the omission of zone dependence.
- Zone-cluster intervals did not show the same failure in the repeated-zone
  scenario (0.910 ± 0.017), but they do not resample shared time shocks and
  are not accepted as generally adequate. In the combined scenario null
  coverage was 0.933 ± 0.014; these finite results do not establish validity.
- Product-weight crossed resampling was conservative in the tested designs
  (null coverage 0.980–1.000 and null rejection 0.000–0.020), with wider
  intervals and low power for the fixed effect. This may reflect conservatism
  or algorithm-specific behavior; it is not a validation of crossed-bootstrap
  assumptions and is not selected.
- IID event resampling undercovered under repeated zones (0.807 ± 0.023),
  concentrated zone sizes (0.790 ± 0.024), and combined serial/shared shocks
  (0.887 ± 0.018). It remains only a negative control.
- The cohort-differential missingness scenario uses missing-at-random within
  cohort, not outcome-dependent missingness. Thus informative exclusion and
  cohort composition remain untested. Point-estimate bias was small relative
  to its MCSE in these generated scenarios, which says nothing about actual
  event selection.

No candidate passes across the declared stress cases, and no numeric
confidence, effective-support or precision policy is recommended for real
events. The harness reports event counts, zones, occupied periods, Kish
concentration summaries, interval width, and support inconclusiveness. Kish
values are not independence counts; precision thresholds remain unset, so
synthetic adequacy cannot be promoted to an approved gate. The current result
is a blocker: before real-data inference, choose and justify a dependence
model with plausible zone/time structure, predeclare support and precision
criteria, and include outcome-dependent missingness stress or a justified
exclusion assumption. SUPPORT_TOUCH_001 remains
**DRAFT — NOT APPROVED FOR EVALUATION**.
