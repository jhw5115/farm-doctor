"""Read-only recursive inspection and report generation for AI Hub data."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from PIL import Image, ImageOps

from scripts.dataset_converter.class_mapping import (
    ClassMapping,
    MappingConfig,
    class_for,
    mapping_readiness,
)
from scripts.dataset_converter.models import DatasetInspection, DatasetRecord
from scripts.dataset_converter.validate_annotations import (
    numeric_code,
    validate_points,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
CODE_FIELDS = ("crop", "disease", "risk", "area", "grow")


def _csv_value(value: Any) -> Any:
    return "null" if value is None else value


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _display_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _path_key(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix().casefold().lstrip("./")


def _folder_identity(name: str) -> tuple[str | None, str | None]:
    value = re.sub(r"^\[[^]]*]", "", name).casefold()
    species = "pear" if "배" in value else "apple" if "사과" in value else None
    condition = (
        "healthy" if "정상" in value else "disease" if "질병" in value else None
    )
    return species, condition


def _mapping_status(
    mapping: ClassMapping, records: list[DatasetRecord], observed_count: int
) -> str:
    if not observed_count:
        return "missing_from_local_dataset"
    conflicting = sum(
        1
        for record in records
        if numeric_code(record.annotation.get("crop")) == mapping.crop
        and numeric_code(record.annotation.get("disease")) == mapping.disease
        and any(
            issue.startswith(
                (
                    "risk_disease_conflict",
                    "label_folder_crop_conflict",
                    "label_folder_disease_conflict",
                    "image_folder_crop_conflict",
                    "image_folder_disease_conflict",
                    "type_disease_conflict",
                )
            )
            for issue in record.issues
        )
    )
    if conflicting:
        return f"local_conflict_{conflicting}_records"
    return "locally_observed_mapped"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _dhash(image: Image.Image) -> int:
    gray = ImageOps.exif_transpose(image).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    result = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            result = (result << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return result


def _read_image(path: Path) -> tuple[int, int, int, str]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
        orientation = image.getexif().get(274, 1)
        image.load()
        perceptual_hash = _dhash(image)
    return width, height, orientation, f"{perceptual_hash:016x}"


def _resolve_image(
    image_root: Path,
    label_path: Path,
    referenced_image: str,
    by_basename: dict[str, list[Path]],
    by_relative_path: dict[str, Path],
) -> tuple[Path | None, str]:
    reference_key = _path_key(referenced_image)
    direct_candidates = []
    for candidate in (
        by_relative_path.get(reference_key),
        by_relative_path.get(_path_key(f"images/{referenced_image}")),
    ):
        if candidate is not None and candidate not in direct_candidates:
            direct_candidates.append(candidate)
    if len(direct_candidates) == 1:
        return direct_candidates[0], "matched"

    basename = PurePosixPath(referenced_image.replace("\\", "/")).name.casefold()
    candidates = list(by_basename.get(basename, []))
    if direct_candidates:
        candidates = direct_candidates
    if not candidates:
        return None, "missing"
    if len(candidates) == 1:
        return candidates[0], "matched"

    label_identity = _folder_identity(label_path.parent.name)
    compatible = [
        candidate
        for candidate in candidates
        if _folder_identity(candidate.parent.name) == label_identity
        and label_identity != (None, None)
    ]
    if len(compatible) == 1:
        return compatible[0], "matched"

    reference_parts = [part.casefold() for part in PurePosixPath(referenced_image.replace("\\", "/")).parts]
    if len(reference_parts) > 1:
        suffix_matches = [
            candidate
            for candidate in candidates
            if _path_key(candidate.relative_to(image_root).as_posix()).endswith(
                "/".join(reference_parts[-2:])
            )
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0], "matched"
    return None, "ambiguous"


def _annotation_issues(
    annotation: dict[str, Any],
    description: dict[str, Any],
    label_path: Path,
    image_path: Path | None,
    width: int | None,
    height: int | None,
    mapping: MappingConfig,
) -> tuple[list[str], int | None]:
    issues: list[str] = []
    mapped = class_for(annotation, mapping)
    crop = numeric_code(annotation.get("crop"))
    disease = numeric_code(annotation.get("disease"))
    risk = numeric_code(annotation.get("risk"))

    if not isinstance(annotation, dict):
        return ["invalid_annotations_object"], None
    if crop is None:
        issues.append("missing_crop_or_invalid_crop")
    if disease is None:
        issues.append("missing_disease_or_invalid_disease")
    if mapped is None and crop is not None and disease is not None:
        issues.append(f"unmapped_crop_disease_pair_{crop}_{disease}")
    if risk is not None and risk not in {0, 1, 2, 3}:
        issues.append(f"invalid_risk_code_{risk}")
    if mapped is not None:
        if mapped.name.endswith("_healthy") and risk not in (None, 0):
            issues.append(f"risk_disease_conflict_{risk}")
        if not mapped.name.endswith("_healthy") and risk == 0:
            issues.append("risk_disease_conflict_0")

    declared_type = description.get("type")
    if declared_type is not None:
        type_code = numeric_code(declared_type)
        if type_code not in {0, 1, 2, 3}:
            issues.append(f"unsupported_type_code_{declared_type}")
        elif type_code in {2, 3}:
            issues.append(f"unsupported_type_code_{type_code}")
        elif type_code == 0 and disease not in (None, 0):
            issues.append(f"type_disease_conflict_type_0_disease_{disease}")
        elif type_code == 1 and disease == 0:
            issues.append("type_disease_conflict_type_1_disease_0")

    label_species, label_condition = _folder_identity(label_path.parent.name)
    image_species, image_condition = (
        _folder_identity(image_path.parent.name)
        if image_path is not None
        else (None, None)
    )
    expected_species = (
        "pear" if crop == 1 else "apple" if crop == 2 else None
    )
    expected_condition = (
        "healthy" if disease == 0 else "disease" if disease is not None else None
    )
    for source, species, condition in (
        ("label_folder", label_species, label_condition),
        ("image_folder", image_species, image_condition),
    ):
        if species is not None and expected_species is not None and species != expected_species:
            issues.append(f"{source}_crop_conflict")
        if condition is not None and expected_condition is not None and condition != expected_condition:
            issues.append(f"{source}_disease_conflict")

    if width is not None and height is not None:
        declared_width = numeric_code(description.get("width"))
        declared_height = numeric_code(description.get("height"))
        if declared_width is not None and declared_width != width:
            issues.append(f"image_width_mismatch_json_{declared_width}_actual_{width}")
        if declared_height is not None and declared_height != height:
            issues.append(f"image_height_mismatch_json_{declared_height}_actual_{height}")
        issues.extend(
            validate_points(annotation.get("points"), width, height)
        )
    elif annotation.get("points") is not None:
        issues.append("image_dimensions_unavailable_for_points")
    return issues, mapped.class_id if mapped is not None else None


def scan_dataset(
    input_root: Path,
    mapping: MappingConfig,
    progress: Callable[[str], None] | None = None,
) -> DatasetInspection:
    input_root = input_root.resolve()
    image_root = input_root / "images"
    label_root = input_root / "labels"
    if not image_root.is_dir() or not label_root.is_dir():
        raise FileNotFoundError(
            f"Expected images and labels directories under {input_root}"
        )

    image_paths = sorted(
        path
        for path in image_root.rglob("*")
        if path.is_file() and path.suffix.casefold() in IMAGE_SUFFIXES
    )
    label_paths = sorted(
        path
        for path in label_root.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".json"
    )
    by_basename: dict[str, list[Path]] = defaultdict(list)
    by_relative_path: dict[str, Path] = {}
    for path in image_paths:
        by_basename[path.name.casefold()].append(path)
        by_relative_path[_path_key(path.relative_to(image_root).as_posix())] = path

    image_dimensions: dict[Path, tuple[int, int]] = {}
    image_hashes: dict[Path, str] = {}
    image_dhashes: dict[Path, int] = {}
    image_orientations: dict[Path, int] = {}
    image_errors: dict[Path, str] = {}
    for index, image_path in enumerate(image_paths, start=1):
        if progress and (index == 1 or index % 100 == 0 or index == len(image_paths)):
            progress(f"Images {index:,}/{len(image_paths):,}")
        try:
            width, height, orientation, perceptual_hash = _read_image(image_path)
            image_dimensions[image_path] = (width, height)
            image_orientations[image_path] = orientation
            image_dhashes[image_path] = int(perceptual_hash, 16)
            image_hashes[image_path] = _sha256(image_path)
        except (OSError, ValueError) as exc:
            image_errors[image_path] = f"{type(exc).__name__}: {exc}"

    records: list[DatasetRecord] = []
    code_counts: dict[str, Counter[str]] = defaultdict(Counter)
    pair_counts: Counter[tuple[int, int]] = Counter()
    folder_pair_counts: Counter[tuple[str, str]] = Counter()
    for index, label_path in enumerate(label_paths, start=1):
        if progress and (index == 1 or index % 100 == 0 or index == len(label_paths)):
            progress(f"JSON labels {index:,}/{len(label_paths):,}")
        try:
            raw = json.loads(label_path.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("JSON root must be an object")
            description = raw.get("description")
            annotation = raw.get("annotations")
            description = description if isinstance(description, dict) else {}
            annotation = annotation if isinstance(annotation, dict) else {}
            parse_issue = ""
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raw = {}
            description = {}
            annotation = {}
            parse_issue = f"invalid_json: {type(exc).__name__}: {exc}"

        fallback = label_path.name[:-5] if label_path.name.casefold().endswith(".json") else label_path.stem
        reference = description.get("image")
        if not isinstance(reference, str) or not reference.strip():
            reference = fallback
        image_path, match_status = _resolve_image(
            image_root, label_path, reference, by_basename, by_relative_path
        )
        width = image_dimensions.get(image_path, (None, None))[0] if image_path else None
        height = image_dimensions.get(image_path, (None, None))[1] if image_path else None
        issues = [parse_issue] if parse_issue else []
        if not isinstance(raw.get("annotations"), dict):
            issues.append("missing_annotations")
        if image_path is None:
            issues.append(f"{match_status}_image_match")
        elif image_path in image_errors:
            issues.append("corrupt_or_unsupported_image")
        validation_issues, class_id = _annotation_issues(
            annotation, description, label_path, image_path, width, height, mapping
        )
        issues.extend(validation_issues)

        for field in CODE_FIELDS:
            value = annotation.get(field)
            key = "null" if value is None else str(value)
            code_counts[f"{label_path.parent.name}:{field}"][key] += 1
        crop = numeric_code(annotation.get("crop"))
        disease = numeric_code(annotation.get("disease"))
        if crop is not None and disease is not None:
            pair_counts[(crop, disease)] += 1
            folder_pair_counts[(label_path.parent.name, f"{crop},{disease}")] += 1
        records.append(
            DatasetRecord(
                label_path=label_path,
                image_path=image_path,
                annotation=annotation,
                description=description,
                match_status=match_status,
                referenced_image=str(reference),
                issues=sorted(set(issues)),
                image_width=width,
                image_height=height,
                image_hash=image_hashes.get(image_path, "") if image_path else "",
                dhash=image_dhashes.get(image_path) if image_path else None,
                class_id=class_id,
            )
        )

    references: dict[Path, list[DatasetRecord]] = defaultdict(list)
    for record in records:
        if record.image_path is not None and record.match_status == "matched":
            references[record.image_path].append(record)
    for image_path, referring_records in references.items():
        if len(referring_records) > 1:
            for record in referring_records:
                record.match_status = "ambiguous"
                record.issues.append(f"image_referenced_by_{len(referring_records)}_json_files")
                record.issues = sorted(set(record.issues))

    image_classes: dict[str, set[int]] = defaultdict(set)
    for record in records:
        if record.image_hash and record.class_id is not None:
            image_classes[record.image_hash].add(record.class_id)
    conflicting_hashes = {
        image_hash for image_hash, classes in image_classes.items() if len(classes) > 1
    }
    for record in records:
        if record.image_hash in conflicting_hashes:
            record.issues.append("duplicate_class_conflict")
            record.issues = sorted(set(record.issues))

    duplicate_groups_by_hash: dict[str, list[Path]] = defaultdict(list)
    for image_path, image_hash in image_hashes.items():
        duplicate_groups_by_hash[image_hash].append(image_path)
    duplicate_groups = [
        sorted(paths) for paths in duplicate_groups_by_hash.values() if len(paths) > 1
    ]

    near_duplicate_pairs: list[tuple[Path, Path, int]] = []
    valid_hashes = [
        (path, image_dhashes[path])
        for path in image_paths
        if path in image_dhashes
    ]
    threshold = mapping.raw.get("split", {}).get("near_duplicate_hamming_threshold", 4)
    if not isinstance(threshold, int) or threshold < 0 or threshold > 64:
        threshold = 4
    for index, (left_path, left_hash) in enumerate(valid_hashes):
        for right_path, right_hash in valid_hashes[index + 1 :]:
            if image_hashes.get(left_path) == image_hashes.get(right_path):
                continue
            distance = (left_hash ^ right_hash).bit_count()
            if distance <= threshold:
                near_duplicate_pairs.append((left_path, right_path, distance))

    referenced_images = {
        record.image_path
        for record in records
        if record.image_path is not None and record.match_status == "matched"
    }
    unmatched_images = [
        path
        for path in image_paths
        if path not in referenced_images
    ]
    class_counts = Counter(
        record.class_id
        for record in records
        if record.class_id is not None and record.match_status == "matched"
    )
    issues = []
    if mapping.errors:
        issues.extend(mapping.errors)
    if image_errors:
        issues.append(f"corrupt_or_unsupported_images: {len(image_errors)}")
    if duplicate_groups:
        issues.append(f"exact_duplicate_groups: {len(duplicate_groups)}")
    if near_duplicate_pairs:
        issues.append(f"near_duplicate_pairs: {len(near_duplicate_pairs)}")
    return DatasetInspection(
        input_root=input_root,
        image_root=image_root,
        label_root=label_root,
        records=records,
        image_paths=image_paths,
        unmatched_images=unmatched_images,
        duplicate_groups=duplicate_groups,
        near_duplicate_pairs=near_duplicate_pairs,
        image_errors=image_errors,
        code_counts={key: dict(value) for key, value in code_counts.items()},
        class_counts=dict(class_counts),
        pair_counts=dict(pair_counts),
        folder_pair_counts=dict(folder_pair_counts),
        issues=issues,
    )


def observed_pairs(inspection: DatasetInspection) -> set[tuple[int, int]]:
    return set(inspection.pair_counts)


def write_inspection_reports(
    inspection: DatasetInspection,
    mapping: MappingConfig,
    report_dir: Path,
) -> list[str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    input_root = inspection.input_root
    mapping_errors = mapping_readiness(mapping, observed_pairs(inspection))

    matching_rows = []
    invalid_rows = []
    for record in inspection.records:
        matching_rows.append(
            {
                "json_path": _display_path(record.label_path, input_root.parent),
                "referenced_image": record.referenced_image,
                "image_path": _display_path(record.image_path, input_root.parent)
                if record.image_path
                else "",
                "label_folder": record.label_path.parent.name,
                "image_folder": record.image_path.parent.name if record.image_path else "",
                "match_status": record.match_status,
                "crop": _csv_value(record.annotation.get("crop")),
                "disease": _csv_value(record.annotation.get("disease")),
                "risk": _csv_value(record.annotation.get("risk")),
                "area": _csv_value(record.annotation.get("area")),
                "grow": _csv_value(record.annotation.get("grow")),
                "description_type": _csv_value(record.description.get("type")),
                "class_id_candidate": record.class_id if record.class_id is not None else "",
                "image_width": record.image_width if record.image_width is not None else "",
                "image_height": record.image_height if record.image_height is not None else "",
                "image_sha256": record.image_hash,
                "group_id_candidate": record.group_id,
            }
        )
        for issue in record.issues:
            invalid_rows.append(
                {
                    "json_path": _display_path(record.label_path, input_root.parent),
                    "image_path": _display_path(record.image_path, input_root.parent)
                    if record.image_path
                    else "",
                    "issue": issue,
                    "class_id_candidate": record.class_id if record.class_id is not None else "",
                }
            )
    for image_path, error in inspection.image_errors.items():
        invalid_rows.append(
            {
                "json_path": "",
                "image_path": _display_path(image_path, input_root.parent),
                "issue": f"image_read_error: {error}",
                "class_id_candidate": "",
            }
        )
    _write_csv(
        report_dir / "image_label_matching.csv",
        [
            "json_path",
            "referenced_image",
            "image_path",
            "label_folder",
            "image_folder",
            "match_status",
            "crop",
            "disease",
            "risk",
            "area",
            "grow",
            "description_type",
            "class_id_candidate",
            "image_width",
            "image_height",
            "image_sha256",
            "group_id_candidate",
        ],
        matching_rows,
    )
    _write_csv(
        report_dir / "invalid_annotations.csv",
        ["json_path", "image_path", "issue", "class_id_candidate"],
        invalid_rows,
    )

    distribution_rows = []
    for class_mapping in mapping.classes:
        count = sum(
            1
            for record in inspection.records
            if record.class_id == class_mapping.class_id
            and record.match_status == "matched"
        )
        distribution_rows.append(
            {
                "record_type": "target_class_candidate",
                "folder": "",
                "field": "",
                "code_or_class": class_mapping.name,
                "class_id": class_mapping.class_id,
                "count": count,
                "mapping_status": _mapping_status(
                    class_mapping, inspection.records, count
                ),
            }
        )
    for key, values in sorted(inspection.code_counts.items()):
        folder, field_name = key.rsplit(":", 1)
        for code, count in sorted(values.items()):
            distribution_rows.append(
                {
                    "record_type": "source_code",
                    "folder": folder,
                    "field": field_name,
                    "code_or_class": code,
                    "class_id": "",
                    "count": count,
                    "mapping_status": "observed_only",
                }
            )
    _write_csv(
        report_dir / "class_distribution.csv",
        [
            "record_type",
            "folder",
            "field",
            "code_or_class",
            "class_id",
            "count",
            "mapping_status",
        ],
        distribution_rows,
    )

    duplicate_rows = []
    for group_index, paths in enumerate(inspection.duplicate_groups, start=1):
        digest = next(
            (record.image_hash for record in inspection.records if record.image_path == paths[0]),
            "",
        )
        for path in paths:
            duplicate_rows.append(
                {
                    "duplicate_type": "exact_sha256",
                    "group_id": f"sha256-{group_index}",
                    "image_path": _display_path(path, input_root.parent),
                    "related_image_path": "",
                    "sha256": digest,
                    "dhash_distance": "",
                    "folder": path.parent.name,
                }
            )
    for pair_index, (left, right, distance) in enumerate(
        inspection.near_duplicate_pairs, start=1
    ):
        duplicate_rows.append(
            {
                "duplicate_type": "near_dhash_candidate",
                "group_id": f"dhash-{pair_index}",
                "image_path": _display_path(left, input_root.parent),
                "related_image_path": _display_path(right, input_root.parent),
                "sha256": "",
                "dhash_distance": distance,
                "folder": left.parent.name,
            }
        )
    _write_csv(
        report_dir / "duplicate_images.csv",
        [
            "duplicate_type",
            "group_id",
            "image_path",
            "related_image_path",
            "sha256",
            "dhash_distance",
            "folder",
        ],
        duplicate_rows,
    )
    _write_csv(
        report_dir / "data_split_report.csv",
        ["scope", "split", "class_id", "class_name", "count", "actual_ratio", "status", "notes"],
        [
            {
                "scope": "overall",
                "split": "",
                "class_id": "",
                "class_name": "",
                "count": "",
                "actual_ratio": "",
                "status": "blocked",
                "notes": "No split was generated during inspection.",
            }
        ],
    )

    class_rows = []
    for item in mapping.classes:
        observed = inspection.pair_counts.get((item.crop, item.disease), 0)
        mapping_status = _mapping_status(item, inspection.records, observed)
        class_rows.append(
            f"| {item.class_id} | {item.name} | ({item.crop}, {item.disease}) | "
            f"{observed} | {mapping_status} |"
        )
    pair_lines = [
        f"| ({crop}, {disease}) | {count} |"
        for (crop, disease), count in sorted(inspection.pair_counts.items())
    ]
    candidate_pairs_match = set(inspection.pair_counts) == set(mapping.mappings)
    unexpected_pairs = set(inspection.pair_counts) - set(mapping.mappings)
    missing_pairs = set(mapping.mappings) - set(inspection.pair_counts)
    official_codebook_path = mapping.path.parent / "official_disease_codebook.csv"
    official_codebook_note = (
        "사용자가 제공한 기존 공식표 전사본은 `config/official_disease_codebook.csv`에 보존했습니다. "
        "이 표는 사과 disease 코드가 로컬 JSON과 다르므로 변환 매핑에는 적용하지 않았습니다."
        if official_codebook_path.is_file()
        else "별도 공식 코드표 파일은 없습니다."
    )
    mapping_report = "\n".join(
        [
            "# 클래스 매핑 검증 보고서",
            "",
            f"- 설정 파일: `{mapping.path}`",
            "- 로컬 JSON의 `crop+disease` 조합을 기준으로 사용자가 승인한 매핑입니다. `class_id`는 9개 목표 클래스에 대해 0~8로 고유하며, JSON의 원본 disease 숫자만으로는 작물 간 코드를 구별하지 않습니다.",
            f"- {official_codebook_note}",
            f"- 설정 승인 상태: `{mapping.raw.get('mapping', {}).get('approved', False)}`",
            f"- 승인 검토자: `{mapping.raw.get('mapping', {}).get('approved_by', '') or '미기재'}`",
            f"- 로컬 매핑 검증 결과: {', '.join(mapping_errors) if mapping_errors else '오류 없음'}",
            f"- 로컬 관측 조합과 9개 설정 조합 일치: `{candidate_pairs_match}`.",
            "",
            "| YOLO ID | 목표 클래스 | 로컬 (crop, disease) | 로컬 관측 수 | 상태 |",
            "|---:|---|---|---:|---|",
            *class_rows,
            "",
            "## 실제 관측 crop-disease 조합",
            "",
            "| 조합 | 개수 |",
            "|---|---:|",
            *pair_lines,
            "",
            f"- 설정에 없는 로컬 조합: {', '.join(str(pair) for pair in sorted(unexpected_pairs)) or '없음'}",
            f"- 로컬에 관측되지 않은 설정 조합: {', '.join(str(pair) for pair in sorted(missing_pairs)) or '없음'}",
            "",
            "질병명은 사용자가 제공한 클래스 목록 순서에 따라 로컬 코드에 대응했습니다. 이는 AI Hub 원본 공식 코드북과의 일치가 검증되었다는 뜻은 아닙니다.",
        ]
    )
    (report_dir / "class_mapping_report.md").write_text(
        mapping_report + "\n", encoding="utf-8"
    )

    folder_counts = Counter(record.label_path.parent.name for record in inspection.records)
    image_folder_counts = Counter(path.parent.name for path in inspection.image_paths)
    matched = Counter(record.label_path.parent.name for record in inspection.matched_records)
    type_counts = Counter(
        "null" if record.description.get("type") is None else str(record.description.get("type"))
        for record in inspection.records
    )
    corrupt_count = len(inspection.image_errors)
    invalid_bbox_count = sum(
        any(
            issue.startswith(
                (
                    "point_",
                    "points_",
                    "image_dimensions_unavailable_for_points",
                    "image_width_mismatch",
                    "image_height_mismatch",
                )
            )
            for issue in record.issues
        )
        for record in inspection.records
    )
    json_parse_error_count = sum(
        any(issue.startswith("invalid_json") for issue in record.issues)
        for record in inspection.records
    )
    annotation_shape_error_count = sum(
        any(
            issue.startswith(
                (
                    "invalid_annotations_object",
                    "missing_crop_or_invalid_crop",
                    "missing_disease_or_invalid_disease",
                )
            )
            for issue in record.issues
        )
        for record in inspection.records
    )
    area_counts = Counter(
        numeric_code(record.annotation.get("area"))
        for record in inspection.records
        if numeric_code(record.annotation.get("area")) is not None
    )
    grow_counts = Counter(
        numeric_code(record.annotation.get("grow"))
        for record in inspection.records
        if numeric_code(record.annotation.get("grow")) is not None
    )
    match_issue_count = sum(record.match_status != "matched" for record in inspection.records)
    folder_lines = [
        f"| {folder} | {image_folder_counts.get(folder, 0)} | {folder_counts.get(label_folder, 0)} | "
        f"{matched.get(label_folder, 0)} |"
        for label_folder, folder, *_ in _folder_pairs(folder_counts, image_folder_counts)
    ]
    distribution_summary = []
    for field_name in CODE_FIELDS:
        counts: Counter[str] = Counter()
        for key, values in inspection.code_counts.items():
            if key.endswith(f":{field_name}"):
                counts.update(values)
        distribution_summary.append(
            f"- `{field_name}`: "
            + (", ".join(f"`{code}`={count}" for code, count in sorted(counts.items())) or "값 없음")
        )
    analysis = "\n".join(
        [
            "# AI Hub 과수 질병 데이터셋 분석",
            "",
            f"- 입력: `{input_root}`",
            f"- 이미지: {len(inspection.image_paths):,}개; JSON: {len(inspection.records):,}개",
            f"- 매칭: {len(inspection.matched_records):,}개; JSON 미매칭/모호: {match_issue_count:,}개; 이미지 미매칭: {len(inspection.unmatched_images):,}개",
            f"- 손상/지원 불가 이미지: {corrupt_count:,}개",
            f"- 좌표 문제가 있는 annotation: {invalid_bbox_count:,}개 (주목 객체 bbox로 확인, 병변 bbox로 해석하지 않음)",
            f"- 완전 중복 그룹: {len(inspection.duplicate_groups):,}; 근접 유사 후보 쌍: {len(inspection.near_duplicate_pairs):,}",
            f"- description.type 분포: {', '.join(f'{key}={value}' for key, value in sorted(type_counts.items()))}",
            "",
            "## 폴더별 파일 대응",
            "",
            "| 이미지 폴더 | 이미지 | 연결 라벨 폴더 JSON | 매칭 |",
            "|---|---:|---:|---:|",
            *folder_lines,
            "",
            "## 원본 코드 분포",
            "",
            *distribution_summary,
            "",
            "## 변환 판단",
            "",
            "- 이미지-JSON 파일명 매칭은 basename과 가능한 상대 경로 및 폴더 작물/상태 힌트를 사용합니다. 충돌이 해소되지 않으면 임의 매칭하지 않습니다.",
            "- `description.type=null`은 단독 제외 사유가 아닙니다. 다른 코드·폴더와 충돌하거나 2/3 유형이면 검토 대상으로 표시합니다.",
            "- 클래스는 로컬 JSON의 crop+disease 매핑을 사용합니다. 제공된 기존 공식 코드표와의 차이는 별도 class_mapping_report.md에서 확인하세요.",
            "- split은 사용자 승인된 파일명/중복/유사도 그룹 기준으로 수행합니다. 실제 동일 개체·과수원·촬영 세션 식별을 보증하지 않으므로 잔여 누수 위험이 있습니다.",
            "- Detection bbox는 제공된 포맷 정의대로 주목 객체 위치로 사용합니다. 병변 위치로 간주하지 않습니다.",
            "- 필드별 허용 코드 범위 대조 결과는 `annotation_format_review.md`를 확인하세요. 범위 차이가 있는 보조 메타데이터는 보존하며 클래스 매핑에는 사용하지 않습니다.",
            "",
            "실제 관측 코드값은 `class_distribution.csv`, 파일 매칭은 `image_label_matching.csv`, 문제 annotation은 `invalid_annotations.csv`, 중복/유사 이미지는 `duplicate_images.csv`를 확인하세요.",
        ]
    )
    (report_dir / "dataset_analysis.md").write_text(analysis + "\n", encoding="utf-8")

    processed_root = report_dir.parent.parent / "data" / "processed"
    generated_outputs = []
    for task, marker in (
        ("classification", processed_root / "classification" / "metadata.csv"),
        ("detection", processed_root / "detection" / "data.yaml"),
    ):
        if marker.is_file():
            archive = processed_root / f"{task}.zip"
            archive_status = f"; ZIP: `{archive}`" if archive.is_file() else ""
            generated_outputs.append(
                f"- `{task}`: generated at `{marker.parent}`{archive_status}"
            )
    detection_config = mapping.raw.get("detection", {})
    bbox_approved = (
        isinstance(detection_config, dict)
        and detection_config.get("bbox_semantics_verified") is True
    )
    summary = "\n".join(
        [
            "# 데이터셋 변환 요약",
            "",
            f"- 입력 이미지: {len(inspection.image_paths):,}; JSON: {len(inspection.records):,}; 고유 매칭: {len(inspection.matched_records):,}.",
            f"- 클래스 매핑 검증 차단 사유: {', '.join(mapping_errors) if mapping_errors else '없음'}.",
            "- 사용자 승인된 그룹 기준 분할을 사용합니다. 그룹이 실제 개체/촬영 세션임을 보증하지 않습니다.",
            f"- 주목 객체 bbox 의미 승인: {'예' if bbox_approved else '아니요'}; 병변 bbox로 간주하지 않습니다.",
            "",
            "## 생성된 결과물",
            "",
            *(generated_outputs or ["- 변환 결과물이 아직 없습니다."]),
        ]
    )
    (report_dir / "conversion_summary.md").write_text(summary + "\n", encoding="utf-8")
    area_out_of_range = {
        code: count for code, count in sorted(area_counts.items()) if not 0 <= code <= 7
    }
    grow_values = ", ".join(
        f"{code}={count}" for code, count in sorted(grow_counts.items())
    ) or "없음"
    area_values = ", ".join(
        f"{code}={count}" for code, count in sorted(area_counts.items())
    ) or "없음"
    format_review = "\n".join(
        [
            "# 어노테이션 포맷 대조 결과",
            "",
            f"- 입력 JSON: {len(inspection.records):,}; 이미지-JSON 매칭: {len(inspection.matched_records):,}.",
            f"- JSON 파싱 오류: {json_parse_error_count:,}건; 필수 annotation 구조/code 오류: {annotation_shape_error_count:,}건; bbox/이미지 크기 문제: {invalid_bbox_count:,}건.",
            "- `description.type`: null은 허용 처리했습니다. 실제 분포는 분석 보고서의 description.type 항목을 참고하세요.",
            f"- `annotations.area`: 제공 포맷의 값 범위 0~7; 실제 분포 {area_values}.",
            f"- 범위 초과 area: {', '.join(f'{code}={count}' for code, count in area_out_of_range.items()) or '없음'}. 이 필드는 학습 클래스 판정에 쓰지 않고 원본 값을 metadata.csv에 보존합니다.",
            f"- `annotations.grow`: 제공된 표에는 11, 12, 13이 제시됐으나 실제 관측은 {grow_values}입니다. 코드 체계/버전 차이 여부는 제공처 확인이 필요하며 값을 임의 변환하지 않고 metadata.csv에 보존합니다.",
            "- `crop`, `disease`, `risk` 실제 코드는 설정된 범위 및 승인된 로컬 crop+disease 매핑으로 검사했습니다.",
            "- `points`는 제공된 정의대로 주목 객체의 bbox입니다. Detection 라벨은 주목 객체 위치를 뜻하며 병변 위치를 뜻하지 않습니다.",
            "- Detection 좌표는 실제 이미지 크기 기준으로 검사했으며 범위 밖 좌표를 자동 보정하지 않았습니다.",
        ]
    )
    (report_dir / "annotation_format_review.md").write_text(
        format_review + "\n", encoding="utf-8"
    )
    return mapping_errors


def _folder_pairs(
    label_counts: Counter[str], image_counts: Counter[str]
) -> list[tuple[str, str, int, int]]:
    image_keys = {
        _folder_identity(name): name
        for name in image_counts
        if _folder_identity(name) != (None, None)
    }
    pairs = []
    for label_name, count in sorted(label_counts.items()):
        identity = _folder_identity(label_name)
        image_name = image_keys.get(identity, "")
        if image_name:
            pairs.append((label_name, image_name, count, image_counts[image_name]))
    return pairs
