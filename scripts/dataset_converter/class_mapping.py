"""Class mapping configuration and source-codebook verification."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.dataset_converter.validate_annotations import numeric_code


TARGET_CLASSES = (
    "pear_healthy",
    "pear_scab",
    "pear_fire_blight",
    "apple_healthy",
    "apple_brown_spot",
    "apple_fire_blight",
    "apple_valsa_canker",
    "apple_alternaria_leaf_spot",
    "apple_anthracnose",
)


@dataclass(frozen=True)
class ClassMapping:
    class_id: int
    name: str
    crop: int
    disease: int


@dataclass
class MappingConfig:
    path: Path
    raw: dict[str, Any]
    mappings: dict[tuple[int, int], ClassMapping]
    classes: tuple[ClassMapping, ...]
    errors: list[str]


def load_mapping(path: Path) -> MappingConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        return MappingConfig(path, {}, {}, (), [f"mapping_config_error: {exc}"])
    if not isinstance(raw, dict):
        return MappingConfig(path, {}, {}, (), ["mapping_config_not_object"])

    mapping_section = raw.get("mapping")
    if not isinstance(mapping_section, dict):
        return MappingConfig(path, raw, {}, (), ["mapping_section_missing"])

    entries = mapping_section.get("classes")
    if not isinstance(entries, list):
        return MappingConfig(path, raw, {}, (), ["mapping_classes_not_list"])

    classes: list[ClassMapping] = []
    errors: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"mapping_entry_{index}_not_object")
            continue
        class_id = numeric_code(entry.get("id"))
        crop = numeric_code(entry.get("crop"))
        disease = numeric_code(entry.get("disease"))
        name = entry.get("name")
        if (
            class_id is None
            or crop is None
            or disease is None
            or not isinstance(name, str)
            or not name.strip()
        ):
            errors.append(f"mapping_entry_{index}_invalid_fields")
            continue
        classes.append(ClassMapping(class_id, name.strip(), crop, disease))

    class_ids = [entry.class_id for entry in classes]
    names = [entry.name for entry in classes]
    pairs = [(entry.crop, entry.disease) for entry in classes]
    if len(set(class_ids)) != len(class_ids):
        errors.append("duplicate_class_id")
    if len(set(names)) != len(names):
        errors.append("duplicate_class_name")
    if len(set(pairs)) != len(pairs):
        errors.append("duplicate_crop_disease_pair")
    if tuple(class_ids) != tuple(range(len(TARGET_CLASSES))):
        errors.append("class_ids_must_be_fixed_0_to_8_in_order")
    if tuple(names) != TARGET_CLASSES:
        errors.append("class_names_do_not_match_fixed_target_classes")
    if len(classes) != len(TARGET_CLASSES):
        errors.append("expected_exactly_9_classes")

    return MappingConfig(
        path=path,
        raw=raw,
        mappings={(entry.crop, entry.disease): entry for entry in classes},
        classes=tuple(classes),
        errors=errors,
    )


def class_for(annotation: dict[str, Any], config: MappingConfig) -> ClassMapping | None:
    crop = numeric_code(annotation.get("crop"))
    disease = numeric_code(annotation.get("disease"))
    if crop is None or disease is None:
        return None
    return config.mappings.get((crop, disease))


def _normalized_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", str(value).casefold())


def load_codebook(path: Path) -> tuple[dict[tuple[int, int], tuple[int, str]], list[str]]:
    errors: list[str] = []
    try:
        if path.suffix.casefold() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
        elif path.suffix.casefold() == ".json":
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            rows = value if isinstance(value, list) else value.get("classes", [])
        else:
            return {}, ["codebook_format_unsupported_use_normalized_csv_or_json"]
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, AttributeError) as exc:
        return {}, [f"codebook_read_error: {exc}"]

    if not rows or not all(isinstance(row, dict) for row in rows):
        return {}, ["codebook_has_no_mapping_rows"]

    codebook: dict[tuple[int, int], tuple[int, str]] = {}
    for index, row in enumerate(rows):
        crop = numeric_code(row.get("crop"))
        disease = numeric_code(row.get("disease"))
        class_id = numeric_code(row.get("class_id", row.get("id")))
        class_name = row.get("class_name", row.get("name", row.get("target_class")))
        if crop is None or disease is None or class_id is None or not isinstance(class_name, str):
            errors.append(f"codebook_row_{index}_requires_crop_disease_class_id_class_name")
            continue
        pair = (crop, disease)
        if pair in codebook:
            errors.append(f"codebook_duplicate_pair_{crop}_{disease}")
            continue
        codebook[pair] = (class_id, class_name.strip())
    return codebook, errors


def _official_codebook_metadata_errors(path: Path, section: dict[str, Any]) -> list[str]:
    """Ensure a claimed official codebook is not silently replaced by a local CSV."""
    required_config = (
        "official_source_url",
        "official_dataset_id",
        "official_dataset_version",
        "official_verified_on",
        "official_access_status",
    )
    errors = [f"official_codebook_metadata_missing_{key}" for key in required_config
              if not str(section.get(key, "")).strip()]
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error) as exc:
        return errors + [f"official_codebook_metadata_read_error: {exc}"]
    required_columns = {"source_url", "dataset_id", "dataset_version", "verified_on", "source_access_status"}
    if not rows or not required_columns.issubset(set(rows[0])):
        return errors + ["official_codebook_provenance_columns_missing"]
    checks = {
        "source_url": "official_source_url",
        "dataset_id": "official_dataset_id",
        "dataset_version": "official_dataset_version",
        "verified_on": "official_verified_on",
    }
    for column, config_key in checks.items():
        expected = str(section.get(config_key, "")).strip()
        if any(str(row.get(column, "")).strip() != expected for row in rows):
            errors.append(f"official_codebook_metadata_mismatch_{column}")
    if any(not str(row.get("source_access_status", "")).strip() for row in rows):
        errors.append("official_codebook_metadata_missing_source_access_status")
    return errors


def mapping_readiness(
    config: MappingConfig, observed_pairs: set[tuple[int, int]]
) -> list[str]:
    errors = list(config.errors)
    expected_pairs = set(config.mappings)
    unknown_pairs = observed_pairs - expected_pairs
    if unknown_pairs:
        errors.append(
            "local_dataset_has_unmapped_crop_disease_pairs: "
            + ", ".join(f"({crop},{disease})" for crop, disease in sorted(unknown_pairs))
        )
    missing_pairs = expected_pairs - observed_pairs
    if missing_pairs:
        errors.append(
            "local_dataset_missing_expected_crop_disease_pairs: "
            + ", ".join(f"({crop},{disease})" for crop, disease in sorted(missing_pairs))
        )
    section = config.raw.get("mapping", {})
    if section.get("approved") is not True:
        errors.append("mapping_not_explicitly_approved")
    if not str(section.get("approved_by", "")).strip():
        errors.append("mapping_approval_reviewer_missing")
    if not str(section.get("approval_note", "")).strip():
        errors.append("mapping_approval_note_missing")

    codebook_value = str(section.get("codebook_path", "")).strip()
    if not codebook_value:
        errors.append("source_codebook_path_missing")
        return errors
    codebook_path = Path(codebook_value)
    if not codebook_path.is_absolute():
        codebook_path = (config.path.parent / codebook_path).resolve()
    if not codebook_path.is_file():
        errors.append(f"source_codebook_not_found: {codebook_path}")
        return errors

    if section.get("codebook_role") == "official_aihub_reference":
        errors.extend(_official_codebook_metadata_errors(codebook_path, section))
    elif codebook_path.name == "official_disease_codebook.csv":
        errors.append("official_codebook_role_not_declared")

    codebook, codebook_errors = load_codebook(codebook_path)
    errors.extend(codebook_errors)
    if set(codebook) != expected_pairs:
        errors.append("source_codebook_pairs_do_not_exactly_match_approved_mapping")
    for pair, mapping in config.mappings.items():
        codebook_value = codebook.get(pair)
        if codebook_value is None:
            continue
        codebook_id, codebook_name = codebook_value
        if codebook_id != mapping.class_id or _normalized_name(codebook_name) != _normalized_name(mapping.name):
            errors.append(
                f"source_codebook_mapping_mismatch_{pair[0]}_{pair[1]}:"
                f"expected={mapping.class_id}:{mapping.name},"
                f"found={codebook_id}:{codebook_name}"
            )

    return errors
