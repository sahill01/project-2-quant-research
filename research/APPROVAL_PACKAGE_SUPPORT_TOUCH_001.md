# Approval package — HYP-SUPPORT-TOUCH-001

> **DRAFT — NOT APPROVED FOR EVALUATION**
>
> This package requests review of a feature-only research design. The
> candidate outcome is **PROPOSED — AWAITING APPROVAL**. Nothing here
> authorizes outcome calculation, holdout access, strategy implementation,
> or trading. No predictive outcomes were calculated in preparing this
> package.

## Research question

Among later touches of confirmed support zones, do zones originating from a
confirmed `higher_low` have a higher mean subsequent close-to-close return
than zones originating from a confirmed `lower_low`?

The comparison is descriptive and observational. It does not test causation,
tradability, profitability after costs, or strategy performance.

### Formal hypothesis

For the as-yet-unselected future horizon `H` and outcome `Y_H`:

`H1: E[Y_H | higher_low-origin support touch] - E[Y_H | lower_low-origin support touch] > 0`

`H0: E[Y_H | higher_low-origin support touch] - E[Y_H | lower_low-origin support touch] <= 0`

### Candidate outcome — PROPOSED, AWAITING APPROVAL

`Y_H = (C_future / C_anchor) - 1`

`C_anchor` is the close of the candle whose support-zone touch becomes
observable at that candle's `available_at`. `C_future` is the close selected
under the future-horizon rule, which remains unresolved. The formula is not
an execution return and does not model whether the wick touch could be
filled.

## Recommended complete methodology (recommendations are not approvals)

1. **Population:** candidate primary family of BTCUSD, ETHUSD, and SOLUSD at
   4h, because this matches the project's existing cross-asset comparison
   cadence and limits the initial family. Retain asset-specific estimates;
   define one across-asset summary before outcome access. Other available
   timeframes remain optional, predeclared secondary robustness families.
   This choice is based on manageability, not feature outcomes.
2. **Eligibility:** only a later source-layer zone event with
   `zone_type == "support"`, `event == "touched"`, and an origin swing-low
   structure label `higher_low` or `lower_low`. Exclude initial/equal lows,
   creation events, resistance zones, and any candle where a break takes
   precedence. Keep the lower-low cohort as the sole primary comparator.
3. **Origin join:** use `zone_id`/`pivot_time` to identify the originating
   swing and join `pivot_time` to the source structure row's
   `swing_low_pivot_time`; obtain `swing_low_structure` from that row. Require
   structure confirmation and zone creation `available_at` no later than
   the touch `available_at`. `pivot_time` is not the knowledge time.
4. **Time contract:** loader `timestamp` and normalized `event_time` identify
   candle opens; `available_at` is the candle close; `pivot_time` is the
   originating swing candle; `formation_time` applies to candle/chart
   geometry and is null for structure/zone lifecycle events. The touch is
   known only at the touch candle close. OHLC does not provide intrabar touch
   chronology.
5. **Outcome:** retain the proposed close-to-close formula only if approved.
   Recommended horizon convention is fixed elapsed time, with the first
   observed close at or after target accepted only within an approved maximum
   lateness. Do not forward-fill, pick a close by its return, or select a
   horizon because it performs best. The horizon and lateness remain unset.
6. **Repeated/overlapping events:** retain every eligible touch in the
   declared cohort for the primary estimand, preserve zone and anchor
   identity, and use zone- and time-dependence-aware uncertainty. Report
   unique zones separately. Approve an explicit policy for simultaneous
   overlapping-zone touches and shared outcome windows before evaluation.
7. **Comparison/confounding:** start with the prespecified higher-low versus
   lower-low contrast, stratified by the selected asset/timeframe and
   calendar period. Do not match in the first study. Treat the contrast as an
   association; report potential regime, trend, volatility, zone-age,
   geometry, prior-touch, and liquidity confounding. Any adjusted analysis
   is secondary and must use only information available by the touch close.
8. **Missing and invalid data:** do not synthesize or forward-fill candles.
   Existing loader validation rejects malformed/non-finite OHLCV, duplicate
   or unordered timestamps, and availability inconsistent with the declared
   timeframe; it permits gaps. Freeze how internal gaps, unavailable target
   closes, and right-edge incomplete windows are handled. Exclusion reasons
   must be reported.
9. **Temporal evaluation:** treat current 730-day data as exploratory only.
   For any later confirmatory study, assign events by `available_at`, define
   chronological UTC half-open development/validation/holdout windows, keep
   holdout untouched, and purge/censor outcomes crossing boundaries. Exact
   boundaries and embargo depend on the approved horizon and adequate history.
