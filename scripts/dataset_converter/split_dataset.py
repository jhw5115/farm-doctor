"""Deterministic group-aware train/validation/test split planning."""

from __future__ import annotations

import csv
import hashlib
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from scripts.dataset_converter.models import DatasetInspection, DatasetRecord

SPLITS = ("train", "val", "test")


def filename_group(path: Path) -> str:
    stem = path.stem.casefold()
    match = re.match(r"^(.*)_\d+_s\d+_\d+$", stem)
    if match:
        return match.group(1)
    match = re.match(r"^(.*)_\d+$", stem)
    return match.group(1) if match else stem


class _DisjointSet:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


@dataclass
class SplitPlan:
    by_split: dict[str, list[DatasetRecord]]
    report_rows: list[dict[str, object]]
    group_count: int
    errors: list[str]


def _group_records(
    inspection: DatasetInspection,
    records: list[DatasetRecord],
    split_config: dict[str, object],
) -> dict[str, list[DatasetRecord]]:
    by_path = {record.image_path: record for record in records if record.image_path}
    dsu = _DisjointSet(str(path.resolve()) for path in by_path)
    by_capture: dict[str, list[str]] = defaultdict(list)
    by_hash: dict[str, list[str]] = defaultdict(list)
    for path, record in by_path.items():
        key = str(path.resolve())
        by_capture[filename_group(path)].append(key)
        if record.image_hash:
            by_hash[record.image_hash].append(key)
    for members in (*by_capture.values(), *by_hash.values()):
        for member in members[1:]:
            dsu.union(members[0], member)

    threshold = split_config.get("near_duplicate_hamming_threshold", 4)
    if isinstance(threshold, int) and threshold >= 0:
        for left, right, distance in inspection.near_duplicate_pairs:
            if distance <= threshold and left in by_path and right in by_path:
                dsu.union(str(left.resolve()), str(right.resolve()))

    grouped: dict[str, list[DatasetRecord]] = defaultdict(list)
    for path, record in by_path.items():
        group_id = dsu.find(str(path.resolve()))
        relative_group = Path(group_id).relative_to(inspection.input_root).as_posix()
        record.group_id = "group-" + hashlib.sha256(
            relative_group.casefold().encode("utf-8")
        ).hexdigest()[:16]
        grouped[record.group_id].append(record)
    return grouped


def build_split_plan(
    inspection: DatasetInspection,
    records: list[DatasetRecord],
    split_config: dict[str, object],
    class_names: dict[int, str] | None = None,
) -> SplitPlan:
    groups = _group_records(inspection, records, split_config)
    ratios = {
        split: float(split_config.get(split, 0.0))
        for split in SPLITS
    }
    errors = []
    if (
        any(not math.isfinite(value) or value <= 0 for value in ratios.values())
        or abs(sum(ratios.values()) - 1.0) > 1e-8
    ):
        errors.append("split_ratios_must_be_positive_and_sum_to_one")
    seed = split_config.get("seed", 42)
    if not isinstance(seed, int):
        errors.append("split_seed_must_be_integer")
        seed = 42

    class_totals = Counter(
        record.class_id for record in records if record.class_id is not None
    )
    targets = {
        split: {class_id: count * ratios[split] for class_id, count in class_totals.items()}
        for split in SPLITS
    }
    total_target = {split: len(records) * ratios[split] for split in SPLITS}
    assigned_counts = {split: Counter() for split in SPLITS}
    assigned_total = Counter()
    assigned: dict[str, list[DatasetRecord]] = {split: [] for split in SPLITS}
    group_assignment: dict[str, str] = {}

    group_items = list(groups.items())
    rng = random.Random(seed)
    rng.shuffle(group_items)
    group_counts = Counter(
        class_id
        for group_records in groups.values()
        for class_id in {
            record.class_id
            for record in group_records
            if record.class_id is not None
        }
    )
    rarity = {
        class_id: 1 / max(grouped_class_count, 1)
        for class_id, grouped_class_count in group_counts.items()
    }
    group_items.sort(
        key=lambda item: (
            -len(item[1]),
            -sum(rarity.get(record.class_id, 0) for record in item[1]),
            item[0],
        )
    )

    for group_id, group_records in group_items:
        group_classes = Counter(
            record.class_id for record in group_records if record.class_id is not None
        )

        def objective(split: str) -> tuple[float, float, int]:
            score = 0.0
            for candidate in SPLITS:
                for class_id in class_totals:
                    value = assigned_counts[candidate][class_id]
                    if candidate == split:
                        value += group_classes[class_id]
                    target = targets[candidate][class_id]
                    score += ((value - target) / max(target, 1.0)) ** 2
                value_total = assigned_total[candidate]
                if candidate == split:
                    value_total += len(group_records)
                score += 0.25 * (
                    (value_total - total_target[candidate]) / max(total_target[candidate], 1.0)
                ) ** 2
            return score, assigned_total[split] / max(total_target[split], 1.0), SPLITS.index(split)

        selected = min(SPLITS, key=objective)
        group_assignment[group_id] = selected
        assigned[selected].extend(group_records)
        assigned_total[selected] += len(group_records)
        assigned_counts[selected].update(group_classes)

    report_rows: list[dict[str, object]] = []
    approved = split_config.get("approved") is True
    status = "preview_approved" if approved else "preview_requires_group_approval"
    for split in SPLITS:
        split_count = len(assigned[split])
        report_rows.append(
            {
                "scope": "overall",
                "split": split,
                "class_id": "",
                "class_name": "",
                "count": split_count,
                "actual_ratio": round(split_count / len(records), 6) if records else 0,
                "status": status,
                "notes": f"target_ratio={ratios[split]:.6f}; seed={seed}; groups={sum(value == split for value in group_assignment.values())}",
            }
        )
        for class_id, count in sorted(assigned_counts[split].items()):
            report_rows.append(
                {
                    "scope": "class",
                    "split": split,
                    "class_id": class_id,
                    "class_name": (class_names or {}).get(class_id, ""),
                    "count": count,
                    "actual_ratio": round(count / max(class_totals[class_id], 1), 6),
                    "status": status,
                    "notes": f"class_total={class_totals[class_id]}",
                }
            )
    if not approved:
        errors.append("group_split_not_explicitly_approved")
    for class_id in class_totals:
        independent_groups = sum(
            any(record.class_id == class_id for record in group_records)
            for group_records in groups.values()
        )
        if independent_groups < 3:
            report_rows.append(
                {
                    "scope": "class_group_warning",
                    "split": "",
                    "class_id": class_id,
                    "class_name": (class_names or {}).get(class_id, ""),
                    "count": independent_groups,
                    "actual_ratio": "",
                    "status": "too_few_independent_groups",
                    "notes": "No samples were duplicated; this class may be absent from one or more splits.",
                }
            )
    return SplitPlan(assigned, report_rows, len(groups), errors)


def write_split_report(path: Path, plan: SplitPlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "scope",
        "split",
        "class_id",
        "class_name",
        "count",
        "actual_ratio",
        "status",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(plan.report_rows)
