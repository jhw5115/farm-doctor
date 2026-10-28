"""Shared data structures used by the dataset inspection and conversion steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DatasetRecord:
    label_path: Path
    image_path: Path | None
    annotation: dict[str, Any]
    description: dict[str, Any]
    match_status: str
    referenced_image: str
    issues: list[str] = field(default_factory=list)
    image_width: int | None = None
    image_height: int | None = None
    image_hash: str = ""
    dhash: int | None = None
    class_id: int | None = None
    group_id: str = ""


@dataclass
class DatasetInspection:
    input_root: Path
    image_root: Path
    label_root: Path
    records: list[DatasetRecord]
    image_paths: list[Path]
    unmatched_images: list[Path]
    duplicate_groups: list[list[Path]]
    near_duplicate_pairs: list[tuple[Path, Path, int]]
    image_errors: dict[Path, str]
    code_counts: dict[str, dict[str, int]]
    class_counts: dict[int, int]
    pair_counts: dict[tuple[int, int], int]
    folder_pair_counts: dict[tuple[str, str], int]
    issues: list[str]

    @property
    def matched_records(self) -> list[DatasetRecord]:
        return [record for record in self.records if record.match_status == "matched"]

    @property
    def valid_class_records(self) -> list[DatasetRecord]:
        return [
            record
            for record in self.matched_records
            if record.class_id is not None
            and not any(
                issue.startswith(
                    (
                        "invalid_json",
                        "invalid_annotations",
                        "missing_annotations",
                        "missing_crop",
                        "missing_disease",
                        "unsupported_type",
                        "type_disease_conflict",
                        "risk_disease_conflict",
                        "invalid_risk",
                        "corrupt_or_unsupported_image",
                        "duplicate_class_conflict",
                        "label_folder_crop_conflict",
                        "label_folder_disease_conflict",
                        "image_folder_crop_conflict",
                        "image_folder_disease_conflict",
                    )
                )
                for issue in record.issues
            )
        ]
