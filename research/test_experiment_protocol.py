"""Synthetic tests for chronological partitions and versioned manifests."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from dataclasses import replace

import pandas as pd

from research.experiment_protocol import (
    ExperimentConfig,
    PreregistrationApproval,
    TemporalSplit,
    TimeWindow,
    config_fingerprint,
    create_preregistration_approval,
    finalize_experiment_manifest,
    append_research_log,
    split_by_availability,
    verify_experiment_manifest,
    write_experiment_manifest,
    validate_preregistration_approval,
)
from research.hypothesis_spec import HypothesisSpec, ResearchDecisions


def split() -> TemporalSplit:
    return TemporalSplit(
        train=TimeWindow("2026-01-01T00:00:00Z", "2026-01-01T02:00:00Z"),
        validation=TimeWindow("2026-01-01T02:00:00Z", "2026-01-01T04:00:00Z"),
        holdout=TimeWindow("2026-01-01T04:00:00Z", "2026-01-01T06:00:00Z"),
    )


def config(parameters=None, *, approval_status="PROPOSED") -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="EXP-SYN-001",
        version=1,
        hypothesis_id="HYP-SYN-001",
        strategy="synthetic_example",
        assets=("SYN",),
        timeframe="1h",
        feature_pipeline_version="synthetic-v1",
        cost_model_version="synthetic-cost-v1",
        parameters=parameters or {"lookback": 4},
        execution={"signal_available_at": "candle_close", "fill": "next_open"},
        split=split(),
        hypothesis_approval_status=approval_status,
    )


def hypothesis(*, status="PROPOSED", decisions=None) -> HypothesisSpec:
    return HypothesisSpec(
        hypothesis_id="HYP-SYN-001", title="Synthetic test hypothesis",
        market_rationale="Synthetic rationale", feature_definition="Synthetic feature",
        signal_definition="No strategy evaluation", information_available_at="available_at before decision",
        entry_and_exit_assumptions="Synthetic only", expected_effect="No predictive claim",
        failure_conditions=("Synthetic failure",), baseline_comparison="Synthetic baseline",
        sample_size_and_validation="Synthetic test fields only", confounders=("Synthetic",),
        transaction_cost_assumptions="Synthetic costs", approval_status=status,
        decisions=decisions if decisions is not None else ResearchDecisions(),
    )


def resolved_decisions():
    from dataclasses import fields
    return ResearchDecisions(**{item.name: "synthetic predeclared value" for item in fields(ResearchDecisions)})


def approval_for(directory, *, experiment_config=None, spec=None):
    root = Path(directory)
    data = root / "data.csv"
    data.write_text("available_at,value\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
    runner = root / "runner.py"
    runner.write_text("RUN_VERSION = 1\n", encoding="utf-8")
    return create_preregistration_approval(
        experiment_config or config(approval_status="APPROVED"),
        spec or hypothesis(status="APPROVED", decisions=resolved_decisions()),
        {"SYN": data}, {"runner.py": runner}, approver="reviewer",
        approved_at_utc="2026-01-01T00:00:00Z", approval_note="Synthetic approval contract test",
    ), data, runner


def test_splits_are_chronological_and_holdout_requires_frozen_config():
    times = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    frame = pd.DataFrame({"available_at": times, "value": range(6)})
    partitions = split_by_availability(frame, split())
    assert partitions.train["value"].tolist() == [0, 1]
    assert partitions.validation["value"].tolist() == [2, 3]
    assert partitions.development["value"].tolist() == [0, 1, 2, 3]

    with TemporaryDirectory() as directory:
        experiment_config = config(approval_status="APPROVED")
        spec = hypothesis(status="APPROVED", decisions=resolved_decisions())
        approval, _, _ = approval_for(directory, experiment_config=experiment_config, spec=spec)
        try:
            partitions.open_holdout(experiment_config, spec, approval)
        except PermissionError:
            pass
        else:
            raise AssertionError("Holdout opened before experiment config was frozen")

        partitions.freeze_for_holdout(experiment_config, spec, approval)
        try:
            partitions.open_holdout(config({"lookback": 5}, approval_status="APPROVED"), spec, approval)
        except PermissionError:
            pass
        else:
            raise AssertionError("Holdout opened with a changed config fingerprint")

        experiment_config.parameters["lookback"] = 5
        try:
            partitions.open_holdout(experiment_config, spec, approval)
        except PermissionError:
            pass
        else:
            raise AssertionError("Holdout opened after the frozen config was mutated")

        experiment_config.parameters["lookback"] = 4
        assert partitions.open_holdout(experiment_config, spec, approval)["value"].tolist() == [4, 5]


def test_overlapping_or_incomplete_windows_are_rejected():
    overlapping = TemporalSplit(
        train=TimeWindow("2026-01-01T00:00:00Z", "2026-01-01T03:00:00Z"),
        validation=TimeWindow("2026-01-01T02:00:00Z", "2026-01-01T04:00:00Z"),
        holdout=TimeWindow("2026-01-01T04:00:00Z", "2026-01-01T06:00:00Z"),
    )
    try:
        overlapping.validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Overlapping time windows were accepted")

    frame = pd.DataFrame({
        "available_at": pd.to_datetime(["2025-12-31T23:00:00Z"], utc=True)
    })
    try:
        split_by_availability(frame, split())
    except ValueError as error:
        assert "outside configured split windows" in str(error)
    else:
        raise AssertionError("Unassigned observation was silently dropped")


def test_empty_availability_input_is_rejected():
    frame = pd.DataFrame({"available_at": pd.Series([], dtype="datetime64[ns, UTC]")})
    try:
        split_by_availability(frame, split())
    except ValueError as error:
        assert "At least one availability observation" in str(error)
    else:
        raise AssertionError("Empty data produced apparently valid empty partitions")


def test_reversed_naive_empty_and_unordered_windows_are_rejected():
    invalid_splits = (
        TemporalSplit(
            TimeWindow("2026-01-01T02:00:00Z", "2026-01-01T02:00:00Z"),
            split().validation, split().holdout,
        ),
        TemporalSplit(
            TimeWindow("2026-01-01T03:00:00Z", "2026-01-01T01:00:00Z"),
            split().validation, split().holdout,
        ),
        TemporalSplit(
            TimeWindow("2026-01-01T00:00:00", "2026-01-01T02:00:00"),
            split().validation, split().holdout,
        ),
        TemporalSplit(
            split().train,
            TimeWindow("2025-12-31T23:00:00Z", "2026-01-01T01:00:00Z"),
            split().holdout,
        ),
    )
    for invalid in invalid_splits:
        try:
            invalid.validate()
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid chronological window was accepted")


def test_incomplete_config_and_unsafe_experiment_ids_are_rejected():
    for invalid in (
        replace(config(), experiment_id="../escape"),
        replace(config(), feature_pipeline_version="unspecified"),
        replace(config(), cost_model_version="unspecified"),
        replace(config(), execution={}),
    ):
        try:
            invalid.validate()
        except ValueError:
            pass
        else:
            raise AssertionError("Incomplete or unsafe experiment config was accepted")


def test_holdout_freeze_requires_explicit_hypothesis_approval():
    times = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    partitions = split_by_availability(
        pd.DataFrame({"available_at": times, "value": range(6)}), split()
    )
    for status in ("PROPOSED", "REJECTED"):
        try:
            partitions.freeze_for_holdout(config(approval_status=status), hypothesis(status=status))
        except PermissionError as error:
            assert "approval record" in str(error)
        else:
            raise AssertionError(f"{status} hypothesis was allowed to freeze holdout")

    approved = config(approval_status="APPROVED")
    approved_spec = hypothesis(status="APPROVED", decisions=resolved_decisions())
    try:
        partitions.freeze_for_holdout(approved, approved_spec)
    except PermissionError:
        pass
    else:
        raise AssertionError("Caller-supplied APPROVED strings passed without an approval record")
    with TemporaryDirectory() as directory:
        approval, _, _ = approval_for(directory, experiment_config=approved, spec=approved_spec)
        partitions.freeze_for_holdout(approved, approved_spec, approval)
        assert partitions.open_holdout(approved, approved_spec, approval)["value"].tolist() == [4, 5]


def test_unresolved_decisions_and_input_or_source_mutations_invalidate_approval():
    approved_config = config(approval_status="APPROVED")
    unresolved = hypothesis(status="APPROVED")
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data.csv"
        data.write_text("available_at,value\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
        runner = root / "runner.py"
        runner.write_text("RUN_VERSION=1\n", encoding="utf-8")
        try:
            create_preregistration_approval(
                approved_config, unresolved, {"SYN": data}, {"runner.py": runner},
                approver="reviewer", approved_at_utc="2026-01-01T00:00:00Z", approval_note="test",
            )
        except PermissionError as error:
            assert "unresolved" in str(error).lower()
        else:
            raise AssertionError("Unresolved research choices were approved")

        spec = hypothesis(status="APPROVED", decisions=resolved_decisions())
        approval, data, runner = approval_for(directory, experiment_config=approved_config, spec=spec)
        partitions = split_by_availability(pd.DataFrame({
            "available_at": pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC"),
            "value": range(6),
        }), split())
        partitions.freeze_for_holdout(approved_config, spec, approval)
        try:
            partitions.open_holdout(
                approved_config, replace(spec, feature_definition="mutated after approval"), approval
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("Changed hypothesis passed the approval gate")
        data.write_text(data.read_text() + "2026-01-01T01:00:00Z,2\n", encoding="utf-8")
        try:
            partitions.open_holdout(approved_config, spec, approval)
        except PermissionError:
            pass
        else:
            raise AssertionError("Changed data file passed the approval gate")

        # Re-approve the changed input, then verify source mutation is detected.
        approval, data, runner = approval_for(directory, experiment_config=approved_config, spec=spec)
        partitions = split_by_availability(pd.DataFrame({
            "available_at": pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC"),
            "value": range(6),
        }), split())
        partitions.freeze_for_holdout(approved_config, spec, approval)
        runner.write_text("RUN_VERSION=2\n", encoding="utf-8")
        try:
            partitions.open_holdout(approved_config, spec, approval)
        except PermissionError:
            pass
        else:
            raise AssertionError("Changed implementation source passed the approval gate")


def test_frozen_partitions_bind_approval_data_and_partition_content():
    approved_config = config(approval_status="APPROVED")
    approved_spec = hypothesis(status="APPROVED", decisions=resolved_decisions())
    frame = pd.DataFrame({
        "available_at": pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC"),
        "value": range(6),
    })
    partitions = split_by_availability(frame, split())
    with TemporaryDirectory() as directory:
        approval_a, _, _ = approval_for(
            directory, experiment_config=approved_config, spec=approved_spec
        )
        partitions.freeze_for_holdout(approved_config, approved_spec, approval_a)
        frozen_state = (
            partitions._frozen_config_hash, partitions._frozen_approval_hash,
            partitions._frozen_partition_hash,
        )

        data_b = Path(directory) / "different_data.csv"
        data_b.write_text("available_at,value\n2026-01-01T00:00:00Z,99\n", encoding="utf-8")
        runner = Path(directory) / "runner.py"
        approval_b = create_preregistration_approval(
            approved_config, approved_spec, {"SYN": data_b}, {"runner.py": runner},
            approver="reviewer", approved_at_utc="2026-01-01T00:00:00Z",
            approval_note="Different approved input fixture",
        )
        validate_preregistration_approval(approved_config, approved_spec, approval_b)
        try:
            partitions.open_holdout(approved_config, approved_spec, approval_b)
        except PermissionError as error:
            assert "frozen approval" in str(error)
        else:
            raise AssertionError("Different approval record opened frozen holdout")
        assert frozen_state == (
            partitions._frozen_config_hash, partitions._frozen_approval_hash,
            partitions._frozen_partition_hash,
        )

        original = partitions.train.loc[partitions.train.index[0], "value"]
        partitions.train.loc[partitions.train.index[0], "value"] = 999
        try:
            partitions.open_holdout(approved_config, approved_spec, approval_a)
        except PermissionError as error:
            assert "partition data changed" in str(error)
        else:
            raise AssertionError("Mutated frozen partition data was accepted")
        assert frozen_state == (
            partitions._frozen_config_hash, partitions._frozen_approval_hash,
            partitions._frozen_partition_hash,
        )
        partitions.train.loc[partitions.train.index[0], "value"] = original
        assert partitions.open_holdout(approved_config, approved_spec, approval_a)["value"].tolist() == [4, 5]

        changed_config = replace(approved_config, split=TemporalSplit(
            train=TimeWindow("2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"),
            validation=split().validation,
            holdout=split().holdout,
        ))
        try:
            partitions.open_holdout(changed_config, approved_spec, approval_a)
        except PermissionError:
            pass
        else:
            raise AssertionError("Changed split boundaries opened frozen holdout")
        assert frozen_state == (
            partitions._frozen_config_hash, partitions._frozen_approval_hash,
            partitions._frozen_partition_hash,
        )


def test_approval_validation_rechecks_direct_records_and_resolution_state():
    approved_config = config(approval_status="APPROVED")
    approved_spec = hypothesis(status="APPROVED", decisions=resolved_decisions())
    with TemporaryDirectory() as directory:
        approval, _, _ = approval_for(
            directory, experiment_config=approved_config, spec=approved_spec
        )
        directly_constructed = PreregistrationApproval(**{
            name: getattr(approval, name)
            for name in PreregistrationApproval.__dataclass_fields__
        })
        validate_preregistration_approval(approved_config, approved_spec, directly_constructed)
        unresolved = replace(
            approved_spec,
            decisions=replace(approved_spec.decisions, matching_method="TODO: decide"),
        )
        import json
        from hashlib import sha256

        unresolved_payload = {
            "config": approved_config.as_dict(),
            "hypothesis": unresolved.as_dict(),
            "data_files": approval.data_files,
            "implementation_files": approval.implementation_files,
        }
        unresolved_hypothesis_hash = sha256(json.dumps(
            unresolved.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
        unresolved_approval_fields = {
            name: getattr(approval, name)
            for name in PreregistrationApproval.__dataclass_fields__
        }
        unresolved_approval_fields.update({
            "hypothesis_id": unresolved.hypothesis_id,
            "hypothesis_version": unresolved.hypothesis_version,
            "hypothesis_sha256": unresolved_hypothesis_hash,
            "specification_sha256": sha256(json.dumps(
                unresolved_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")).hexdigest(),
        })
        unresolved_approval = PreregistrationApproval(**unresolved_approval_fields)
        try:
            validate_preregistration_approval(approved_config, unresolved, unresolved_approval)
        except PermissionError as error:
            assert "Unresolved research decisions" in str(error)
        else:
            raise AssertionError("Matching direct approval bypassed unresolved-decision checks")

        try:
            validate_preregistration_approval(
                approved_config, approved_spec, replace(approval, approval_note="")
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("Approval with an empty note was accepted")


def test_partition_representation_does_not_expose_holdout_rows():
    frame = pd.DataFrame({
        "available_at": pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC"),
        "value": ["train0", "train1", "validation0", "validation1", "HOLDOUT_SENTINEL", "holdout1"],
    })
    partitions = split_by_availability(frame, split())
    assert "HOLDOUT_SENTINEL" not in repr(partitions)
    assert "HOLDOUT_SENTINEL" not in repr(partitions.development)


def test_config_fingerprint_and_manifest_are_reproducible_and_no_clobber():
    assert config_fingerprint(config()) == config_fingerprint(config())
    assert config_fingerprint(config()) != config_fingerprint(config({"lookback": 5}))
    assert config_fingerprint(config()) != config_fingerprint(
        config(approval_status="APPROVED")
    )
    for nonfinite in (float("nan"), float("inf"), float("-inf")):
        try:
            config_fingerprint(config({"threshold": nonfinite}))
        except ValueError:
            pass
        else:
            raise AssertionError("Non-standard non-finite config value was fingerprinted")
    with TemporaryDirectory() as directory:
        data = Path(directory) / "data.csv"
        data.write_text("available_at,value\n2026-01-01T00:00:00Z,1\n")
        runner = Path(directory) / "experiment_runner.py"
        runner.write_text("RUN_VERSION = 1\n")
        output = Path(directory) / "runs"
        approved_config = config(approval_status="APPROVED")
        approved_spec = hypothesis(status="APPROVED", decisions=resolved_decisions())
        approval = create_preregistration_approval(
            approved_config, approved_spec, {"SYN": data}, {"runner.py": runner},
            approver="synthetic reviewer", approved_at_utc="2026-01-01T00:00:00Z",
            approval_note="Synthetic manifest lifecycle test",
        )
        manifest = write_experiment_manifest(
            approved_config, output, {"SYN": data}, {"runner.py": runner}, approved_spec,
            approval=approval,
        )
        assert manifest.is_file()
        import json
        from hashlib import sha256

        content = json.loads(manifest.read_text(encoding="utf-8"))
        assert content["lifecycle_status"] == "configured_not_run"
        assert content["actual_inputs_and_implementation"]["implementation_sha256"]["runner.py"]["sha256"] == sha256(
            runner.read_bytes()
        ).hexdigest()
        assert "experiment_protocol.py" in content["actual_inputs_and_implementation"]["implementation_sha256"]
        assert content["actual_inputs_and_implementation"]["input_data"]["SYN"]["first_timestamp_utc"] == "2026-01-01T00:00:00+00:00"
        artifact = manifest.parent / "metrics.json"
        artifact.write_text('{"synthetic": true}\n', encoding="utf-8")
        initial_manifest = manifest.read_bytes()
        try:
            finalize_experiment_manifest(manifest, {"metrics": artifact}, {
                "computation_status": "failed", "scientific_status": "not_assessed",
            })
        except ValueError as error:
            assert "completed computations" in str(error)
        else:
            raise AssertionError("Failed computation was finalized")
        assert manifest.read_bytes() == initial_manifest

        for contradictory_validation in (
            {"computation_status": "completed", "scientific_status": "criteria_met",
             "validation_status": "FAILED"},
            {"computation_status": "completed", "scientific_status": "criteria_met",
             "status": "rejected"},
        ):
            try:
                finalize_experiment_manifest(
                    manifest, {"metrics": artifact}, contradictory_validation
                )
            except ValueError as error:
                assert "Unsupported validation" in str(error)
            else:
                raise AssertionError("Contradictory validation metadata was finalized")
            assert manifest.read_bytes() == initial_manifest

        original_runner = runner.read_bytes()
        runner.write_text("RUN_VERSION = 2\n", encoding="utf-8")
        try:
            finalize_experiment_manifest(manifest, {"metrics": artifact}, {"computation_status": "failed", "scientific_status": "not_assessed"})
        except PermissionError as error:
            assert "changed after" in str(error)
        else:
            raise AssertionError("Changed implementation was finalized under stale approval")
        runner.write_bytes(original_runner)
        for invalid_validation in (
            {},
            {"computation_status": "completed"},
            {"computation_status": "rejected", "scientific_status": "criteria_not_met"},
            {"computation_status": "completed", "scientific_status": "FAILED"},
            {"computation_status": "completed", "scientific_status": []},
            "malformed",
        ):
            try:
                finalize_experiment_manifest(manifest, {"metrics": artifact}, invalid_validation)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid validation state finalized successfully")
            assert manifest.read_bytes() == initial_manifest
        finalize_experiment_manifest(manifest, {"metrics": artifact}, {
            "computation_status": "completed", "scientific_status": "criteria_not_met",
            "note": "Synthetic status test only",
        })
        completed = json.loads(manifest.read_text(encoding="utf-8"))
        assert completed["lifecycle_status"] == "evaluation_completed"
        assert completed["validation_and_approval"]["validation_status"] == "criteria_not_met"
        assert completed["outputs"][0]["sha256"] == sha256(artifact.read_bytes()).hexdigest()
        assert verify_experiment_manifest(manifest)
        completed_manifest = manifest.read_bytes()

        contradictory = json.loads(completed_manifest)
        contradictory["validation_and_approval"]["validation"]["validation_status"] = "FAILED"
        manifest.write_text(json.dumps(contradictory), encoding="utf-8")
        try:
            verify_experiment_manifest(manifest)
        except ValueError as error:
            assert "validation metadata" in str(error)
        else:
            raise AssertionError("Verifier accepted contradictory nested validation state")
        manifest.write_bytes(completed_manifest)

        unhashable_status = json.loads(completed_manifest)
        unhashable_status["validation_and_approval"]["validation"]["scientific_status"] = []
        manifest.write_text(json.dumps(unhashable_status), encoding="utf-8")
        try:
            verify_experiment_manifest(manifest)
        except ValueError as error:
            assert "validation metadata" in str(error)
        else:
            raise AssertionError("Verifier accepted an unhashable scientific status")
        manifest.write_bytes(completed_manifest)

        for key, bad_value, expected in (
            ("config_sha256", "0" * 64, "config fingerprint"),
            ("hypothesis_sha256", "0" * 64, "hypothesis fingerprint"),
        ):
            altered_manifest = json.loads(completed_manifest)
            altered_manifest["intended_specification"][key] = bad_value
            manifest.write_text(json.dumps(altered_manifest), encoding="utf-8")
            try:
                verify_experiment_manifest(manifest)
            except ValueError as error:
                assert expected in str(error)
            else:
                raise AssertionError(f"Verifier accepted altered {key}")
            manifest.write_bytes(completed_manifest)

        altered_identity = json.loads(completed_manifest)
        altered_identity["experiment_id"] = "EXP-SYN-OTHER"
        manifest.write_text(json.dumps(altered_identity), encoding="utf-8")
        try:
            verify_experiment_manifest(manifest)
        except ValueError as error:
            assert "identity" in str(error)
        else:
            raise AssertionError("Verifier accepted an experiment/config identity mismatch")
        manifest.write_bytes(completed_manifest)

        import shutil
        misplaced_run = manifest.parent.parent / "MISNAMED-RUN"
        shutil.copytree(manifest.parent, misplaced_run)
        try:
            verify_experiment_manifest(misplaced_run / "manifest.json")
        except ValueError as error:
            assert "run directory" in str(error)
        else:
            raise AssertionError("Verifier accepted a manifest in the wrong run directory")

        artifact.write_text('{"modified": true}\n', encoding="utf-8")
        try:
            verify_experiment_manifest(manifest)
        except ValueError as error:
            assert "hash mismatch" in str(error)
        else:
            raise AssertionError("Post-finalization artifact mutation was not detected")
        artifact.write_text('{"synthetic": true}\n', encoding="utf-8")
        altered = json.loads(completed_manifest)
        altered["outputs"][0]["path"] = "../outside.json"
        manifest.write_text(json.dumps(altered), encoding="utf-8")
        try:
            verify_experiment_manifest(manifest)
        except ValueError as error:
            assert "run directory" in str(error)
        else:
            raise AssertionError("Escaping artifact path was accepted")
        manifest.write_bytes(completed_manifest)
        missing_artifact = artifact.with_name("deleted-metrics.json")
        artifact.rename(missing_artifact)
        try:
            verify_experiment_manifest(manifest)
        except ValueError as error:
            assert "missing" in str(error).lower()
        else:
            raise AssertionError("Deleted artifact passed manifest verification")
        missing_artifact.rename(artifact)
        duplicated = json.loads(completed_manifest)
        duplicated["outputs"].append(dict(duplicated["outputs"][0], name="duplicate"))
        manifest.write_text(json.dumps(duplicated), encoding="utf-8")
        try:
            verify_experiment_manifest(manifest)
        except ValueError as error:
            assert "unique" in str(error)
        else:
            raise AssertionError("Duplicate artifact reference passed verification")
        manifest.write_bytes(completed_manifest)
        try:
            write_experiment_manifest(
                approved_config, output, {"SYN": data}, {"runner.py": runner}, approved_spec,
                approval=approval,
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("Manifest writer overwrote an existing experiment")

        try:
            write_experiment_manifest(
                config(), Path(directory) / "missing-source", {"SYN": data}, {}, hypothesis()
            )
        except ValueError as error:
            assert "implementation file" in str(error)
        else:
            raise AssertionError("Manifest omitted experiment-specific implementation hashes")

        empty_data_output = Path(directory) / "empty-data-runs"
        try:
            write_experiment_manifest(
                config(), empty_data_output, {}, {"runner.py": runner}, hypothesis()
            )
        except ValueError as error:
            assert "input data file" in str(error)
        else:
            raise AssertionError("Manifest without input data was accepted")
        assert not (empty_data_output / config().experiment_id).exists()


def test_research_log_appends_results_and_requires_rejection_reasons():
    from research.experiment_protocol import RESEARCH_LOG_FIELDS

    with TemporaryDirectory() as directory:
        path = Path(directory) / "research_log.csv"
        path.write_text(",".join(RESEARCH_LOG_FIELDS) + "\n", encoding="utf-8")
        entry = {field: "" for field in RESEARCH_LOG_FIELDS}
        entry.update({
            "experiment_id": "EXP-SYN-LOG-001",
            "date": "2026-01-01",
            "decision": "DESCRIPTIVE_ONLY",
            "notes": "Synthetic test record",
        })
        append_research_log(path, entry)
        original = path.read_text(encoding="utf-8")
        try:
            append_research_log(path, entry)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Duplicate experiment log row was allowed")
        assert path.read_text(encoding="utf-8") == original

        rejected = dict(entry)
        rejected.update({"experiment_id": "EXP-SYN-LOG-002", "decision": "REJECTED", "notes": ""})
        try:
            append_research_log(path, rejected)
        except ValueError as error:
            assert "reason" in str(error)
        else:
            raise AssertionError("Rejection without a reason was logged")


def test_manifest_publish_failure_cleans_staged_file_and_run_directory():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data.csv"
        data.write_text("available_at,value\n2026-01-01T00:00:00Z,1\n")
        runner = root / "runner.py"
        runner.write_text("RUN_VERSION = 1\n")
        output = root / "runs"

        try:
            with patch(
                "research.experiment_protocol.os.link",
                side_effect=OSError("synthetic publish failure"),
            ):
                write_experiment_manifest(
                    config(), output, {"SYN": data}, {"runner.py": runner}, hypothesis()
                )
        except OSError as error:
            assert "synthetic publish failure" in str(error)
        else:
            raise AssertionError("Synthetic manifest publish failure was ignored")

        assert not (output / config().experiment_id).exists()
        assert list(output.iterdir()) == []


def main():
    tests = [
        test_splits_are_chronological_and_holdout_requires_frozen_config,
        test_overlapping_or_incomplete_windows_are_rejected,
        test_empty_availability_input_is_rejected,
        test_reversed_naive_empty_and_unordered_windows_are_rejected,
        test_incomplete_config_and_unsafe_experiment_ids_are_rejected,
        test_holdout_freeze_requires_explicit_hypothesis_approval,
        test_unresolved_decisions_and_input_or_source_mutations_invalidate_approval,
        test_frozen_partitions_bind_approval_data_and_partition_content,
        test_approval_validation_rechecks_direct_records_and_resolution_state,
        test_partition_representation_does_not_expose_holdout_rows,
        test_config_fingerprint_and_manifest_are_reproducible_and_no_clobber,
        test_research_log_appends_results_and_requires_rejection_reasons,
        test_manifest_publish_failure_cleans_staged_file_and_run_directory,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
