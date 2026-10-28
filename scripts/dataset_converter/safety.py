"""Shared preconditions for all dataset conversion entry points."""

from __future__ import annotations

from scripts.dataset_converter.class_mapping import MappingConfig, mapping_readiness
from scripts.dataset_converter.models import DatasetInspection
from scripts.dataset_converter.split_dataset import SplitPlan


def conversion_blockers(
    inspection: DatasetInspection,
    mapping: MappingConfig,
    split_plan: SplitPlan,
    task: str,
) -> list[str]:
    blockers = mapping_readiness(mapping, set(inspection.pair_counts))
    blockers.extend(split_plan.errors)
    split = mapping.raw.get("split", {})
    if not isinstance(split, dict):
        blockers.append("split_config_missing")
    else:
        if split.get("approved") is not True:
            blockers.append("group_split_not_explicitly_approved")
        if not str(split.get("approval_note", "")).strip():
            blockers.append("split_approval_note_missing")
        group_strategy = str(split.get("group_strategy", "")).strip()
        if not group_strategy or "unverified" in group_strategy.casefold():
            blockers.append("group_strategy_not_verified_and_approved")

    if task in {"detection", "classification_crops"}:
        detection = mapping.raw.get("detection", {})
        if not isinstance(detection, dict):
            blockers.append("bbox_semantics_config_missing")
        else:
            if detection.get("bbox_semantics_verified") is not True:
                blockers.append("bbox_semantics_not_verified")
            if not str(detection.get("approval_note", "")).strip():
                blockers.append("bbox_semantics_approval_note_missing")
        for record in inspection.valid_class_records:
            issues = [
                issue
                for issue in record.issues
                if issue.startswith(
                    (
                        "point_",
                        "points_",
                        "image_dimensions_unavailable_for_points",
                        "image_width_mismatch",
                        "image_height_mismatch",
                    )
                )
            ]
            if issues:
                blockers.append(
                    f"{task}_annotation_invalid: {record.label_path.as_posix()}:"
                    + ",".join(issues)
                )
    return list(dict.fromkeys(blockers))