10. **Inference and decisions:** define sample sufficiency from precision or
    power against a separately approved minimum meaningful effect, using
    effective dependence-adjusted sample size. Candidate uncertainty method
    is a contiguous calendar-block resampling scheme retaining cross-asset
    co-movement and zone identity; its block construction must be justified
    and frozen. Select one primary contrast/horizon and a multiplicity plan
    before outcomes. Advance/reject/defer rules must use approved effect,
    uncertainty, sample, validation, and data-quality criteria.

The rationale, alternatives, and limitations are detailed in
[METHODOLOGY_REVIEW_SUPPORT_TOUCH_001.md](METHODOLOGY_REVIEW_SUPPORT_TOUCH_001.md).
The existing broad feature protocol and experiment infrastructure context
remain in [VALIDATION_AND_READINESS_PLAN.md](VALIDATION_AND_READINESS_PLAN.md)
and [RESEARCH_PLAN.md](../RESEARCH_PLAN.md).

## Decision table

No row is approved. “Recommended” means a proposed default for user review;
approval status remains unresolved until you explicitly accept or amend it.

| Decision | Recommended default | Alternatives and trade-off | Approval status |
|---|---|---|---|
| Outcome formula | `Y_H = C_future/C_anchor - 1` | Choose a different prespecified outcome; the current formula is a descriptive endpoint return, not execution P&L. | **Unresolved; formula awaiting approval** |
| Asset/timeframe family | Three assets at 4h; separate asset estimates and a predeclared summary | All 12 combinations broadens coverage but adds multiplicity/dependence; one asset limits generality. | **Unresolved** |
| Swing/zone settings | One frozen setting per selected timeframe, chosen without outcome inspection | Common settings aid comparability; timeframe-specific settings may fit scale but add degrees of freedom. Exact values not set. | **Unresolved** |
| Horizon convention/value | Fixed elapsed time; first close at/after target subject to approved lateness; no numeric horizon proposed | Fixed observed bars gives uniform count but different elapsed duration across gaps/timeframes. | **Unresolved** |
| Missing bars/endpoints | No forward-fill; exclude/censor events without an eligible endpoint under a predeclared rule | Retaining irregular elapsed spans preserves rows but changes realized duration; a censoring model adds assumptions. | **Unresolved** |
| Touch repetitions/overlap | Retain eligible touches and account for zone/time dependence | First touch per zone simplifies dependence but changes estimand; deduplication reduces rows and needs a deterministic rule. | **Unresolved** |
| Comparator/confounding | Lower-low support touches; stratify, no matching in primary analysis; describe as association | Match/adjust on pre-event variables for balance but add choices, reduce sample, and cannot remove unmeasured confounding. | **Unresolved** |
| Temporal design | Current 730-day history exploratory; later chronological holdout for confirmation | Split current history three ways if adequately supported; this may leave insufficient independent data. Boundaries/embargo unset. | **Unresolved** |
| Minimum sample | Precision/power rationale based on meaningful effect and effective sample | Raw count threshold is simpler but is not a power justification. If assumptions unavailable, defer confirmation. | **Unresolved** |
| Uncertainty | Calendar-block resampling that preserves time dependence, with zone repetition accounted for | IID inference is invalid under dependence; cluster/bootstrap alternatives need enough blocks and frozen settings. | **Unresolved** |
| Multiplicity | One primary contrast/horizon; family-wise control for confirmatory secondary tests | Hierarchical or false-discovery methods are options for broader families. Exact family/error criterion unset. | **Unresolved** |
| Meaningful effect | Set a nonzero minimum contrast before outcome access | Direction-only testing may accept a negligible association. No numerical threshold proposed. | **Unresolved** |
| Decision rule | Advance only under predeclared effect, uncertainty, validation, and sample criteria; otherwise reject or defer per rule | A holdout can confirm only once; exact criteria unset. | **Unresolved** |
| Experiment schema | Use the implemented feature-only `EventStudySpec` and stage-bounded runner | The strategy-oriented config remains separate; the implemented runner is mechanically tested but is not a scientific approval or security boundary. | **Implemented; no additional schema decision required** |

## Mandatory decisions before evaluation

User approval is needed for the outcome formula; primary asset/timeframe and
aggregation; feature parameters; numerical horizon and future-close rule;
missing-data and endpoint policy; repeated/overlapping-event treatment;
comparator and confounding plan; chronological split and purge/embargo rules;
minimum sample rationale; uncertainty method; multiple-testing family;
meaningful effect threshold; and advance/reject/defer criteria.
These scientific choices must be frozen before any outcome calculation. The
feature-only schema and runner implementation are complete; this does not
approve the hypothesis or its methodological choices.

## Optional robustness checks

After the primary plan is frozen, optional checks can include other
asset/timeframe strata, predeclared zone-width or swing-window sensitivity,
alternate dependence-aware intervals, alternative horizon conventions,
one-touch-per-zone sensitivity, and placebo anchors. Label these exploratory
or include them in the multiplicity plan before evaluation. They cannot be
used to select a winning variant.

