"""Versioned experiment configuration, chronological partitions, and manifests."""

from dataclasses import dataclass, field
from copy import deepcopy
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
from typing import Any

import pandas as pd
import numpy as np

from research.hypothesis_spec import HypothesisSpec, ResearchDecisions


RESEARCH_LOG_FIELDS = (
    "experiment_id", "date", "hypothesis", "symbol", "timeframe",
    "start", "end", "parameters", "baseline", "result", "decision", "notes",
)

MANIFEST_SCIENTIFIC_STATUSES = frozenset({
    "not_assessed", "criteria_met", "criteria_not_met", "inconclusive",
})
MANIFEST_VALIDATION_FIELDS = frozenset({
    "computation_status", "scientific_status", "note",
})


def _validate_manifest_validation(validation: Any) -> dict[str, Any]:
    """Enforce the small, explicit manifest validation-state contract.

    Computation completion is operational state; scientific status records
    the separate assessment. ``note`` is the only optional descriptive field.
    """
    if not isinstance(validation, dict):
        raise ValueError("Validation metadata must be an object")
    unsupported = set(validation) - MANIFEST_VALIDATION_FIELDS
    if unsupported:
        raise ValueError(
            f"Unsupported validation metadata fields: {sorted(map(str, unsupported))}"
        )
    if validation.get("computation_status") != "completed":
        raise ValueError("Only completed computations can be finalized")
    scientific_status = validation.get("scientific_status")
    if (not isinstance(scientific_status, str)
            or scientific_status not in MANIFEST_SCIENTIFIC_STATUSES):
        raise ValueError("An explicit supported scientific_status is required")
    if "note" in validation and not isinstance(validation["note"], str):
        raise ValueError("Validation note must be a string")
    return validation


@dataclass(frozen=True)
class TimeWindow:
    start: str
    end: str

    def parsed(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        start = pd.Timestamp(self.start)
        end = pd.Timestamp(self.end)
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Experiment window boundaries must include a timezone")
        start = start.tz_convert("UTC")
        end = end.tz_convert("UTC")
        if start >= end:
            raise ValueError(f"Invalid time window: {start} >= {end}")
        return start, end


@dataclass(frozen=True)
class TemporalSplit:
    train: TimeWindow
    validation: TimeWindow
    holdout: TimeWindow

    def validate(self) -> None:
        train_start, train_end = self.train.parsed()
        validation_start, validation_end = self.validation.parsed()
        holdout_start, holdout_end = self.holdout.parsed()
        if not (
            train_start < train_end <= validation_start < validation_end
            <= holdout_start < holdout_end
        ):
            raise ValueError("Train, validation, and holdout windows overlap or are unordered")


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_id: str
    version: int
    hypothesis_id: str
    strategy: str
    assets: tuple[str, ...]
    timeframe: str
    parameters: dict[str, Any]
    execution: dict[str, Any]
    split: TemporalSplit
    hypothesis_approval_status: str = "PROPOSED"
    hypothesis_version: int = 1
    feature_pipeline_version: str = "unspecified"
    cost_model_version: str = "unspecified"
    random_seeds: dict[str, int] = field(default_factory=dict)

    def validate(self) -> None:
        if (not self.experiment_id.strip() or self.experiment_id in {".", ".."}
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.experiment_id)):
            raise ValueError("Experiment ID must be a stable, path-safe identifier")
        if not self.hypothesis_id.strip():
            raise ValueError("Experiment and hypothesis identifiers are required")
        if self.version < 1:
            raise ValueError("Experiment config version must be positive")
        if self.hypothesis_version < 1:
            raise ValueError("Hypothesis version must be positive")
        if not self.strategy.strip() or not self.assets:
            raise ValueError("Strategy and at least one asset are required")
        if len(set(self.assets)) != len(self.assets):
            raise ValueError("Experiment assets must be unique")
        if not self.timeframe.strip():
            raise ValueError("Timeframe is required")
        if not self.execution:
            raise ValueError("Execution and cost assumptions are required")
        if not self.feature_pipeline_version.strip() or self.feature_pipeline_version == "unspecified":
            raise ValueError("Feature-pipeline version must be explicit (use 'none' if not applicable)")
        if not self.cost_model_version.strip() or self.cost_model_version == "unspecified":
            raise ValueError("Cost-model version must be explicit")
        if self.hypothesis_approval_status.strip().upper() not in {
            "PROPOSED", "APPROVED", "REJECTED"
        }:
            raise ValueError(
                "hypothesis_approval_status must be PROPOSED, APPROVED, or REJECTED"
            )
        self.split.validate()

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "experiment_id": self.experiment_id,
            "version": self.version,
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_version": self.hypothesis_version,
            "hypothesis_approval_status": self.hypothesis_approval_status.strip().upper(),
            "strategy": self.strategy,
            "assets": list(self.assets),
            "timeframe": self.timeframe,
            "feature_pipeline_version": self.feature_pipeline_version,
            "cost_model_version": self.cost_model_version,
            "random_seeds": deepcopy(self.random_seeds),
            "parameters": deepcopy(self.parameters),
            "execution": deepcopy(self.execution),
            "split": {
                "train": {"start": self.split.train.start, "end": self.split.train.end},
                "validation": {
                    "start": self.split.validation.start,
                    "end": self.split.validation.end,
                },
                "holdout": {"start": self.split.holdout.start, "end": self.split.holdout.end},
                "boundary_semantics": "UTC half-open intervals [start, end)",
            },
        }


