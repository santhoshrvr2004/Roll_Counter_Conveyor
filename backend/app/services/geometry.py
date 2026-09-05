from __future__ import annotations

import math
from typing import Optional

PointF = tuple[float, float]
PointI = tuple[int, int]
RectI = tuple[int, int, int, int]
LineI = tuple[PointI, PointI]


def clamp_rect(rect: RectI, width: int, height: int) -> RectI:
    x, y, w, h = rect
    x1 = max(0, min(width - 1, int(x)))
    y1 = max(0, min(height - 1, int(y)))
    x2 = max(x1 + 1, min(width, int(x + w)))
    y2 = max(y1 + 1, min(height, int(y + h)))
    return x1, y1, x2 - x1, y2 - y1


def point_in_rect(point: PointF, rect: RectI, margin: float = 0.0) -> bool:
    px, py = point
    x, y, w, h = rect
    return x - margin <= px <= x + w + margin and y - margin <= py <= y + h + margin


def signed_line_distance(point: PointF, line: LineI) -> float:
    (x1, y1), (x2, y2) = line
    px, py = point
    dx = float(x2 - x1)
    dy = float(y2 - y1)
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 0.0
    return ((px - x1) * dy - (py - y1) * dx) / length


def segment_line_intersection(
    segment_a: PointF,
    segment_b: PointF,
    line: LineI,
) -> Optional[PointF]:
    """Intersection between a finite movement segment and the finite crossing line."""
    x1, y1 = segment_a
    x2, y2 = segment_b
    x3, y3 = line[0]
    x4, y4 = line[1]

    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-8:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denominator
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return x1 + t * (x2 - x1), y1 + t * (y2 - y1)
    return None
