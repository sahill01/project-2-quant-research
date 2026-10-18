"""Structured, testable specifications for future strategy hypotheses.

This module validates research documentation only. It does not generate
features, signals, or trades.
"""

from dataclasses import asdict, dataclass, field
import re


_UNRESOLVED_PLACEHOLDER = re.compile(
    r"^(?:UNRESOLVED|TBD|TODO|TO\s+BE\s+DETERMINED|PENDING)(?:\b.*)?$",
    re.IGNORECASE,
)


def _is_unresolved(value: str | None) -> bool:
    if value is None or not value.strip():
        return True
    return _UNRESOLVED_PLACEHOLDER.fullmatch(value.strip()) is not None


@dataclass(frozen=True)
class ResearchDecisions:
    """Methodological choices required before predictive evaluation.

    None means explicitly unresolved. This schema deliberately supplies no
    defaults for research decisions.
    """

    null_and_baseline: str | None = None
    event_definition: str | None = None
    outcome_horizon_and_calculation: str | None = None
    missing_candle_policy: str | None = None
    overlapping_event_treatment: str | None = None
    chronological_windows: str | None = None
    matching_method: str | None = None
    minimum_sample_rationale: str | None = None
    effect_size_criteria: str | None = None
    uncertainty_and_multiple_testing: str | None = None
    advancement_rejection_deferral: str | None = None

    def unresolved_fields(self) -> tuple[str, ...]:
        return tuple(
            name for name, value in asdict(self).items()
            if _is_unresolved(value)
        )

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if value is not None and not value.strip():
                raise ValueError(f"Research decision {name} must be non-empty or unresolved")

    def as_dict(self) -> dict[str, str | None]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class HypothesisSpec:
    hypothesis_id: str
    title: str
    market_rationale: str
    feature_definition: str
    signal_definition: str
    information_available_at: str
    entry_and_exit_assumptions: str
    expected_effect: str
    failure_conditions: tuple[str, ...]
    baseline_comparison: str
    sample_size_and_validation: str
    confounders: tuple[str, ...]
    transaction_cost_assumptions: str
    approval_status: str = "PROPOSED"
    hypothesis_version: int = 1
    decisions: ResearchDecisions = field(default_factory=ResearchDecisions)

    def validate(self) -> None:
        if self.hypothesis_version < 1:
            raise ValueError("Hypothesis version must be positive")
        required = {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "market_rationale": self.market_rationale,
            "feature_definition": self.feature_definition,
            "signal_definition": self.signal_definition,
            "information_available_at": self.information_available_at,
            "entry_and_exit_assumptions": self.entry_and_exit_assumptions,
            "expected_effect": self.expected_effect,
            "baseline_comparison": self.baseline_comparison,
            "sample_size_and_validation": self.sample_size_and_validation,
            "transaction_cost_assumptions": self.transaction_cost_assumptions,
        }
        missing = [key for key, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Hypothesis specification missing: {missing}")
        if not self.failure_conditions or any(not item.strip() for item in self.failure_conditions):
            raise ValueError("At least one explicit failure condition is required")
        if not self.confounders or any(not item.strip() for item in self.confounders):
            raise ValueError("At least one confounder must be documented")
        if self.approval_status.strip().upper() not in {
            "PROPOSED", "APPROVED", "REJECTED"
        }:
            raise ValueError("Approval status must be PROPOSED, APPROVED, or REJECTED")
        availability = self.information_available_at.lower()
        if "available_at" not in availability or "decision" not in availability:
            raise ValueError(
                "Availability must state how feature available_at constrains decisions"
            )
        self.decisions.validate()

    def as_dict(self) -> dict[str, object]:
        self.validate()
        result = asdict(self)
        result["approval_status"] = self.approval_status.strip().upper()
        return result


def validate_hypothesis(spec: HypothesisSpec) -> HypothesisSpec:
    spec.validate()
    return spec
