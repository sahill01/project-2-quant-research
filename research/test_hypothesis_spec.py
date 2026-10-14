"""Tests for complete causal hypothesis documentation."""

from dataclasses import replace

from research.hypothesis_spec import HypothesisSpec, validate_hypothesis


def example_spec() -> HypothesisSpec:
    return HypothesisSpec(
        hypothesis_id="HYP-SYN-001",
        title="Synthetic documentation example",
        market_rationale="This text exists only to test the schema.",
        feature_definition="A named scalar derived from closed candle data.",
        signal_definition="An exact, predeclared threshold maps to long, short, or flat.",
        information_available_at="Use only once feature available_at is before the decision.",
        entry_and_exit_assumptions="Signal at close; order fills at next bar open.",
        expected_effect="A measurable change in a preregistered baseline metric.",
        failure_conditions=("No improvement after costs",),
        baseline_comparison="Compare with unchanged Buy & Hold and EMA 20/50.",
        sample_size_and_validation="Predeclare sample size and untouched chronological holdout.",
        confounders=("Market regime",),
        transaction_cost_assumptions="Use the frozen taker fee and adverse slippage assumptions.",
    )


def test_complete_spec_is_accepted():
    assert validate_hypothesis(example_spec()).hypothesis_id == "HYP-SYN-001"


def test_missing_causal_availability_is_rejected():
    spec = replace(example_spec(), information_available_at="After candle close.")
    try:
        validate_hypothesis(spec)
    except ValueError as error:
        assert "available_at" in str(error)
    else:
        raise AssertionError("Hypothesis omitted the availability constraint")


def test_failure_conditions_and_confounders_are_required():
    for field in ("failure_conditions", "confounders"):
        spec = replace(example_spec(), **{field: ()})
        try:
            validate_hypothesis(spec)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Empty {field} were accepted")


def test_approval_status_is_explicitly_constrained():
    assert validate_hypothesis(example_spec()).approval_status == "PROPOSED"
    approved = replace(example_spec(), approval_status="APPROVED")
    assert validate_hypothesis(approved).approval_status == "APPROVED"
    invalid = replace(example_spec(), approval_status="MAYBE")
    try:
        validate_hypothesis(invalid)
    except ValueError as error:
        assert "Approval status" in str(error)
    else:
        raise AssertionError("Invalid approval status was accepted")


def main():
    tests = [
        test_complete_spec_is_accepted,
        test_missing_causal_availability_is_rejected,
        test_failure_conditions_and_confounders_are_required,
        test_approval_status_is_explicitly_constrained,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
