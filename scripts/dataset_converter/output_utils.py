"""Safe staging, publishing, and packaging for derived datasets."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def ensure_safe_target(
    target: Path, input_root: Path, image_root: Path, label_root: Path, overwrite: bool
) -> None:
    resolved_target = target.resolve()
    for source_root in (image_root.resolve(), label_root.resolve()):
        if resolved_target == source_root or source_root in resolved_target.parents:
            raise ValueError(f"Output target must not be inside a source directory: {target}")
    if resolved_target.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {resolved_target}; pass --overwrite to preserve it as a backup and replace it."
        )
    if resolved_target == input_root.resolve():
        raise ValueError("Output target must not replace the input dataset directory.")


def create_staging_directory(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    return Path(
        tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent)
    )


def publish_directory(staging: Path, target: Path, overwrite: bool) -> Path | None:
    backup: Path | None = None
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {target}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = target.with_name(f"{target.name}.backup-{stamp}")
        suffix = 1
        while backup.exists():
            backup = target.with_name(f"{target.name}.backup-{stamp}-{suffix}")
            suffix += 1
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except OSError:
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    return backup


def remove_staging_directory(staging: Path | None) -> None:
    if staging is not None and staging.exists():
        shutil.rmtree(staging)


def create_zip(dataset_dir: Path, zip_path: Path, overwrite: bool) -> Path | None:
    if zip_path.exists() and not overwrite:
        raise FileExistsError(
            f"ZIP already exists: {zip_path}; pass --overwrite to preserve it as a backup."
        )
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{zip_path.name}.staging-",
        suffix=".zip",
        dir=zip_path.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(dataset_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(dataset_dir).as_posix())
        backup = None
        if zip_path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = zip_path.with_name(f"{zip_path.name}.backup-{stamp}")
            suffix = 1
            while backup.exists():
                backup = zip_path.with_name(f"{zip_path.name}.backup-{stamp}-{suffix}")
                suffix += 1
            os.replace(zip_path, backup)
        try:
            os.replace(temporary, zip_path)
        except OSError:
            if backup is not None and backup.exists() and not zip_path.exists():
                os.replace(backup, zip_path)
            raise
        return backup
    finally:
        if temporary.exists():
            temporary.unlink()
