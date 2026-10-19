"""Synthetic-only regressions for causal feature-event-study primitives."""

from dataclasses import replace
from hashlib import sha256
import io
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from research.event_study import (
    EventStudySpec,
    OutcomeRule,
    _EVENT_LEDGER_COLUMNS,
    _OUTCOME_COLUMNS,
    assign_event_partitions,
    authorize_event_study_holdout,
    build_event_study_manifest,
    canonical_json,
    calculate_forward_close_outcomes,
    classify_registered_decision,
    create_event_study_approval,
    event_study_spec_fingerprint,
    lock_event_study_plan,
    prepare_support_touch_events,
    summarize_event_contrast,
    validate_event_study_execution,
    validate_test_family,
    verify_event_study_bundle,
    write_json_no_clobber,
)
from research.experiment_protocol import TemporalSplit, TimeWindow
from research import event_study_runner as _event_study_runner
from research.event_study_runner import required_event_study_source_files, run_event_study


def swing_fixture() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01T00:00:00Z", periods=13, freq="1h")
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "open": [10.0, 10.0, 10.0, 9.0, 9.0, 10.0, 8.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0],
        "high": [11.0, 12.0, 11.0, 10.0, 10.0, 11.0, 9.0, 10.0, 9.5, 10.0, 9.5, 10.0, 10.0],
        "low": [9.0, 8.0, 9.0, 8.5, 7.0, 9.0, 7.0, 9.0, 8.5, 9.0, 8.5, 9.0, 9.0],
        "close": [10.0, 10.0, 10.0, 9.0, 8.0, 9.0, 8.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0],
        "volume": [100.0] * 13,
    })


def test_support_touch_cohorts_join_confirmed_structure_causally_and_retain_repeats():
    candles = swing_fixture()
    events = prepare_support_touch_events(
        candles, asset="SYN", timeframe="1h", left_bars=1, right_bars=1,
        zone_width_fraction=0.02,
    )
    assert events["event_id"].is_unique
    assert events["asset"].eq("SYN").all()
    assert events["timeframe"].eq("1h").all()
    assert (events["origin_available_at"] <= events["created_at"]).all()
    assert (events["created_at"] <= events["available_at"]).all()
    assert (events.loc[events.event_type == "touched", "created_at"] <
            events.loc[events.event_type == "touched", "available_at"]).all()
    assert all(
        row.source_event_time == row.source_payload["event_time"]
        and row.source_event_time == row.available_at
        for row in events.itertuples()
    )
    eligible = events.loc[events.eligible]
    assert set(eligible.cohort) == {"higher_low", "lower_low"}
    assert eligible.groupby("zone_id").size().max() >= 1
    support_touches = events.loc[(events.zone_type == "support") & (events.event_type == "touched")]
    assert support_touches.groupby("zone_id").size().max() >= 2
    assert support_touches.groupby("available_at").zone_id.nunique().max() >= 2
    assert (events.loc[~events.eligible, "exclusion_reason"].notna()).all()

    prefix_end = candles.loc[10, "available_at"]
    prefix = prepare_support_touch_events(
        candles.iloc[:11].copy(), asset="SYN", timeframe="1h", left_bars=1,
        right_bars=1, zone_width_fraction=0.02,
    )
    before = events.loc[events.available_at <= prefix_end].reset_index(drop=True)
    pd.testing.assert_frame_equal(before, prefix.reset_index(drop=True))

    perturbed = candles.copy()
    perturbed.loc[11:, ["open", "high", "low", "close"]] = [
        [10.0, 12.0, 9.5, 11.0], [11.0, 12.5, 10.0, 12.0]
    ]
    changed = prepare_support_touch_events(
        perturbed, asset="SYN", timeframe="1h", left_bars=1, right_bars=1,
        zone_width_fraction=0.02,
    )
    pd.testing.assert_frame_equal(
        events.loc[events.available_at <= prefix_end].reset_index(drop=True),
        changed.loc[changed.available_at <= prefix_end].reset_index(drop=True),
    )


def test_support_touch_builder_rejects_invalid_timing():
    candles = swing_fixture()
    bad = candles.copy()
    bad.loc[3, "available_at"] += pd.Timedelta(minutes=1)
    try:
        prepare_support_touch_events(
            bad, asset="SYN", timeframe="1h", left_bars=1, right_bars=1,
            zone_width_fraction=0.02,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Inconsistent candle availability was accepted")


def event_rows(candles: pd.DataFrame, positions: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": [f"E{i}" for i in positions],
        "eligible": [True] * len(positions),
        "cohort": ["higher_low"] * len(positions),
        "zone_id": [f"Z{i}" for i in positions],
        "anchor_timestamp": [candles.timestamp.iloc[i] for i in positions],
        "available_at": [candles.available_at.iloc[i] for i in positions],
    })


def price_candles(opens: list[str], closes: list[float]) -> pd.DataFrame:
    timestamps = pd.to_datetime(opens, utc=True)
    return pd.DataFrame({
        "timestamp": timestamps,
        "available_at": timestamps + pd.Timedelta(hours=1),
        "close": closes,
    })


def test_fixed_observed_bar_outcome_reports_elapsed_time_and_gap_without_filling():
    candles = price_candles([
        "2026-02-01T00:00Z", "2026-02-01T01:00Z",
        "2026-02-01T03:00Z", "2026-02-01T04:00Z", "2026-02-01T05:00Z",
    ], [10.0, 11.0, 12.0, 14.0, 9.0])
    events = event_rows(candles, [1])
    result = calculate_forward_close_outcomes(
        events, candles, timeframe="1h",
        rule=OutcomeRule("fixed_observed_bars", 2, "exact", None,
                         "allow_and_report", "exclude"),
        data_role="synthetic",
    ).iloc[0]
    assert abs(result.outcome_return - (14.0 / 11.0 - 1.0)) < 1e-12
    assert result.target_timestamp == candles.timestamp.iloc[3]
    assert result.target_available_at == candles.available_at.iloc[3]
    assert result.realized_elapsed == pd.Timedelta(hours=3)
    assert result.observed_bars_forward == 2
    assert result.missing_candle_gaps == 1

    future_perturbation = candles.copy()
    future_perturbation.loc[4, "close"] = 1000.0
    unchanged = calculate_forward_close_outcomes(
        events, future_perturbation, timeframe="1h",
        rule=OutcomeRule("fixed_observed_bars", 2, "exact", None,
                         "allow_and_report", "exclude"),
        data_role="synthetic",
    ).iloc[0]
    assert unchanged.outcome_return == result.outcome_return

    excluded = calculate_forward_close_outcomes(
        events, candles, timeframe="1h",
        rule=OutcomeRule("fixed_observed_bars", 2, "exact", None,
                         "exclude_if_gap", "exclude"),
        data_role="synthetic",
    ).iloc[0]
    assert not excluded.outcome_included
    assert excluded.outcome_exclusion_reason == "missing_candle_inside_outcome_window"
    assert excluded.missing_candle_gaps == 1
    assert excluded.target_timestamp == candles.timestamp.iloc[3]
    assert excluded.realized_elapsed == pd.Timedelta(hours=3)
    assert excluded.observed_bars_forward == 2