## Red-team findings and resolutions

- **Major — pseudoreplication:** repeated touches, overlapping zones, and
  shared future windows inflate apparent sample size. Resolve with a frozen
  event-retention rule and dependence-aware inference; report zones and
  effective time blocks.
- **Major — confounding:** origin labels differ across trend, volatility,
  period, zone age, and geometry. Resolve through predeclared stratification
  and cautious associative interpretation; no observational adjustment
  proves causation.
- **Major — leakage/split contamination:** pivot time predates confirmation;
  future zone state or outcome windows crossing partitions can leak. Join by
  identity but gate on `available_at`; assign by touch availability and
  purge/censor crossing outcome windows.
- **Major — limited history:** 730 days may not support independent
  development, validation, and holdout evidence. Keep it exploratory unless
  adequacy is justified; obtain longer history for confirmation if needed.
- **Major — researcher degrees of freedom:** assets, timeframes, horizons,
  parameters, matching, and exclusions permit outcome-driven selection.
  Freeze one primary family and record all variants/nulls.
- **Minor — non-executable touch:** OHLC wick intersection is candle-level
  and not a fill. Keep this strictly a descriptive event study.
- **Minor — schema mismatch:** current protocol uses strategy-oriented
  fields and equity/trade metrics. Add a separately reviewed event-study
  contract rather than supplying fictitious entries/costs.

No critical defect makes the cohort impossible to construct. The design as
currently specified cannot establish causation or tradability.

## Event-study infrastructure status

The feature-only mechanics have now been implemented in
[`event_study.py`](event_study.py), with synthetic regressions in
[`test_event_study.py`](test_event_study.py). This is engineering support for
future review, not an approved study or evaluation.

| Status | Component |
|---|---|
| **Implemented and synthetically tested** | Versioned `EventStudySpec`, canonical serialization/fingerprint, unresolved-choice validation, local approval binding to spec/data/source hashes, stage authorization, no-clobber JSON writing, and output path containment. |
| **Implemented and synthetically tested** | Support-zone lifecycle ledger joined to confirmed swing-low structure by pivot identity; causal availability checks; explicit exclusions; repeated touches and overlapping zones retained. |
| **Implemented and synthetically tested** | Forward close return calculator for observed-bar and elapsed-time endpoints; exact/first-close sampling, lateness, gap and incomplete-window handling; target timestamps and elapsed/bar counts. Tests use synthetic candles only. |
| **Implemented and synthetically tested** | UTC half-open partition assignment, embargo, and cross-boundary outcome purge/error. Descriptive cohort means/counts and caller-supplied decision classification are implemented without an inferential interval method. |
| **Implemented and synthetically tested** | `event_study_runner.py` coordinates approved-stage loading, causal cohort construction, outcomes, partition checks, descriptive summaries, staged bundle publication, and artifact verification. It requires hashes for the current event-study, runner, loader, swing, and zone source files. |
| **Not implemented** | Dependence-aware uncertainty estimator. Inferential execution is disabled; summaries are descriptive only. |
| **Blocked pending explicit scientific approval** | All choices in the mandatory decision checklist below, including whether the proposed outcome is approved. No approval record, frozen holdout, experiment manifest, or real-data outcome was created. |

### Future approved-run workflow

1. The study owner resolves and approves every required methodological choice
   in a frozen `EventStudySpec`. The current draft is not approved.
2. An authorized reviewer creates a local approval record binding the full
   spec fingerprint, data-file identities/hashes, source-file identities/
   hashes, and allowed stages. The runner requires the current implementations
   of the event-study primitives, runner, loader, swing layer, and zone layer
   to appear in that source set.
3. `run_event_study()` checks approval, stage authorization, implementation
   compatibility, and data/source hashes before parsing OHLCV. Its bounded
   loader streams the timestamp column through the file to validate order and
   locate the stage boundary, but materializes only candles whose `available_at`
   is before that boundary. It computes features using
   the available historical prefix, filters events to the requested
   availability window, applies the registered embargo before outcomes, then
   calculates only that stage's outcomes and purges/rejects boundary-crossing
   windows.
4. The runner stages the specification, event and outcome ledgers, exclusions,
   data-quality report, descriptive summary, validation record, and manifest.
   It publishes to a new run directory only after the required artifacts
   exist. The manifest distinguishes `computation_completed` from
   `scientific_status=not_assessed`; verification rechecks schemas, paths,
   status consistency, and artifact hashes.
5. The owner/reviewer assesses the registered scientific criteria separately.
   Successful computation does not mean the hypothesis passed.

