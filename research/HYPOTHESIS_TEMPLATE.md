# Research hypothesis specification

No signal or trading rule is approved by completing this template. An approved
specification must be frozen before implementation and before accessing an
untouched holdout.

- **Hypothesis ID and version:**
- **Title:**
- **Market rationale:**
- **Feature definition:** Include inputs, formula, lookback, and warm-up behavior.
- **Signal definition:** Exact condition for long, short, and flat.
- **Information availability:** State the source candle's `available_at` and
  the decision timestamp. A feature cannot be used before it is available.
- **Entry and exit assumptions:** Include signal timing, fill timing, and
  terminal-position handling.
- **Expected effect:** State the expected measurable change, not a return goal.
- **Failure conditions:** List observable outcomes that reject the hypothesis.
- **Baseline comparison:** Identify unchanged Buy & Hold and incumbent baselines.
- **Sample size and validation:** Predeclare assets, time periods, minimum
  trade/event count, train/validation/holdout boundaries, and uncertainty
  reporting. Do not reuse holdout data to select a variant.
- **Confounders:** Include regime dependence, survivorship/selection effects,
  and any data or execution limitations that apply.
- **Transaction costs:** Specify fee, slippage, and any excluded costs.
- **Approval status:** Proposed / Approved / Rejected. Implementation requires
  explicit approval of the hypothesis and its signal definition.
- **Null and baseline comparison:**
- **Event definition and feature availability:** Include the event's actual
  observation anchor, availability timestamp, and eligible decision time.
- **Forward-outcome horizon and calculation:** Mark unresolved until approved.
- **Missing-candle policy:** Mark unresolved until approved.
- **Overlapping-event treatment:** Mark unresolved until approved.
- **Chronological development/validation/holdout windows:** Include timezone
  and half-open boundary semantics; do not expose holdout before approval.
- **Matching or control-selection method:** Mark unresolved until approved.
- **Minimum sample rationale:** Mark unresolved until approved.
- **Effect-size criteria:** Mark unresolved until approved.
- **Uncertainty and multiple-testing criteria:** Mark unresolved until approved.
- **Advance/reject/defer rule:** Mark unresolved until approved.

An unresolved field must remain explicitly unresolved; infrastructure tests may
use synthetic values only to verify validation and lifecycle behavior. A local
approval record stores approver, time, note, and the spec/data/source
fingerprint. It provides an audit trail and stale-input check, not identity
verification or scientific validity.
