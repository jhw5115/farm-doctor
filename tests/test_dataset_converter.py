from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path

import pytest
import yaml
from PIL import Image

from scripts.dataset_converter.class_mapping import (
    TARGET_CLASSES,
    class_for,
    load_mapping,
    mapping_readiness,
)
from scripts.dataset_converter.convert_classification import convert_classification
from scripts.dataset_converter.convert_detection import (
    convert_detection,
    validate_data_yaml,
)
from scripts.dataset_converter.inspect_dataset import (
    scan_dataset,
    write_inspection_reports,
)
from scripts.dataset_converter.split_dataset import build_split_plan
from scripts.dataset_converter.validate_annotations import normalized_box, validate_box


CLASS_ROWS = [
    (0, "pear_healthy", 1, 0, "배_정상", "[라벨]배_0.정상"),
    (1, "pear_scab", 1, 1, "배_질병", "[라벨]배_1.질병"),
    (2, "pear_fire_blight", 1, 2, "배_질병", "[라벨]배_1.질병"),
    (3, "apple_healthy", 2, 0, "사과_정상", "[라벨]사과_0.정상"),
    (4, "apple_brown_spot", 2, 3, "사과_질병", "[라벨]사과_1.질병"),
    (5, "apple_fire_blight", 2, 4, "사과_질병", "[라벨]사과_1.질병"),
    (6, "apple_valsa_canker", 2, 5, "사과_질병", "[라벨]사과_1.질병"),
    (7, "apple_alternaria_leaf_spot", 2, 6, "사과_질병", "[라벨]사과_1.질병"),
    (8, "apple_anthracnose", 2, 7, "사과_질병", "[라벨]사과_1.질병"),
]


def _write_config(path: Path, *, approved: bool = True, detection: bool = True) -> Path:
    config_path = path / "config" / "dataset_mapping.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    codebook = config_path.parent / "verified_codebook.csv"
    with codebook.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("crop", "disease", "class_id", "class_name"),
        )
        writer.writeheader()
        for class_id, name, crop, disease, _, _ in CLASS_ROWS:
            writer.writerow(
                {
                    "crop": crop,
                    "disease": disease,
                    "class_id": class_id,
                    "class_name": name,
                }
            )
    config = {
        "version": 1,
        "mapping": {
            "approved": approved,
            "approved_by": "test reviewer" if approved else "",
            "approval_note": "test approval" if approved else "",
            "codebook_path": "verified_codebook.csv" if approved else "",
            "classes": [
                {"id": class_id, "name": name, "crop": crop, "disease": disease}
                for class_id, name, crop, disease, _, _ in CLASS_ROWS
            ],
        },
        "split": {
            "train": 0.7,
            "val": 0.2,
            "test": 0.1,
            "seed": 42,
            "approved": approved,
            "approval_note": "groups reviewed" if approved else "",
            "group_strategy": "reviewed_test_capture_groups" if approved else "unverified",
            "near_duplicate_hamming_threshold": 0,
        },
        "detection": {
            "bbox_semantics_verified": detection,
            "approval_note": "subject boxes verified" if detection else "",
        },
    }
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return config_path


def _write_sample(
    data_root: Path,
    class_row: tuple[int, str, int, int, str, str],
    sample_id: int,
    *,
    image_name: str | None = None,
    disease: int | None = None,
    description_type: int | None = None,
    points: list[dict[str, int]] | None = None,
    risk: int | None = None,
    duplicate_bytes: bytes | None = None,
) -> tuple[Path, Path]:
    class_id, class_name, crop, disease_code, image_folder, label_folder = class_row
    del class_name
    image_dir = data_root / "images" / image_folder
    label_dir = data_root / "labels" / label_folder
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    image_name = image_name or f"sample_{crop}_{disease_code}_{sample_id}_S01_1.png"
    image_path = image_dir / image_name
    if duplicate_bytes is not None:
        image_path.write_bytes(duplicate_bytes)
    else:
        rng = random.Random(sample_id * 100 + class_id)
        image = Image.new("RGB", (64, 48))
        image.putdata(
            [
                (rng.randrange(256), rng.randrange(256), rng.randrange(256))
                for _ in range(64 * 48)
            ]
        )
        image.save(image_path)

    actual_disease = disease_code if disease is None else disease
    actual_risk = (0 if actual_disease == 0 else 1) if risk is None else risk
    payload = {
        "description": {
            "image": image_name,
            "width": 64,
            "height": 48,
            "type": description_type,
        },
        "annotations": {
            "crop": crop,
            "disease": actual_disease,
            "risk": actual_risk,
            "area": None,
            "grow": 25,
            "points": points if points is not None else [{"xtl": 8, "ytl": 6, "xbr": 40, "ybr": 36}],
        },
    }
    json_path = label_dir / f"{Path(image_name).stem}.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    return image_path, json_path


