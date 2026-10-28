"""CLI entry point for inspecting, validating, and converting AI Hub data."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from scripts.dataset_converter.class_mapping import (
    MappingConfig,
    load_mapping,
    mapping_readiness,
)
from scripts.dataset_converter.convert_classification import convert_classification
from scripts.dataset_converter.convert_detection import convert_detection
from scripts.dataset_converter.inspect_dataset import (
    scan_dataset,
    write_inspection_reports,
)
from scripts.dataset_converter.models import DatasetInspection
from scripts.dataset_converter.output_utils import ensure_safe_target
from scripts.dataset_converter.safety import conversion_blockers
from scripts.dataset_converter.split_dataset import SplitPlan, build_split_plan, write_split_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and safely convert AI Hub orchard disease datasets."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "validate"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--input", type=Path, default=Path("data"))
        subparser.add_argument(
            "--config", type=Path, default=Path("config/dataset_mapping.yaml")
        )
        subparser.add_argument(
            "--reports-dir", type=Path, default=Path("reports/dataset")
        )
    convert = commands.add_parser("convert")
    convert.add_argument("--input", type=Path, default=Path("data"))
    convert.add_argument("--output", type=Path, default=Path("data/processed"))
    convert.add_argument(
        "--config", type=Path, default=Path("config/dataset_mapping.yaml")
    )
    convert.add_argument(
        "--reports-dir", type=Path, default=Path("reports/dataset")
    )
    convert.add_argument(
        "--task", choices=("classification", "detection"), required=True
    )
    convert.add_argument("--dry-run", action="store_true")
    convert.add_argument("--include-crops", action="store_true")
    convert.add_argument("--zip", action="store_true", dest="make_zip")
    convert.add_argument(
        "--overwrite",
        action="store_true",
        help="Preserve an existing output as a timestamped backup before replacement.",
    )
    return parser


def _resolve_from_cwd(path: Path) -> Path:
    return path.resolve()


def _progress(message: str) -> None:
    print(message.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def _inspect(
    input_root: Path, config_path: Path, report_dir: Path
) -> tuple[DatasetInspection, MappingConfig, SplitPlan]:
    config_path = _resolve_from_cwd(config_path)
    input_root = _resolve_from_cwd(input_root)
    report_dir = _resolve_from_cwd(report_dir)
    mapping = load_mapping(config_path)
    inspection = scan_dataset(input_root, mapping, progress=_progress)
    split_config = mapping.raw.get("split", {})
    if not isinstance(split_config, dict):
        split_config = {}
    split_config = dict(split_config)
    split_plan = build_split_plan(
        inspection,
        inspection.valid_class_records,
        split_config,
        {entry.class_id: entry.name for entry in mapping.classes},
    )
    write_inspection_reports(inspection, mapping, report_dir)
    write_split_report(report_dir / "data_split_report.csv", split_plan)
    processed_root = input_root / "processed"
    if any(
        marker.is_file()
        for marker in (
            processed_root / "classification" / "metadata.csv",
            processed_root / "detection" / "data.yaml",
        )
    ):
        _mark_split_report_generated(report_dir)
    return inspection, mapping, split_plan


def _validation_errors(
    inspection: DatasetInspection, mapping: MappingConfig
) -> list[str]:
    errors = []
    for record in inspection.records:
        for issue in record.issues:
            if issue.startswith(
                (
                    "invalid_json",
                    "invalid_annotations",
                    "missing_annotations",
                    "missing_crop",
                    "missing_disease",
                    "unmapped_crop_disease_pair",
                    "invalid_risk",
                    "risk_disease_conflict",
                    "unsupported_type",
                    "type_disease_conflict",
                    "point_",
                    "points_",
                    "image_dimensions_unavailable_for_points",
                    "image_width_mismatch",
                    "image_height_mismatch",
                    "label_folder_",
                    "image_folder_",
                    "ambiguous_image_match",
                    "missing_image_match",
                    "image_referenced_by_",
                    "duplicate_class_conflict",
                )
            ):
                errors.append(f"{record.label_path}: {issue}")
    errors.extend(
        f"{path}: corrupt_or_unsupported_image: {reason}"
        for path, reason in inspection.image_errors.items()
    )
    errors.extend(
        f"{path}: image_without_matching_json"
        for path in inspection.unmatched_images
    )
    errors.extend(
        f"class_mapping: {issue}"
        for issue in mapping_readiness(mapping, set(inspection.pair_counts))
    )
    return errors


def _write_conversion_summary(
    report_dir: Path,
    task: str,
    inspection: DatasetInspection,
    split_plan: SplitPlan,
    blockers: list[str],
    output: Path | None = None,
    output_count: int | None = None,
    dry_run: bool = False,
) -> None:
    split_counts = ", ".join(
        f"{split}={len(split_plan.by_split[split])}"
        for split in ("train", "val", "test")
    )
    if blockers:
        status = "BLOCKED"
        result = "\n".join(f"- {blocker}" for blocker in blockers)
    elif dry_run:
        status = "DRY RUN"
        result = "- No conversion files were created."
    else:
        status = "COMPLETED"
        result = (
            f"- Output: `{output}`\n"
            f"- Generated samples: {output_count if output_count is not None else 0:,}"
        )
    content = "\n".join(
        [
            "# Dataset conversion summary",
            "",
            f"- Task: `{task}`",
            f"- Status: **{status}**",
            f"- Input images: {len(inspection.image_paths):,}",
            f"- Input JSON: {len(inspection.records):,}",
            f"- Unique matched image/JSON pairs: {len(inspection.matched_records):,}",
            f"- Eligible mapped samples: {len(inspection.valid_class_records):,}",
            f"- Proposed split counts: {split_counts}",
            "",
            "## Result",
            "",
            result,
            "",
            "Classification uses full-scene images by default. Detection boxes "
            "are approved subject/object locations and are not described as lesion locations.",
        ]
    )
    (report_dir / "conversion_summary.md").write_text(content + "\n", encoding="utf-8")


def _mark_split_report_generated(report_dir: Path) -> None:
    path = report_dir / "data_split_report.csv"
    if not path.is_file():
        return
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
        columns = list(rows[0]) if rows else [
            "scope",
            "split",
            "class_id",
            "class_name",
            "count",
            "actual_ratio",
            "status",
            "notes",
        ]
    for row in rows:
        if row["status"] == "preview_approved":
            row["status"] = "generated"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        inspection, mapping, split_plan = _inspect(
            args.input, args.config, args.reports_dir
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    report_dir = _resolve_from_cwd(args.reports_dir)
    if args.command == "inspect":
        print(
            f"Inspection complete: {len(inspection.image_paths)} images, "
            f"{len(inspection.records)} JSON, "
            f"{len(inspection.matched_records)} matched."
        )
        print(f"Reports: {report_dir}")
        return 0
    if args.command == "validate":
        errors = _validation_errors(inspection, mapping)
        print(f"Validation complete: {len(errors)} issue(s).")
        print(f"Reports: {report_dir}")
        if errors:
            for error in errors[:20]:
                print(f"- {error}")
            if len(errors) > 20:
                print(f"- ... and {len(errors) - 20} more (see invalid_annotations.csv)")
            return 1
        return 0

    all_blockers = conversion_blockers(
        inspection, mapping, split_plan, args.task
    )
    if args.task == "detection":
        if args.include_crops:
            all_blockers.append("include_crops_is_only_valid_for_classification")
    elif args.include_crops:
        all_blockers.extend(
            conversion_blockers(
                inspection, mapping, split_plan, "classification_crops"
            )
        )

    output_root = _resolve_from_cwd(args.output)
    targets = [output_root / args.task]
    if args.task == "classification" and args.include_crops:
        targets.append(output_root / "classification_crops")
    if args.make_zip:
        targets.append(output_root / f"{args.task}.zip")
        if args.task == "classification" and args.include_crops:
            targets.append(output_root / "classification_crops.zip")
    try:
        for target in targets:
            ensure_safe_target(
                target,
                inspection.input_root,
                inspection.image_root,
                inspection.label_root,
                args.overwrite,
            )
    except (OSError, ValueError) as exc:
        all_blockers.append(f"output_target_not_ready: {exc}")

    # Matching ambiguities and invalid class annotations are excluded and visible
    # in reports; no unresolved record is silently assigned a class.
    all_blockers = list(dict.fromkeys(all_blockers))
    eligible = len(split_plan.by_split["train"]) + len(split_plan.by_split["val"]) + len(
        split_plan.by_split["test"]
    )
    print(
        f"{'Dry run' if args.dry_run else 'Conversion'} {args.task}: "
        f"eligible={eligible}, proposed "
        f"train={len(split_plan.by_split['train'])}, "
        f"val={len(split_plan.by_split['val'])}, "
        f"test={len(split_plan.by_split['test'])}."
    )
    if all_blockers:
        _write_conversion_summary(
            report_dir,
            args.task,
            inspection,
            split_plan,
            all_blockers,
            dry_run=args.dry_run,
        )
        print("BLOCKED: " + "; ".join(all_blockers))
        print(f"See {report_dir / 'class_mapping_report.md'}")
        return 0 if args.dry_run else 2
    if args.dry_run:
        _write_conversion_summary(
            report_dir,
            args.task,
            inspection,
            split_plan,
            [],
            dry_run=True,
        )
        print("Dry run complete; no converted dataset files were created.")
        return 0

    try:
        if args.task == "classification":
            result = convert_classification(
                inspection,
                mapping,
                split_plan,
                _resolve_from_cwd(args.output),
                include_crops=args.include_crops,
                overwrite=args.overwrite,
                make_zip=args.make_zip,
            )
            output = result["target"]
            output_count = result["images"]
        else:
            result = convert_detection(
                inspection,
                mapping,
                split_plan,
                _resolve_from_cwd(args.output),
                overwrite=args.overwrite,
                make_zip=args.make_zip,
            )
            output = result["target"]
            output_count = result["images"]
    except (OSError, ValueError, RuntimeError) as exc:
        _write_conversion_summary(
            report_dir,
            args.task,
            inspection,
            split_plan,
            [f"conversion_error: {exc}"],
        )
        print(f"ERROR: conversion failed: {exc}", file=sys.stderr)
        return 2

    _mark_split_report_generated(report_dir)
    _write_conversion_summary(
        report_dir,
        args.task,
        inspection,
        split_plan,
        [],
        output=output,
        output_count=output_count,
    )
    print(f"Conversion complete: {output} ({output_count} images).")
    if args.make_zip:
        print(f"Colab ZIP: {_resolve_from_cwd(args.output) / (args.task + '.zip')}")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
