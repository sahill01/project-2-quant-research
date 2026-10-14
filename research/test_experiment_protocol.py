"""Synthetic tests for chronological partitions and versioned manifests."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from research.experiment_protocol import (
    ExperimentConfig,
    TemporalSplit,
    TimeWindow,
    config_fingerprint,
    append_research_log,
    split_by_availability,
    write_experiment_manifest,
)


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
        parameters=parameters or {"lookback": 4},
        execution={"signal_available_at": "candle_close", "fill": "next_open"},
        split=split(),
        hypothesis_approval_status=approval_status,
    )


def test_splits_are_chronological_and_holdout_requires_frozen_config():
    times = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    frame = pd.DataFrame({"available_at": times, "value": range(6)})
    partitions = split_by_availability(frame, split())
    assert partitions.train["value"].tolist() == [0, 1]
    assert partitions.validation["value"].tolist() == [2, 3]
    assert partitions.development["value"].tolist() == [0, 1, 2, 3]

    experiment_config = config(approval_status="APPROVED")
    try:
        partitions.open_holdout(experiment_config)
    except PermissionError:
        pass
    else:
        raise AssertionError("Holdout opened before experiment config was frozen")

    partitions.freeze_for_holdout(experiment_config)
    try:
        partitions.open_holdout(
            config({"lookback": 5}, approval_status="APPROVED")
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("Holdout opened with a changed config fingerprint")

    # The config dataclass is frozen but its nested dicts are mutable. The
    # guard must fingerprint the current object, not trust a stale hash from
    # before the mutation.
    experiment_config.parameters["lookback"] = 5
    try:
        partitions.open_holdout(experiment_config)
    except PermissionError:
        pass
    else:
        raise AssertionError("Holdout opened after the frozen config was mutated")

    experiment_config.parameters["lookback"] = 4
    assert partitions.open_holdout(experiment_config)["value"].tolist() == [4, 5]


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


def test_holdout_freeze_requires_explicit_hypothesis_approval():
    times = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    partitions = split_by_availability(
        pd.DataFrame({"available_at": times, "value": range(6)}), split()
    )
    for status in ("PROPOSED", "REJECTED"):
        try:
            partitions.freeze_for_holdout(config(approval_status=status))
        except PermissionError as error:
            assert "APPROVED" in str(error)
        else:
            raise AssertionError(f"{status} hypothesis was allowed to freeze holdout")

    approved = config(approval_status="APPROVED")
    partitions.freeze_for_holdout(approved)
    assert partitions.open_holdout(approved)["value"].tolist() == [4, 5]


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
        manifest = write_experiment_manifest(
            config(), output, {"SYN": data}, {"runner.py": runner}
        )
        assert manifest.is_file()
        import json
        from hashlib import sha256

        content = json.loads(manifest.read_text(encoding="utf-8"))
        assert content["status"] == "configured_not_run"
        assert content["implementation_sha256"]["runner.py"] == sha256(
            runner.read_bytes()
        ).hexdigest()
        assert "experiment_protocol.py" in content["implementation_sha256"]
        try:
            write_experiment_manifest(
                config(), output, {"SYN": data}, {"runner.py": runner}
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("Manifest writer overwrote an existing experiment")

        try:
            write_experiment_manifest(
                config(), Path(directory) / "missing-source", {"SYN": data}, {}
            )
        except ValueError as error:
            assert "implementation file" in str(error)
        else:
            raise AssertionError("Manifest omitted experiment-specific implementation hashes")

        empty_data_output = Path(directory) / "empty-data-runs"
        try:
            write_experiment_manifest(
                config(), empty_data_output, {}, {"runner.py": runner}
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
                    config(), output, {"SYN": data}, {"runner.py": runner}
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
        test_holdout_freeze_requires_explicit_hypothesis_approval,
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
