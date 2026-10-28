"""YOLO Classification dataset generation from whole images and optional crops."""

from __future__ import annotations

import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.dataset_converter.class_mapping import ClassMapping, MappingConfig
from scripts.dataset_converter.models import DatasetInspection, DatasetRecord
from scripts.dataset_converter.output_utils import (
    create_staging_directory,
    create_zip,
    ensure_safe_target,
    publish_directory,
    remove_staging_directory,
)
from scripts.dataset_converter.safety import conversion_blockers
from scripts.dataset_converter.split_dataset import SplitPlan, SPLITS
from scripts.dataset_converter.validate_annotations import validate_box


def _metadata_row(
    record: DatasetRecord,
    split: str,
    class_mapping: ClassMapping,
    relative_path: str,
    box_index: int | None = None,
) -> dict[str, Any]:
    return {
        "split": split,
        "relative_path": relative_path,
        "class_id": class_mapping.class_id,
        "class_name": class_mapping.name,
        "source_image": record.image_path.name if record.image_path else "",
        "source_image_path": record.image_path.as_posix() if record.image_path else "",
        "source_json_path": record.label_path.as_posix(),
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
        "box_index": box_index if box_index is not None else "",
    }


def _write_metadata(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "split",
        "relative_path",
        "class_id",
        "class_name",
        "source_image",
        "source_image_path",
        "source_json_path",
        "source_sha256",
        "risk",
        "area",
        "grow",
        "description_type",
        "box_index",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_dataset_readme(
    staging: Path, mapping: MappingConfig, task_name: str
) -> None:
    names = [entry.name for entry in mapping.classes]
    (staging / "classes.json").write_text(
        json.dumps(
            {"nc": len(names), "names": names},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (staging / "README.md").write_text(
        f"""# YOLO {task_name} dataset

This directory contains derived copies of the source images. The source files
were not moved or modified. Class names and IDs are defined in `classes.json`.
Risk, area, growth stage, source paths, and SHA-256 hashes are in `metadata.csv`.

Before training, inspect the conversion report and verify class mapping approval.

## Google Colab

```python
from google.colab import files
uploaded = files.upload()  # select the generated ZIP
import zipfile
with zipfile.ZipFile(next(iter(uploaded))) as archive:
    archive.extractall('/content/orchard_dataset')
```

Classification training example:

```python
from ultralytics import YOLO
model = YOLO('yolo11n-cls.pt')
model.train(data='/content/orchard_dataset', epochs=50, imgsz=224)
```

Do not infer disease localization from a Classification prediction. Detection
outputs, when separately approved, describe the annotated object location and
not a lesion location.
""",
        encoding="utf-8",
    )


def _create_one_dataset(
    inspection: DatasetInspection,
    mapping: MappingConfig,
    split_plan: SplitPlan,
    target: Path,
    overwrite: bool,
    crops: bool,
) -> tuple[Path | None, list[dict[str, Any]]]:
    ensure_safe_target(
        target,
        inspection.input_root,
        inspection.image_root,
        inspection.label_root,
        overwrite,
    )
    staging: Path | None = create_staging_directory(target)
    metadata: list[dict[str, Any]] = []
    try:
        for split in SPLITS:
            for class_mapping in mapping.classes:
                (staging / split / class_mapping.name).mkdir(parents=True, exist_ok=True)
        index = 0
        for split in SPLITS:
            for record in sorted(
                split_plan.by_split[split],
                key=lambda item: item.image_path.as_posix() if item.image_path else "",
            ):
                if record.image_path is None or record.class_id is None:
                    continue
                class_mapping = mapping.classes[record.class_id]
                index += 1
                if not crops:
                    filename = (
                        f"{index:06d}_{record.image_hash[:12]}"
                        f"{record.image_path.suffix.lower()}"
                    )
                    relative = Path(split) / class_mapping.name / filename
                    destination = staging / relative
                    shutil.copy2(record.image_path, destination)
                    metadata.append(
                        _metadata_row(
                            record,
                            split,
                            class_mapping,
                            relative.as_posix(),
                        )
                    )
                if not crops:
                    continue
                points = record.annotation.get("points")
                if not isinstance(points, list):
                    continue
                if record.image_width is None or record.image_height is None:
                    continue
                with Image.open(record.image_path) as source:
                    for box_index, point in enumerate(points):
                        valid, _, coordinates = validate_box(
                            point, record.image_width, record.image_height
                        )
                        if not valid or coordinates is None:
                            continue
                        left, top = math.floor(coordinates[0]), math.floor(coordinates[1])
                        right, bottom = math.ceil(coordinates[2]), math.ceil(coordinates[3])
                        crop_image = source.crop((left, top, right, bottom))
                        crop_relative = (
                            Path(split)
                            / class_mapping.name
                            / f"{index:06d}_crop_{box_index:03d}.jpg"
                        )
                        crop_destination = staging / crop_relative
                        crop_image.convert("RGB").save(crop_destination, format="JPEG", quality=95)
                        metadata.append(
                            _metadata_row(
                                record,
                                split,
                                class_mapping,
                                crop_relative.as_posix(),
                                box_index,
                            )
                        )
        _write_metadata(staging / "metadata.csv", metadata)
        _write_dataset_readme(
            staging,
            mapping,
            "Classification crops" if crops else "Classification",
        )
        backup = publish_directory(staging, target, overwrite)
        staging = None
        return backup, metadata
    finally:
        remove_staging_directory(staging)


def convert_classification(
    inspection: DatasetInspection,
    mapping: MappingConfig,
    split_plan: SplitPlan,
    output_root: Path,
    include_crops: bool = False,
    overwrite: bool = False,
    make_zip: bool = False,
) -> dict[str, Any]:
    blockers = conversion_blockers(
        inspection,
        mapping,
        split_plan,
        "classification_crops" if include_crops else "classification",
    )
    if blockers:
        raise ValueError("Classification conversion is blocked: " + "; ".join(blockers))
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / "classification"
    ensure_safe_target(
        target,
        inspection.input_root,
        inspection.image_root,
        inspection.label_root,
        overwrite,
    )
    targets = [target]
    if include_crops:
        crop_target = output_root / "classification_crops"
        ensure_safe_target(
            crop_target,
            inspection.input_root,
            inspection.image_root,
            inspection.label_root,
            overwrite,
        )
        targets.append(crop_target)
    if make_zip:
        zip_targets = [output_root / "classification.zip"]
        if include_crops:
            zip_targets.append(output_root / "classification_crops.zip")
        for zip_target in zip_targets:
            if zip_target.exists() and not overwrite:
                raise FileExistsError(
                    f"ZIP already exists: {zip_target}; pass --overwrite to preserve it as a backup."
                )

    _, metadata = _create_one_dataset(
        inspection, mapping, split_plan, target, overwrite, crops=False
    )
    crop_metadata: list[dict[str, Any]] = []
    if include_crops:
        _, crop_metadata = _create_one_dataset(
            inspection,
            mapping,
            split_plan,
            output_root / "classification_crops",
            overwrite,
            crops=True,
        )
    zip_paths = []
    if make_zip:
        zip_paths.append(create_zip(target, output_root / "classification.zip", overwrite))
        if include_crops:
            zip_paths.append(
                create_zip(
                    output_root / "classification_crops",
                    output_root / "classification_crops.zip",
                    overwrite,
                )
            )
    return {
        "target": target,
        "images": sum(1 for row in metadata if row["box_index"] == ""),
        "crop_images": sum(1 for row in crop_metadata if row["box_index"] != ""),
        "zip_paths": [
            path for path in (output_root / "classification.zip", output_root / "classification_crops.zip") if path.exists()
        ] if make_zip else [],
        "targets": targets,
    }