def test_synthetic_repeats_and_overlapping_outcome_windows_remain_distinct():
    candles = price_candles([
        "2026-02-01T00:00Z", "2026-02-01T01:00Z", "2026-02-01T02:00Z",
        "2026-02-01T03:00Z", "2026-02-01T04:00Z",
    ], [10.0, 11.0, 12.0, 13.0, 14.0])
    events = pd.DataFrame({
        "event_id": ["repeat-1", "repeat-2", "shared-anchor"],
        "eligible": [True, True, True],
        "cohort": ["higher_low", "higher_low", "lower_low"],
        "zone_id": ["zone-A", "zone-A", "zone-B"],
        "anchor_timestamp": [candles.timestamp.iloc[0], candles.timestamp.iloc[1], candles.timestamp.iloc[0]],
        "available_at": [candles.available_at.iloc[0], candles.available_at.iloc[1], candles.available_at.iloc[0]],
    })
    outcomes = calculate_forward_close_outcomes(
        events, candles, timeframe="1h",
        rule=OutcomeRule("fixed_observed_bars", 2, "exact", None,
                         "allow_and_report", "exclude"),
        data_role="synthetic",
    )
    assert outcomes.outcome_included.all()
    assert outcomes.event_id.tolist() == ["repeat-1", "repeat-2", "shared-anchor"]
    assert outcomes.zone_id.tolist().count("zone-A") == 2
    assert outcomes.target_available_at.iloc[0] == outcomes.target_available_at.iloc[2]
    first_window = (outcomes.available_at.iloc[0], outcomes.target_available_at.iloc[0])
    second_window = (outcomes.available_at.iloc[1], outcomes.target_available_at.iloc[1])
    assert max(first_window[0], second_window[0]) < min(first_window[1], second_window[1])


def test_elapsed_endpoint_exact_and_first_after_rules_and_tolerance():
    candles = price_candles([
        "2026-02-01T00:00Z", "2026-02-01T01:00Z", "2026-02-01T02:00Z",
        "2026-02-01T03:00Z",
    ], [10.0, 11.0, 12.0, 13.0])
    events = event_rows(candles, [0])
    exact = calculate_forward_close_outcomes(
        events, candles, timeframe="1h",
        rule=OutcomeRule("fixed_elapsed_time", "2h", "exact", None,
                         "allow_and_report", "exclude"),
        data_role="synthetic",
    ).iloc[0]
    assert exact.target_available_at == candles.available_at.iloc[2]
    assert abs(exact.outcome_return - 0.2) < 1e-12

    after = calculate_forward_close_outcomes(
        events, candles, timeframe="1h",
        rule=OutcomeRule("fixed_elapsed_time", "150min", "first_close_at_or_after", "30min",
                         "allow_and_report", "exclude"),
        data_role="synthetic",
    ).iloc[0]
    assert after.requested_target_at == pd.Timestamp("2026-02-01T03:30:00Z")
    assert after.target_available_at == candles.available_at.iloc[3]
    assert after.observed_bars_forward == 3

    late = calculate_forward_close_outcomes(
        events, candles, timeframe="1h",
        rule=OutcomeRule("fixed_elapsed_time", "150min", "first_close_at_or_after", "1min",
                         "allow_and_report", "exclude"),
        data_role="synthetic",
    ).iloc[0]
    assert not late.outcome_included
    assert late.outcome_exclusion_reason == "endpoint_unavailable_or_outside_tolerance"


