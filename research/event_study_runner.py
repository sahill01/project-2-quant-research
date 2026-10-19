"""Approval-gated, stage-bounded runner for feature-only event studies.

This runner is an accidental-misuse safeguard inside one Python process. It
does not prevent a caller from reading files directly or bypassing the API.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Mapping

import numpy as np
import pandas as pd

from research.data_loader import load_ohlcv_before, timeframe_to_timedelta
from research import data_loader as _data_loader
from research import event_study as _event_study
from research import experiment_protocol as _experiment_protocol
from research import hypothesis_spec as _hypothesis_spec
from research import structure_features as _structure_features
from research import support_resistance as _support_resistance
from research.event_study import (
    EventStudyApproval,
    EventStudyHoldoutRelease,
    EventStudySpec,
    OutcomeRule,
    _canonical_value,
    assign_event_partitions,
    build_event_study_manifest,
    calculate_forward_close_outcomes,
    canonical_json,
    event_study_spec_fingerprint,
    prepare_support_touch_events,
    summarize_event_contrast,
    verify_event_study_bundle,
    validate_event_study_execution,
    write_json_no_clobber,
)


_REQUIRED_SOURCE_MODULES = {
    "research.data_loader": _data_loader,
    "research.event_study": _event_study,
    # EventStudySpec and partitioning use TemporalSplit/TimeWindow from here.
    "research.experiment_protocol": _experiment_protocol,
    # experiment_protocol imports these schema definitions at module load.
    "research.hypothesis_spec": _hypothesis_spec,
    "research.event_study_runner": None,
    "research.structure_features": _structure_features,
    "research.support_resistance": _support_resistance,
}


def required_event_study_source_files() -> dict[str, Path]:
    """Return the exact source inventory every official-runner approval binds.

    The inventory covers the runner, its event-study implementation, the loader,
    swing/zone feature layers, and the temporal-split and hypothesis-schema
    modules imported by that path. The general feature assembler and unrelated
    candlestick/chart layers are excluded because this runner does not call them.
    """
    paths = {
        identity: Path(module.__file__).resolve()
        for identity, module in _REQUIRED_SOURCE_MODULES.items()
        if module is not None
    }
    paths["research.event_study_runner"] = Path(__file__).resolve()
    return dict(sorted(paths.items()))


def _validate_scientific_contract(spec: EventStudySpec) -> None:
    required = {
        "event_definition": "confirmed_support_zone_touch_by_origin_swing_low_v1",
        "event_anchor_semantics": "touch_candle_close",
        "availability_semantics": "touch_candle_available_at",
        "causal_availability_rule": "origin_confirmation_and_zone_creation_at_or_before_touch_availability",
        "outcome_formula": "(C_future/C_anchor)-1",
        "estimand": "mean higher_low outcome minus mean lower_low outcome",
        "repeated_touch_policy": "retain_all",
        "overlapping_event_policy": "retain_separately",
        "uncertainty_method": "not_performed_descriptive_only",
    }
    for field, expected in required.items():
        actual = getattr(spec, field)
        normalized = "".join(actual.split()) if field == "outcome_formula" and actual else actual
        if normalized != expected:
            raise PermissionError(
                f"Runner does not implement the approved {field} contract {actual!r}"
            )
    if set(spec.cohort_labels or ()) != {"higher_low", "lower_low"}:
        raise PermissionError("Runner supports only higher_low and lower_low cohorts")
    if tuple(spec.origin_join_keys or ()) != (
        "zone_id", "pivot_time", "swing_low_pivot_time"
    ):
        raise PermissionError("Runner does not implement the approved origin join keys")


def _scope_identity(asset: str, timeframe: str) -> str:
    return f"{asset}|{timeframe}"


def _stage_window(spec: EventStudySpec, stage: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if spec.split is None:
        raise PermissionError("A resolved chronological split is required")
    name = {"development": "train", "validation": "validation", "holdout": "holdout"}.get(stage)
    if name is None:
        raise ValueError(f"Unsupported event-study stage: {stage!r}")
    return getattr(spec.split, name).parsed()


def _validate_horizon_embargo(spec: EventStudySpec) -> None:
    """Require a nominal embargo at least as long as each registered horizon.

    Outcome endpoints are independently checked against stage boundaries, so
    gaps cannot extend an included window across a partition even when an
    observed-bar horizon takes longer in elapsed time than its nominal span.
    """
    if spec.split is None or not spec.asset_timeframe_scope:
        raise ValueError("A complete split and asset/timeframe scope are required")
    spec.split.validate()
    try:
        embargo = pd.Timedelta(spec.embargo)
    except (TypeError, ValueError) as error:
        raise ValueError("A valid horizon-linked embargo is required") from error
    if pd.isna(embargo) or embargo < pd.Timedelta(0):
        raise ValueError("Embargo must be finite and non-negative")
    if spec.horizon_convention == "fixed_elapsed_time":
        horizon = pd.Timedelta(spec.horizon_value)
    elif spec.horizon_convention == "fixed_observed_bars":
        horizon = max(
            timeframe_to_timedelta(timeframe) * int(spec.horizon_value)
            for _, timeframe in spec.asset_timeframe_scope
        )
    else:
        raise ValueError("A resolved outcome horizon is required")
    if embargo < horizon:
        raise ValueError(
            f"Embargo {embargo} is shorter than the registered horizon {horizon}"
        )


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    serialized = frame.copy()
    if "source_payload" in serialized:
        serialized["source_payload"] = serialized["source_payload"].map(
            lambda value: canonical_json(value) if isinstance(value, dict) else ""
        )
    return serialized.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _write_bytes(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _rename_directory_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish a directory only if its destination is absent.

    Linux ``renameat2(RENAME_NOREPLACE)`` closes the race that exists between
    checking a path and a normal ``rename`` that may replace an empty directory.
    Fail closed on platforms/filesystems without this primitive.
    """
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError("Atomic no-replace directory publication is unavailable")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p,
                          ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100, os.fsencode(source), -100, os.fsencode(destination), 1
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), str(destination))


