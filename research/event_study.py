"""Causal feature-event-study primitives; no trading or live-data runner.

The outcome calculator is deliberately a pure table operation. Callers must
identify synthetic fixtures as such, or provide a current approved
specification and provenance for research data. These local checks guard
against accidental misuse; they are not a security boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
import os
import platform
from pathlib import Path
import tempfile
from typing import Any, Mapping

import numpy as np
import pandas as pd

from research.data_loader import timeframe_to_timedelta, validate_candle_availability
from research.experiment_protocol import TemporalSplit
from research.structure_features import confirmed_market_structure
from research.support_resistance import confirmed_swing_zones


_PLACEHOLDERS = ("UNRESOLVED", "TBD", "TODO", "PENDING", "TO BE DETERMINED")
_COHORT_LABELS = {"higher_low", "lower_low"}
_STRUCTURE_LABELS = _COHORT_LABELS | {"initial_low", "equal_low"}
_STAGES = {"development", "validation", "holdout"}
_EVENT_LEDGER_COLUMNS = (
    "event_id", "asset", "timeframe", "event_type", "zone_type", "zone_id",
    "pivot_time", "origin_structure_label", "cohort", "origin_available_at",
    "created_at", "anchor_timestamp", "available_at", "anchor_close",
    "lower_bound", "upper_bound", "touch_count", "eligible", "exclusion_reason",
    "source_event_time", "source_payload",
)
_OUTCOME_COLUMNS = (
    "outcome_return", "target_timestamp", "target_available_at", "requested_target_at",
    "realized_elapsed", "observed_bars_forward", "missing_candle_gaps",
    "outcome_included", "outcome_exclusion_reason",
)
_BUNDLE_ARTIFACTS = {
    "specification", "events", "outcomes", "exclusions", "data_quality",
    "summary", "validation",
}
_REQUIRED_RUN_CHECKS = {
    "approved_spec_and_current_hashes",
    "requested_stage_authorized",
    "only_stage_prefix_ohlcv_materialized",
    "cohort_and_outcome_rows_within_scope",
    "included_outcomes_finite_and_after_anchor",
    "included_outcomes_before_stage_end",
}


def _is_unresolved(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = value.strip().upper()
        return not normalized or any(
            normalized == item or normalized.startswith(item + ":")
            for item in _PLACEHOLDERS
        )
    if isinstance(value, (tuple, list, dict, set)):
        return not value
    return False


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value):
        return _canonical_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, pd.Timedelta):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            raise ValueError("Canonical timestamps must include a timezone")
        return timestamp.tz_convert("UTC").isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def canonical_json(value: Any) -> str:
    """Canonical JSON used for spec and local approval fingerprints."""
    try:
        return json.dumps(
            _canonical_value(value), sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Event-study metadata is not canonical-JSON compatible") from error


def _hash_mapping(mapping: Mapping[str, str], name: str) -> dict[str, str]:
    if not isinstance(mapping, Mapping) or not mapping:
        raise ValueError(f"{name} must contain at least one identity and hash")
    result = dict(mapping)
    for identity, digest in result.items():
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError(f"{name} identities must be non-empty strings")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"{name} values must be SHA-256 hex digests")
        try:
            int(digest, 16)
        except ValueError as error:
            raise ValueError(f"{name} values must be SHA-256 hex digests") from error
    return dict(sorted(result.items()))


@dataclass(frozen=True)
class EventStudySpec:
    """Versioned, feature-only study contract; unresolved fields block approval."""

    hypothesis_id: str
    hypothesis_version: int
    event_definition: str | None
    cohort_labels: tuple[str, ...] | None
    event_anchor_semantics: str | None
    availability_semantics: str | None
    origin_join_keys: tuple[str, ...] | None
    causal_availability_rule: str | None
    outcome_formula: str | None
    horizon_convention: str | None
    horizon_value: str | int | float | None
    endpoint_rule: str | None
    max_lateness: str | None
    asset_timeframe_scope: tuple[tuple[str, str], ...] | None
    feature_parameters: Mapping[str, Any] | None
    missing_data_policy: str | None
    incomplete_window_policy: str | None
    repeated_touch_policy: str | None
    overlapping_event_policy: str | None
    split: TemporalSplit | None
    boundary_policy: str | None
    embargo: str | None
    estimand: str | None
    uncertainty_method: str | None
    multiplicity_family: tuple[str, ...] | None
    decision_criteria: str | None
    minimum_sample_rationale: str | None
    meaningful_effect_threshold: str | float | None
    data_file_hashes: Mapping[str, str] | None
    source_file_hashes: Mapping[str, str] | None
    approval_status: str = "DRAFT"
    experiment_type: str = "feature_event_study"
    schema_version: int = 1

    def unresolved_fields(self) -> tuple[str, ...]:
        names = (
            "event_definition", "cohort_labels", "event_anchor_semantics",
            "availability_semantics", "origin_join_keys", "causal_availability_rule",
            "outcome_formula", "horizon_convention", "horizon_value", "endpoint_rule",
            "asset_timeframe_scope", "feature_parameters", "missing_data_policy",
            "incomplete_window_policy", "repeated_touch_policy", "overlapping_event_policy",
            "split", "boundary_policy", "embargo", "estimand", "uncertainty_method",
            "multiplicity_family", "decision_criteria", "minimum_sample_rationale",
            "meaningful_effect_threshold", "data_file_hashes", "source_file_hashes",
        )
        missing = [name for name in names if _is_unresolved(getattr(self, name))]
        if (self.horizon_convention == "fixed_elapsed_time"
                and self.endpoint_rule == "first_close_at_or_after"
                and _is_unresolved(self.max_lateness)):
            missing.append("max_lateness")
        return tuple(missing)

    def validate(self, *, require_approved: bool = False) -> None:
        if self.experiment_type != "feature_event_study" or self.schema_version != 1:
            raise ValueError("Unsupported event-study type or schema version")
        if not self.hypothesis_id.strip() or self.hypothesis_version < 1:
            raise ValueError("A hypothesis identifier and positive version are required")
        if self.approval_status not in {"DRAFT", "APPROVED", "REJECTED"}:
            raise ValueError("Approval status must be DRAFT, APPROVED, or REJECTED")
        if self.asset_timeframe_scope:
            if (len(set(self.asset_timeframe_scope)) != len(self.asset_timeframe_scope)
                    or any(len(item) != 2 or not item[0].strip() or not item[1].strip()
                           for item in self.asset_timeframe_scope)):
                raise ValueError("Asset/timeframe scope must contain unique non-empty pairs")
        if isinstance(self.meaningful_effect_threshold, bool):
            raise ValueError("Meaningful effect threshold cannot be Boolean")
        if isinstance(self.meaningful_effect_threshold, (int, float)) and (
            not math.isfinite(float(self.meaningful_effect_threshold))
            or float(self.meaningful_effect_threshold) < 0
        ):
            raise ValueError("Numeric meaningful effect threshold must be finite and non-negative")
        if require_approved and self.approval_status != "APPROVED":
            raise PermissionError("Event study is not explicitly approved")
        if self.horizon_convention not in (None, "fixed_observed_bars", "fixed_elapsed_time"):
            raise ValueError("Unsupported horizon convention")
        if self.horizon_convention == "fixed_observed_bars" and self.horizon_value is not None:
            if (isinstance(self.horizon_value, bool)
                    or not isinstance(self.horizon_value, int)
                    or self.horizon_value < 1):
                raise ValueError("Observed-bar horizon must be a positive integer")
        if self.horizon_convention == "fixed_elapsed_time" and self.horizon_value is not None:
            if not isinstance(self.horizon_value, (str, pd.Timedelta)):
                raise ValueError("Elapsed horizon must be an explicit duration string")
            try:
                duration = pd.Timedelta(self.horizon_value)
            except (TypeError, ValueError) as error:
                raise ValueError("Elapsed horizon must be a valid positive duration") from error
            if pd.isna(duration) or duration <= pd.Timedelta(0):
                raise ValueError("Elapsed horizon must be positive")
        if self.endpoint_rule not in (None, "exact", "first_close_at_or_after"):
            raise ValueError("Unsupported endpoint rule")
        if (self.horizon_convention == "fixed_observed_bars"
                and self.endpoint_rule not in (None, "exact")):
            raise ValueError("Fixed observed-bar horizons require the exact indexed endpoint")
        if (self.horizon_convention == "fixed_elapsed_time"
                and self.endpoint_rule == "first_close_at_or_after"
                and self.max_lateness is not None
                and not isinstance(self.max_lateness, (str, pd.Timedelta))):
            raise ValueError("Endpoint lateness must be an explicit duration string")
        if (self.horizon_convention == "fixed_elapsed_time"
                and self.endpoint_rule == "first_close_at_or_after"
                and self.max_lateness is not None):
            lateness = pd.Timedelta(self.max_lateness)
            if pd.isna(lateness) or lateness < pd.Timedelta(0):
                raise ValueError("Endpoint lateness must be finite and non-negative")
        if self.boundary_policy not in (None, "purge", "error"):
            raise ValueError("Boundary policy must be purge or error")
        if self.missing_data_policy not in (
            None, "allow_and_report", "exclude_if_gap"
        ):
            raise ValueError("Missing-data policy must be allow_and_report or exclude_if_gap")
        if self.incomplete_window_policy not in (None, "exclude", "error"):
            raise ValueError("Incomplete-window policy must be exclude or error")
        if self.split is not None:
            self.split.validate()
        for mapping, label in (
            (self.data_file_hashes, "Data-file hashes"),
            (self.source_file_hashes, "Source-file hashes"),
        ):
            if mapping:
                _hash_mapping(mapping, label)
        if require_approved:
            unresolved = self.unresolved_fields()
            if unresolved:
                raise PermissionError(
                    "Unresolved scientific decisions block event-study approval: "
                    + ", ".join(unresolved)
                )
        canonical_json(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return _canonical_value(asdict(self))


def event_study_spec_fingerprint(spec: EventStudySpec) -> str:
    spec.validate()
    return sha256(canonical_json(spec.as_dict()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EventStudyApproval:
    hypothesis_id: str
    hypothesis_version: int
    approver: str
    approved_at_utc: str
    allowed_stages: tuple[str, ...]
    specification_sha256: str
    data_files: Mapping[str, Mapping[str, str]]
    source_files: Mapping[str, Mapping[str, str]]
    approval_sha256: str


@dataclass(frozen=True)
class EventStudyPlanLock:
    """Local, non-security record binding a resolved plan before holdout release."""

    specification_sha256: str
    approval_sha256: str
    locked_by: str
    locked_at_utc: str
    lock_sha256: str


@dataclass(frozen=True)
class EventStudyHoldoutRelease:
    """Explicit local authorization to run holdout against one locked plan."""

    specification_sha256: str
    approval_sha256: str
    plan_lock_sha256: str
    authorized_by: str
    authorized_at_utc: str
    release_sha256: str


def _validate_utc_actor(actor: str, timestamp: str, label: str) -> str:
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError(f"{label} actor must be non-empty")
    parsed = pd.Timestamp(timestamp)
    if parsed.tzinfo is None:
        raise ValueError(f"{label} timestamp must include a timezone")
    return parsed.tz_convert("UTC").isoformat()


def lock_event_study_plan(
    spec: EventStudySpec,
    approval: EventStudyApproval,
    *,
    locked_by: str,
    locked_at_utc: str,
    data_files: Mapping[str, str | Path],
    source_files: Mapping[str, str | Path],
) -> EventStudyPlanLock:
    """Bind the approved analysis plan before a separate holdout release step."""
    if "holdout" in approval.allowed_stages:
        raise PermissionError("Holdout must not be included in the initial stage approval")
    validate_event_study_execution(
        spec, approval, stage="validation", data_files=data_files, source_files=source_files
    )
    stamp = _validate_utc_actor(locked_by, locked_at_utc, "Plan lock")
    spec_hash = event_study_spec_fingerprint(spec)
    payload = {
        "specification_sha256": spec_hash,
        "approval_sha256": approval.approval_sha256,
        "locked_by": locked_by.strip(),
        "locked_at_utc": stamp,
    }
    return EventStudyPlanLock(**payload, lock_sha256=sha256(canonical_json(payload).encode()).hexdigest())


def authorize_event_study_holdout(
    spec: EventStudySpec,
    approval: EventStudyApproval,
    plan_lock: EventStudyPlanLock,
    *,
    authorized_by: str,
    authorized_at_utc: str,
    data_files: Mapping[str, str | Path],
    source_files: Mapping[str, str | Path],
) -> EventStudyHoldoutRelease:
    """Create a separate explicit release bound to the locked approved plan."""
    validate_event_study_execution(
        spec, approval, stage="validation", data_files=data_files, source_files=source_files
    )
    spec_hash = event_study_spec_fingerprint(spec)
    lock_payload = {
        "specification_sha256": plan_lock.specification_sha256,
        "approval_sha256": plan_lock.approval_sha256,
        "locked_by": plan_lock.locked_by,
        "locked_at_utc": plan_lock.locked_at_utc,
    }
    expected_lock = sha256(canonical_json(lock_payload).encode()).hexdigest()
    if (plan_lock.lock_sha256 != expected_lock
            or plan_lock.specification_sha256 != spec_hash
            or plan_lock.approval_sha256 != approval.approval_sha256):
        raise PermissionError("Plan lock is stale or inconsistent")
    stamp = _validate_utc_actor(authorized_by, authorized_at_utc, "Holdout release")
    if pd.Timestamp(stamp) <= pd.Timestamp(plan_lock.locked_at_utc):
        raise ValueError("Holdout release time must follow the analysis-plan lock")
    payload = {
        "specification_sha256": spec_hash,
        "approval_sha256": approval.approval_sha256,
        "plan_lock_sha256": plan_lock.lock_sha256,
        "authorized_by": authorized_by.strip(),
        "authorized_at_utc": stamp,
    }
    return EventStudyHoldoutRelease(
        **payload, release_sha256=sha256(canonical_json(payload).encode()).hexdigest()
    )


def _current_file_records(files: Mapping[str, str | Path]) -> dict[str, dict[str, str]]:
    if not files:
        raise ValueError("At least one data/source file is required")
    records: dict[str, dict[str, str]] = {}
    for identity, value in sorted(files.items()):
        path = Path(value).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Required provenance file does not exist: {path}")
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        records[identity] = {
            "path": str(path), "sha256": digest.hexdigest(),
        }
    return records


def _approval_payload(
    hypothesis_id: str,
    hypothesis_version: int,
    approver: str,
    approved_at_utc: str,
    allowed_stages: tuple[str, ...],
    specification_sha256: str,
    data_files: Mapping[str, Mapping[str, str]],
    source_files: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis_id,
        "hypothesis_version": hypothesis_version,
        "approver": approver,
        "approved_at_utc": approved_at_utc,
        "allowed_stages": allowed_stages,
        "specification_sha256": specification_sha256,
        "data_files": data_files,
        "source_files": source_files,
    }


def create_event_study_approval(
    spec: EventStudySpec,
    data_files: Mapping[str, str | Path],
    source_files: Mapping[str, str | Path],
    *,
    approver: str,
    approved_at_utc: str,
    allowed_stages: tuple[str, ...],
) -> EventStudyApproval:
    """Create a local approval record for a fully resolved, explicitly approved spec."""
    spec.validate(require_approved=True)
    if not approver.strip():
        raise ValueError("Approver must be non-empty")
    approved = pd.Timestamp(approved_at_utc)
    if approved.tzinfo is None:
        raise ValueError("Approval timestamp must include a timezone")
    stages = tuple(sorted(set(allowed_stages)))
    if not stages or not set(stages).issubset(_STAGES):
        raise ValueError("Approval must list supported evaluation stages")
    if "holdout" in stages:
        raise ValueError("Holdout requires a separate release after the analysis plan is locked")
    data_records = _current_file_records(data_files)
    source_records = _current_file_records(source_files)
    expected_data = _hash_mapping(spec.data_file_hashes or {}, "Data-file hashes")
    expected_sources = _hash_mapping(spec.source_file_hashes or {}, "Source-file hashes")
    if {key: value["sha256"] for key, value in data_records.items()} != expected_data:
        raise PermissionError("Current data files do not match the approved specification")
    if {key: value["sha256"] for key, value in source_records.items()} != expected_sources:
        raise PermissionError("Current source files do not match the approved specification")
    approved_time = approved.tz_convert("UTC").isoformat()
    fingerprint = event_study_spec_fingerprint(spec)
    payload = _approval_payload(
        spec.hypothesis_id, spec.hypothesis_version, approver.strip(), approved_time,
        stages, fingerprint, data_records, source_records,
    )
    return EventStudyApproval(
        hypothesis_id=spec.hypothesis_id,
        hypothesis_version=spec.hypothesis_version,
        approver=approver.strip(),
        approved_at_utc=approved_time,
        allowed_stages=stages,
        specification_sha256=fingerprint,
        data_files=data_records,
        source_files=source_records,
        approval_sha256=sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
    )


def validate_event_study_execution(
    spec: EventStudySpec,
    approval: EventStudyApproval,
    *,
    stage: str,
    data_files: Mapping[str, str | Path],
    source_files: Mapping[str, str | Path],
    holdout_release: EventStudyHoldoutRelease | None = None,
) -> None:
    """Fail closed on unresolved/stale inputs or a stage outside the approval."""
    spec.validate(require_approved=True)
    if not isinstance(approval, EventStudyApproval):
        raise PermissionError("A matching event-study approval record is required")
    if stage not in _STAGES:
        raise PermissionError(f"Unsupported event-study stage {stage!r}")
    if stage == "holdout":
        if holdout_release is None:
            raise PermissionError("Holdout requires a separate release after the plan is locked")
    elif stage not in approval.allowed_stages:
        raise PermissionError(f"Stage {stage!r} is not authorized by the approval")
    if (approval.hypothesis_id, approval.hypothesis_version) != (
        spec.hypothesis_id, spec.hypothesis_version
    ):
        raise PermissionError("Approval does not match this hypothesis")
    fingerprint = event_study_spec_fingerprint(spec)
    payload = _approval_payload(
        approval.hypothesis_id, approval.hypothesis_version, approval.approver,
        approval.approved_at_utc, approval.allowed_stages,
        approval.specification_sha256, approval.data_files, approval.source_files,
    )
    if (fingerprint != approval.specification_sha256
            or sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            != approval.approval_sha256):
        raise PermissionError("Approval fingerprint is stale or inconsistent")
    if _current_file_records(data_files) != dict(approval.data_files):
        raise PermissionError("Approved data inputs are stale or substituted")
    if _current_file_records(source_files) != dict(approval.source_files):
        raise PermissionError("Approved source inputs are stale or substituted")
    if stage == "holdout":
        assert holdout_release is not None
        payload = {
            "specification_sha256": approval.specification_sha256,
            "approval_sha256": approval.approval_sha256,
            "plan_lock_sha256": holdout_release.plan_lock_sha256,
            "authorized_by": holdout_release.authorized_by,
            "authorized_at_utc": holdout_release.authorized_at_utc,
        }
        expected = sha256(canonical_json(payload).encode()).hexdigest()
        if (holdout_release.specification_sha256 != fingerprint
                or holdout_release.approval_sha256 != approval.approval_sha256
                or not holdout_release.plan_lock_sha256
                or holdout_release.release_sha256 != expected):
            raise PermissionError("Holdout release is stale or inconsistent with the locked plan")


def prepare_support_touch_events(
    candles: pd.DataFrame,
    *,
    asset: str,
    timeframe: str,
    left_bars: int,
    right_bars: int,
    zone_width_fraction: float,
) -> pd.DataFrame:
    """Build an as-of support-touch cohort ledger from existing feature APIs.

    Every zone lifecycle row is retained with an eligibility flag and reason.
    Repeated touches and overlapping zones remain separate rows. No outcomes
    are calculated here and no later zone state is consulted.
    """
    if not isinstance(asset, str) or not asset.strip():
        raise ValueError("Asset identity must be non-empty")
    required = {"timestamp", "available_at", "open", "high", "low", "close", "volume"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Candle frame missing columns: {sorted(missing)}")
    frame = candles.reset_index(drop=True).copy()
    opens, closes = validate_candle_availability(
        frame["timestamp"], frame["available_at"], timeframe
    )
    close_values = pd.to_numeric(frame["close"], errors="raise").astype(float)
    if not np.isfinite(close_values.to_numpy()).all() or (close_values <= 0).any():
        raise ValueError("Candle close values must be finite and positive")

    structure = confirmed_market_structure(
        frame, timeframe=timeframe, left_bars=left_bars, right_bars=right_bars
    )
    zone_events = confirmed_swing_zones(
        frame, timeframe=timeframe, left_bars=left_bars,
        right_bars=right_bars, zone_width_fraction=zone_width_fraction,
    )
    open_by_close = dict(zip(closes.tolist(), opens.tolist()))
    close_row = {value: idx for idx, value in enumerate(closes.tolist())}
    structure_by_pivot: dict[pd.Timestamp, tuple[pd.Timestamp, str]] = {}
    for idx, row in structure.iterrows():
        pivot = row["swing_low_pivot_time"]
        if pd.isna(pivot):
            continue
        pivot = pd.Timestamp(pivot)
        if pivot in structure_by_pivot:
            raise ValueError("Origin swing pivot is not unique in structure output")
        label = row["swing_low_structure"]
        if label not in _STRUCTURE_LABELS:
            raise ValueError(f"Unsupported origin structure label: {label!r}")
        structure_by_pivot[pivot] = (pd.Timestamp(row["available_at"]), label)

    rows: list[dict[str, Any]] = []
    for _, event in zone_events.iterrows():
        zone_type = event["zone_type"]
        event_type = event["event"]
        if zone_type not in {"support", "resistance"} or event_type not in {
            "created", "touched", "broken"
        }:
            raise ValueError("Zone feature emitted an unsupported event")
        pivot = pd.Timestamp(event["pivot_time"])
        created_at = pd.Timestamp(event["created_at"])
        available_at = pd.Timestamp(event["event_time"])
        if zone_type == "support":
            if pivot not in structure_by_pivot:
                raise ValueError("Support-zone origin does not join to a confirmed swing-low structure row")
            origin_available, label = structure_by_pivot[pivot]
            expected_zone_id = f"support:{pivot.isoformat()}"
            if event["zone_id"] != expected_zone_id or created_at != origin_available:
                raise ValueError("Support-zone identity or creation availability disagrees with its swing origin")
        else:
            # Resistance events are retained as exclusions; the primary
            # hypothesis only joins swing-low-origin support zones.
            origin_available, label = created_at, None
        anchor = open_by_close.get(available_at)
        row_idx = close_row.get(available_at)
        if anchor is None or row_idx is None:
            raise ValueError("Zone lifecycle time does not match a candle close")
        if not origin_available <= created_at <= available_at:
            raise ValueError("Origin confirmation/zone creation is later than the event")
        if event_type != "created" and not created_at < available_at:
            raise ValueError("Zone lifecycle event must follow zone creation")

        if zone_type != "support":
            eligible, reason = False, "not_support_zone"
        elif event_type != "touched":
            eligible, reason = False, "not_touch_event"
        elif label not in _COHORT_LABELS:
            eligible, reason = False, "origin_label_outside_primary_cohorts"
        else:
            eligible, reason = True, None
        event_id = (
            f"{asset}:{timeframe}:{event['zone_id']}:{event_type}:"
            f"{available_at.isoformat()}"
        )
        rows.append({
            "event_id": event_id,
            "asset": asset,
            "timeframe": timeframe,
            "event_type": event_type,
            "zone_type": zone_type,
            "zone_id": event["zone_id"],
            "pivot_time": pivot,
            "origin_structure_label": label,
            "cohort": label if eligible else None,
            "origin_available_at": origin_available,
            "created_at": created_at,
            "anchor_timestamp": anchor,
            "available_at": available_at,
            "anchor_close": float(close_values.iloc[row_idx]),
            "lower_bound": float(event["lower_bound"]),
            "upper_bound": float(event["upper_bound"]),
            "touch_count": int(event["touch_count"]),
            "eligible": eligible,
            "exclusion_reason": reason,
            "source_event_time": available_at,
            "source_payload": event.to_dict(),
        })
    result = pd.DataFrame(rows, columns=_EVENT_LEDGER_COLUMNS)
    if not result.empty and result["event_id"].duplicated().any():
        raise ValueError("Duplicate zone lifecycle event identities")
    return result


@dataclass(frozen=True)
class OutcomeRule:
    horizon_convention: str | None
    horizon_value: str | int | float | None
    endpoint_rule: str | None
    max_lateness: str | None
    gap_policy: str | None
    incomplete_window_policy: str | None

    def validate(self) -> None:
        if self.horizon_convention not in {"fixed_observed_bars", "fixed_elapsed_time"}:
            raise ValueError("Outcome horizon convention is unresolved or unsupported")
        if self.endpoint_rule not in {"exact", "first_close_at_or_after"}:
            raise ValueError("Outcome endpoint selection is unresolved or unsupported")
        if self.gap_policy not in {"allow_and_report", "exclude_if_gap"}:
            raise ValueError("Outcome gap policy is unresolved or unsupported")
        if self.incomplete_window_policy not in {"exclude", "error"}:
            raise ValueError("Incomplete-window policy is unresolved or unsupported")
        if self.horizon_convention == "fixed_observed_bars":
            if (isinstance(self.horizon_value, bool)
                    or not isinstance(self.horizon_value, int)
                    or self.horizon_value < 1):
                raise ValueError("Observed-bar horizon must be a positive integer")
            if self.endpoint_rule != "exact":
                raise ValueError("Fixed observed-bar horizons require the exact indexed endpoint")
        else:
            if not isinstance(self.horizon_value, (str, pd.Timedelta)):
                raise ValueError("Elapsed horizon must be an explicit duration string")
            try:
                horizon = pd.Timedelta(self.horizon_value)
            except (TypeError, ValueError) as error:
                raise ValueError("Elapsed horizon must be a positive duration") from error
            if pd.isna(horizon) or horizon <= pd.Timedelta(0):
                raise ValueError("Elapsed horizon must be positive")
            if self.endpoint_rule == "first_close_at_or_after":
                if not isinstance(self.max_lateness, (str, pd.Timedelta)):
                    raise ValueError("Endpoint lateness must be explicit")
                try:
                    late = pd.Timedelta(self.max_lateness)
                except (TypeError, ValueError) as error:
                    raise ValueError("Endpoint lateness must be explicit") from error
                if pd.isna(late) or late < pd.Timedelta(0):
                    raise ValueError("Endpoint lateness must be finite and non-negative")


def calculate_forward_close_outcomes(
    events: pd.DataFrame,
    candles: pd.DataFrame,
    *,
    timeframe: str,
    rule: OutcomeRule,
    data_role: str,
    spec: EventStudySpec | None = None,
    approval: EventStudyApproval | None = None,
    stage: str | None = None,
    data_files: Mapping[str, str | Path] | None = None,
    source_files: Mapping[str, str | Path] | None = None,
    stage_data_truncated: bool = False,
    holdout_release: EventStudyHoldoutRelease | None = None,
) -> pd.DataFrame:
    """Calculate endpoint returns; research-role calls require current approval.

    This API can only enforce the supplied data-role declaration. The official
    runner authorizes a stage and supplies only its bounded candle prefix, but
    callers can still bypass the runner or lie about the synthetic-data role.
    """
    rule.validate()
    if data_role == "research":
        if (spec is None or approval is None or stage is None
                or data_files is None or source_files is None):
            raise PermissionError("Approved research provenance is required")
        validate_event_study_execution(
            spec, approval, stage=stage, data_files=data_files, source_files=source_files,
            holdout_release=holdout_release,
        )
        assert spec is not None and stage is not None
        if spec.outcome_formula is None or "".join(spec.outcome_formula.split()) != "(C_future/C_anchor)-1":
            raise PermissionError("Outcome formula does not match the approved close-return definition")
        normalized_horizon = (
            int(spec.horizon_value)
            if spec.horizon_convention == "fixed_observed_bars"
            else pd.Timedelta(spec.horizon_value)
        )
        supplied_horizon = (
            int(rule.horizon_value)
            if rule.horizon_convention == "fixed_observed_bars"
            else pd.Timedelta(rule.horizon_value)
        )
        if (spec.horizon_convention != rule.horizon_convention
                or normalized_horizon != supplied_horizon
                or spec.endpoint_rule != rule.endpoint_rule
                or (spec.max_lateness is not None and pd.Timedelta(spec.max_lateness) !=
                    (pd.Timedelta(rule.max_lateness) if rule.max_lateness is not None else pd.Timedelta(0)))
                or spec.missing_data_policy != rule.gap_policy
                or spec.incomplete_window_policy != rule.incomplete_window_policy):
            raise PermissionError("Outcome rule differs from the approved specification")
    elif data_role != "synthetic":
        raise ValueError("data_role must be synthetic or research")

    required_event = {"event_id", "eligible", "anchor_timestamp", "available_at"}
    if required_event - set(events.columns):
        raise ValueError("Event table is missing identity, eligibility, or anchor fields")
    if events["event_id"].duplicated().any():
        raise ValueError("Event IDs must be unique before outcome calculation")
    if events["eligible"].isna().any() or not events["eligible"].isin((True, False)).all():
        raise ValueError("Event eligibility must be explicitly Boolean")
    frame = candles.reset_index(drop=True).copy()
    required_candles = {"timestamp", "available_at", "close"}
    if required_candles - set(frame.columns):
        raise ValueError("Candle table is missing timestamp, availability, or close")
    opens, closes = validate_candle_availability(
        frame["timestamp"], frame["available_at"], timeframe
    )
    stage_window = None
    if data_role == "research":
        scope = set(spec.asset_timeframe_scope or ())
        if not {"asset", "timeframe"}.issubset(events.columns):
            raise ValueError("Research events must retain asset and timeframe identity")
        if not {tuple(item) for item in events[["asset", "timeframe"]].drop_duplicates().to_numpy()} <= scope:
            raise PermissionError("Event asset/timeframe is outside the approved scope")
        split_name = {"development": "train", "validation": "validation", "holdout": "holdout"}[stage]
        stage_window = getattr(spec.split, split_name).parsed()
        if (closes >= stage_window[1]).any():
            raise PermissionError(
                "Research candle frame contains availability at or beyond the authorized stage end"
            )
    close_values = pd.to_numeric(frame["close"], errors="raise").astype(float)
    if not np.isfinite(close_values.to_numpy()).all() or (close_values <= 0).any():
        raise ValueError("Outcome closes must be finite and positive")
    close_index = {value: index for index, value in enumerate(closes.tolist())}
    interval = timeframe_to_timedelta(timeframe)
    late = pd.Timedelta(rule.max_lateness) if rule.max_lateness is not None else pd.Timedelta(0)
    results: list[dict[str, Any]] = []
    for _, event in events.iterrows():
        record = event.to_dict()
        record.update({
            "outcome_return": np.nan,
            "target_timestamp": pd.NaT,
            "target_available_at": pd.NaT,
            "requested_target_at": pd.NaT,
            "realized_elapsed": pd.NaT,
            "observed_bars_forward": pd.NA,
            "missing_candle_gaps": pd.NA,
            "outcome_included": False,
            "outcome_exclusion_reason": None,
        })
        if not bool(event["eligible"]):
            record["outcome_exclusion_reason"] = event.get("exclusion_reason") or "event_ineligible"
            results.append(record)
            continue
        anchor_available = pd.Timestamp(event["available_at"])
        anchor_open = pd.Timestamp(event["anchor_timestamp"])
        if anchor_available.tzinfo is None or anchor_open.tzinfo is None:
            raise ValueError("Event timestamps must be timezone-aware")
        anchor_available = anchor_available.tz_convert("UTC")
        anchor_open = anchor_open.tz_convert("UTC")
        if stage_window is not None and not stage_window[0] <= anchor_available < stage_window[1]:
            raise PermissionError("Events must be prefiltered to the explicitly authorized stage")
        anchor_idx = close_index.get(anchor_available)
        if anchor_idx is None or opens.iloc[anchor_idx] != anchor_open:
            raise ValueError("Event anchor does not match an observed candle close")

        if rule.horizon_convention == "fixed_observed_bars":
            endpoint_idx = anchor_idx + int(rule.horizon_value)
            requested_target = closes.iloc[endpoint_idx] if endpoint_idx < len(frame) else pd.NaT
        else:
            requested_target = anchor_available + pd.Timedelta(rule.horizon_value)
            if rule.endpoint_rule == "exact":
                candidate_idx = int(closes.searchsorted(requested_target, side="left"))
                endpoint_idx = (
                    candidate_idx
                    if candidate_idx < len(frame) and closes.iloc[candidate_idx] == requested_target
                    else len(frame)
                )
            else:
                endpoint_idx = int(closes.searchsorted(requested_target, side="left"))
                if endpoint_idx < len(frame) and closes.iloc[endpoint_idx] - requested_target > late:
                    endpoint_idx = len(frame)
        record["requested_target_at"] = requested_target
        if endpoint_idx >= len(frame):
            crosses_stage = False
            if stage_window is not None and stage_data_truncated:
                if rule.horizon_convention == "fixed_observed_bars":
                    crosses_stage = True
                elif rule.endpoint_rule == "exact":
                    crosses_stage = requested_target >= stage_window[1]
                else:
                    crosses_stage = requested_target + late >= stage_window[1]
            if crosses_stage:
                if spec.boundary_policy == "error":
                    raise ValueError("Outcome window crosses the authorized stage boundary")
                record["outcome_exclusion_reason"] = "outcome_window_crosses_partition_boundary"
                results.append(record)
                continue
            if rule.incomplete_window_policy == "error":
                raise ValueError(f"No eligible endpoint for event {event['event_id']}")
            record["outcome_exclusion_reason"] = "endpoint_unavailable_or_outside_tolerance"
            results.append(record)
            continue
        endpoint_close_time = closes.iloc[endpoint_idx]
        if endpoint_close_time <= anchor_available:
            raise ValueError("Outcome endpoint must be strictly after the anchor close")
        gap_count = sum(
            (opens.iloc[index] - opens.iloc[index - 1]) > interval
            for index in range(anchor_idx + 1, endpoint_idx + 1)
        )
        record.update({
            "target_timestamp": opens.iloc[endpoint_idx],
            "target_available_at": endpoint_close_time,
            "realized_elapsed": endpoint_close_time - anchor_available,
            "observed_bars_forward": endpoint_idx - anchor_idx,
            "missing_candle_gaps": gap_count,
        })
        if stage_window is not None and endpoint_close_time >= stage_window[1]:
            if spec.boundary_policy == "error":
                raise ValueError("Outcome window crosses the authorized stage boundary")
            record["requested_target_at"] = requested_target
            record["target_timestamp"] = opens.iloc[endpoint_idx]
            record["target_available_at"] = endpoint_close_time
            record["outcome_exclusion_reason"] = "outcome_window_crosses_partition_boundary"
            results.append(record)
            continue
        if gap_count and rule.gap_policy == "exclude_if_gap":
            record["outcome_exclusion_reason"] = "missing_candle_inside_outcome_window"
            results.append(record)
            continue
        record.update({
            "outcome_return": float(close_values.iloc[endpoint_idx] / close_values.iloc[anchor_idx] - 1.0),
            "outcome_included": True,
            "outcome_exclusion_reason": None,
        })
        results.append(record)
    if not results:
        return pd.DataFrame(columns=list(events.columns) + list(_OUTCOME_COLUMNS))
    return pd.DataFrame(results)


def assign_event_partitions(
    outcomes: pd.DataFrame,
    split: TemporalSplit,
    *,
    boundary_policy: str,
    embargo: str = "0s",
) -> pd.DataFrame:
    """Assign by event availability using UTC half-open windows and purge crossings."""
    split.validate()
    if boundary_policy not in {"purge", "error"}:
        raise ValueError("Boundary policy must explicitly be purge or error")
    try:
        embargo_delta = pd.Timedelta(embargo)
    except (TypeError, ValueError) as error:
        raise ValueError("Embargo must be a valid non-negative duration") from error
    if pd.isna(embargo_delta) or embargo_delta < pd.Timedelta(0):
        raise ValueError("Embargo must be finite and non-negative")
    required = {"event_id", "available_at", "target_available_at", "outcome_included"}
    if required - set(outcomes.columns):
        raise ValueError("Outcome table is missing split assignment fields")
    if outcomes["event_id"].duplicated().any():
        raise ValueError("Event IDs must be unique for split assignment")
    windows = {
        "development": split.train.parsed(),
        "validation": split.validation.parsed(),
        "holdout": split.holdout.parsed(),
    }
    result = outcomes.copy()
    partitions: list[str | None] = []
    excluded: list[str | None] = []
    for _, event in result.iterrows():
        available = pd.Timestamp(event["available_at"])
        if available.tzinfo is None:
            raise ValueError("Event availability timestamps must include a timezone")
        available = available.tz_convert("UTC")
        match = next((name for name, (start, end) in windows.items() if start <= available < end), None)
        if match is None:
            partitions.append(None)
            excluded.append("event_outside_configured_windows")
            continue
        start, end = windows[match]
        if embargo_delta and (available < start + embargo_delta or available >= end - embargo_delta):
            partitions.append(match)
            excluded.append("event_inside_declared_embargo")
            continue
        target = event["target_available_at"]
        if bool(event["outcome_included"]) and pd.notna(target):
            target = pd.Timestamp(target)
            if target.tzinfo is None:
                raise ValueError("Outcome endpoint timestamps must include a timezone")
            target = target.tz_convert("UTC")
            if target <= available:
                raise ValueError("Outcome endpoint must be after event availability")
            if target >= end:
                if boundary_policy == "error":
                    raise ValueError(f"Outcome window crosses {match} boundary")
                partitions.append(match)
                excluded.append("outcome_window_crosses_partition_boundary")
                continue
        partitions.append(match)
        excluded.append(None)
    result["partition"] = partitions
    result["split_exclusion_reason"] = excluded
    result["partition_eligible"] = [reason is None for reason in excluded]
    return result


def summarize_event_contrast(
    outcomes: pd.DataFrame,
    *,
    outcome_column: str = "outcome_return",
    missing_policy: str,
) -> dict[str, Any]:
    """Return descriptive group counts/means only; no IID inference or p-value."""
    if missing_policy not in {"exclude", "error"}:
        raise ValueError("Missing-outcome policy must be exclude or error")
    required = {"eligible", "cohort", "zone_id", outcome_column}
    if required - set(outcomes.columns):
        raise ValueError("Outcome ledger lacks cohort summary columns")
    if outcomes["eligible"].isna().any() or not outcomes["eligible"].isin((True, False)).all():
        raise ValueError("Eligibility must be explicitly Boolean")
    eligible = outcomes.loc[outcomes["eligible"]].copy()
    values = pd.to_numeric(eligible[outcome_column], errors="raise")
    if np.isinf(values.to_numpy(dtype=float, na_value=np.nan)).any():
        raise ValueError("Outcome values must not be infinite")
    missing = values.isna()
    if missing.any() and missing_policy == "error":
        raise ValueError("Eligible events contain missing outcomes")
    eligible = eligible.loc[~missing].copy()
    eligible[outcome_column] = values.loc[~missing].astype(float)
    expected = {"higher_low", "lower_low"}
    if eligible["cohort"].isna().any() or set(eligible["cohort"]) - expected:
        raise ValueError("Unsupported cohort label in contrast ledger")
    if eligible["zone_id"].isna().any():
        raise ValueError("Eligible events must retain zone identity")
    group_stats = {}
    for label in ("higher_low", "lower_low"):
        group = eligible.loc[eligible["cohort"] == label]
        group_stats[label] = {
            "event_count": int(len(group)),
            "unique_zone_count": int(group["zone_id"].nunique()),
            "mean_outcome": float(group[outcome_column].mean()) if len(group) else None,
        }
    high_mean = group_stats["higher_low"]["mean_outcome"]
    low_mean = group_stats["lower_low"]["mean_outcome"]
    difference = high_mean - low_mean if high_mean is not None and low_mean is not None else None
    return {
        "estimand": "mean higher_low outcome minus mean lower_low outcome",
        "groups": group_stats,
        "mean_difference": difference,
        "missing_outcomes_excluded": int(missing.sum()),
        "inferential_status": "descriptive_only_no_uncertainty_or_significance_claim",
    }


def classify_registered_decision(
    *,
    estimate: float,
    lower_bound: float,
    upper_bound: float,
    minimum_effect: float,
    higher_low_count: int,
    lower_low_count: int,
    minimum_count_per_group: int,
) -> str:
    """Apply caller-supplied registered criteria to an external interval."""
    values = (estimate, lower_bound, upper_bound, minimum_effect)
    if (not all(math.isfinite(value) for value in values)
            or lower_bound > estimate or estimate > upper_bound):
        raise ValueError("Decision inputs must be finite and interval ordered")
    if minimum_effect < 0 or minimum_count_per_group < 1:
        raise ValueError("Decision thresholds must be non-negative/positive")
    if min(higher_low_count, lower_low_count) < minimum_count_per_group:
        return "defer_inconclusive"
    if lower_bound >= minimum_effect:
        return "advance_to_next_gate"
    if upper_bound <= 0:
        return "reject_directional_hypothesis"
    return "defer_inconclusive"


def validate_test_family(registered: tuple[str, ...], requested: tuple[str, ...]) -> None:
    """Ensure requested tests are unique members of the frozen family."""
    if not registered or len(set(registered)) != len(registered):
        raise ValueError("Registered multiplicity family must be non-empty and unique")
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("Requested test IDs must be non-empty and unique")
    if not set(requested).issubset(registered):
        raise PermissionError("Requested tests are outside the registered family")


def build_event_study_manifest(
    spec: EventStudySpec,
    approval: EventStudyApproval,
    *,
    outputs: Mapping[str, str | Path],
    run_directory: str | Path,
    stage: str,
    data_files: Mapping[str, str | Path],
    source_files: Mapping[str, str | Path],
    run_id: str,
    holdout_release: EventStudyHoldoutRelease | None = None,
) -> dict[str, Any]:
    """Build a completion manifest only from a complete, checked bundle."""
    validate_event_study_execution(
        spec, approval, stage=stage, data_files=data_files, source_files=source_files,
        holdout_release=holdout_release,
    )
    run_root = Path(run_directory).resolve()
    if (not isinstance(run_id, str)
            or not run_id
            or not all(character.isalnum() or character in "._-" for character in run_id)
            or run_id in {".", ".."}):
        raise ValueError("Run ID must be a non-empty path-safe identifier")
    if set(outputs) != _BUNDLE_ARTIFACTS:
        raise ValueError(
            "A completed event-study bundle requires specification, events, outcomes, "
            "exclusions, data_quality, summary, and validation artifacts only"
        )
    output_records: dict[str, dict[str, str]] = {}
    resolved_outputs: set[Path] = set()
    for identity, value in sorted(outputs.items()):
        path = Path(value).resolve()
        if path in resolved_outputs:
            raise ValueError("Bundle artifacts must resolve to distinct files")
        resolved_outputs.add(path)
        try:
            relative = path.relative_to(run_root)
        except ValueError as error:
            raise ValueError("Manifest outputs must be contained in the run directory") from error
        if not path.is_file():
            raise FileNotFoundError(f"Manifest output is missing: {path}")
        output_records[identity] = {
            "path": str(relative), "sha256": sha256(path.read_bytes()).hexdigest(),
        }
    if not output_records:
        raise ValueError("At least one output artifact is required")
    _validate_bundle_artifacts(
        {identity: Path(value).resolve() for identity, value in outputs.items()},
        specification=spec.as_dict(), run_id=run_id, stage=stage,
    )
    return {
        "manifest_schema_version": 1,
        "experiment_type": "feature_event_study",
        "run_id": run_id,
        "hypothesis_id": spec.hypothesis_id,
        "hypothesis_version": spec.hypothesis_version,
        "lifecycle_status": "computation_completed",
        "computation_status": "completed",
        "scientific_status": "not_assessed",
        "evaluation_claim": "none_descriptive_outputs_only",
        "stage": stage,
        "specification_sha256": event_study_spec_fingerprint(spec),
        "approval_sha256": approval.approval_sha256,
        "holdout_release": _canonical_value(holdout_release),
        "data_files": _canonical_value(approval.data_files),
        "source_files": _canonical_value(approval.source_files),
        "runtime": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "outcome_definition": {
            "formula": spec.outcome_formula,
            "horizon_convention": spec.horizon_convention,
            "horizon_value": spec.horizon_value,
            "endpoint_rule": spec.endpoint_rule,
        },
        "split": _canonical_value(spec.split),
        "analysis_plan": {
            "estimand": spec.estimand,
            "uncertainty_method": spec.uncertainty_method,
            "multiplicity_family": spec.multiplicity_family,
            "decision_criteria": spec.decision_criteria,
        },
        "outputs": output_records,
    }


def _validate_bundle_artifacts(
    paths: Mapping[str, Path],
    *,
    specification: Mapping[str, Any],
    run_id: str,
    stage: str,
) -> None:
    """Check artifact schemas and internal completion consistency."""
    if set(paths) != _BUNDLE_ARTIFACTS:
        raise ValueError("Bundle artifact identities do not match the required schema")
    try:
        event_frame = pd.read_csv(paths["events"])
        outcome_frame = pd.read_csv(paths["outcomes"])
        exclusion_frame = pd.read_csv(paths["exclusions"])
        data_quality = json.loads(paths["data_quality"].read_text(encoding="utf-8"))
        summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
        validation = json.loads(paths["validation"].read_text(encoding="utf-8"))
        stored_specification = json.loads(
            paths["specification"].read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError, pd.errors.EmptyDataError) as error:
        raise ValueError("One or more required bundle artifacts are malformed") from error

    required_event = set(_EVENT_LEDGER_COLUMNS)
    required_outcome = required_event | set(_OUTCOME_COLUMNS) | {
        "partition", "split_exclusion_reason", "partition_eligible",
    }
    if required_event - set(event_frame.columns):
        raise ValueError("Event ledger is missing required event schema columns")
    if required_outcome - set(outcome_frame.columns):
        raise ValueError("Outcome ledger is missing required outcome schema columns")
    if {"event_id", "asset", "timeframe", "exclusion_stage", "reason"} - set(exclusion_frame.columns):
        raise ValueError("Exclusion ledger is missing required columns")
    event_ids = event_frame["event_id"]
    outcome_ids = outcome_frame["event_id"]
    if (event_ids.isna().any() or outcome_ids.isna().any()
            or event_ids.duplicated().any() or outcome_ids.duplicated().any()
            or set(event_ids) != set(outcome_ids)):
        raise ValueError("Event and outcome ledgers must have matching unique identities")

    split = specification.get("split") if isinstance(specification, dict) else None
    split_name = {"development": "train", "validation": "validation", "holdout": "holdout"}.get(stage)
    try:
        stage_start = pd.Timestamp(split[split_name]["start"]).tz_convert("UTC")
        stage_end = pd.Timestamp(split[split_name]["end"]).tz_convert("UTC")
        event_available = pd.to_datetime(event_frame["available_at"], utc=True, errors="raise")
        outcome_available = pd.to_datetime(outcome_frame["available_at"], utc=True, errors="raise")
        event_eligible = event_frame["eligible"]
        if event_eligible.isna().any() or not event_eligible.isin((True, False)).all():
            raise ValueError("Event eligibility flags must be explicitly Boolean")
        included = outcome_frame["outcome_included"]
        if included.isna().any() or not included.isin((True, False)).all():
            raise ValueError("Outcome inclusion flags must be explicitly Boolean")
        included = included.astype(bool)
        partition_eligible = outcome_frame.loc[included, "partition_eligible"]
        if (partition_eligible.isna().any()
                or not partition_eligible.isin((True, False)).all()
                or not partition_eligible.astype(bool).all()):
            raise ValueError("Included outcomes must be explicitly partition-eligible")
        target_available = pd.to_datetime(
            outcome_frame.loc[included, "target_available_at"], utc=True, errors="raise"
        )
        outcome_values = pd.to_numeric(
            outcome_frame.loc[included, "outcome_return"], errors="raise"
        ).to_numpy(dtype=float)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Bundle timestamps, outcomes, or split metadata are malformed") from error
    if (event_available.isna().any()
            or not ((event_available >= stage_start) & (event_available < stage_end)).all()
            or outcome_available.isna().any()
            or not ((outcome_available >= stage_start) & (outcome_available < stage_end)).all()
            or target_available.isna().any()
            or not (target_available > outcome_available.loc[included]).all()
            or not (target_available < stage_end).all()
            or not np.isfinite(outcome_values).all()
            ):
        raise ValueError("Event or included outcome escapes the authorized stage contract")

    specification_hash = sha256(canonical_json(specification).encode("utf-8")).hexdigest()
    checks = validation.get("checks") if isinstance(validation, dict) else None
    counts = validation.get("counts") if isinstance(validation, dict) else None
    expected_counts = {
        "event_rows": len(event_frame),
        "outcome_rows": len(outcome_frame),
        "exclusion_rows": len(exclusion_frame),
    }
    if (canonical_json(stored_specification) != canonical_json(specification)
            or not isinstance(data_quality, dict)
            or data_quality.get("schema_version") != 1
            or data_quality.get("stage") != stage
            or not isinstance(data_quality.get("scope"), dict)
            or not isinstance(summary, dict)
            or summary.get("run_id") != run_id
            or summary.get("stage") != stage
            or summary.get("specification_sha256") != specification_hash
            or summary.get("scientific_status") != "not_assessed"
            or summary.get("inferential_status") !=
                "descriptive_only_no_uncertainty_or_significance_claim"
            or not isinstance(validation, dict)
            or validation.get("schema_version") != 1
            or validation.get("run_id") != run_id
            or validation.get("stage") != stage
            or validation.get("specification_sha256") != specification_hash
            or validation.get("computation_status") != "completed"
            or validation.get("scientific_status") != "not_assessed"
            or not isinstance(checks, dict)
            or set(checks) != _REQUIRED_RUN_CHECKS
            or not all(value is True for value in checks.values())
            or counts != expected_counts):
        raise ValueError("Bundle metadata or mechanical completion record is inconsistent")
    if (stage == "holdout") != isinstance(validation.get("holdout_release"), dict):
        raise ValueError("Holdout bundle must record its explicit release authorization")


def verify_event_study_bundle(run_directory: str | Path) -> dict[str, Any]:
    """Verify completed-bundle schema, containment, and artifact SHA-256s."""
    root = Path(run_directory).resolve()
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Event-study manifest is missing or malformed") from error
    if (manifest.get("manifest_schema_version") != 1
            or manifest.get("experiment_type") != "feature_event_study"
            or manifest.get("lifecycle_status") != "computation_completed"
            or manifest.get("computation_status") != "completed"
            or manifest.get("scientific_status") != "not_assessed"
            or manifest.get("run_id") != root.name):
        raise ValueError("Manifest status or identity is inconsistent")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != _BUNDLE_ARTIFACTS:
        raise ValueError("Manifest is missing required bundle artifacts")
    resolved: dict[str, Path] = {}
    relative_paths: set[str] = set()
    resolved_paths: set[Path] = set()
    for identity, record in outputs.items():
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise ValueError(f"Malformed artifact record: {identity}")
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Manifest artifact path must be a contained relative path")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError("Manifest artifact escapes the run directory") from error
        if str(relative) in relative_paths:
            raise ValueError("Manifest artifacts must have unique paths")
        relative_paths.add(str(relative))
        if path in resolved_paths:
            raise ValueError("Manifest artifacts must resolve to distinct files")
        resolved_paths.add(path)
        if not path.is_file():
            raise FileNotFoundError(f"Manifest artifact is missing: {identity}")
        actual = sha256(path.read_bytes()).hexdigest()
        if actual != record["sha256"]:
            raise ValueError(f"Manifest artifact hash mismatch: {identity}")
        resolved[identity] = path
    try:
        specification = json.loads(resolved["specification"].read_text(encoding="utf-8"))
        validation = json.loads(resolved["validation"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Specification or validation artifact is malformed") from error
    if not isinstance(specification, dict) or not isinstance(validation, dict):
        raise ValueError("Specification and validation artifacts must be JSON objects")
    spec_hash = sha256(canonical_json(specification).encode("utf-8")).hexdigest()
    if (spec_hash != manifest.get("specification_sha256")
            or validation.get("specification_sha256") != spec_hash
            or validation.get("run_id") != manifest.get("run_id")
            or validation.get("stage") != manifest.get("stage")
            or validation.get("computation_status") != "completed"
            or validation.get("scientific_status") != "not_assessed"
            or not isinstance(validation.get("checks"), dict)
            or not validation["checks"]
            or not all(value is True for value in validation["checks"].values())):
        raise ValueError("Completion record is inconsistent with manifest metadata")
    release = manifest.get("holdout_release")
    if manifest.get("stage") == "holdout":
        expected_release_keys = {
            "specification_sha256", "approval_sha256", "plan_lock_sha256",
            "authorized_by", "authorized_at_utc", "release_sha256",
        }
        if not isinstance(release, dict) or set(release) != expected_release_keys:
            raise ValueError("Holdout manifest lacks a complete release record")
        release_payload = {key: release[key] for key in expected_release_keys - {"release_sha256"}}
        expected_release_hash = sha256(canonical_json(release_payload).encode()).hexdigest()
        if (release.get("specification_sha256") != spec_hash
                or release.get("approval_sha256") != manifest.get("approval_sha256")
                or not release.get("plan_lock_sha256")
                or not release.get("authorized_by")
                or release.get("release_sha256") != expected_release_hash
                or validation.get("holdout_release") != {
                    "release_sha256": release.get("release_sha256"),
                    "authorized_by": release.get("authorized_by"),
                    "authorized_at_utc": release.get("authorized_at_utc"),
                }):
            raise ValueError("Holdout release does not match its locked plan or validation record")
    elif release is not None or validation.get("holdout_release") is not None:
        raise ValueError("Non-holdout bundle must not contain a holdout release")
    if (specification.get("hypothesis_id") != manifest.get("hypothesis_id")
            or specification.get("hypothesis_version") != manifest.get("hypothesis_version")):
        raise ValueError("Specification identity does not match the manifest")
    _validate_bundle_artifacts(
        resolved, specification=specification,
        run_id=manifest["run_id"], stage=manifest["stage"],
    )
    try:
        events_header = pd.read_csv(resolved["events"], nrows=0).columns
        outcomes_header = pd.read_csv(resolved["outcomes"], nrows=0).columns
        exclusions_header = pd.read_csv(resolved["exclusions"], nrows=0).columns
        data_quality = json.loads(resolved["data_quality"].read_text(encoding="utf-8"))
        summary = json.loads(resolved["summary"].read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, pd.errors.EmptyDataError) as error:
        raise ValueError("One or more bundle artifacts have malformed contents") from error
    if not {"event_id", "eligible", "available_at"}.issubset(events_header):
        raise ValueError("Event ledger is missing required columns")
    if not {
        "event_id", "eligible", "available_at", "outcome_return", "outcome_included",
        "target_available_at", "outcome_exclusion_reason",
    }.issubset(outcomes_header):
        raise ValueError("Outcome ledger is missing required columns")
    if not {"event_id", "exclusion_stage", "reason"}.issubset(exclusions_header):
        raise ValueError("Exclusion ledger is missing required columns")
    if (not isinstance(data_quality, dict) or data_quality.get("schema_version") != 1
            or data_quality.get("stage") != manifest.get("stage")
            or not isinstance(data_quality.get("scope"), dict)
            or not isinstance(summary, dict)
            or summary.get("run_id") != manifest.get("run_id")
            or summary.get("stage") != manifest.get("stage")
            or summary.get("scientific_status") != "not_assessed"):
        raise ValueError("Data-quality or descriptive-summary artifact is inconsistent")
    expected_files = {manifest_path.name, *relative_paths}
    actual_files = {
        str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("Bundle contains missing or unregistered files")
    return manifest


def write_json_no_clobber(document: Mapping[str, Any], path: str | Path) -> Path:
    """Write canonical JSON atomically to a new path, refusing overwrite."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing artifact: {target}")
    content = (canonical_json(document) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