def _make_dataset(
    tmp_path: Path, repeats: int = 3
) -> tuple[Path, Path, list[tuple[Path, Path]]]:
    data_root = tmp_path / "data"
    config_path = _write_config(tmp_path)
    pairs = []
    sample_id = 0
    for class_row in CLASS_ROWS:
        for _ in range(repeats):
            sample_id += 1
            pairs.append(_write_sample(data_root, class_row, sample_id))
    return data_root, config_path, pairs


def test_healthy_and_disease_json_and_null_type(tmp_path: Path) -> None:
    data_root, config_path, pairs = _make_dataset(tmp_path, repeats=1)
    config = load_mapping(config_path)
    inspection = scan_dataset(data_root, config)
    healthy = next(record for record in inspection.records if record.class_id == 0)
    disease = next(record for record in inspection.records if record.class_id == 1)

    assert healthy.annotation["disease"] == 0
    assert healthy.class_id == 0
    assert disease.annotation["disease"] == 1
    assert disease.description["type"] is None
    assert disease.class_id == 1
    assert len(pairs) == len(inspection.matched_records) == 9
    assert "unsupported_type_code_None" not in disease.issues


def test_null_optional_fields_are_preserved(tmp_path: Path) -> None:
    data_root, config_path, _ = _make_dataset(tmp_path, repeats=1)
    config = load_mapping(config_path)
    inspection = scan_dataset(data_root, config)
    record = inspection.records[0]

    assert record.annotation["area"] is None
    assert record.description["type"] is None
    assert record.class_id is not None


def test_fixed_nine_class_mapping_and_unknown_code_rejection(tmp_path: Path) -> None:
    config = load_mapping(_write_config(tmp_path))

    assert [entry.name for entry in config.classes] == list(TARGET_CLASSES)
    assert class_for({"crop": 1, "disease": 2}, config).class_id == 2
    assert class_for({"crop": 1, "disease": 88}, config) is None


def test_user_approved_local_mapping_has_unique_target_ids() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    config = load_mapping(repository_root / "config" / "dataset_mapping.yaml")
    local_pairs = {
        (1, 0),
        (1, 1),
        (1, 2),
        (2, 0),
        (2, 3),
        (2, 4),
        (2, 5),
        (2, 6),
        (2, 7),
    }

    errors = mapping_readiness(config, local_pairs)

    assert not errors
    assert config.mappings[(2, 0)].class_id == 3
    assert config.mappings[(2, 0)].name == "apple_healthy"
    assert config.mappings[(2, 3)].class_id == 4
    assert config.mappings[(2, 7)].class_id == 8
    assert len({mapping.class_id for mapping in config.classes}) == 9