def config_fingerprint(config: ExperimentConfig) -> str:
    payload = json.dumps(
        config.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def dataframe_fingerprint(frame: pd.DataFrame) -> str:
    """Fingerprint dataframe content/schema for accidental-mutation checks.

    This establishes content integrity only; it does not prove which source
    file or process produced the frame.
    """
    try:
        schema = {
            "columns": [(repr(column), str(dtype)) for column, dtype in zip(frame.columns, frame.dtypes)],
            "index_type": type(frame.index).__name__,
            "index_dtype": str(frame.index.dtype),
            "shape": frame.shape,
        }
        digest = sha256(json.dumps(schema, sort_keys=True).encode("utf-8"))
        digest.update(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
    except (TypeError, ValueError) as error:
        raise ValueError("Dataframe contains values that cannot be fingerprinted") from error
    return digest.hexdigest()


def _split_fingerprint(split: "TemporalSplit", timestamp_col: str) -> str:
    split.validate()
    payload = {
        "timestamp_col": timestamp_col,
        "windows": {
            name: {"start": getattr(split, name).parsed()[0].isoformat(),
                   "end": getattr(split, name).parsed()[1].isoformat()}
            for name in ("train", "validation", "holdout")
        },
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _approval_record_fingerprint(approval: "PreregistrationApproval") -> str:
    payload = {
        name: getattr(approval, name)
        for name in PreregistrationApproval.__dataclass_fields__
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _file_hashes(files: dict[str, str | Path]) -> dict[str, dict[str, str]]:
    if not files:
        raise ValueError("At least one file is required for an approval fingerprint")
    result: dict[str, dict[str, str]] = {}
    for name, value in sorted(files.items()):
        path = Path(value).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Required provenance file does not exist: {path}")
        result[name] = {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}
    return result


def _core_source_files() -> dict[str, Path]:
    root = Path(__file__).parent
    names = ("backtester.py", "data_loader.py", "strategies.py", "experiment_protocol.py")
    return {name: root / name for name in names}


def _merge_source_files(implementation_files: dict[str, str | Path]) -> dict[str, Path]:
    sources = _core_source_files()
    duplicate_names = set(sources) & set(implementation_files)
    if duplicate_names:
        raise ValueError(
            f"Experiment implementation names conflict with core files: {sorted(duplicate_names)}"
        )
    sources.update({name: Path(path) for name, path in implementation_files.items()})
    return sources


def _current_code_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parents[1],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


@dataclass(frozen=True)
class PreregistrationApproval:
    """Local review record; use the factory, as direct construction is unsupported.

    This is an auditable accidental-use safeguard, not a tamper-proof
    authorization service.
    """

    hypothesis_id: str
    hypothesis_version: int
    approver: str
    approved_at_utc: str
    approval_note: str
    specification_sha256: str
    config_sha256: str
    hypothesis_sha256: str
    data_files: dict[str, dict[str, str]]
    implementation_files: dict[str, dict[str, str]]


def create_preregistration_approval(
    config: ExperimentConfig,
    hypothesis: HypothesisSpec,
    data_files: dict[str, str | Path],
    implementation_files: dict[str, str | Path],
    *,
    approver: str,
    approved_at_utc: str,
    approval_note: str,
) -> PreregistrationApproval:
    """Create a review record bound to the current spec, data, and source bytes."""
    config.validate()
    hypothesis.validate()
    if config.hypothesis_approval_status.strip().upper() != "APPROVED":
        raise PermissionError("Config must record APPROVED alongside an approval record")
    if hypothesis.approval_status.strip().upper() != "APPROVED":
        raise PermissionError("Hypothesis must record APPROVED alongside an approval record")
    if (config.hypothesis_id, config.hypothesis_version) != (
        hypothesis.hypothesis_id, hypothesis.hypothesis_version
    ):
        raise ValueError("Config and hypothesis identifiers/versions do not match")
    if hypothesis.decisions.unresolved_fields():
        raise PermissionError(
            "Unresolved research decisions block approval: "
            + ", ".join(hypothesis.decisions.unresolved_fields())
        )
    if not approver.strip() or not approval_note.strip():
        raise ValueError("Approver identity and approval note are required")
    approved = pd.Timestamp(approved_at_utc)
    if approved.tzinfo is None:
        raise ValueError("Approval timestamp must include a timezone")
    approved_at_utc = approved.tz_convert("UTC").isoformat()
    data_hashes = _file_hashes(data_files)
    implementation_hashes = _file_hashes(_merge_source_files(implementation_files))
    spec = {
        "config": config.as_dict(),
        "hypothesis": hypothesis.as_dict(),
        "data_files": data_hashes,
        "implementation_files": implementation_hashes,
    }
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return PreregistrationApproval(
        hypothesis_id=hypothesis.hypothesis_id,
        hypothesis_version=hypothesis.hypothesis_version,
        approver=approver.strip(),
        approved_at_utc=approved_at_utc,
        approval_note=approval_note.strip(),
        specification_sha256=sha256(canonical.encode("utf-8")).hexdigest(),
        config_sha256=config_fingerprint(config),
        hypothesis_sha256=sha256(json.dumps(
            hypothesis.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest(),
        data_files=data_hashes,
        implementation_files=implementation_hashes,
    )


def _approval_matches_unchecked(
    config: ExperimentConfig,
    hypothesis: HypothesisSpec,
    approval: PreregistrationApproval,
) -> bool:
    if not isinstance(approval, PreregistrationApproval):
        return False
    if config.hypothesis_approval_status.strip().upper() != "APPROVED":
        return False
    if hypothesis.approval_status.strip().upper() != "APPROVED":
        return False
    if hypothesis.decisions.unresolved_fields():
        return False
    if (config.hypothesis_id, config.hypothesis_version) != (
        hypothesis.hypothesis_id, hypothesis.hypothesis_version
    ):
        return False
    if (config.hypothesis_id, config.hypothesis_version) != (
        approval.hypothesis_id, approval.hypothesis_version
    ):
        return False
    if not all((approval.approver.strip(), approval.approval_note.strip())):
        return False
    try:
        approved_at = pd.Timestamp(approval.approved_at_utc)
        if approved_at.tzinfo is None:
            return False
        approved_at.tz_convert("UTC")
        if len(approval.specification_sha256) != 64:
            return False
    except (AttributeError, TypeError, ValueError):
        return False
    try:
        data_now = _file_hashes({k: v["path"] for k, v in approval.data_files.items()})
        impl_now = _file_hashes({k: v["path"] for k, v in approval.implementation_files.items()})
    except (OSError, KeyError, TypeError, AttributeError, ValueError):
        return False
    if data_now != approval.data_files or impl_now != approval.implementation_files:
        return False
    hypothesis_json = json.dumps(
        hypothesis.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    hypothesis_hash = sha256(hypothesis_json.encode("utf-8")).hexdigest()
    if config_fingerprint(config) != approval.config_sha256 or hypothesis_hash != approval.hypothesis_sha256:
        return False
    payload = {
        "config": config.as_dict(),
        "hypothesis": hypothesis.as_dict(),
        "data_files": data_now,
        "implementation_files": impl_now,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest() == approval.specification_sha256


def _approval_matches(
    config: ExperimentConfig,
    hypothesis: HypothesisSpec,
    approval: PreregistrationApproval,
) -> bool:
    try:
        return _approval_matches_unchecked(config, hypothesis, approval)
    except (OSError, KeyError, TypeError, AttributeError, ValueError, OverflowError):
        return False


def validate_preregistration_approval(
    config: ExperimentConfig,
    hypothesis: HypothesisSpec,
    approval: PreregistrationApproval | None,
) -> None:
    """Fail unless an explicit approval still matches current spec and files."""
    config.validate()
    hypothesis.validate()
    if config.hypothesis_approval_status.strip().upper() != "APPROVED":
        raise PermissionError("An approval record requires config status APPROVED")
    if hypothesis.approval_status.strip().upper() != "APPROVED":
        raise PermissionError("An approval record requires hypothesis status APPROVED")
    unresolved = hypothesis.decisions.unresolved_fields()
    if unresolved:
        raise PermissionError("Unresolved research decisions block approval: " + ", ".join(unresolved))
    if approval is None or not _approval_matches(config, hypothesis, approval):
        raise PermissionError("Preregistration approval is missing, stale, or mismatched")


@dataclass
class TemporalPartitions:
    train: pd.DataFrame
    validation: pd.DataFrame
    _holdout: pd.DataFrame = field(repr=False)
    source_frame_sha256: str = field(default="", repr=False)
    _timestamp_col: str = field(default="available_at", repr=False)
    _partition_spec_sha256: str = field(default="", repr=False)
    _initial_partition_sha256: str = field(default="", repr=False)
    _frozen_config_hash: str | None = None
    _frozen_approval_hash: str | None = field(default=None, repr=False)
    _frozen_partition_hash: str | None = field(default=None, repr=False)

    def _current_partition_fingerprint(self) -> str:
        material = "".join((
            self.source_frame_sha256,
            self._partition_spec_sha256,
            *(dataframe_fingerprint(frame)
              for frame in (self.train, self.validation, self._holdout)),
        ))
        return sha256(material.encode("ascii")).hexdigest()

    @property
    def development(self) -> pd.DataFrame:
        """Training and validation data available before holdout evaluation."""
        return pd.concat([self.train, self.validation], ignore_index=True)

    def freeze_for_holdout(
        self,
        config: ExperimentConfig,
        hypothesis: HypothesisSpec,
        approval: PreregistrationApproval | None = None,
    ) -> None:
        """Freeze the current experiment definition before holdout access."""
        validate_preregistration_approval(config, hypothesis, approval)
        if _split_fingerprint(config.split, self._timestamp_col) != self._partition_spec_sha256:
            raise PermissionError("Configured split does not match the partition boundaries")
        current_partition_hash = self._current_partition_fingerprint()
        if current_partition_hash != self._initial_partition_sha256:
            raise PermissionError("Partition data changed after partition creation")
        config_hash = config_fingerprint(config)
        if self._frozen_config_hash is not None and self._frozen_config_hash != config_hash:
            raise ValueError("Experiment config is already frozen for another fingerprint")
        approval_hash = _approval_record_fingerprint(approval)
        if self._frozen_approval_hash is not None and self._frozen_approval_hash != approval_hash:
            raise ValueError("Partitions are already frozen under another approval record")
        self._frozen_config_hash = config_hash
        self._frozen_approval_hash = approval_hash
        self._frozen_partition_hash = current_partition_hash

    def open_holdout(
        self,
        config: ExperimentConfig,
        hypothesis: HypothesisSpec,
        approval: PreregistrationApproval | None = None,
    ) -> pd.DataFrame:
        if self._frozen_config_hash is None:
            raise PermissionError("Freeze the experiment config before opening holdout data")
        validate_preregistration_approval(config, hypothesis, approval)
        config_hash = config_fingerprint(config)
        if config_hash != self._frozen_config_hash:
            raise PermissionError("Holdout config fingerprint does not match frozen config")
        if _approval_record_fingerprint(approval) != self._frozen_approval_hash:
            raise PermissionError("Holdout approval differs from the frozen approval record")
        if _split_fingerprint(config.split, self._timestamp_col) != self._partition_spec_sha256:
            raise PermissionError("Holdout partition boundaries changed after creation")
        if self._current_partition_fingerprint() != self._frozen_partition_hash:
            raise PermissionError("Holdout partition data changed after freeze")
        return self._holdout.copy()


def split_by_availability(
    frame: pd.DataFrame,
    split: TemporalSplit,
    timestamp_col: str = "available_at",
) -> TemporalPartitions:
    split.validate()
    if frame.empty:
        raise ValueError("At least one availability observation is required")
    if timestamp_col not in frame:
        raise ValueError(f"Missing availability column: {timestamp_col}")
    timestamps = pd.to_datetime(frame[timestamp_col], utc=True, errors="raise")
    if timestamps.isna().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("Availability timestamps must be valid and ordered")

    windows = {
        "train": split.train.parsed(),
        "validation": split.validation.parsed(),
        "holdout": split.holdout.parsed(),
    }
    masks = {
        name: (timestamps >= start) & (timestamps < end)
        for name, (start, end) in windows.items()
    }
    assigned = masks["train"] | masks["validation"] | masks["holdout"]
    if not assigned.all():
        raise ValueError(
            f"{int((~assigned).sum())} observations fall outside configured split windows"
        )
    if (masks["train"] & masks["validation"]).any() or (
        masks["validation"] & masks["holdout"]
    ).any():
        raise ValueError("Temporal partition overlap detected")

    train = frame.loc[masks["train"]].copy()
    validation = frame.loc[masks["validation"]].copy()
    holdout = frame.loc[masks["holdout"]].copy()
    source_hash = dataframe_fingerprint(frame)
    split_hash = _split_fingerprint(split, timestamp_col)
    initial_hash = sha256("".join((
        source_hash, split_hash,
        dataframe_fingerprint(train), dataframe_fingerprint(validation),
        dataframe_fingerprint(holdout),
    )).encode("ascii")).hexdigest()
    return TemporalPartitions(
        train=train,
        validation=validation,
        _holdout=holdout,
        source_frame_sha256=source_hash,
        _timestamp_col=timestamp_col,
        _partition_spec_sha256=split_hash,
        _initial_partition_sha256=initial_hash,
    )


def write_experiment_manifest(
    config: ExperimentConfig,
    output_root: str | Path,
    data_files: dict[str, str | Path],
    implementation_files: dict[str, str | Path],
    hypothesis: HypothesisSpec,
    *,
    code_revision: str | None = None,
    approval: PreregistrationApproval | None = None,
) -> Path:
    config.validate()
    hypothesis.validate()
    if (config.hypothesis_id, config.hypothesis_version) != (
        hypothesis.hypothesis_id, hypothesis.hypothesis_version
    ):
        raise ValueError("Config and hypothesis identifiers/versions do not match")
    if approval is not None and not _approval_matches(config, hypothesis, approval):
        raise PermissionError("Manifest approval record does not match current inputs")
    run_dir = Path(output_root) / config.experiment_id
    if run_dir.exists():
        raise FileExistsError(f"Experiment directory already exists: {run_dir}")
    if not data_files:
        raise ValueError("At least one input data file is required for a reproducible manifest")
    missing = [str(path) for path in data_files.values() if not Path(path).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing experiment data files: {missing}")
    if not implementation_files:
        raise ValueError("At least one experiment-specific implementation file is required")
    missing = [
        str(path) for path in implementation_files.values()
        if not Path(path).is_file()
    ]
    if missing:
        raise FileNotFoundError(f"Missing experiment implementation files: {missing}")

    source_files = _merge_source_files(implementation_files)
    data_hashes = _file_hashes(data_files)
    implementation_hashes = _file_hashes(source_files)
    input_data = {}
    for key, entry in data_hashes.items():
        path = Path(entry["path"])
        columns = pd.read_csv(path, nrows=0).columns
        time_col = next(
            (name for name in ("available_at", "timestamp", "open_time", "time") if name in columns),
            None,
        )
        if time_col is None:
            raise ValueError(f"Cannot identify dataset time column for provenance: {path}")
        values = pd.read_csv(path, usecols=[time_col])[time_col]
        timestamps = pd.to_datetime(values, utc=True, errors="raise").dropna()
        if timestamps.empty:
            raise ValueError(f"Dataset has no usable timestamps: {path}")
        input_data[key] = {
            **entry,
            "dataset_id": key,
            "time_column": time_col,
            "first_timestamp_utc": timestamps.min().isoformat(),
            "last_timestamp_utc": timestamps.max().isoformat(),
            "timeframe": config.timeframe,
        }
    config_data = config.as_dict()
    hypothesis_data = hypothesis.as_dict()
    manifest = {
        "manifest_schema_version": 2,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": config.experiment_id,
        "intended_specification": {
            "config": config_data,
            "config_sha256": config_fingerprint(config),
            "hypothesis": hypothesis_data,
            "hypothesis_sha256": sha256(json.dumps(
                hypothesis_data, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")).hexdigest(),
        },
        "actual_inputs_and_implementation": {
            "input_data": input_data,
            "implementation_sha256": implementation_hashes,
            "code_revision": code_revision or _current_code_revision(),
            "runtime": {
                "python": platform.python_version(),
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "platform": platform.platform(),
            },
        },
        "outputs": [],
        "validation_and_approval": {
            "status": "approved_for_evaluation" if approval else "not_approved",
            "approval_record": (
                None if approval is None else {
                    "approver": approval.approver,
                    "approved_at_utc": approval.approved_at_utc,
                    "approval_note": approval.approval_note,
                    "specification_sha256": approval.specification_sha256,
                }
            ),
            "validation_status": "not_run",
        },
        "lifecycle_status": "configured_not_run",
    }
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{config.experiment_id}.manifest.",
        suffix=".tmp",
        dir=output_root,
    )
    temporary_path = Path(temporary_name)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor_open = False
            handle.write(json.dumps(manifest, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        run_dir.mkdir(exist_ok=False)
        manifest_path = run_dir / "manifest.json"
        try:
            # Publish a fully written manifest without replacing an existing file.
            os.link(temporary_path, manifest_path)
        except Exception:
            try:
                run_dir.rmdir()
            except OSError:
                pass
            raise
        return manifest_path
    finally:
        if descriptor_open:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def finalize_experiment_manifest(
    manifest_path: str | Path,
    artifacts: dict[str, str | Path],
    validation: dict[str, Any],
) -> None:
    """Record completed computation and separately reported scientific status.

    Validation requires ``computation_status='completed'`` and an explicit
    ``scientific_status`` of ``not_assessed``, ``criteria_met``,
    ``criteria_not_met``, or ``inconclusive``. No scientific thresholds are
    defined here. Artifact hashes are first captured at finalization and do
    not establish integrity before that moment.
    """
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("lifecycle_status") != "configured_not_run":
        raise ValueError("Only a configured, not-run manifest can be finalized")
    if manifest.get("validation_and_approval", {}).get("approval_record") is None:
        raise PermissionError("An approved experiment cannot be finalized without its approval record")
    intended = manifest.get("intended_specification", {})
    actual = manifest.get("actual_inputs_and_implementation", {})
    config_snapshot = intended.get("config", {})
    hypothesis_snapshot = intended.get("hypothesis", {})
    try:
        snapshot_decisions = ResearchDecisions(**hypothesis_snapshot["decisions"])
    except (KeyError, TypeError) as error:
        raise PermissionError("Manifest approval decision record is malformed") from error
    if (str(config_snapshot.get("hypothesis_approval_status", "")).upper() != "APPROVED"
            or str(hypothesis_snapshot.get("approval_status", "")).upper() != "APPROVED"
            or snapshot_decisions.unresolved_fields()):
        raise PermissionError("Manifest does not contain an approved, resolved hypothesis")
    if (config_snapshot.get("hypothesis_id"), config_snapshot.get("hypothesis_version")) != (
        hypothesis_snapshot.get("hypothesis_id"), hypothesis_snapshot.get("hypothesis_version")
    ):
        raise PermissionError("Manifest config and hypothesis identifiers do not match")
    data_meta = actual.get("input_data", {})
    source_meta = actual.get("implementation_sha256", {})
    try:
        data_current = _file_hashes({key: value["path"] for key, value in data_meta.items()})
        sources_current = _file_hashes({key: value["path"] for key, value in source_meta.items()})
    except (KeyError, FileNotFoundError, ValueError) as error:
        raise PermissionError("Approved data or source inputs are unavailable") from error
    if data_current != {
        key: {"path": value["path"], "sha256": value["sha256"]}
        for key, value in data_meta.items()
    } or sources_current != source_meta:
        raise PermissionError("Data or implementation changed after experiment approval")
    approval_payload = {
        "config": intended["config"],
        "hypothesis": intended["hypothesis"],
        "data_files": data_current,
        "implementation_files": sources_current,
    }
    approval_json = json.dumps(
        approval_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    approval_block = manifest["validation_and_approval"]
    if approval_block.get("status") != "approved_for_evaluation":
        raise PermissionError("Manifest is not marked approved for evaluation")
    recorded_approval = approval_block["approval_record"]
    if sha256(approval_json.encode("utf-8")).hexdigest() != recorded_approval.get("specification_sha256"):
        raise PermissionError("Manifest specification no longer matches its approval record")
    if not artifacts:
        raise ValueError("Completed experiments must identify at least one artifact")
    run_dir = manifest_path.parent.resolve()
    output_records = []
    resolved_artifact_paths: set[Path] = set()
    for name, value in sorted(artifacts.items()):
        path = Path(value).resolve()
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Artifact names must be non-empty strings")
        if not path.is_file() or run_dir not in path.parents:
            raise ValueError("Artifacts must exist inside the experiment run directory")
        if path in resolved_artifact_paths:
            raise ValueError("Artifact paths must be unique")
        resolved_artifact_paths.add(path)
        output_records.append({
            "name": name,
            "path": str(path.relative_to(run_dir)),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "created_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    validation = _validate_manifest_validation(validation)
    manifest["outputs"] = output_records
    manifest["validation_and_approval"]["validation_status"] = validation["scientific_status"]
    manifest["validation_and_approval"]["validation"] = validation
    manifest["lifecycle_status"] = "evaluation_completed"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{manifest_path.name}.", suffix=".tmp", dir=manifest_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, manifest_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def verify_experiment_manifest(manifest_path: str | Path) -> bool:
    """Verify finalized manifest structure and artifact path/hash integrity.

    Raises ``ValueError`` for malformed, inconsistent, missing, escaping,
    duplicate, or modified artifacts. This verifies bytes only from the
    recorded finalization point onward.
    """
    manifest_path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Manifest is missing or malformed") from error
    if manifest.get("manifest_schema_version") != 2:
        raise ValueError("Unsupported manifest schema")
    if manifest.get("lifecycle_status") != "evaluation_completed":
        raise ValueError("Manifest does not describe a finalized evaluation")
    validation_block = manifest.get("validation_and_approval")
    if not isinstance(validation_block, dict) or validation_block.get("approval_record") is None:
        raise ValueError("Finalized manifest is missing approval metadata")
    approval = validation_block.get("approval_record")
    if (validation_block.get("status") != "approved_for_evaluation"
            or not isinstance(approval, dict)
            or not isinstance(approval.get("specification_sha256"), str)
            or len(approval["specification_sha256"]) != 64):
        raise ValueError("Finalized manifest has inconsistent approval status")
    validation = validation_block.get("validation")
    try:
        validation = _validate_manifest_validation(validation)
    except ValueError as error:
        raise ValueError("Finalized manifest has invalid validation metadata") from error
    if validation_block.get("validation_status") != validation.get("scientific_status"):
        raise ValueError("Finalized manifest has inconsistent scientific status")
    intended = manifest.get("intended_specification")
    actual = manifest.get("actual_inputs_and_implementation")
    if not isinstance(intended, dict) or not isinstance(actual, dict):
        raise ValueError("Finalized manifest is missing specification or provenance")
    config_snapshot = intended.get("config")
    hypothesis_snapshot = intended.get("hypothesis")
    if not isinstance(config_snapshot, dict) or not isinstance(hypothesis_snapshot, dict):
        raise ValueError("Finalized manifest specification is malformed")
    if manifest.get("experiment_id") != config_snapshot.get("experiment_id"):
        raise ValueError("Finalized manifest experiment identity does not match config")
    run_dir = manifest_path.parent.resolve()
    if manifest_path.name != "manifest.json" or run_dir.name != manifest.get("experiment_id"):
        raise ValueError("Finalized manifest identity does not match its run directory")
    try:
        decisions = ResearchDecisions(**hypothesis_snapshot["decisions"])
    except (KeyError, TypeError) as error:
        raise ValueError("Finalized manifest decision record is malformed") from error
    if (str(config_snapshot.get("hypothesis_approval_status", "")).upper() != "APPROVED"
            or str(hypothesis_snapshot.get("approval_status", "")).upper() != "APPROVED"
            or decisions.unresolved_fields()):
        raise ValueError("Finalized manifest does not contain an approved, resolved spec")
    try:
        data_hashes = {
            name: {"path": item["path"], "sha256": item["sha256"]}
            for name, item in actual["input_data"].items()
        }
        implementation_hashes = actual["implementation_sha256"]
        approval_payload = {
            "config": config_snapshot,
            "hypothesis": hypothesis_snapshot,
            "data_files": data_hashes,
            "implementation_files": implementation_hashes,
        }
        computed_specification_hash = sha256(json.dumps(
            approval_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
        computed_config_hash = sha256(json.dumps(
            config_snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
        computed_hypothesis_hash = sha256(json.dumps(
            hypothesis_snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Finalized manifest provenance is malformed") from error
    if computed_specification_hash != approval["specification_sha256"]:
        raise ValueError("Finalized manifest approval fingerprint is inconsistent")
    if computed_config_hash != intended.get("config_sha256"):
        raise ValueError("Finalized manifest config fingerprint is inconsistent")
    if computed_hypothesis_hash != intended.get("hypothesis_sha256"):
        raise ValueError("Finalized manifest hypothesis fingerprint is inconsistent")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Finalized manifest must reference at least one artifact")
    names: set[str] = set()
    paths: set[Path] = set()
    for record in outputs:
        if not isinstance(record, dict):
            raise ValueError("Artifact record must be an object")
        name, relative = record.get("name"), record.get("path")
        expected_hash = record.get("sha256")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Artifact names must be present and unique")
        if not isinstance(relative, str) or not relative:
            raise ValueError("Artifact path must be a non-empty relative path")
        artifact_ref = Path(relative)
        if artifact_ref.is_absolute() or ".." in artifact_ref.parts:
            raise ValueError("Artifact path must remain within the run directory")
        artifact = (run_dir / artifact_ref).resolve()
        if artifact != run_dir and run_dir not in artifact.parents:
            raise ValueError("Artifact path escapes the run directory")
        if artifact in paths:
            raise ValueError("Artifact paths must be unique")
        if not artifact.is_file():
            raise ValueError(f"Artifact is missing: {relative}")
        if (not isinstance(expected_hash, str) or len(expected_hash) != 64
                or sha256(artifact.read_bytes()).hexdigest() != expected_hash):
            raise ValueError(f"Artifact hash mismatch: {relative}")
        names.add(name)
        paths.add(artifact)
    return True


def append_research_log(path: str | Path, entry: dict[str, Any]) -> None:
    """Append one auditable result or rejection reason without replacing the log."""
    path = Path(path)
    missing = [field for field in RESEARCH_LOG_FIELDS if field not in entry]
    if missing:
        raise ValueError(f"Research log entry missing fields: {missing}")
    if not str(entry["experiment_id"]).strip():
        raise ValueError("Research log experiment_id is required")
    decision = str(entry["decision"]).strip().upper()
    if decision in {"REJECTED", "FAILED", "BLOCKED"} and not str(entry["notes"]).strip():
        raise ValueError("Rejected/failed/blocked entries must record a reason in notes")

    if path.exists():
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != RESEARCH_LOG_FIELDS:
                raise ValueError("Research log columns do not match the known schema")
            if any(row["experiment_id"] == entry["experiment_id"] for row in reader):
                raise FileExistsError(
                    f"Research log already contains {entry['experiment_id']}"
                )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESEARCH_LOG_FIELDS)
        if path.stat().st_size == 0:
            writer.writeheader()
        writer.writerow({field: entry[field] for field in RESEARCH_LOG_FIELDS})
