#!/usr/bin/env python3
"""Read-only audit of the supplied orchard image/JSON dataset."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROOT = ROOT / "data" / "images"
LABEL_ROOT = ROOT / "data" / "labels"

TARGET_CLASSES = [
    ("pear_healthy", "pear", "healthy", "배_0.정상"),
    ("pear_scab", "pear", "disease", "배_1.질병"),
    ("pear_fire_blight", "pear", "disease", "배_1.질병"),
    ("apple_healthy", "apple", "healthy", "사과_0.정상"),
    ("apple_brown_spot", "apple", "disease", "사과_1.질병"),
    ("apple_fire_blight", "apple", "disease", "사과_1.질병"),
    ("apple_valsa_canker", "apple", "disease", "사과_1.질병"),
    ("apple_alternaria_leaf_spot", "apple", "disease", "사과_1.질병"),
    ("apple_anthracnose", "apple", "disease", "사과_1.질병"),
]
CODE_FIELDS = ("crop", "disease", "area", "grow", "risk")
EXPECTED_LABEL_FOLDERS = {
    "배_정상": "pear/healthy",
    "배_질병": "pear/disease",
    "사과_정상": "apple/healthy",
    "사과_질병": "apple/disease",
}


def image_size(path: Path) -> tuple[int, int]:
    """Return (width, height) from PNG/JPEG headers without third-party packages."""
    with path.open("rb") as stream:
        header = stream.read(24)
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return struct.unpack(">II", header[16:24])
        if not header.startswith(b"\xff\xd8"):
            raise ValueError("unsupported or invalid image header")

        stream.seek(2)
        while True:
            marker_start = stream.read(1)
            if not marker_start:
                break
            if marker_start != b"\xff":
                continue
            marker_bytes = stream.read(1)
            while marker_bytes == b"\xff":
                marker_bytes = stream.read(1)
            if not marker_bytes:
                break
            marker = marker_bytes[0]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) != 2:
                break
            segment_length = struct.unpack(">H", length_bytes)[0]
            if segment_length < 2:
                raise ValueError("invalid JPEG segment length")
            if marker in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            }:
                data = stream.read(5)
                if len(data) != 5:
                    break
                height, width = struct.unpack(">HH", data[1:5])
                return width, height
            stream.seek(segment_length - 2, 1)
    raise ValueError("image dimensions not found")


def normalized_code(value: Any) -> str:
    if value is None:
        return "<missing>"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def stable_group(filename: str) -> str:
    stem = Path(filename).stem
    # Dataset filenames end with a frame number; pear sequences may include
    # camera/side suffixes after it.
    match = re.match(r"^(.*)_\d+_S\d+_\d+$", stem)
    if match:
        return match.group(1)
    match = re.match(r"^(.*)_\d+$", stem)
    return match.group(1) if match else stem


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not IMAGE_ROOT.is_dir() or not LABEL_ROOT.is_dir():
        raise FileNotFoundError("Expected data/images and data/labels directories")

    images = sorted(p for p in IMAGE_ROOT.rglob("*") if p.is_file())
    labels = sorted(p for p in LABEL_ROOT.rglob("*.json") if p.is_file())
    images_by_name: dict[str, list[Path]] = defaultdict(list)
    for image in images:
        images_by_name[image.name].append(image)

    validation_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    stats: Counter[tuple[str, str, str, str]] = Counter()
    image_hashes: dict[str, list[str]] = defaultdict(list)
    matched_image_names: Counter[str] = Counter()
    matching_counts = Counter()
    folder_conventions: Counter[tuple[str, str]] = Counter()
    errors = Counter()

    for image in images:
        try:
            image_hashes[hashlib.sha256(image.read_bytes()).hexdigest()].append(
                image.relative_to(ROOT).as_posix()
            )
        except OSError as exc:
            errors["image_read_error"] += 1
            unmatched_rows.append({
                "file_type": "image",
                "path": image.relative_to(ROOT).as_posix(),
                "reason": f"image_read_error: {exc}",
            })

    for label in labels:
        rel_label = label.relative_to(ROOT).as_posix()
        label_folder = label.parent.name
        fallback_name = label.name[:-5] if label.name.lower().endswith(".json") else label.stem
        image_path: Path | None = None
        record: dict[str, Any] = {}
        json_error = ""
        try:
            with label.open(encoding="utf-8-sig") as stream:
                record = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            json_error = f"{type(exc).__name__}: {exc}"
            errors["json_error"] += 1

        description = record.get("description") if isinstance(record, dict) else {}
        annotations = record.get("annotations") if isinstance(record, dict) else {}
        description = description if isinstance(description, dict) else {}
        annotations = annotations if isinstance(annotations, dict) else {}
        referenced_name = Path(str(description.get("image", fallback_name))).name
        candidates = images_by_name.get(referenced_name, [])
        if len(candidates) == 1:
            image_path = candidates[0]
            matching_counts["matched"] += 1
            matched_image_names[image_path.name] += 1
        elif len(candidates) > 1:
            matching_counts["ambiguous"] += 1
            unmatched_rows.append({
                "file_type": "label",
                "path": rel_label,
                "reason": f"ambiguous_image_basename: {referenced_name}",
            })
        else:
            matching_counts["unmatched_label"] += 1
            unmatched_rows.append({
                "file_type": "label",
                "path": rel_label,
                "reason": f"no_image_with_basename: {referenced_name}",
            })

        if label_folder.startswith("[라벨]"):
            label_folder_key = label_folder[len("[라벨]"):]
        else:
            label_folder_key = label_folder
        image_folder_key = image_path.parent.name if image_path else "<unmatched>"

        for field in CODE_FIELDS:
            code = normalized_code(annotations.get(field))
            if field not in annotations:
                errors[f"missing_{field}"] += 1
            stats[(field, code, label_folder_key, image_folder_key)] += 1

        crop_code = normalized_code(annotations.get("crop"))
        disease_code = normalized_code(annotations.get("disease"))
        folder_conventions[(label_folder_key, f"crop={crop_code},disease={disease_code}")] += 1

        image_w = image_h = None
        image_size_error = ""
        if image_path is not None:
            try:
                image_w, image_h = image_size(image_path)
            except (OSError, ValueError) as exc:
                image_size_error = f"{type(exc).__name__}: {exc}"
                errors["image_size_error"] += 1

        json_w = description.get("width")
        json_h = description.get("height")
        points = annotations.get("points")
        points = points if isinstance(points, list) else None
        point_statuses: list[str] = []
        point_details: list[str] = []
        if points is None:
            point_statuses.append("points_missing_or_not_array")
            errors["invalid_points_array"] += 1
        else:
            if not points:
                point_statuses.append("points_empty")
            for index, point in enumerate(points):
                if not isinstance(point, dict):
                    point_statuses.append(f"point_{index}_not_object")
                    errors["invalid_point_object"] += 1
                    continue
                coordinates = [point.get(k) for k in ("xtl", "ytl", "xbr", "ybr")]
                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in coordinates
                ):
                    point_statuses.append(f"point_{index}_invalid_coordinate")
                    errors["invalid_coordinate"] += 1
                    continue
                xtl, ytl, xbr, ybr = coordinates
                if xbr <= xtl or ybr <= ytl:
                    point_statuses.append(f"point_{index}_invalid_order")
                    point_details.append(
                        f"point {index}: invalid order ({xtl},{ytl},{xbr},{ybr})"
                    )
                    errors["invalid_box_order"] += 1
                width = image_w if image_w is not None else json_w
                height = image_h if image_h is not None else json_h
                if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
                    point_statuses.append(f"point_{index}_image_dimensions_unavailable")
                elif xtl < 0 or ytl < 0 or xbr > width or ybr > height:
                    point_statuses.append(f"point_{index}_out_of_bounds")
                    point_details.append(
                        f"point {index}: ({xtl},{ytl},{xbr},{ybr}) outside {width}x{height}"
                    )
                    errors["out_of_bounds_point"] += 1

        dimension_mismatch = (
            image_w is not None
            and image_h is not None
            and json_w != image_w
            or image_w is not None
            and image_h is not None
            and json_h != image_h
        )
        if dimension_mismatch:
            errors["dimension_mismatch"] += 1
        if image_size_error:
            point_statuses.append("image_dimensions_unavailable")
        if not point_statuses:
            point_statuses.append("valid")

        validation_rows.append({
            "label_path": rel_label,
            "image_path": image_path.relative_to(ROOT).as_posix() if image_path else "",
            "referenced_image": referenced_name,
            "match_status": "matched" if image_path else "unmatched",
            "label_folder": label_folder_key,
            "image_folder": image_folder_key,
            "crop": crop_code,
            "disease": disease_code,
            "risk": normalized_code(annotations.get("risk")),
            "json_width": json_w if json_w is not None else "",
            "json_height": json_h if json_h is not None else "",
            "image_width": image_w if image_w is not None else "",
            "image_height": image_h if image_h is not None else "",
            "dimension_match": "no" if dimension_mismatch else (
                "yes" if image_w is not None and image_h is not None else "unknown"
            ),
            "point_count": len(points) if points is not None else "",
            "coordinate_status": ";".join(point_statuses),
            "coordinate_detail": ";".join(point_details),
            "annotation_semantics": "unverified; not assumed to be lesion boxes",
            "json_error": json_error,
            "image_size_error": image_size_error,
        })

    for image in images:
        if matched_image_names[image.name] == 0:
            matching_counts["unmatched_image"] += 1
            unmatched_rows.append({
                "file_type": "image",
                "path": image.relative_to(ROOT).as_posix(),
                "reason": "no_label_references_image_basename",
            })
        elif matched_image_names[image.name] > 1:
            unmatched_rows.append({
                "file_type": "image",
                "path": image.relative_to(ROOT).as_posix(),
                "reason": f"referenced_by_multiple_labels: {matched_image_names[image.name]}",
            })

    stat_rows = [
        {
            "field": field,
            "code": code,
            "label_folder": label_folder,
            "image_folder": image_folder,
            "count": count,
        }
        for (field, code, label_folder, image_folder), count in sorted(stats.items())
    ]

    # Crop/disease candidates are derived from the folder convention only. They
    # are intentionally not certified mappings in the absence of the codebook.
    class_rows = []
    for target_index, (target, crop, condition, raw_folder) in enumerate(TARGET_CLASSES):
        normalized_folder = raw_folder
        crop_codes = sorted({
            code for (field, code, folder, _), count in stats.items()
            if field == "crop" and folder == normalized_folder and code != "<missing>"
        })
        disease_codes = sorted({
            code for (field, code, folder, _), count in stats.items()
            if field == "disease" and folder == normalized_folder and code != "<missing>"
        })
        risk_codes = sorted({
            code for (field, code, folder, _), count in stats.items()
            if field == "risk" and folder == normalized_folder and code != "<missing>"
        })
        broad_class_possible = target.endswith("_healthy") or target in {
            "pear_scab", "pear_fire_blight", "apple_brown_spot",
            "apple_fire_blight", "apple_valsa_canker",
            "apple_alternaria_leaf_spot", "apple_anthracnose",
        }
        class_rows.append({
            "target_class_id": target_index,
            "target_class": target,
            "target_crop": crop,
            "target_condition": condition,
            "source_folder_candidate": f"[라벨]{raw_folder}",
            "observed_crop_codes_in_folder": "|".join(crop_codes),
            "observed_disease_codes_in_folder": "|".join(disease_codes),
            "observed_risk_codes_in_folder": "|".join(risk_codes),
            "source_disease_code": "",
            "mapping_status": (
                "unverified_folder_candidate_only"
                if target.endswith("_healthy")
                else "unresolved_no_subtype_codebook"
            ) if broad_class_possible else "unresolved",
            "training_label_approved": "no",
            "evidence": (
                "Numeric disease codes are observed, but no source codebook maps them to this "
                "named subtype; validated subtype labels are required."
                if condition == "disease"
                else "Healthy folder is a candidate only; code semantics still require the "
                "original codebook and review."
            ),
        })

    write_csv(
        ROOT / "dataset_statistics.csv",
        ["field", "code", "label_folder", "image_folder", "count"],
        stat_rows,
    )
    write_csv(
        ROOT / "class_mapping.csv",
        [
            "target_class_id", "target_class", "target_crop", "target_condition",
            "source_folder_candidate", "observed_crop_codes_in_folder",
            "observed_disease_codes_in_folder", "observed_risk_codes_in_folder",
            "source_disease_code", "mapping_status", "training_label_approved", "evidence",
        ],
        class_rows,
    )
    write_csv(
        ROOT / "unmatched_files.csv",
        ["file_type", "path", "reason"],
        unmatched_rows,
    )
    write_csv(
        ROOT / "annotation_validation.csv",
        [
            "label_path", "image_path", "referenced_image", "match_status",
            "label_folder", "image_folder", "crop", "disease", "risk", "json_width", "json_height",
            "image_width", "image_height", "dimension_match", "point_count",
            "coordinate_status", "coordinate_detail", "annotation_semantics",
            "json_error", "image_size_error",
        ],
        validation_rows,
    )

    groups: dict[str, set[str]] = defaultdict(set)
    group_counts: Counter[str] = Counter()
    for row in validation_rows:
        if row["match_status"] == "matched":
            group = stable_group(row["referenced_image"])
            groups[group].add(row["label_folder"])
            group_counts[group] += 1
    cross_folder_groups = sum(1 for values in groups.values() if len(values) > 1)
    duplicate_hash_groups = [paths for paths in image_hashes.values() if len(paths) > 1]
    duplicate_hash_files = sum(len(paths) for paths in duplicate_hash_groups)
    average_sequence_size = (
        sum(group_counts.values()) / len(group_counts) if group_counts else 0
    )

    def codes_in_folder(field: str, folder: str) -> str:
        counts: Counter[str] = Counter()
        for (candidate_field, code, label_folder, _), count in stats.items():
            if candidate_field == field and label_folder == folder:
                counts[code] += count
        pairs = sorted(counts.items())
        return ", ".join(f"{code}={count}" for code, count in pairs) or "(none)"

    folder_totals = Counter(row["label_folder"] for row in validation_rows)
    mapped = sum(1 for row in validation_rows if row["match_status"] == "matched")
    valid_boxes = sum(
        1 for row in validation_rows if row["coordinate_status"] == "valid"
    )
    out_of_bounds = errors["out_of_bounds_point"]
    dimensions_ok = sum(1 for row in validation_rows if row["dimension_match"] == "yes")
    expected_image_folder = {
        "배_0.정상": "배_정상",
        "배_1.질병": "배_질병",
        "사과_0.정상": "사과_정상",
        "사과_1.질병": "사과_질병",
    }
    folder_pair_matches = sum(
        1 for row in validation_rows
        if row["image_folder"] == expected_image_folder.get(row["label_folder"])
    )
    report = [
        "# 데이터셋 구조 및 YOLO 적용 사전 분석",
        "",
        "## 범위 및 안전 경계",
        "",
        "- `data/images`와 `data/labels`를 재귀 조사했습니다. 원본 이미지와 JSON은 읽기만 했으며 수정·삭제하지 않았습니다.",
        "- 질병 코드북은 프로젝트 파일에서 확인되지 않았습니다. 폴더와 코드 빈도는 관측 사실로 기록했지만, 세부 질병명으로의 매핑은 확정하지 않았습니다.",
        "- `class_mapping.csv`의 모든 행은 `training_label_approved=no`입니다. 검증 전 학습용 라벨을 생성하거나 YOLO 형식으로 변환하지 않습니다.",
        "",
        "## 데이터 요약",
        "",
        f"- 이미지: {len(images)}개; JSON: {len(labels)}개",
        f"- 파일명 기준 매칭: {mapped}개; unmatched image: {matching_counts['unmatched_image']}개; unmatched label: {matching_counts['unmatched_label']}개; ambiguous label: {matching_counts['ambiguous']}개",
        f"- 실제 이미지 크기와 JSON 선언 크기가 일치: {dimensions_ok}/{len(validation_rows)}개",
        f"- 좌표가 문법·범위 검사에서 유효한 JSON: {valid_boxes}/{len(validation_rows)}개",
        f"- 실제 이미지 범위를 벗어난 개별 points: {out_of_bounds}개",
        f"- 이미지/JSON 폴더 대응(배_0.정상→배_정상 등): {folder_pair_matches}/{len(validation_rows)}개 일치",
        f"- 중복 SHA-256 그룹: {len(duplicate_hash_groups)}개 ({duplicate_hash_files}개 파일 포함)",
        "",
        "### 폴더별 코드 빈도",
        "",
    ]
    for folder in sorted(folder_totals):
        report.append(f"- `{folder}` ({folder_totals[folder]} JSON)")
        for field in CODE_FIELDS:
            report.append(f"  - `{field}`: {codes_in_folder(field, folder)}")
    report.extend([
        "",
        "전체 필드·코드별 건수는 JSON 라벨 폴더명과 매칭 이미지 폴더명을 나란히 기록한 `dataset_statistics.csv`에 있습니다.",
        "",
        "## 목표 9개 클래스와 원본 코드 매핑",
        "",
        "`class_mapping.csv`는 목표 클래스별 후보 원본 폴더 및 그 폴더에서 관측된 crop/disease/risk 코드를 표시합니다. disease 코드는 배에서 1·2, 사과에서 3–7로 구분되어 관측되지만, 이를 목표 질병명에 대응시키는 원본 코드북은 없습니다. 따라서 숫자 코드들은 후보 신호일 뿐이고 특정 병명에 연결하지 않았습니다. 정상/질병 상위 폴더는 확인되지만, 질병 코드와 목표 병명 간의 의미 대응은 검증되지 않았습니다.",
        "",
        "| ID | 목표 클래스 | 현 단계 매핑 |",
        "|---:|---|---|",
    ])
    for row in class_rows:
        report.append(
            f"| {row['target_class_id']} | `{row['target_class']}` | "
            f"{row['mapping_status']} |"
        )
    report.extend([
        "",
        "배/사과의 crop 코드 의미도 원본 코드북으로 대조해야 합니다. 코드북과 질병별 검수 라벨이 확보되기 전에는 어떤 세부 병해 클래스도 학습 대상으로 승인할 수 없습니다.",
        "",
        "## 이미지-JSON 매칭 및 좌표 검증",
        "",
        "JSON `description.image`의 basename을 이미지 basename과 정확히 비교했습니다. 이미지 헤더에서 JPEG/PNG 실제 가로·세로를 읽어 JSON의 `description.width/height` 및 각 points의 `xtl,ytl,xbr,ybr`를 검사했습니다. 자세한 파일별 결과와 실패 사유는 `annotation_validation.csv`, 미매칭·중복 참조는 `unmatched_files.csv`에 있습니다.",
        "",
        "좌표가 이미지 안에 있고 순서가 올바르다는 검사는 주석의 의미를 입증하지 않습니다. 정상 이미지에도 points가 존재하므로 points를 병변 박스라 가정하지 않았습니다. Detection 변환은 주석 대상이 병변인지, 과실/잎 등 촬영 대상인지, 점 좌표 의미가 무엇인지 데이터 제공자 확인 후에만 가능합니다.",
        "",
        "## YOLO Classification 데이터셋 생성 가능성",
        "",
        "- JSON에는 배 질병 코드 1·2(각 250건), 사과 질병 코드 3–7(각 100건)이 관측됩니다. 숫자값이 나뉘어 있어 세부 클래스 후보가 될 수 있지만, 코드-병명 코드북이 없으므로 목표 9개 클래스의 정답 라벨로 확정할 수 없습니다.",
        "- 원본 코드북과 질병별 검수 라벨을 확보해 각 숫자 코드가 목표 병명과 맞는지 확인하고, 작물 코드 정의와 클래스별 표본 수/오류 사례를 재검토해야 합니다. 불명확 사례는 임의 배정 대신 제외/보류해야 합니다.",
        "- 허가된 분류 라벨을 얻은 후에만 `train/<class>`, `val/<class>`, `test/<class>` 구조로 내보낼 수 있습니다. 이번 작업에서는 이 디렉터리나 학습 라벨을 만들지 않았습니다.",
        "- 정확한 중복 이미지를 제거하거나 동일 그룹에 묶고, 같은 개체와 연속 촬영 시리즈가 서로 다른 split에 들어가지 않도록 해야 합니다.",
        "",
        "## YOLO Detection 적용 가능성",
        "",
        "- 원본 points는 박스 형태이고 좌표 범위 검증은 가능하지만, `annotation_semantics`가 확인되지 않았습니다. 정상 이미지의 박스 존재는 병변 박스 해석과 양립하지 않으므로 자동 변환은 부적절합니다.",
        "- 제공자/주석 지침에서 대상 객체, 경계 규칙, 클래스 의미, 정상 이미지의 박스 의미를 확인하고 샘플을 육안 검수해야 합니다.",
        "- 의미 검증 후 image size와 좌표를 사용해 중심점/너비/높이 정규화 및 클래스 ID 변환을 설계할 수 있습니다. 현재는 YOLO Detection 라벨을 생성하지 않았습니다.",
        "",
        "## 개체·연속 촬영 누수 방지",
        "",
        f"- 파일명의 마지막 숫자 프레임(배의 `_Sxx_1` 접미부 포함)을 제외한 후보 그룹이 {len(groups)}개 발견됐고, 그룹당 평균 {average_sequence_size:.2f}개 이미지입니다. 이 규칙은 파일명 기반 후보일 뿐, 동일 개체를 완전히 식별한다는 보장은 없습니다.",
        f"- 후보 그룹 중 여러 라벨 폴더를 포함하는 그룹은 {cross_folder_groups}개입니다. 이 파일명 규칙으로 교차 폴더 그룹은 나오지 않았지만, 동일 개체가 다른 파일명/촬영 세션으로 기록됐는지는 별도 확인이 필요합니다.",
        "- 최종 split 전 촬영 세션/개체 ID를 메타데이터에서 검증하고, 검증된 group ID 단위로 train/val/test에 할당해야 합니다. 시간·연속 촬영이 같거나 동일 개체로 판단되는 사진은 전부 한 split에 둡니다. 가능한 경우 별도 촬영일/과원 기준 외부 테스트도 고려합니다.",
        "- 이번 분석은 split 디렉터리나 학습 데이터를 만들지 않았습니다.",
        "",
        "## 산출물",
        "",
        "- `class_mapping.csv`: 목표 9개 클래스와 미확정 원본 코드 매핑",
        "- `dataset_statistics.csv`: crop/disease/area/grow/risk 코드별 폴더 빈도",
        "- `unmatched_files.csv`: 미매칭, 모호한 매칭, 중복 참조 및 읽기 오류",
        "- `annotation_validation.csv`: 파일별 매칭·이미지 크기·좌표 결과",
        "- `scripts/analyze_dataset.py`: 원본 데이터를 읽기만 하며 위 보고서와 CSV를 재생성하는 분석 스크립트 (`python scripts/analyze_dataset.py`)",
        "",
    ])
    (ROOT / "dataset_analysis.md").write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