def test_image_matching_uses_folder_identity_to_resolve_duplicate_basenames(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    left, _ = _write_sample(
        data_root, CLASS_ROWS[0], 1, image_name="same.jpg"
    )
    right, _ = _write_sample(
        data_root, CLASS_ROWS[3], 2, image_name="same.jpg"
    )
    config = load_mapping(_write_config(tmp_path))
    inspection = scan_dataset(data_root, config)

    matched = [record for record in inspection.records if record.match_status == "matched"]
    assert len(matched) == 2
    assert {record.image_path for record in matched} == {left, right}


def test_ambiguous_duplicate_basename_is_not_arbitrarily_matched(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    left = data_root / "images" / "source_a" / "same.png"
    right = data_root / "images" / "source_b" / "same.png"
    left.parent.mkdir(parents=True)
    right.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "red").save(left)
    Image.new("RGB", (8, 8), "blue").save(right)
    json_dir = data_root / "labels" / "unknown"
    json_dir.mkdir(parents=True)
    (json_dir / "item.json").write_text(
        json.dumps(
            {
                "description": {"image": "same.png", "width": 8, "height": 8},
                "annotations": {
                    "crop": 1,
                    "disease": 0,
                    "risk": 0,
                    "points": [{"xtl": 1, "ytl": 1, "xbr": 7, "ybr": 7}],
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_mapping(_write_config(tmp_path))

    inspection = scan_dataset(data_root, config)

    assert inspection.records[0].match_status == "ambiguous"
    assert inspection.records[0].image_path is None


def test_invalid_json_and_corrupt_image_are_reported(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    image_path, json_path = _write_sample(data_root, CLASS_ROWS[0], 1)
    json_path.write_text("{invalid json", encoding="utf-8")
    corrupt_path = image_path.parent / "corrupt.png"
    corrupt_path.write_bytes(b"not an image")
    corrupt_json = json_path.parent / "corrupt.json"
    corrupt_json.write_text(
        json.dumps(
            {
                "description": {"image": "corrupt.png"},
                "annotations": {"crop": 1, "disease": 0, "risk": 0},
            }
        ),
        encoding="utf-8",
    )
    config = load_mapping(_write_config(tmp_path))

    inspection = scan_dataset(data_root, config)

    assert any(
        issue.startswith("invalid_json")
        for record in inspection.records
        for issue in record.issues
    )
    assert corrupt_path in inspection.image_errors
    assert not any(record.image_path == corrupt_path for record in inspection.valid_class_records)


def test_bbox_normalization_and_invalid_boxes() -> None:
    assert normalized_box(
        {"xtl": 10, "ytl": 5, "xbr": 30, "ybr": 25}, 40, 30
    ) == pytest.approx((0.5, 0.5, 0.5, 2 / 3))
    assert validate_box(
        {"xtl": -1, "ytl": 5, "xbr": 30, "ybr": 25}, 40, 30
    )[:2] == (False, "out_of_bounds")
    with pytest.raises(ValueError, match="Invalid bounding box"):
        normalized_box({"xtl": 20, "ytl": 5, "xbr": 10, "ybr": 25}, 40, 30)


def test_split_is_reproducible_and_exact_duplicates_stay_together(
    tmp_path: Path,
) -> None:
    data_root, config_path, pairs = _make_dataset(tmp_path, repeats=3)
    source_image, _ = pairs[0]
    duplicate_image, _ = _write_sample(
        data_root,
        CLASS_ROWS[0],
        1000,
        image_name="duplicate_copy.png",
        duplicate_bytes=source_image.read_bytes(),
    )
    config = load_mapping(config_path)
    inspection = scan_dataset(data_root, config)
    eligible = inspection.valid_class_records
    split_config = dict(config.raw["split"])

    first = build_split_plan(inspection, eligible, split_config)
    first_assignment = {
        record.image_path: split
        for split, records in first.by_split.items()
        for record in records
    }
    second = build_split_plan(inspection, eligible, split_config)
    second_assignment = {
        record.image_path: split
        for split, records in second.by_split.items()
        for record in records
    }

    assert first_assignment == second_assignment
    assert first_assignment[source_image] == first_assignment[duplicate_image]
    assert not first.errors


def test_unverified_mapping_blocks_conversion_and_creates_reports(
    tmp_path: Path,
) -> None:
    data_root, _, _ = _make_dataset(tmp_path, repeats=1)
    unverified_config_path = _write_config(tmp_path / "unverified", approved=False)
    config = load_mapping(unverified_config_path)
    inspection = scan_dataset(data_root, config)
    errors = mapping_readiness(config, set(inspection.pair_counts))
    report_dir = tmp_path / "reports"
    write_inspection_reports(inspection, config, report_dir)

    assert "mapping_not_explicitly_approved" in errors
    assert "source_codebook_path_missing" in errors
    assert (report_dir / "class_mapping_report.md").is_file()
    assert "unverified" in (report_dir / "class_mapping_report.md").read_text(
        encoding="utf-8"
    )


def test_classification_output_structure_and_source_preservation(
    tmp_path: Path,
) -> None:
    data_root, config_path, pairs = _make_dataset(tmp_path, repeats=3)
    original_hashes = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for pair in pairs
        for path in pair
    }
    config = load_mapping(config_path)
    inspection = scan_dataset(data_root, config)
    split_plan = build_split_plan(
        inspection, inspection.valid_class_records, config.raw["split"]
    )
    output_root = tmp_path / "processed"

    result = convert_classification(
        inspection, config, split_plan, output_root, make_zip=True
    )

    assert result["images"] == len(pairs)
    assert (output_root / "classification.zip").is_file()
    for split in ("train", "val", "test"):
        for _, class_name, _, _, _, _ in CLASS_ROWS:
            assert (result["target"] / split / class_name).is_dir()
    with (result["target"] / "metadata.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        metadata = list(csv.DictReader(stream))
    assert len(metadata) == len(pairs)
    assert any(row["risk"] == "0" for row in metadata)
    assert all(row["area"] == "null" for row in metadata)
    assert all(row["description_type"] == "null" for row in metadata)
    assert all(
        hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
        for path, original_hash in original_hashes.items()
    )


def test_crop_classification_is_separate_and_reuses_parent_split(
    tmp_path: Path,
) -> None:
    data_root, config_path, pairs = _make_dataset(tmp_path, repeats=3)
    config = load_mapping(config_path)
    inspection = scan_dataset(data_root, config)
    split_plan = build_split_plan(
        inspection, inspection.valid_class_records, config.raw["split"]
    )

    result = convert_classification(
        inspection,
        config,
        split_plan,
        tmp_path / "processed",
        include_crops=True,
    )

    crop_target = tmp_path / "processed" / "classification_crops"
    full_images = list(result["target"].glob("*/*/*"))
    crop_images = list(crop_target.glob("*/*/*"))
    assert result["images"] == len(pairs)
    assert result["crop_images"] == len(pairs)
    assert len(full_images) == len(pairs)
    assert len(crop_images) == len(pairs)
    with (result["target"] / "metadata.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        full_metadata = list(csv.DictReader(stream))
    with (crop_target / "metadata.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        crops_metadata = list(csv.DictReader(stream))
    full_splits = {row["source_image"]: row["split"] for row in full_metadata}
    assert all(
        full_splits[row["source_image"]] == row["split"] for row in crops_metadata
    )


def test_existing_classification_output_is_not_overwritten(tmp_path: Path) -> None:
    data_root, config_path, _ = _make_dataset(tmp_path, repeats=3)
    config = load_mapping(config_path)
    inspection = scan_dataset(data_root, config)
    split_plan = build_split_plan(
        inspection, inspection.valid_class_records, config.raw["split"]
    )
    existing = tmp_path / "processed" / "classification"
    existing.mkdir(parents=True)
    marker = existing / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Output already exists"):
        convert_classification(
            inspection, config, split_plan, tmp_path / "processed"
        )

    assert marker.read_text(encoding="utf-8") == "preserve"


def test_detection_output_and_data_yaml_validation(tmp_path: Path) -> None:
    data_root, config_path, pairs = _make_dataset(tmp_path, repeats=3)
    config = load_mapping(config_path)
    inspection = scan_dataset(data_root, config)
    split_plan = build_split_plan(
        inspection, inspection.valid_class_records, config.raw["split"]
    )

    result = convert_detection(
        inspection, config, split_plan, tmp_path / "processed", make_zip=True
    )

    data_yaml = result["target"] / "data.yaml"
    validate_data_yaml(data_yaml, config)
    assert (tmp_path / "processed" / "detection.zip").is_file()
    assert result["images"] == len(pairs)
    label_files = list((result["target"] / "labels").rglob("*.txt"))
    assert len(label_files) == len(pairs)
    assert result["boxes"] == len(pairs)
    with (result["target"] / "metadata.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        metadata = list(csv.DictReader(stream))
    assert len(metadata) == len(pairs)
    assert {row["annotation_semantics"] for row in metadata} == {
        "approved_subject_object_not_lesion"
    }
    assert all(
        line.split()[0].isdigit()
        and len(line.split()) == 5
        and all(0 <= float(value) <= 1 for value in line.split()[1:])
        for path in label_files
        for line in path.read_text(encoding="ascii").splitlines()
    )


def test_detection_rejects_invalid_bbox_without_creating_output(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    invalid_row = CLASS_ROWS[1]
    _write_sample(
        data_root,
        invalid_row,
        1,
        points=[{"xtl": -1, "ytl": 1, "xbr": 50, "ybr": 30}],
    )
    config = load_mapping(_write_config(tmp_path))
    inspection = scan_dataset(data_root, config)
    split_plan = build_split_plan(
        inspection, inspection.valid_class_records, config.raw["split"]
    )
    output_root = tmp_path / "processed"

    with pytest.raises(ValueError, match="detection_annotation_invalid"):
        convert_detection(inspection, config, split_plan, output_root)
    assert not (output_root / "detection").exists()


def test_local_mapping_codebook_mismatch_is_rejected(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    codebook = config_path.parent / "verified_codebook.csv"
    lines = codebook.read_text(encoding="utf-8").splitlines()
    lines[1] = "1,0,8,pear_healthy"
    codebook.write_text("\n".join(lines) + "\n", encoding="utf-8")
    config = load_mapping(config_path)
    expected_pairs = {
        (crop, disease) for _, _, crop, disease, _, _ in CLASS_ROWS
    }

    errors = mapping_readiness(config, expected_pairs)

    assert any("source_codebook_mapping_mismatch_1_0" in error for error in errors)


def test_converter_cli_dry_run_does_not_create_dataset(tmp_path: Path) -> None:
    from scripts.dataset_converter.main import run

    data_root, _, _ = _make_dataset(tmp_path, repeats=1)
    config_path = _write_config(tmp_path / "unverified", approved=False)
    output_root = tmp_path / "processed"
    reports = tmp_path / "reports"

    result = run(
        [
            "convert",
            "--input",
            str(data_root),
            "--output",
            str(output_root),
            "--config",
            str(config_path),
            "--reports-dir",
            str(reports),
            "--task",
            "classification",
            "--dry-run",
        ]
    )

    assert result == 0
    assert not output_root.exists()
    assert "BLOCKED" in (reports / "conversion_summary.md").read_text(
        encoding="utf-8"
    )