def test_outcome_calculator_rejects_anchor_endpoint_duplicates_and_bad_prices():
    candles = price_candles([
        "2026-02-01T00:00Z", "2026-02-01T01:00Z", "2026-02-01T02:00Z",
    ], [10.0, 11.0, 12.0])
    events = event_rows(candles, [1])
    rule = OutcomeRule("fixed_observed_bars", 1, "exact", None,
                       "allow_and_report", "exclude")
    same_anchor = replace(rule, horizon_value=0)
    for candidate_events, candidate_candles, candidate_rule in (
        (pd.concat([events, events], ignore_index=True), candles, rule),
        (events.assign(eligible=["False"]), candles, rule),
        (events.assign(anchor_timestamp=pd.Timestamp("2026-02-01T00:00Z")), candles, rule),
        (events, candles.assign(close=[10.0, float("inf"), 12.0]), rule),
        (events, candles, same_anchor),
    ):
        try:
            calculate_forward_close_outcomes(
                candidate_events, candidate_candles, timeframe="1h",
                rule=candidate_rule, data_role="synthetic",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid outcome input was accepted")

    no_endpoint = calculate_forward_close_outcomes(
        events, candles, timeframe="1h",
        rule=OutcomeRule("fixed_observed_bars", 3, "exact", None,
                         "allow_and_report", "exclude"),
        data_role="synthetic",
    ).iloc[0]
    assert not no_endpoint.outcome_included
    assert no_endpoint.outcome_exclusion_reason == "endpoint_unavailable_or_outside_tolerance"

    for invalid_rule in (
        OutcomeRule("fixed_elapsed_time", "NaT", "exact", None,
                    "allow_and_report", "exclude"),
        OutcomeRule("fixed_elapsed_time", "1h", "first_close_at_or_after", "NaT",
                    "allow_and_report", "exclude"),
    ):
        try:
            invalid_rule.validate()
        except ValueError:
            pass
        else:
            raise AssertionError("Missing/NaT outcome duration was accepted")


def test_temporal_assignment_uses_utc_half_open_boundaries_and_purges_crossings():
    split = TemporalSplit(
        TimeWindow("2026-03-01T00:00:00Z", "2026-03-01T02:00:00Z"),
        TimeWindow("2026-03-01T02:00:00Z", "2026-03-01T04:00:00Z"),
        TimeWindow("2026-03-01T04:00:00Z", "2026-03-01T06:00:00Z"),
    )
    frame = pd.DataFrame({
        "event_id": ["before", "boundary", "cross", "holdout"],
        "available_at": pd.to_datetime([
            "2026-02-28T23:00Z", "2026-03-01T02:00Z",
            "2026-03-01T03:00Z", "2026-03-01T04:00Z",
        ], utc=True),
        "target_available_at": pd.to_datetime([
            "2026-03-01T01:00Z", "2026-03-01T03:00Z",
            "2026-03-01T04:00Z", "2026-03-01T05:00Z",
        ], utc=True),
        "outcome_included": [True] * 4,
    })
    result = assign_event_partitions(frame, split, boundary_policy="purge")
    assert result.partition.tolist()[1:] == ["validation", "validation", "holdout"]
    assert result.loc[result.event_id == "cross", "split_exclusion_reason"].iloc[0] == "outcome_window_crosses_partition_boundary"
    assert not result.loc[result.event_id == "cross", "partition_eligible"].iloc[0]
    try:
        assign_event_partitions(frame, split, boundary_policy="error")
    except ValueError as error:
        assert "crosses" in str(error)
    else:
        raise AssertionError("Cross-boundary outcome was accepted under error policy")


def test_split_rejects_naive_and_duplicate_event_times_and_applies_embargo():
    split = TemporalSplit(
        TimeWindow("2026-03-01T00:00:00Z", "2026-03-01T02:00:00Z"),
        TimeWindow("2026-03-01T02:00:00Z", "2026-03-01T04:00:00Z"),
        TimeWindow("2026-03-01T04:00:00Z", "2026-03-01T06:00:00Z"),
    )
    base = pd.DataFrame({
        "event_id": ["A"], "available_at": pd.to_datetime(["2026-03-01T00:30Z"], utc=True),
        "target_available_at": pd.to_datetime(["2026-03-01T01:00Z"], utc=True),
        "outcome_included": [True],
    })
    embargoed = assign_event_partitions(base, split, boundary_policy="purge", embargo="1h")
    assert not embargoed.partition_eligible.iloc[0]
    for frame in (
        base.assign(available_at=pd.to_datetime(["2026-03-01T00:30"])),
        pd.concat([base, base], ignore_index=True),
    ):
        try:
            assign_event_partitions(frame, split, boundary_policy="purge")
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid or duplicate split event was accepted")
    try:
        assign_event_partitions(base, split, boundary_policy="purge", embargo="NaT")
    except ValueError:
        pass
    else:
        raise AssertionError("NaT embargo was accepted")


def test_descriptive_contrast_counts_unique_zones_and_decision_helper_uses_given_criteria():
    ledger = pd.DataFrame({
        "eligible": [True, True, True, True, False],
        "cohort": ["higher_low", "higher_low", "lower_low", "lower_low", "higher_low"],
        "zone_id": ["A", "A", "B", "C", "D"],
        "outcome_return": [0.1, -0.1, 0.0, 0.02, 100.0],
    })
    summary = summarize_event_contrast(ledger, missing_policy="error")
    assert summary["groups"]["higher_low"]["event_count"] == 2
    assert summary["groups"]["higher_low"]["unique_zone_count"] == 1
    assert summary["groups"]["lower_low"]["unique_zone_count"] == 2
    assert abs(summary["mean_difference"] + 0.01) < 1e-12
    assert summary["inferential_status"].startswith("descriptive_only")
    assert classify_registered_decision(
        estimate=0.03, lower_bound=0.02, upper_bound=0.04, minimum_effect=0.01,
        higher_low_count=30, lower_low_count=30, minimum_count_per_group=20,
    ) == "advance_to_next_gate"
    assert classify_registered_decision(
        estimate=-0.01, lower_bound=-0.02, upper_bound=-0.001, minimum_effect=0.01,
        higher_low_count=30, lower_low_count=30, minimum_count_per_group=20,
    ) == "reject_directional_hypothesis"
    assert classify_registered_decision(
        estimate=0.02, lower_bound=-0.01, upper_bound=0.04, minimum_effect=0.01,
        higher_low_count=4, lower_low_count=30, minimum_count_per_group=20,
    ) == "defer_inconclusive"


def unresolved_spec() -> EventStudySpec:
    return EventStudySpec(
        hypothesis_id="HYP-SYN-001", hypothesis_version=1,
        event_definition=None, cohort_labels=None, event_anchor_semantics=None,
        availability_semantics=None, origin_join_keys=None,
        causal_availability_rule=None, outcome_formula=None,
        horizon_convention=None, horizon_value=None, endpoint_rule=None,
        max_lateness=None, asset_timeframe_scope=None, feature_parameters=None,
        missing_data_policy=None, incomplete_window_policy=None,
        repeated_touch_policy=None, overlapping_event_policy=None,
        split=None, boundary_policy=None, embargo=None, estimand=None,
        uncertainty_method=None, multiplicity_family=None,
        decision_criteria=None, minimum_sample_rationale=None,
        meaningful_effect_threshold=None, data_file_hashes=None,
        source_file_hashes=None,
    )


def resolved_synthetic_spec(data_path: Path, source_path: Path) -> EventStudySpec:
    return EventStudySpec(
        hypothesis_id="HYP-SYN-001", hypothesis_version=1,
        event_definition="Synthetic support-zone touch",
        cohort_labels=("higher_low", "lower_low"),
        event_anchor_semantics="Touch candle close",
        availability_semantics="Use only at available_at",
        origin_join_keys=("zone_id", "pivot_time", "swing_low_pivot_time"),
        causal_availability_rule="origin availability <= touch availability",
        outcome_formula="(C_future / C_anchor) - 1",
        horizon_convention="fixed_observed_bars", horizon_value=2,
        endpoint_rule="exact", max_lateness=None,
        asset_timeframe_scope=(("SYN", "1h"),),
        feature_parameters={"left_bars": 1, "right_bars": 1, "zone_width_fraction": 0.02},
        missing_data_policy="exclude_if_gap", incomplete_window_policy="exclude",
        repeated_touch_policy="retain", overlapping_event_policy="cluster_by_zone_and_time",
        split=TemporalSplit(
            TimeWindow("2026-01-01T00:00Z", "2026-01-02T00:00Z"),
            TimeWindow("2026-01-02T00:00Z", "2026-01-03T00:00Z"),
            TimeWindow("2026-01-03T00:00Z", "2026-01-04T00:00Z"),
        ),
        boundary_policy="purge", embargo="1h",
        estimand="mean higher_low outcome minus mean lower_low outcome",
        uncertainty_method="synthetic contract only; method predeclared",
        multiplicity_family=("primary_contrast",),
        decision_criteria="synthetic decision fixture",
        minimum_sample_rationale="synthetic only",
        meaningful_effect_threshold=0.01,
        data_file_hashes={"SYN": sha256(data_path.read_bytes()).hexdigest()},
        source_file_hashes={"runner.py": sha256(source_path.read_bytes()).hexdigest()},
        approval_status="APPROVED",
    )


def test_unresolved_spec_blocks_approval_and_fingerprint_is_deterministic():
    spec = unresolved_spec()
    assert "horizon_value" in spec.unresolved_fields()
    spec.validate()
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data.csv"
        source = root / "runner.py"
        data.write_text("synthetic data\n", encoding="utf-8")
        source.write_text("synthetic source\n", encoding="utf-8")
        resolved = resolved_synthetic_spec(data, source)
        assert event_study_spec_fingerprint(resolved) == event_study_spec_fingerprint(resolved)
        elapsed = replace(
            resolved, horizon_convention="fixed_elapsed_time",
            horizon_value=pd.Timedelta(hours=2), endpoint_rule="exact",
        )
        assert event_study_spec_fingerprint(elapsed) == event_study_spec_fingerprint(elapsed)
        try:
            create_event_study_approval(
                replace(resolved, approval_status="DRAFT"), {"SYN": data}, {"runner.py": source},
                approver="test", approved_at_utc="2026-01-01T00:00Z", allowed_stages=("development",),
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("Draft spec received an approval record")


def test_approval_binds_spec_data_sources_and_allowed_stage():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data.csv"
        source = root / "runner.py"
        data.write_text("synthetic data\n", encoding="utf-8")
        source.write_text("synthetic source\n", encoding="utf-8")
        spec = resolved_synthetic_spec(data, source)
        approval = create_event_study_approval(
            spec, {"SYN": data}, {"runner.py": source}, approver="synthetic reviewer",
            approved_at_utc="2026-01-01T00:00Z", allowed_stages=("development", "validation"),
        )
        validate_event_study_execution(
            spec, approval, stage="development", data_files={"SYN": data}, source_files={"runner.py": source},
        )
        for candidate_spec, stage in (
            (replace(spec, outcome_formula="altered"), "development"),
            (spec, "holdout"),
        ):
            try:
                validate_event_study_execution(
                    candidate_spec, approval, stage=stage,
                    data_files={"SYN": data}, source_files={"runner.py": source},
                )
            except PermissionError:
                pass
            else:
                raise AssertionError("Changed specification or unauthorized stage passed")
        data.write_text("changed synthetic data\n", encoding="utf-8")
        try:
            validate_event_study_execution(
                spec, approval, stage="development", data_files={"SYN": data},
                source_files={"runner.py": source},
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("Stale data passed approval verification")

        data.write_text("synthetic data\n", encoding="utf-8")
        source.write_text("changed synthetic source\n", encoding="utf-8")
        try:
            validate_event_study_execution(
                spec, approval, stage="development", data_files={"SYN": data},
                source_files={"runner.py": source},
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("Stale source passed approval verification")


def test_approval_hashes_full_inputs_without_read_bytes_materialization():
    from unittest.mock import patch

    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data.csv"
        source = root / "runner.py"
        data.write_text("synthetic data\n", encoding="utf-8")
        source.write_text("synthetic source\n", encoding="utf-8")
        spec = resolved_synthetic_spec(data, source)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("read_bytes called")):
            approval = create_event_study_approval(
                spec, {"SYN": data}, {"runner.py": source},
                approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
                allowed_stages=("development",),
            )
        assert approval.data_files["SYN"]["sha256"] == spec.data_file_hashes["SYN"]
        assert approval.source_files["runner.py"]["sha256"] == spec.source_file_hashes["runner.py"]


def test_research_outcome_requires_approved_execution_guard():
    candles = price_candles([
        "2026-02-01T00:00Z", "2026-02-01T01:00Z", "2026-02-01T02:00Z",
    ], [10.0, 11.0, 12.0])
    events = event_rows(candles, [0])
    try:
        calculate_forward_close_outcomes(
            events, candles, timeframe="1h",
            rule=OutcomeRule("fixed_observed_bars", 1, "exact", None,
                             "allow_and_report", "exclude"),
            data_role="research",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("Research outcome ran without approval provenance")


def test_approved_research_outcome_blocks_split_crossing_and_rule_mismatch():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data.csv"
        source = root / "runner.py"
        data.write_text("synthetic research-role fixture\n", encoding="utf-8")
        source.write_text("synthetic implementation fixture\n", encoding="utf-8")
        spec = resolved_synthetic_spec(data, source)
        approval = create_event_study_approval(
            spec, {"SYN": data}, {"runner.py": source}, approver="synthetic reviewer",
            approved_at_utc="2026-01-01T00:00Z", allowed_stages=("development",),
        )
        full_candles = price_candles([
            "2026-01-01T20:00Z", "2026-01-01T21:00Z",
            "2026-01-01T22:00Z", "2026-01-01T23:00Z",
        ], [10.0, 11.0, 12.0, 14.0])
        events = event_rows(full_candles, [1]).assign(asset="SYN", timeframe="1h")
        candles = full_candles.iloc[:3].copy()  # All closes are before the stage end.
        result = calculate_forward_close_outcomes(
            events, candles, timeframe="1h",
            rule=OutcomeRule("fixed_observed_bars", 2, "exact", None,
                             "exclude_if_gap", "exclude"),
            data_role="research", spec=spec, approval=approval, stage="development",
            data_files={"SYN": data}, source_files={"runner.py": source},
            stage_data_truncated=True,
        ).iloc[0]
        assert not result.outcome_included
        assert result.outcome_exclusion_reason == "outcome_window_crosses_partition_boundary"
        assert pd.isna(result.outcome_return)

        try:
            calculate_forward_close_outcomes(
                events, candles, timeframe="1h",
                rule=OutcomeRule("fixed_observed_bars", 1, "exact", None,
                                 "exclude_if_gap", "exclude"),
                data_role="research", spec=spec, approval=approval, stage="development",
                data_files={"SYN": data}, source_files={"runner.py": source},
                stage_data_truncated=True,
            )
        except PermissionError as error:
            assert "differs" in str(error)
        else:
            raise AssertionError("Outcome rule differing from approved spec was accepted")

        error_spec = replace(spec, boundary_policy="error")
        error_approval = create_event_study_approval(
            error_spec, {"SYN": data}, {"runner.py": source},
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("development",),
        )
        try:
            calculate_forward_close_outcomes(
                events, candles, timeframe="1h",
                rule=OutcomeRule("fixed_observed_bars", 2, "exact", None,
                                 "exclude_if_gap", "exclude"),
                data_role="research", spec=error_spec, approval=error_approval,
                stage="development", data_files={"SYN": data},
                source_files={"runner.py": source},
                stage_data_truncated=True,
            )
        except ValueError as error:
            assert "crosses" in str(error)
        else:
            raise AssertionError("Cross-boundary outcome passed under error policy")

        future_poisoned = full_candles.copy()
        future_poisoned.loc[3, "close"] = float("inf")
        try:
            calculate_forward_close_outcomes(
                events, future_poisoned, timeframe="1h",
                rule=OutcomeRule("fixed_observed_bars", 2, "exact", None,
                                 "exclude_if_gap", "exclude"),
                data_role="research", spec=spec, approval=approval,
                stage="development", data_files={"SYN": data},
                source_files={"runner.py": source}, stage_data_truncated=True,
            )
        except PermissionError as error:
            assert "authorized stage end" in str(error)
        else:
            raise AssertionError("Research helper accepted a stage-boundary candle")


def test_manifest_is_deterministic_contained_and_no_clobber():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data.csv"
        source = root / "runner.py"
        run_id = "synthetic-run"
        run_dir = root / run_id
        run_dir.mkdir()
        data.write_text("synthetic data\n", encoding="utf-8")
        source.write_text("synthetic source\n", encoding="utf-8")
        spec = resolved_synthetic_spec(data, source)
        approval = create_event_study_approval(
            spec, {"SYN": data}, {"runner.py": source}, approver="synthetic reviewer",
            approved_at_utc="2026-01-01T00:00Z", allowed_stages=("development",),
        )
        spec_hash = event_study_spec_fingerprint(spec)
        documents = {
            "specification": spec.as_dict(),
            "data_quality": {
                "schema_version": 1, "stage": "development", "scope": {"SYN": {}}
            },
            "summary": {
                "run_id": run_id, "stage": "development",
                "specification_sha256": spec_hash,
                "scientific_status": "not_assessed",
                "inferential_status": "descriptive_only_no_uncertainty_or_significance_claim",
            },
            "validation": {
                "schema_version": 1, "run_id": run_id, "stage": "development",
                "specification_sha256": spec_hash, "computation_status": "completed",
                "scientific_status": "not_assessed",
                "checks": {
                    key: True for key in (
                        "approved_spec_and_current_hashes", "requested_stage_authorized",
                        "only_stage_prefix_ohlcv_materialized", "cohort_and_outcome_rows_within_scope",
                        "included_outcomes_finite_and_after_anchor",
                        "included_outcomes_before_stage_end",
                    )
                },
                "counts": {"event_rows": 0, "outcome_rows": 0, "exclusion_rows": 0},
            },
        }
        outputs = {}
        csv_headers = {
            "events": ",".join(_EVENT_LEDGER_COLUMNS) + "\n",
            "outcomes": ",".join(
                list(_EVENT_LEDGER_COLUMNS) + list(_OUTCOME_COLUMNS)
                + ["partition", "split_exclusion_reason", "partition_eligible"]
            ) + "\n",
            "exclusions": "event_id,asset,timeframe,exclusion_stage,reason\n",
        }
        for name, content in csv_headers.items():
            path = run_dir / f"{name}.csv"
            path.write_text(content, encoding="utf-8")
            outputs[name] = path
        for name, document in documents.items():
            path = run_dir / f"{name}.json"
            path.write_text(canonical_json(document) + "\n", encoding="utf-8")
            outputs[name] = path
        valid_event_bytes = outputs["events"].read_bytes()
        outputs["events"].write_text("event_id,eligible,available_at\n", encoding="utf-8")
        try:
            build_event_study_manifest(
                spec, approval, outputs=outputs, run_directory=run_dir,
                stage="development", data_files={"SYN": data}, source_files={"runner.py": source},
                run_id=run_id,
            )
        except ValueError as error:
            assert "schema" in str(error)
        else:
            raise AssertionError("Manifest builder certified arbitrary underspecified ledgers")
        outputs["events"].write_bytes(valid_event_bytes)
        manifest = build_event_study_manifest(
            spec, approval, outputs=outputs, run_directory=run_dir,
            stage="development", data_files={"SYN": data}, source_files={"runner.py": source},
            run_id=run_id,
        )
        outside = root / "outside.csv"
        outside.write_text("outside\n", encoding="utf-8")
        symlink = run_dir / "events-link.csv"
        symlink.symlink_to(outside)
        try:
            build_event_study_manifest(
                spec, approval, outputs={**outputs, "events": symlink},
                run_directory=run_dir, stage="development",
                data_files={"SYN": data}, source_files={"runner.py": source},
                run_id=run_id,
            )
        except ValueError as error:
            assert "contained" in str(error)
        else:
            raise AssertionError("Manifest accepted a symlink escaping the run directory")
        symlink.unlink()
        internal_alias = run_dir / "events-alias.csv"
        internal_alias.symlink_to(outputs["events"])
        try:
            build_event_study_manifest(
                spec, approval, outputs={**outputs, "outcomes": internal_alias},
                run_directory=run_dir, stage="development",
                data_files={"SYN": data}, source_files={"runner.py": source},
                run_id=run_id,
            )
        except ValueError as error:
            assert "distinct files" in str(error)
        else:
            raise AssertionError("Manifest builder accepted aliased artifact paths")
        internal_alias.unlink()
        assert manifest == build_event_study_manifest(
            spec, approval, outputs=outputs, run_directory=run_dir,
            stage="development", data_files={"SYN": data}, source_files={"runner.py": source},
            run_id=run_id,
        )
        target = run_dir / "manifest.json"
        write_json_no_clobber(manifest, target)
        assert verify_event_study_bundle(run_dir)["scientific_status"] == "not_assessed"
        original = target.read_bytes()
        try:
            write_json_no_clobber(manifest, target)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Manifest writer overwrote an existing artifact")
        assert target.read_bytes() == original

        unexpected = run_dir / "unregistered.txt"
        unexpected.write_text("unexpected\n", encoding="utf-8")
        try:
            verify_event_study_bundle(run_dir)
        except ValueError as error:
            assert "unregistered" in str(error)
        else:
            raise AssertionError("Bundle verifier accepted an unregistered artifact")
        unexpected.unlink()

        try:
            build_event_study_manifest(
                spec, approval, outputs={**outputs, "events": outside}, run_directory=run_dir,
                stage="development", data_files={"SYN": data}, source_files={"runner.py": source},
                run_id=run_id,
            )
        except ValueError as error:
            assert "contained" in str(error)
        else:
            raise AssertionError("Manifest accepted an artifact outside run directory")

        duplicate_manifest = dict(manifest)
        duplicate_manifest["outputs"] = dict(manifest["outputs"])
        duplicate_manifest["outputs"]["outcomes"] = dict(
            duplicate_manifest["outputs"]["events"]
        )
        target.write_text(canonical_json(duplicate_manifest) + "\n", encoding="utf-8")
        try:
            verify_event_study_bundle(run_dir)
        except ValueError as error:
            assert "unique paths" in str(error)
        else:
            raise AssertionError("Bundle verifier accepted duplicate artifact paths")
        target.write_bytes(original)

        symlink = run_dir / "escape.csv"
        symlink.symlink_to(outside)
        escape_manifest = dict(manifest)
        escape_manifest["outputs"] = dict(manifest["outputs"])
        escape_manifest["outputs"]["events"] = {
            "path": symlink.name,
            "sha256": sha256(outside.read_bytes()).hexdigest(),
        }
        target.write_text(canonical_json(escape_manifest) + "\n", encoding="utf-8")
        try:
            verify_event_study_bundle(run_dir)
        except ValueError as error:
            assert "escapes" in str(error)
        else:
            raise AssertionError("Bundle verifier accepted a symlink escaping the run directory")
        symlink.unlink()
        target.write_bytes(original)

        internal_alias = run_dir / "events-alias.csv"
        internal_alias.symlink_to(outputs["events"])
        alias_manifest = dict(manifest)
        alias_manifest["outputs"] = dict(manifest["outputs"])
        alias_manifest["outputs"]["outcomes"] = {
            "path": internal_alias.name,
            "sha256": sha256(outputs["events"].read_bytes()).hexdigest(),
        }
        target.write_text(canonical_json(alias_manifest) + "\n", encoding="utf-8")
        try:
            verify_event_study_bundle(run_dir)
        except ValueError as error:
            assert "distinct files" in str(error)
        else:
            raise AssertionError("Bundle verifier accepted symlink aliases as distinct artifacts")
        internal_alias.unlink()
        target.write_bytes(original)

        outputs["events"].unlink()
        try:
            verify_event_study_bundle(run_dir)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Bundle verifier accepted a missing artifact")

        outputs["events"].write_text("tampered\n", encoding="utf-8")
        try:
            verify_event_study_bundle(run_dir)
        except ValueError as error:
            assert "hash mismatch" in str(error)
        else:
            raise AssertionError("Bundle verification accepted a modified artifact")


def stage_runner_spec(data_path: Path, source_files, *, boundary_policy="purge"):
    base = resolved_synthetic_spec(data_path, next(iter(source_files.values())))
    return replace(
        base,
        event_definition="confirmed_support_zone_touch_by_origin_swing_low_v1",
        event_anchor_semantics="touch_candle_close",
        availability_semantics="touch_candle_available_at",
        causal_availability_rule=(
            "origin_confirmation_and_zone_creation_at_or_before_touch_availability"
        ),
        origin_join_keys=("zone_id", "pivot_time", "swing_low_pivot_time"),
        outcome_formula="(C_future/C_anchor)-1",
        repeated_touch_policy="retain_all",
        overlapping_event_policy="retain_separately",
        uncertainty_method="not_performed_descriptive_only",
        asset_timeframe_scope=(("SYN", "1h"),),
        data_file_hashes={"SYN|1h": sha256(data_path.read_bytes()).hexdigest()},
        source_file_hashes={
            identity: sha256(path.read_bytes()).hexdigest()
            for identity, path in source_files.items()
        },
        split=TemporalSplit(
            TimeWindow("2026-01-01T00:00Z", "2026-01-01T20:00Z"),
            TimeWindow("2026-01-01T20:00Z", "2026-01-01T22:00Z"),
            TimeWindow("2026-01-01T22:00Z", "2026-01-02T00:00Z"),
        ),
        horizon_convention="fixed_observed_bars",
        horizon_value=2,
        endpoint_rule="exact",
        max_lateness=None,
        boundary_policy=boundary_policy,
        embargo="2h",
    )


def runner_candles_with_invalid_future_values() -> pd.DataFrame:
    prefix = swing_fixture()
    tail_times = pd.date_range("2026-01-01T13:00:00Z", periods=12, freq="1h")
    tail = pd.DataFrame({
        "timestamp": tail_times,
        "open": [9.0] * len(tail_times),
        "high": [10.0] * len(tail_times),
        "low": [8.5] * len(tail_times),
        "close": [9.0] * len(tail_times),
        "volume": [100.0] * len(tail_times),
    })
    frame = pd.concat([prefix, tail], ignore_index=True)
    frame.loc[19:, "high"] = 1.0  # Invalid OHLC, at/after the development boundary.
    return frame


def test_runner_publishes_reproducible_stage_bounded_bundle_and_refuses_clobber():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "synthetic.csv"
        source_files = required_event_study_source_files()
        runner_candles_with_invalid_future_values().to_csv(data, index=False)
        spec = stage_runner_spec(data, source_files)
        approval = create_event_study_approval(
            spec, {"SYN|1h": data}, source_files,
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("development",),
        )
        first = run_event_study(
            spec, approval, stage="development", data_files={"SYN|1h": data},
            source_files=source_files, output_root=root / "out-a",
            run_id="synthetic-run",
        )
        second = run_event_study(
            spec, approval, stage="development", data_files={"SYN|1h": data},
            source_files=source_files, output_root=root / "out-b",
            run_id="synthetic-run",
        )
        manifest = verify_event_study_bundle(first)
        assert manifest["computation_status"] == "completed"
        assert manifest["scientific_status"] == "not_assessed"
        assert set(manifest["outputs"]) == {
            "specification", "events", "outcomes", "exclusions", "data_quality",
            "summary", "validation"
        }
        events = pd.read_csv(first / "events.csv")
        outcomes = pd.read_csv(first / "outcomes.csv")
        assert not events.empty
        assert (pd.to_datetime(events.available_at, utc=True) < pd.Timestamp("2026-01-01T20:00Z")).all()
        included = outcomes.loc[outcomes.outcome_included]
        assert not included.empty
        assert (pd.to_datetime(included.target_available_at, utc=True) <
                pd.Timestamp("2026-01-01T20:00Z")).all()
        assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
        for name, record in manifest["outputs"].items():
            assert (first / record["path"]).read_bytes() == (second / record["path"]).read_bytes(), name
        original_manifest = (first / "manifest.json").read_bytes()
        try:
            run_event_study(
                spec, approval, stage="development", data_files={"SYN|1h": data},
                source_files=source_files, output_root=root / "out-a",
                run_id="synthetic-run",
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("Runner overwrote an existing bundle")
        assert (first / "manifest.json").read_bytes() == original_manifest

        elapsed_spec = replace(
            spec, horizon_convention="fixed_elapsed_time", horizon_value="2h",
            endpoint_rule="exact",
        )
        elapsed_approval = create_event_study_approval(
            elapsed_spec, {"SYN|1h": data}, source_files,
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("development",),
        )
        elapsed_run = run_event_study(
            elapsed_spec, elapsed_approval, stage="development",
            data_files={"SYN|1h": data}, source_files=source_files,
            output_root=root / "out-elapsed", run_id="elapsed-run",
        )
        elapsed_outcomes = pd.read_csv(elapsed_run / "outcomes.csv")
        assert elapsed_outcomes.outcome_included.any()
        assert set(elapsed_outcomes.loc[elapsed_outcomes.outcome_included, "observed_bars_forward"]) == {2}


def test_horizon_embargo_and_explicit_locked_holdout_release():
    import json
    from unittest.mock import patch

    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "synthetic.csv"
        source_files = required_event_study_source_files()
        holdout_candles = runner_candles_with_invalid_future_values()
        holdout_candles["high"] = 10.0
        holdout_candles.to_csv(data, index=False)
        data_files = {"SYN|1h": data}
        spec = stage_runner_spec(data, source_files)
        approval = create_event_study_approval(
            spec, data_files, source_files,
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("development", "validation"),
        )
        try:
            create_event_study_approval(
                spec, data_files, source_files,
                approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
                allowed_stages=("development", "validation", "holdout"),
            )
        except ValueError as error:
            assert "separate release" in str(error)
        else:
            raise AssertionError("Initial approval directly authorized holdout")

        short_embargo = replace(spec, embargo="1h")
        short_approval = create_event_study_approval(
            short_embargo, data_files, source_files,
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("development", "validation"),
        )
        with patch("research.event_study_runner.load_ohlcv_before") as load_candles:
            try:
                run_event_study(
                    short_embargo, short_approval, stage="development",
                    data_files=data_files, source_files=source_files,
                    output_root=root / "short-embargo", run_id="short-embargo",
                )
            except ValueError as error:
                assert "shorter than" in str(error)
            else:
                raise AssertionError("Embargo shorter than the horizon was accepted")
            load_candles.assert_not_called()

        try:
            run_event_study(
                spec, approval, stage="holdout", data_files=data_files,
                source_files=source_files, output_root=root / "unreleased",
                run_id="unreleased",
            )
        except PermissionError as error:
            assert "separate release" in str(error)
        else:
            raise AssertionError("Holdout ran without explicit release")

        invalid_splits = (
            replace(spec, split=None),
            replace(spec, split=TemporalSplit(
                TimeWindow("2026-01-01T00:00Z", "2026-01-01T20:00Z"),
                TimeWindow("2026-01-01T19:00Z", "2026-01-01T22:00Z"),
                TimeWindow("2026-01-01T22:00Z", "2026-01-02T00:00Z"),
            )),
        )
        with patch("research.event_study_runner.load_ohlcv_before") as load_candles:
            for invalid_spec in invalid_splits:
                try:
                    run_event_study(
                        invalid_spec, approval, stage="development",
                        data_files=data_files, source_files=source_files,
                        output_root=root / "invalid-split", run_id="invalid-split",
                    )
                except (ValueError, PermissionError):
                    pass
                else:
                    raise AssertionError("Missing or inconsistent split was accepted")
            load_candles.assert_not_called()

        lock = lock_event_study_plan(
            spec, approval, locked_by="synthetic reviewer",
            locked_at_utc="2026-01-01T00:00Z", data_files=data_files,
            source_files=source_files,
        )
        try:
            authorize_event_study_holdout(
                spec, approval, lock, authorized_by="synthetic reviewer",
                authorized_at_utc="2025-12-31T23:59Z", data_files=data_files,
                source_files=source_files,
            )
        except ValueError as error:
            assert "follow" in str(error)
        else:
            raise AssertionError("Holdout authorization predating plan lock was accepted")
        release = authorize_event_study_holdout(
            spec, approval, lock, authorized_by="synthetic reviewer",
            authorized_at_utc="2026-01-01T00:01Z", data_files=data_files,
            source_files=source_files,
        )
        released = run_event_study(
            spec, approval, stage="holdout", data_files=data_files,
            source_files=source_files, output_root=root / "released",
            run_id="released", holdout_release=release,
        )
        bundle = verify_event_study_bundle(released)
        validation = pd.read_json(released / "validation.json", typ="series")
        assert bundle["stage"] == "holdout"
        assert validation["holdout_release"]["release_sha256"] == release.release_sha256

        manifest_path = released / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["holdout_release"]["authorized_by"] = "substituted"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            verify_event_study_bundle(released)
        except ValueError as error:
            assert "release" in str(error).lower()
        else:
            raise AssertionError("Bundle verifier accepted a substituted holdout release")

        changed_plan = replace(spec, decision_criteria="changed after release")
        with patch("research.event_study_runner.load_ohlcv_before") as load_candles:
            try:
                run_event_study(
                    changed_plan, approval, stage="holdout", data_files=data_files,
                    source_files=source_files, output_root=root / "stale-release",
                    run_id="stale-release", holdout_release=release,
                )
            except PermissionError:
                pass
            else:
                raise AssertionError("Holdout release accepted a changed analysis plan")
            load_candles.assert_not_called()


def test_runner_denies_unauthorized_stage_and_cleans_failed_publication():
    import shutil
    from unittest.mock import patch

    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "synthetic.csv"
        source_files = required_event_study_source_files()
        runner_candles_with_invalid_future_values().to_csv(data, index=False)
        spec = stage_runner_spec(data, source_files)
        approval = create_event_study_approval(
            spec, {"SYN|1h": data}, source_files,
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("development",),
        )
        denied_root = root / "denied"
        try:
            run_event_study(
                spec, approval, stage="validation", data_files={"SYN|1h": data},
                source_files=source_files, output_root=denied_root,
                run_id="denied-run",
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("Unauthorized stage was executed")
        assert not denied_root.exists()

        raced_root = root / "raced"
        raced_target = raced_root / "raced-run"
        original_publish = _event_study_runner._rename_directory_no_replace

        def create_competing_target(source, destination):
            if destination == raced_target:
                raced_target.mkdir()
                (raced_target / "competitor-marker").write_text("preserve", encoding="utf-8")
            return original_publish(source, destination)

        with patch("research.event_study_runner._rename_directory_no_replace",
                   side_effect=create_competing_target):
            try:
                run_event_study(
                    spec, approval, stage="development", data_files={"SYN|1h": data},
                    source_files=source_files, output_root=raced_root, run_id="raced-run",
                )
            except FileExistsError:
                pass
            else:
                raise AssertionError("Publication replaced a target created after preflight")
        assert raced_target.is_dir()
        assert (raced_target / "competitor-marker").read_text(encoding="utf-8") == "preserve"
        assert list(raced_root.iterdir()) == [raced_target]

        failed_root = root / "failed"
        with patch("research.event_study_runner.build_event_study_manifest",
                   side_effect=RuntimeError("injected manifest failure")):
            try:
                run_event_study(
                    spec, approval, stage="development", data_files={"SYN|1h": data},
                    source_files=source_files, output_root=failed_root,
                    run_id="failed-run",
                )
            except RuntimeError as error:
                assert "injected" in str(error)
            else:
                raise AssertionError("Injected publication failure was ignored")
        assert not (failed_root / "failed-run").exists()
        assert list(failed_root.iterdir()) == []

        replaced_root = root / "replaced-after-publication"
        replaced_target = replaced_root / "replacement-run"

        def replace_published_bundle(bundle_path):
            shutil.rmtree(bundle_path)
            bundle_path.mkdir()
            (bundle_path / "competitor-marker").write_text("preserve", encoding="utf-8")
            raise RuntimeError("injected verification failure")

        with patch("research.event_study_runner.verify_event_study_bundle",
                   side_effect=replace_published_bundle):
            try:
                run_event_study(
                    spec, approval, stage="development", data_files={"SYN|1h": data},
                    source_files=source_files, output_root=replaced_root,
                    run_id="replacement-run",
                )
            except RuntimeError as error:
                assert "verification" in str(error)
            else:
                raise AssertionError("Injected verification failure was ignored")
        assert (replaced_target / "competitor-marker").read_text(encoding="utf-8") == "preserve"

        modified = replace(spec, event_definition="different event definition")
        modified_approval = create_event_study_approval(
            modified, {"SYN|1h": data}, source_files,
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("development",),
        )
        try:
            run_event_study(
                modified, modified_approval, stage="development",
                data_files={"SYN|1h": data}, source_files=source_files,
                output_root=root / "modified", run_id="modified-run",
            )
        except PermissionError as error:
            assert "event_definition" in str(error)
        else:
            raise AssertionError("Unsupported approved event definition was executed")

        unsupported_estimand = replace(
            spec, estimand="median higher_low minus lower_low outcome"
        )
        estimand_approval = create_event_study_approval(
            unsupported_estimand, {"SYN|1h": data}, source_files,
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("development",),
        )
        try:
            run_event_study(
                unsupported_estimand, estimand_approval, stage="development",
                data_files={"SYN|1h": data}, source_files=source_files,
                output_root=root / "unsupported-estimand", run_id="unsupported-estimand",
            )
        except PermissionError as error:
            assert "estimand" in str(error)
        else:
            raise AssertionError("Runner silently replaced an approved estimand")


def test_runner_rejects_stale_split_dependency_before_parsing_ohlcv():
    from unittest.mock import patch

    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "synthetic.csv"
        source_files = required_event_study_source_files()
        runner_candles_with_invalid_future_values().to_csv(data, index=False)
        original_open = Path.open
        for index, identity in enumerate((
            "research.experiment_protocol", "research.hypothesis_spec",
        )):
            spec = stage_runner_spec(data, source_files)
            approval = create_event_study_approval(
                spec, {"SYN|1h": data}, source_files,
                approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
                allowed_stages=("development",),
            )
            dependency = source_files[identity].resolve()

            def substituted_open(path, *args, **kwargs):
                mode = args[0] if args else kwargs.get("mode", "r")
                if path.resolve() == dependency and mode == "rb":
                    return io.BytesIO(f"synthetic substituted source: {identity}".encode())
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", autospec=True, side_effect=substituted_open):
                with patch("research.event_study_runner.load_ohlcv_before") as load_candles:
                    try:
                        run_event_study(
                            spec, approval, stage="development",
                            data_files={"SYN|1h": data}, source_files=source_files,
                            output_root=root / f"output-{index}", run_id="stale-source-run",
                        )
                    except PermissionError as error:
                        assert "source inputs are stale" in str(error)
                    else:
                        raise AssertionError(f"Runner accepted stale source dependency {identity}")
                    load_candles.assert_not_called()


def test_validation_runner_does_not_materialize_holdout_candles_or_outcomes():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "synthetic.csv"
        candles = runner_candles_with_invalid_future_values()
        validation_rows = (
            (candles.timestamp >= pd.Timestamp("2026-01-01T19:00Z"))
            & (candles.timestamp < pd.Timestamp("2026-01-01T21:00Z"))
        )
        candles.loc[validation_rows, "high"] = 10.0
        candles.loc[candles.timestamp >= pd.Timestamp("2026-01-01T21:00Z"), "high"] = 1.0
        candles.to_csv(data, index=False)
        source_files = required_event_study_source_files()
        spec = stage_runner_spec(data, source_files)
        approval = create_event_study_approval(
            spec, {"SYN|1h": data}, source_files,
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00Z",
            allowed_stages=("validation",),
        )

        bundle = run_event_study(
            spec, approval, stage="validation", data_files={"SYN|1h": data},
            source_files=source_files, output_root=root / "validation-output",
            run_id="validation-run",
        )
        events = pd.read_csv(bundle / "events.csv")
        outcomes = pd.read_csv(bundle / "outcomes.csv")
        assert events.empty or (
            (pd.to_datetime(events.available_at, utc=True) >= pd.Timestamp("2026-01-01T20:00Z"))
            & (pd.to_datetime(events.available_at, utc=True) < pd.Timestamp("2026-01-01T22:00Z"))
        ).all()
        included = outcomes.loc[outcomes.outcome_included]
        assert included.empty or (
            pd.to_datetime(included.target_available_at, utc=True)
            < pd.Timestamp("2026-01-01T22:00Z")
        ).all()
        assert verify_event_study_bundle(bundle)["stage"] == "validation"


def test_multiple_testing_family_and_unresolved_endpoint_configuration_fail_closed():
    validate_test_family(("primary", "secondary"), ("primary",))
    for registered, requested in (
        (("primary",), ("outside",)),
        (("primary",), ("primary", "primary")),
        ((), ("primary",)),
    ):
        try:
            validate_test_family(registered, requested)
        except (ValueError, PermissionError):
            pass
        else:
            raise AssertionError("Unregistered or duplicate test family was accepted")
    try:
        OutcomeRule(None, None, None, None, None, None).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Unresolved outcome configuration was accepted")


def main():
    tests = [
        test_support_touch_cohorts_join_confirmed_structure_causally_and_retain_repeats,
        test_support_touch_builder_rejects_invalid_timing,
        test_fixed_observed_bar_outcome_reports_elapsed_time_and_gap_without_filling,
        test_synthetic_repeats_and_overlapping_outcome_windows_remain_distinct,
        test_elapsed_endpoint_exact_and_first_after_rules_and_tolerance,
        test_outcome_calculator_rejects_anchor_endpoint_duplicates_and_bad_prices,
        test_temporal_assignment_uses_utc_half_open_boundaries_and_purges_crossings,
        test_split_rejects_naive_and_duplicate_event_times_and_applies_embargo,
        test_descriptive_contrast_counts_unique_zones_and_decision_helper_uses_given_criteria,
        test_unresolved_spec_blocks_approval_and_fingerprint_is_deterministic,
        test_approval_binds_spec_data_sources_and_allowed_stage,
        test_approval_hashes_full_inputs_without_read_bytes_materialization,
        test_research_outcome_requires_approved_execution_guard,
        test_approved_research_outcome_blocks_split_crossing_and_rule_mismatch,
        test_manifest_is_deterministic_contained_and_no_clobber,
        test_runner_publishes_reproducible_stage_bounded_bundle_and_refuses_clobber,
        test_horizon_embargo_and_explicit_locked_holdout_release,
        test_runner_denies_unauthorized_stage_and_cleans_failed_publication,
        test_runner_rejects_stale_split_dependency_before_parsing_ohlcv,
        test_validation_runner_does_not_materialize_holdout_candles_or_outcomes,
        test_multiple_testing_family_and_unresolved_endpoint_configuration_fail_closed,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
