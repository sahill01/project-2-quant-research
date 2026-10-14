"""No-clobber helpers for persistent research result files."""

from pathlib import Path
import os
import tempfile
from typing import Iterable

import pandas as pd


def assert_paths_available(paths: Iterable[str | Path]) -> list[Path]:
    """Return normalized targets, failing if any already exists or repeats."""
    targets = [Path(path) for path in paths]
    normalized = [path.resolve() for path in targets]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Result output paths must be unique")
    existing = [path for path in targets if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing result files: "
            + ", ".join(str(path) for path in existing)
        )
    return targets


def write_csv_batch_no_clobber(
    outputs: Iterable[tuple[pd.DataFrame, str | Path]],
) -> None:
    """Write CSVs only to new paths, staging all files before committing.

    Each destination is created with a no-clobber hard link from a staged file.
    If serialization or a later destination commit fails, files committed by
    this call are removed and staged files are cleaned up.
    """
    batch = [(frame, Path(path)) for frame, path in outputs]
    if not batch:
        raise ValueError("At least one result CSV is required")
    targets = assert_paths_available(path for _, path in batch)
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)

    staged: list[tuple[Path, Path]] = []
    committed: list[tuple[Path, int, int]] = []
    try:
        for (frame, _), target in zip(batch, targets):
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            staged.append((temporary, target))
            frame.to_csv(temporary, index=False)

        for temporary, target in staged:
            # A hard link creates the destination atomically and fails if a
            # concurrent writer has created it since the preflight check.
            staged_stat = temporary.stat()
            os.link(temporary, target)
            committed.append((target, staged_stat.st_dev, staged_stat.st_ino))
    except Exception:
        for target, device, inode in committed:
            try:
                target_stat = target.stat()
            except FileNotFoundError:
                continue
            if (target_stat.st_dev, target_stat.st_ino) == (device, inode):
                target.unlink()
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
