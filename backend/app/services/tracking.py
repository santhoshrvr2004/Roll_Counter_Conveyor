from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .geometry import LineI, PointF, RectI, point_in_rect, segment_line_intersection, signed_line_distance
from .vision import Detection


@dataclass(slots=True)
class Track:
    track_id: int
    bbox: RectI
    centroid: PointF
    previous_centroid: PointF
    velocity: PointF
    area: float
    current_units: int
    hits: int = 1
    missed: int = 0
    matched: bool = True
    counted: bool = False
    stable_side: int = 0
    stable_point: Optional[PointF] = None
    recent_units: deque[int] = field(default_factory=lambda: deque(maxlen=4))

    def predicted(self) -> PointF:
        return self.centroid[0] + self.velocity[0], self.centroid[1] + self.velocity[1]


class AreaTracker:
    def __init__(self) -> None:
        self.tracks: list[Track] = []
        self._next_id = 1

    def reset(self) -> None:
        self.tracks.clear()
        self._next_id = 1

    def update(self, detections: list[Detection], max_distance: float, max_missed: int) -> list[Track]:
        for track in self.tracks:
            track.matched = False

        pairs: list[tuple[float, int, int]] = []
        for track_index, track in enumerate(self.tracks):
            predicted_x, predicted_y = track.predicted()
            for detection_index, detection in enumerate(detections):
                distance = math.hypot(
                    detection.centroid[0] - predicted_x,
                    detection.centroid[1] - predicted_y,
                )
                if distance > max_distance:
                    continue
                area_ratio = detection.area / max(track.area, 1.0)
                if not 0.25 <= area_ratio <= 4.5:
                    continue
                cost = distance + 14.0 * abs(math.log(max(area_ratio, 1e-6)))
                pairs.append((cost, track_index, detection_index))

        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        for _cost, track_index, detection_index in sorted(pairs, key=lambda item: item[0]):
            if track_index in matched_tracks or detection_index in matched_detections:
                continue
            matched_tracks.add(track_index)
            matched_detections.add(detection_index)
            self._apply_detection(self.tracks[track_index], detections[detection_index])

        for track_index, track in enumerate(self.tracks):
            if track_index in matched_tracks:
                continue
            track.previous_centroid = track.centroid
            track.centroid = track.predicted()
            vx, vy = track.velocity
            bx, by, bw, bh = track.bbox
            track.bbox = (int(round(bx + vx)), int(round(by + vy)), bw, bh)
            track.missed += 1

        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            track = Track(
                track_id=self._next_id,
                bbox=detection.bbox,
                centroid=detection.centroid,
                previous_centroid=detection.centroid,
                velocity=(0.0, 0.0),
                area=detection.area,
                current_units=detection.units,
            )
            track.recent_units.append(detection.units)
            self.tracks.append(track)
            self._next_id += 1

        self.tracks = [track for track in self.tracks if track.missed <= max_missed]
        return self.tracks

    @staticmethod
    def _apply_detection(track: Track, detection: Detection) -> None:
        old_x, old_y = track.centroid
        dx = detection.centroid[0] - old_x
        dy = detection.centroid[1] - old_y
        track.previous_centroid = track.centroid
        track.velocity = (
            0.65 * track.velocity[0] + 0.35 * dx,
            0.65 * track.velocity[1] + 0.35 * dy,
        )
        track.centroid = detection.centroid
        track.bbox = detection.bbox
        track.area = 0.70 * track.area + 0.30 * detection.area
        track.current_units = detection.units
        track.recent_units.append(detection.units)
        track.hits += 1
        track.missed = 0
        track.matched = True


@dataclass(slots=True)
class CountEvent:
    units: int
    direction: int
    point: PointF
    track_id: int


class GateCounter:
    def __init__(self) -> None:
        self.total = 0
        self.negative_to_positive = 0
        self.positive_to_negative = 0

    def reset(self) -> None:
        self.total = 0
        self.negative_to_positive = 0
        self.positive_to_negative = 0

    def update(
        self,
        tracks: list[Track],
        line: LineI,
        gate_box: RectI,
        min_hits: int,
        hysteresis_px: float,
    ) -> list[CountEvent]:
        events: list[CountEvent] = []
        for track in tracks:
            if track.counted or not track.matched or track.hits < min_hits:
                continue

            distance = signed_line_distance(track.centroid, line)
            side = 0
            if distance > hysteresis_px:
                side = 1
            elif distance < -hysteresis_px:
                side = -1

            if side == 0:
                continue
            if track.stable_side == 0:
                track.stable_side = side
                track.stable_point = track.centroid
                continue
            if side == track.stable_side:
                track.stable_point = track.centroid
                continue

            start = track.stable_point or track.previous_centroid
            crossing = segment_line_intersection(start, track.centroid, line)
            old_side = track.stable_side
            track.stable_side = side
            track.stable_point = track.centroid
            if crossing is None or not point_in_rect(crossing, gate_box):
                continue

            units = max(1, max(track.recent_units, default=track.current_units))
            direction = 1 if old_side < side else -1
            self.total += units
            if direction > 0:
                self.negative_to_positive += units
            else:
                self.positive_to_negative += units
            track.counted = True
            events.append(CountEvent(units, direction, crossing, track.track_id))

            if units > 1:
                bx, by, bw, bh = track.bbox
                expanded = (bx - 15, by - 15, bw + 30, bh + 30)
                remaining = units - 1
                nearby = sorted(
                    (
                        other
                        for other in tracks
                        if other.track_id != track.track_id
                        and not other.counted
                        and point_in_rect(other.centroid, expanded)
                    ),
                    key=lambda other: math.hypot(
                        other.centroid[0] - track.centroid[0],
                        other.centroid[1] - track.centroid[1],
                    ),
                )
                for other in nearby[:remaining]:
                    other.counted = True

        return events
