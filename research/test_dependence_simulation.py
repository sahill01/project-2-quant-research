"""Synthetic-only contract tests for dependence simulation mechanics."""

import numpy as np
import pandas as pd

from research.dependence_simulation import (
    METHODS,
    SCENARIOS,
    Scenario,
    bootstrap_interval,
    generate_dataset,
    support_diagnostics,
    _interval_from_draws,
)


def test_generator_is_reproducible_and_contains_repeated_overlapping_events():
    scenario = next(s for s in SCENARIOS if s.name == "persistent_repeated_zones")
    first = generate_dataset(scenario, 0.25, seed=417)
    second = generate_dataset(scenario, 0.25, seed=417)
    pd.testing.assert_frame_equal(first, second)
    assert first.groupby("zone").size().max() > 1
    same_zone = first.loc[first.cohort == 0].sort_values(["zone", "period"])
    pair_found = False
    for _, group in same_zone.groupby("zone"):
        periods = group.period.to_numpy()
        if any(0 < periods[j] - periods[i] < 6
               for i in range(len(periods)) for j in range(i + 1, len(periods))):
            pair_found = True
            break
    assert pair_found, "fixture should contain overlapping six-period outcome windows"
    assert first.window_component.notna().all()


def test_null_and_effect_dgp_share_structure_and_shift_only_higher_low_mean():
    scenario = next(s for s in SCENARIOS if s.name == "serial_overlapping_shared_shocks")
    null = generate_dataset(scenario, 0.0, seed=514)
    alternative = generate_dataset(scenario, 0.25, seed=514)
    pd.testing.assert_frame_equal(
        null.drop(columns="outcome"), alternative.drop(columns="outcome"),
    )
    delta = alternative.outcome.to_numpy() - null.outcome.to_numpy()
    np.testing.assert_allclose(delta, np.where(null.cohort.to_numpy() == 0, 0.25, 0.0))
    shared_periods = null.groupby("period").filter(lambda g: g.zone.nunique() > 1)
    for _, group in shared_periods.groupby("period"):
        assert group.window_component.nunique() == 1


def test_support_gate_distinguishes_events_zones_periods_and_concentration():
    events = pd.DataFrame({
        "cohort": [0] * 40 + [1] * 40,
        "zone": [0] * 37 + [1, 2, 3] + [4] * 37 + [5, 6, 7],
        "period": list(range(40)) + list(range(40)),
        "outcome": np.linspace(-1, 1, 80),
    })
    support = support_diagnostics(events)
    assert support["events_higher"] == 40
    assert support["zones_higher"] == 4
    assert support["kish_zones_higher"] < 2
    assert support["periods_higher"] == 40
    assert support["blocks_higher"] >= 4
    assert support["support_sufficient"]


def test_few_zones_or_periods_returns_inconclusive_not_iid_fallback():
    scenario = next(s for s in SCENARIOS if s.name == "few_independent_zones")
    events = generate_dataset(scenario, 0.25, seed=91)
    for method in METHODS:
        result = bootstrap_interval(events, method, seed=100 + METHODS.index(method), draws=40)
        assert result["inconclusive"]
        assert np.isnan(result["lower"])
    few_periods = Scenario("tiny", 8, 5, 4)
    tiny = generate_dataset(few_periods, 0.0, seed=92)
    assert not support_diagnostics(tiny)["support_sufficient"]
    for method in METHODS:
        result = bootstrap_interval(tiny, method, seed=40 + METHODS.index(method), draws=20)
        assert result["inconclusive"]


def test_bootstrap_methods_are_deterministic_and_intervals_finite_when_supported():
    scenario = Scenario("supported_synthetic", 12, 48, 5, zone_sd=0.3,
                        period_sd=0.2, ar1=0.4, shared_period_shock=True)
    events = generate_dataset(scenario, 0.25, seed=312)
    assert support_diagnostics(events)["support_sufficient"]
    for method in METHODS:
        left = bootstrap_interval(events, method, seed=811, draws=80)
        right = bootstrap_interval(events, method, seed=811, draws=80)
        assert left == right
        assert not left["inconclusive"]
        assert np.isfinite(left["estimate"])
        assert np.isfinite(left["lower"])
        assert left["lower"] <= left["upper"]


def test_differential_missingness_is_synthetic_and_reported_in_observed_counts():
    scenario = next(s for s in SCENARIOS if s.name == "cohort_differential_missingness")
    events = generate_dataset(scenario, 0.0, seed=2026)
    counts = events.groupby("cohort").size()
    assert counts.loc[0] > counts.loc[1]
    assert set(events.columns) == {"cohort", "zone", "period", "window_component", "outcome"}


def test_invalid_bootstrap_draws_are_counted_and_failure_is_inconclusive():
    accepted = _interval_from_draws(
        0.0, np.array([1.0] * 9 + [np.nan]), 10,
    )
    assert accepted["valid_draws"] == 9
    assert accepted["valid_draw_fraction"] == 0.9
    assert not accepted["inconclusive"]

    failed = _interval_from_draws(0.0, np.array([1.0] * 8 + [np.nan] * 2), 10)
    assert failed["valid_draws"] == 8
    assert failed["valid_draw_fraction"] == 0.8
    assert failed["inconclusive"]
    assert failed["inconclusive_reason"] == "too_many_invalid_bootstrap_draws"


def main():
    tests = [
        test_generator_is_reproducible_and_contains_repeated_overlapping_events,
        test_null_and_effect_dgp_share_structure_and_shift_only_higher_low_mean,
        test_support_gate_distinguishes_events_zones_periods_and_concentration,
        test_few_zones_or_periods_returns_inconclusive_not_iid_fallback,
        test_bootstrap_methods_are_deterministic_and_intervals_finite_when_supported,
        test_differential_missingness_is_synthetic_and_reported_in_observed_counts,
        test_invalid_bootstrap_draws_are_counted_and_failure_is_inconclusive,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