These controls reduce accidental misuse but are not tamper-proof. Python
callers can read files directly, call lower-level table functions, lie about
the synthetic-data declaration, or modify local approval records. The runner
does not provide process/filesystem isolation. No runner or approval record
for the real hypothesis was used in this milestone.

## DECISIONS REQUIRED FROM USER

1. Approve or amend the proposed close-to-close outcome formula.
2. Approve or amend the recommended primary family (three assets at 4h),
   aggregation, and frozen swing/zone settings.
3. Choose a numerical horizon and approve the horizon convention and target
   close/lateness rule.
4. Choose missing-candle, incomplete-window, repeated-touch, and overlap
   policies.
5. Approve the comparator and whether the primary analysis is stratified or
   adjusted/matched.
6. Decide whether the 730-day sample is exploratory only and approve the
   future chronological split/holdout and purge/embargo design.
7. Set the minimum meaningful effect, sample-size rationale, uncertainty
   method, multiple-testing family, and advance/reject/defer criteria—or
   direct that confirmation be deferred until suitable assumptions/history
   are available.

## Milestone 4A — decision-ready proposal (supersedes recommendations above)

> **DRAFT — NOT APPROVED FOR EVALUATION.** This section refines the earlier
> broad recommendations. Older text above is retained as history; where it
> differs, this narrower proposal is the current recommendation, not an
> approval.

### Recommended primary specification

- Preserve the existing primary contrast and null: higher-low-origin support
  touch minus lower-low-origin support touch in mean subsequent outcome;
  `H1: difference > 0`, `H0: difference <= 0`.
- Primary population: BTCUSD 4h only. ETHUSD and SOLUSD 4h are separate
  exploratory replications; do not pool them or other timeframes into the
  confirmatory estimate.
- Eligible event: each later `touched` lifecycle row for a support zone
  originating from a confirmed swing low whose structure label is exactly
  `higher_low` or `lower_low`. The touch is known at its candle close
  (`available_at`), also the proposed `C_anchor`. Exclude creation, break,
  resistance, initial/equal low, invalid/unjoinable origin and incomplete
  outcomes. Preserve repeated touches and overlapping zones as separate
  events with stable event and zone identity.
- Origin join: zone identity plus `pivot_time` joins to the structure row's
  `swing_low_pivot_time`; take `swing_low_structure` from that row only when
  structure confirmation `available_at` and zone `created_at` are no later
  than touch `available_at`. `pivot_time` is not availability. No later zone
  state may revise earlier event eligibility.
- Proposed outcome: `Y_24h = (C_future / C_anchor) - 1`, where `C_future` is
  the exact close 24 elapsed hours after touch close. Do not forward-fill or
  substitute another close. Recommend excluding outcomes with a missing
  expected 4h candle, absent exact endpoint, or right-edge incomplete window;
  retain exclusion reasons. Twenty-four hours is a proposed, interpretable
  one-day horizon (six bars only on a complete 4h grid), not an empirical
  choice.
- Dependence: keep each repeated/overlapping event in the target population,
  but do not treat event rows as independent. Recommend a calendar-block
  resampling interval with all events within sampled blocks retained;
  block unit/length, interval method and minimum usable blocks require
  methodological approval and new synthetic validation. Until implemented,
  report descriptive estimates only.
- Chronology: recommend timestamp-derived UTC 50%/25%/25% development,
  validation and untouched holdout windows. Assign by touch `available_at`,
  use half-open intervals, purge any outcome endpoint at or beyond a window
  end, and embargo at least the approved horizon at each boundary. Exact
  timestamps and adequacy are not yet known. The available ~730 days may be
  insufficient; if evidence or independent blocks are inadequate, defer and
  seek longer history instead of moving boundaries after outcomes.
- Comparison/confounding: lower-low touches remain the only primary
  comparator. Recommend no matching in the primary estimate; report known at-
  touch cohort characteristics and interpret the contrast as observational,
  potentially confounded by trend, volatility, calendar period, zone age,
  touch history and liquidity.
- Decision: report cohort means, difference, event/zone/block counts,
  exclusions and quality. Advance only if an approved dependence-aware
  holdout interval exceeds an approved positive minimum effect and evidence
  gates pass. Reject the directional claim only if the interval upper bound
  is <= 0 with adequate evidence. Otherwise defer/inconclusive. Numerical
  thresholds, confidence level, method and sample rationale are not proposed
  as settled values.

### Approval choices still required

The owner must accept or amend the primary scope and exploratory designation;
feature parameter values; the 24-hour exact-close outcome and gap rule;
retention of repeated/overlapping events and the uncertainty method; temporal
allocation/boundaries and horizon-linked embargo; confounding/reporting plan;
minimum evidence rationale; multiplicity family; minimum meaningful effect,
confidence level and decision rules. The event-study code does not establish
these choices as approved. See the decision register for each enforcement
path and remaining blockers.
