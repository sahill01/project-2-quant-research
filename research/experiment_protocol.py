"""Versioned experiment configuration, chronological partitions, and manifests."""

from dataclasses import dataclass, field
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd


RESEARCH_LOG_FIELDS = (
    "experiment_id", "date", "hypothesis", "symbol", "timeframe",
    "start", "end", "parameters", "baseline", "result", "decision", "notes",
)


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

    def validate(self) -> None:
        if not self.experiment_id.strip() or not self.hypothesis_id.strip():
            raise ValueError("Experiment and hypothesis identifiers are required")
        if self.version < 1:
            raise ValueError("Experiment config version must be positive")
        if not self.strategy.strip() or not self.assets:
            raise ValueError("Strategy and at least one asset are required")
        if len(set(self.assets)) != len(self.assets):
            raise ValueError("Experiment assets must be unique")
        if not self.timeframe.strip():
            raise ValueError("Timeframe is required")
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
            "hypothesis_approval_status": self.hypothesis_approval_status.strip().upper(),
            "strategy": self.strategy,
            "assets": list(self.assets),
            "timeframe": self.timeframe,
            "parameters": self.parameters,
            "execution": self.execution,
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


@dataclass
class TemporalPartitions:
    train: pd.DataFrame
    validation: pd.DataFrame
    _holdout: pd.DataFrame = field(repr=False)
    _frozen_config_hash: str | None = None

    @property
    def development(self) -> pd.DataFrame:
        """Training and validation data available before holdout evaluation."""
        return pd.concat([self.train, self.validation], ignore_index=True)

    def freeze_for_holdout(self, config: ExperimentConfig) -> None:
        """Freeze the current experiment definition before holdout access."""
        config.validate()
        if config.hypothesis_approval_status.strip().upper() != "APPROVED":
            raise PermissionError(
                "An explicitly APPROVED hypothesis is required before holdout freeze"
            )
        config_hash = config_fingerprint(config)
        if self._frozen_config_hash is not None and self._frozen_config_hash != config_hash:
            raise ValueError("Experiment config is already frozen for another fingerprint")
        self._frozen_config_hash = config_hash

    def open_holdout(self, config: ExperimentConfig) -> pd.DataFrame:
        if self._frozen_config_hash is None:
            raise PermissionError("Freeze the experiment config before opening holdout data")
        config_hash = config_fingerprint(config)
        if config_hash != self._frozen_config_hash:
            raise PermissionError("Holdout config fingerprint does not match frozen config")
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

    return TemporalPartitions(
        train=frame.loc[masks["train"]].copy(),
        validation=frame.loc[masks["validation"]].copy(),
        _holdout=frame.loc[masks["holdout"]].copy(),
    )


def write_experiment_manifest(
    config: ExperimentConfig,
    output_root: str | Path,
    data_files: dict[str, str | Path],
    implementation_files: dict[str, str | Path],
) -> Path:
    config.validate()
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

    source_files = {
        "backtester.py": Path(__file__).with_name("backtester.py"),
        "data_loader.py": Path(__file__).with_name("data_loader.py"),
        "strategies.py": Path(__file__).with_name("strategies.py"),
        "experiment_protocol.py": Path(__file__),
    }
    duplicate_names = set(source_files) & set(implementation_files)
    if duplicate_names:
        raise ValueError(
            f"Experiment implementation names conflict with core files: {sorted(duplicate_names)}"
        )
    source_files.update({
        name: Path(path) for name, path in implementation_files.items()
    })
    config_data = config.as_dict()
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config_data,
        "config_sha256": config_fingerprint(config),
        "input_data": {
            key: {
                "path": str(Path(path)),
                "sha256": sha256(Path(path).read_bytes()).hexdigest(),
            }
            for key, path in sorted(data_files.items())
        },
        "implementation_sha256": {
            name: sha256(path.read_bytes()).hexdigest()
            for name, path in sorted(source_files.items())
        },
        "status": "configured_not_run",
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
