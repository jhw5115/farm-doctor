"""Validation helpers for AI Hub annotations and bounding boxes."""

from __future__ import annotations

import math
from typing import Any


def numeric_code(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def validate_box(
    point: Any, image_width: int, image_height: int
) -> tuple[bool, str, tuple[float, float, float, float] | None]:
    if not isinstance(point, dict):
        return False, "point_not_object", None

    coordinates = [point.get(key) for key in ("xtl", "ytl", "xbr", "ybr")]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in coordinates
    ):
        return False, "invalid_coordinate", None

    xtl, ytl, xbr, ybr = (float(value) for value in coordinates)
    if xbr <= xtl or ybr <= ytl:
        return False, "invalid_box_order", None
    if xtl < 0 or ytl < 0 or xbr > image_width or ybr > image_height:
        return False, "out_of_bounds", None
    return True, "", (xtl, ytl, xbr, ybr)


def validate_points(
    points: Any, image_width: int | None, image_height: int | None
) -> list[str]:
    if not isinstance(points, list):
        return ["points_missing_or_not_array"]
    if not points:
        return ["points_empty"]
    if image_width is None or image_height is None:
        return ["image_dimensions_unavailable"]

    issues = []
    for index, point in enumerate(points):
        valid, reason, _ = validate_box(point, image_width, image_height)
        if not valid:
            issues.append(f"point_{index}_{reason}")
    return issues


def normalized_box(
    point: Any, image_width: int, image_height: int
) -> tuple[float, float, float, float]:
    valid, reason, coordinates = validate_box(point, image_width, image_height)
    if not valid or coordinates is None:
        raise ValueError(f"Invalid bounding box: {reason}")
    xtl, ytl, xbr, ybr = coordinates
    return (
        ((xtl + xbr) / 2) / image_width,
        ((ytl + ybr) / 2) / image_height,
        (xbr - xtl) / image_width,
        (ybr - ytl) / image_height,
    )
