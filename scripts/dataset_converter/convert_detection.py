"""YOLO Detection export, enabled only after explicit annotation approval."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any

import yaml

from scripts.dataset_converter.class_mapping import MappingConfig
from scripts.dataset_converter.models import DatasetInspection
from scripts.dataset_converter.output_utils import (
    create_staging_directory,
    create_zip,
    ensure_safe_target,
    publish_directory,
    remove_staging_directory,
)
from scripts.dataset_converter.safety import conversion_blockers
from scripts.dataset_converter.split_dataset import SplitPlan, SPLITS
from scripts.dataset_converter.validate_annotations import normalized_box, validate_box


def validate_data_yaml(path: Path, mapping: MappingConfig) -> None:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("data.yaml must contain a mapping")
    names = value.get("names")
    expected = [entry.name for entry in mapping.classes]
    if value.get("nc") != len(expected) or names != expected:
        raise ValueError("data.yaml class count or names do not match the approved mapping")
    for split in SPLITS:
        if value.get(split) != f"images/{split}":
            raise ValueError(f"data.yaml has an invalid {split} image path")


def convert_detection(
    inspection: DatasetInspection,
    mapping: MappingConfig,
    split_plan: SplitPlan,
    output_root: Path,
    overwrite: bool = False,
    make_zip: bool = False,
) -> dict[str, Any]:
    blockers = conversion_blockers(inspection, mapping, split_plan, "detection")
    if blockers:
        raise ValueError("Detection conversion is blocked: " + "; ".join(blockers))
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "detection"
    ensure_safe_target(
        target,
        inspection.input_root,
        inspection.image_root,
        inspection.label_root,
        overwrite,
    )
    for record in inspection.valid_class_records:
        points = record.annotation.get("points")
        if not isinstance(points, list) or not points:
            raise ValueError(f"Detection annotation has no points: {record.label_path}")
        if record.image_width is None or record.image_height is None:
            raise ValueError(f"Detection image dimensions unavailable: {record.label_path}")
        for index, point in enumerate(points):
            valid, reason, _ = validate_box(
                point, record.image_width, record.image_height
            )
            if not valid:
                raise ValueError(
                    f"Invalid Detection box at {record.label_path} point {index}: {reason}"
                )

    staging: Path | None = create_staging_directory(target)
    metadata_rows: list[dict[str, Any]] = []
    try:
        for split in SPLITS:
            (staging / "images" / split).mkdir(parents=True, exist_ok=True)
            (staging / "labels" / split).mkdir(parents=True, exist_ok=True)
        record_index = 0
        for split in SPLITS:
            for record in sorted(
                split_plan.by_split[split],
                key=lambda item: item.image_path.as_posix() if item.image_path else "",
            ):
                if record.image_path is None or record.class_id is None:
                    continue
                record_index += 1
                stem = (
                    f"{record_index:06d}_"
                    f"{record.image_hash[:12]}_"
                    f"{record.image_path.stem[:80]}"
                )
                image_filename = stem + record.image_path.suffix.lower()
                label_filename = stem + ".txt"
                image_relative = Path("images") / split / image_filename
                label_relative = Path("labels") / split / label_filename
                shutil.copy2(record.image_path, staging / image_relative)
                lines = []
                points = record.annotation.get("points")
                for point in points:
                    xc, yc, width, height = normalized_box(
                        point, record.image_width, record.image_height
                    )
                    lines.append(
                        f"{record.class_id} {xc:.8f} {yc:.8f} {width:.8f} {height:.8f}"
                    )
                (staging / label_relative).write_text(
                    "\n".join(lines) + "\n", encoding="ascii"
                )
                metadata_rows.append(
                    {
                        "split": split,
                        "image_path": image_relative.as_posix(),
                        "label_path": label_relative.as_posix(),
                        "class_id": record.class_id,
                        "source_image": record.image_path.as_posix(),
                        "source_json": record.label_path.as_posix(),
                        "source_sha256": record.image_hash,
                        "risk": record.annotation.get("risk")
                        if record.annotation.get("risk") is not None
                        else "null",
                        "area": record.annotation.get("area")
                        if record.annotation.get("area") is not None
                        else "null",
                        "grow": record.annotation.get("grow")
                        if record.annotation.get("grow") is not None
                        else "null",
                        "description_type": record.description.get("type")
                        if record.description.get("type") is not None
                        else "null",
                        "annotation_semantics": "approved_subject_object_not_lesion",
                    }
                )
        class_names = [entry.name for entry in mapping.classes]
        data_yaml = {
            "path": ".",
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": len(class_names),
            "names": class_names,
        }
        (staging / "data.yaml").write_text(
            yaml.safe_dump(data_yaml, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        with (staging / "metadata.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            columns = [
                "split",
                "image_path",
                "label_path",
                "class_id",
                "source_image",
                "source_json",
                "source_sha256",
                "risk",
                "area",
                "grow",
                "description_type",
                "annotation_semantics",
            ]
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(metadata_rows)
        (staging / "README.md").write_text(
            """# YOLO Detection dataset

The labels represent the approved annotated subject/object location. They do
not represent lesion locations. `risk`, `area`, and `grow` metadata is preserved
in `metadata.csv`.

## Google Colab

```python
from google.colab import files
uploaded = files.upload()  # select detection.zip
import zipfile
with zipfile.ZipFile(next(iter(uploaded))) as archive:
    archive.extractall('/content/orchard_detection')
from ultralytics import YOLO
model = YOLO('yolo11n.pt')
model.train(data='/content/orchard_detection/data.yaml', epochs=50, imgsz=640)
```
""",
            encoding="utf-8",
        )
        validate_data_yaml(staging / "data.yaml", mapping)
        publish_directory(staging, target, overwrite)
        staging = None
        zip_path = output_root / "detection.zip"
        if make_zip:
            create_zip(target, zip_path, overwrite)
        return {
            "target": target,
            "images": len(metadata_rows),
            "boxes": sum(
                len(record.annotation.get("points", []))
                for split in SPLITS
                for record in split_plan.by_split[split]
            ),
            "zip_path": zip_path if make_zip else None,
        }
    finally:
        remove_staging_directory(staging)