def run_event_study(
    spec: EventStudySpec,
    approval: EventStudyApproval,
    *,
    stage: str,
    data_files: Mapping[str, str | Path],
    source_files: Mapping[str, str | Path],
    output_root: str | Path,
    run_id: str,
    holdout_release: EventStudyHoldoutRelease | None = None,
) -> Path:
    """Run one approved stage and atomically publish a verified result bundle.

    Data and source identities must match the approved spec. For each scope
    item, only candles with ``available_at < stage_end`` enter the feature or
    outcome calculations. The timestamp-only scan validates ordering across
    the source and locates the boundary; post-boundary OHLCV values are not
    materialized.
    """
    spec.validate(require_approved=True)
    required_sources = required_event_study_source_files()
    if set(source_files) != set(required_sources):
        raise PermissionError(
            "Approval source inventory must exactly match the runner implementation inventory"
        )
    for identity, path in required_sources.items():
        if identity not in source_files or Path(source_files[identity]).resolve() != path:
            raise PermissionError(
                f"Approval must bind the current implementation file {identity}"
            )
    validate_event_study_execution(
        spec, approval, stage=stage, data_files=data_files, source_files=source_files,
        holdout_release=holdout_release,
    )
    _validate_horizon_embargo(spec)
    _validate_scientific_contract(spec)
    if (not isinstance(run_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id)):
        raise ValueError("Run ID must be a stable, path-safe identifier")
    root = Path(output_root).resolve()
    target = root / run_id
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite event-study run: {target}")

    window_start, window_end = _stage_window(spec, stage)
    scope = tuple(spec.asset_timeframe_scope or ())
    expected_ids = {_scope_identity(asset, timeframe) for asset, timeframe in scope}
    if not scope or set(data_files) != expected_ids:
        raise ValueError("Dataset identities must exactly match the approved asset/timeframe scope")
    if not set(spec.feature_parameters or {}) == {
        "left_bars", "right_bars", "zone_width_fraction"
    }:
        raise ValueError("Support-touch execution requires exactly the registered swing/zone parameters")
    rule = OutcomeRule(
        spec.horizon_convention,
        spec.horizon_value,
        spec.endpoint_rule,
        spec.max_lateness,
        spec.missing_data_policy,
        spec.incomplete_window_policy,
    )
    rule.validate()

    event_frames: list[pd.DataFrame] = []
    outcome_frames: list[pd.DataFrame] = []
    exclusion_records: list[dict[str, object]] = []
    data_quality: dict[str, dict[str, object]] = {}
    for asset, timeframe in scope:
        identity = _scope_identity(asset, timeframe)
        candles, boundary_reached = load_ohlcv_before(
            data_files[identity], timeframe, window_end
        )
        events = prepare_support_touch_events(
            candles,
            asset=asset,
            timeframe=timeframe,
            left_bars=spec.feature_parameters["left_bars"],
            right_bars=spec.feature_parameters["right_bars"],
            zone_width_fraction=spec.feature_parameters["zone_width_fraction"],
        )
        events = events.loc[
            (events["available_at"] >= window_start)
            & (events["available_at"] < window_end)
        ].reset_index(drop=True)
        embargo_delta = pd.Timedelta(spec.embargo)
        in_embargo = (
            (events["available_at"] < window_start + embargo_delta)
            | (events["available_at"] >= window_end - embargo_delta)
        ) if embargo_delta else pd.Series(False, index=events.index)
        calculate_mask = events["eligible"] & ~in_embargo
        to_calculate = events.loc[calculate_mask].reset_index(drop=True)
        not_calculated = events.loc[~calculate_mask].copy()
        not_calculated["outcome_return"] = np.nan
        not_calculated["target_timestamp"] = pd.NaT
        not_calculated["target_available_at"] = pd.NaT
        not_calculated["requested_target_at"] = pd.NaT
        not_calculated["realized_elapsed"] = pd.NaT
        not_calculated["observed_bars_forward"] = pd.NA
        not_calculated["missing_candle_gaps"] = pd.NA
        not_calculated["outcome_included"] = False
        not_calculated["outcome_exclusion_reason"] = [
            row["exclusion_reason"] or "event_inside_declared_embargo"
            for _, row in not_calculated.iterrows()
        ]
        outcomes = calculate_forward_close_outcomes(
            to_calculate,
            candles,
            timeframe=timeframe,
            rule=rule,
            data_role="research",
            spec=spec,
            approval=approval,
            stage=stage,
            data_files=data_files,
            source_files=source_files,
            stage_data_truncated=boundary_reached,
            holdout_release=holdout_release,
        )
        outcomes = pd.concat([outcomes, not_calculated], ignore_index=True, sort=False)
        if not outcomes.empty:
            outcomes = outcomes.sort_values("event_id", kind="stable").reset_index(drop=True)
        outcomes = assign_event_partitions(
            outcomes,
            spec.split,
            boundary_policy=spec.boundary_policy,
            embargo=spec.embargo,
        )
        event_frames.append(events)
        outcome_frames.append(outcomes)
        for _, event in events.loc[~events["eligible"]].iterrows():
            exclusion_records.append({
                "event_id": event["event_id"], "asset": asset, "timeframe": timeframe,
                "exclusion_stage": "eligibility", "reason": event["exclusion_reason"],
            })
        for _, outcome in outcomes.iterrows():
            if not bool(outcome["outcome_included"]):
                exclusion_records.append({
                    "event_id": outcome["event_id"], "asset": asset,
                    "timeframe": timeframe, "exclusion_stage": "outcome",
                    "reason": outcome["outcome_exclusion_reason"],
                })
            if not bool(outcome["partition_eligible"]):
                exclusion_records.append({
                    "event_id": outcome["event_id"], "asset": asset,
                    "timeframe": timeframe, "exclusion_stage": "partition",
                    "reason": outcome["split_exclusion_reason"],
                })
        included = outcomes.loc[outcomes["outcome_included"]]
        data_quality[identity] = {
            "loaded_candle_count": int(len(candles)),
            "first_loaded_timestamp": candles["timestamp"].iloc[0].isoformat(),
            "last_loaded_available_at": candles["available_at"].iloc[-1].isoformat(),
            "stage_boundary_timestamp_observed": bool(boundary_reached),
            "event_count": int(len(events)),
            "eligible_event_count": int(events["eligible"].sum()),
            "included_outcome_count": int(len(included)),
            "excluded_outcome_count": int((~outcomes["outcome_included"]).sum()),
        }

    events_all = pd.concat(event_frames, ignore_index=True)
    outcomes_all = pd.concat(outcome_frames, ignore_index=True)
    if not outcomes_all.empty:
        included = outcomes_all.loc[
            outcomes_all["outcome_included"] & outcomes_all["partition_eligible"]
        ]
        if not np.isfinite(included["outcome_return"].to_numpy(dtype=float)).all():
            raise ValueError("Included outcomes must be finite")
        if not ((included["target_available_at"] > included["available_at"])
                & (included["target_available_at"] < window_end)).all():
            raise ValueError("Included outcome endpoint escaped its authorized stage")
    summary_rows = []
    for asset, timeframe in scope:
        identity = _scope_identity(asset, timeframe)
        selected = outcomes_all.loc[
            (outcomes_all["asset"] == asset)
            & (outcomes_all["timeframe"] == timeframe)
        ] if not outcomes_all.empty else pd.DataFrame(columns=[
            "eligible", "cohort", "zone_id", "outcome_return"
        ])
        summary_rows.append({
            "asset": asset,
            "timeframe": timeframe,
            **summarize_event_contrast(selected, missing_policy="exclude"),
            "data_quality": data_quality[identity],
        })

    spec_hash = event_study_spec_fingerprint(spec)
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "stage": stage,
        "specification_sha256": spec_hash,
        "scientific_status": "not_assessed",
        "inferential_status": "descriptive_only_no_uncertainty_or_significance_claim",
        "groups": summary_rows,
    }
    exclusions = pd.DataFrame(
        exclusion_records,
        columns=("event_id", "asset", "timeframe", "exclusion_stage", "reason"),
    )
    validation = {
        "schema_version": 1,
        "run_id": run_id,
        "stage": stage,
        "specification_sha256": spec_hash,
        "computation_status": "completed",
        "scientific_status": "not_assessed",
        "checks": {
            "approved_spec_and_current_hashes": True,
            "requested_stage_authorized": True,
            "only_stage_prefix_ohlcv_materialized": True,
            "cohort_and_outcome_rows_within_scope": True,
            "included_outcomes_finite_and_after_anchor": True,
            "included_outcomes_before_stage_end": True,
        },
        "holdout_release": (
            {
                "release_sha256": holdout_release.release_sha256,
                "authorized_by": holdout_release.authorized_by,
                "authorized_at_utc": holdout_release.authorized_at_utc,
            } if stage == "holdout" and holdout_release is not None else None
        ),
        "counts": {
            "event_rows": int(len(events_all)),
            "outcome_rows": int(len(outcomes_all)),
            "exclusion_rows": int(len(exclusions)),
        },
        "note": "Mechanical validation only; no scientific hypothesis assessment was performed.",
    }

    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite event-study run: {target}")
    stage_directory = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=root))
    stage_directory_fd = os.open(stage_directory, os.O_RDONLY)
    stage_stat = os.fstat(stage_directory_fd)
    stage_identity = (stage_stat.st_dev, stage_stat.st_ino)
    published = False
    try:
        artifact_frames = {
            "events": events_all,
            "outcomes": outcomes_all,
            "exclusions": exclusions,
        }
        paths: dict[str, Path] = {}
        for name, frame in artifact_frames.items():
            path = stage_directory / f"{name}.csv"
            _write_bytes(path, _csv_bytes(frame))
            paths[name] = path
        documents = {
            "specification": spec.as_dict(),
            "data_quality": {
                "schema_version": 1,
                "stage": stage,
                "scope": data_quality,
                "note": "Only prefix candles available before the stage end were materialized.",
            },
            "summary": summary,
            "validation": validation,
        }
        for name, document in documents.items():
            path = stage_directory / f"{name}.json"
            _write_bytes(path, (canonical_json(document) + "\n").encode("utf-8"))
            paths[name] = path
        manifest = build_event_study_manifest(
            spec,
            approval,
            outputs=paths,
            run_directory=stage_directory,
            stage=stage,
            data_files=data_files,
            source_files=source_files,
            run_id=run_id,
            holdout_release=holdout_release,
        )
        write_json_no_clobber(manifest, stage_directory / "manifest.json")
        _rename_directory_no_replace(stage_directory, target)
        published = True
        verify_event_study_bundle(target)
        return target
    except Exception:
        if published and target.exists():
            try:
                target_stat = target.lstat()
            except FileNotFoundError:
                target_stat = None
            # Do not remove a destination that another process replaced after
            # publication but before bundle verification failed.
            if (target_stat is not None
                    and (target_stat.st_dev, target_stat.st_ino) == stage_identity):
                shutil.rmtree(target)
        elif stage_directory.exists():
            try:
                staged_stat = stage_directory.lstat()
            except FileNotFoundError:
                staged_stat = None
            if (staged_stat is not None
                    and (staged_stat.st_dev, staged_stat.st_ino) == stage_identity):
                shutil.rmtree(stage_directory)
        raise
    finally:
        os.close(stage_directory_fd)
