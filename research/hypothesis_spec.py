"""Structured, testable specifications for future strategy hypotheses.

This module validates research documentation only. It does not generate
features, signals, or trades.
"""

from dataclasses import dataclass


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

    def validate(self) -> None:
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


def validate_hypothesis(spec: HypothesisSpec) -> HypothesisSpec:
    spec.validate()
    return spec
