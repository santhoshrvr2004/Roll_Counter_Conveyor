#!/usr/bin/env python3
"""
Single-file PySide6 + Intel RealSense conveyor roll counter.

Workflow
--------
1. Connect Camera
2. Draw ROI
3. Draw Count Box
4. Draw Crossing Line
5. Keep one isolated roll in view and draw Calibrate Piece around it
6. Remove the calibration roll, then click Start Counting

Install:
    pip install PySide6 opencv-python numpy pyrealsense2

Notes:
- Contour pixel area is rotation/orientation independent.
- The count box is a gate: a line crossing is counted only when the calculated
  crossing point lies inside that box.
- A connected blob near 2x/3x the calibrated area is counted as 2/3 rolls.
- Only accepted detections are drawn; rejected noise is intentionally hidden.
"""

from __future__ import annotations

import math
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, QThread, Signal
from PySide6.QtGui import QColor, QCloseEvent, QFont, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    
    
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# -----------------------------------------------------------------------------
# Geometry helpers
# -----------------------------------------------------------------------------

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




def segment_line_intersection(segment_a: PointF, segment_b: PointF, line: LineI) -> Optional[PointF]:
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


# -----------------------------------------------------------------------------
# RealSense capture thread
# -----------------------------------------------------------------------------


class RealSenseThread(QThread):
    frame_ready = Signal(object, object)  # BGR ndarray, depth-mm ndarray|None
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30, parent=None):
        super().__init__(parent)
        self.width = width
        self.height = height
        self.fps = fps
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            import pyrealsense2 as rs  # type: ignore
        except Exception as exc:
            self.failed.emit(
                "pyrealsense2 is not installed or could not be loaded.\n"
                "Install it with: pip install pyrealsense2\n\n"
                f"Details: {exc}"
            )
            return

        pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
        config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)

        started = False
        try:
            self.status.emit("Opening RealSense camera...")
            profile = pipeline.start(config)
            started = True
            align = rs.align(rs.stream.color)
            depth_sensor = profile.get_device().first_depth_sensor()
            depth_scale_mm = float(depth_sensor.get_depth_scale()) * 1000.0
            self.status.emit("RealSense connected")

            while not self._stop_event.is_set():
                try:
                    frames = pipeline.wait_for_frames(timeout_ms=1000)
                except RuntimeError:
                    continue

                aligned = align.process(frames)
                color_frame = aligned.get_color_frame()
                depth_frame = aligned.get_depth_frame()
                if not color_frame:
                    continue

                color_bgr = np.asanyarray(color_frame.get_data()).copy()
                depth_mm: Optional[np.ndarray] = None
                if depth_frame:
                    depth_raw = np.asanyarray(depth_frame.get_data()).copy()
                    depth_mm = depth_raw.astype(np.float32) * depth_scale_mm
                    depth_mm[depth_raw == 0] = np.nan

                self.frame_ready.emit(color_bgr, depth_mm)

        except Exception as exc:
            self.failed.emit(f"Could not open/read the RealSense camera.\n\n{exc}")
        finally:
            if started:
                try:
                    pipeline.stop()
                except Exception:
                    pass
            self.status.emit("Camera disconnected")


# -----------------------------------------------------------------------------
# Calibration and vision
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class CalibrationData:
    area_px: float
    object_lab: np.ndarray
    background_lab: np.ndarray
    separation: float
    depth_low_mm: Optional[float]
    depth_high_mm: Optional[float]
    selection: RectI
    contour_global: np.ndarray


@dataclass(slots=True)
class Detection:
    bbox: RectI
    centroid: PointF
    area: float
    units: int
    contour: np.ndarray


class VisionEngine:
    def __init__(self) -> None:
        self.calibration: Optional[CalibrationData] = None

    def clear_calibration(self) -> None:
        self.calibration = None

    def calibrate(
        self,
        color_bgr: np.ndarray,
        depth_mm: Optional[np.ndarray],
        selection: RectI,
    ) -> CalibrationData:
        frame_h, frame_w = color_bgr.shape[:2]
        x, y, w, h = clamp_rect(selection, frame_w, frame_h)
        if w < 20 or h < 20:
            raise ValueError("Calibration selection is too small.")

        crop = color_bgr[y : y + h, x : x + w]
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
        lab_smooth = cv2.GaussianBlur(lab, (5, 5), 0)
        pixels = lab_smooth.reshape(-1, 3)

        # K-means separates the isolated roll from the visible belt/background.
        # Use a bounded sample for predictable calibration time.
        if len(pixels) > 50000:
            indices = np.linspace(0, len(pixels) - 1, 50000, dtype=np.int32)
            samples = pixels[indices]
        else:
            samples = pixels
        samples = np.ascontiguousarray(samples, dtype=np.float32)

        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 60, 0.15)
        _compactness, _sample_labels, centers = cv2.kmeans(
            samples,
            2,
            None,
            criteria,
            8,
            cv2.KMEANS_PP_CENTERS,
        )

        distances = np.linalg.norm(pixels[:, None, :] - centers[None, :, :], axis=2)
        labels = np.argmin(distances, axis=1).reshape(h, w)

        yy, xx = np.ogrid[:h, :w]
        cx, cy = w / 2.0, h / 2.0
        center_mask = (
            (xx >= 0.25 * w)
            & (xx <= 0.75 * w)
            & (yy >= 0.25 * h)
            & (yy <= 0.75 * h)
        )
        border_width = max(3, int(round(min(w, h) * 0.12)))
        border_mask = np.zeros((h, w), dtype=bool)
        border_mask[:border_width, :] = True
        border_mask[-border_width:, :] = True
        border_mask[:, :border_width] = True
        border_mask[:, -border_width:] = True

        scores: list[float] = []
        for cluster in range(2):
            center_fraction = float(np.mean(labels[center_mask] == cluster))
            border_fraction = float(np.mean(labels[border_mask] == cluster))
            # The selected roll should dominate the middle more than the border.
            scores.append(center_fraction - border_fraction)
        object_cluster = int(np.argmax(scores))

        raw_mask = (labels == object_cluster).astype(np.uint8) * 255
        kernel_size = max(3, min(9, (min(w, h) // 35) | 1))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        raw_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel)
        raw_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_CLOSE, kernel)

        count, component_labels, stats, centroids = cv2.connectedComponentsWithStats(raw_mask, 8)
        if count <= 1:
            raise ValueError("Could not isolate the roll. Draw the rectangle with some belt visible around it.")

        center_x, center_y = (w - 1) / 2.0, (h - 1) / 2.0
        best_label = -1
        best_score = -1.0
        for label_id in range(1, count):
            area = float(stats[label_id, cv2.CC_STAT_AREA])
            if area < 40:
                continue
            comp_cx, comp_cy = centroids[label_id]
            distance = math.hypot(comp_cx - center_x, comp_cy - center_y)
            contains_center = component_labels[int(round(center_y)), int(round(center_x))] == label_id
            score = area / (1.0 + distance / max(1.0, math.hypot(w, h)))
            if contains_center:
                score *= 5.0
            if score > best_score:
                best_score = score
                best_label = label_id

        if best_label < 0:
            raise ValueError("Could not find a usable roll contour in the calibration selection.")

        object_mask = (component_labels == best_label).astype(np.uint8) * 255
        contours, _ = cv2.findContours(object_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            raise ValueError("Calibration contour extraction failed.")
        contour = max(contours, key=cv2.contourArea)
        area_px = float(cv2.contourArea(contour))
        if area_px < 80:
            raise ValueError("The calibrated roll area is too small. Move the camera closer or select more accurately.")

        object_pixels = lab[object_mask > 0]
        background_pixels = lab[(object_mask == 0) & border_mask]
        if len(background_pixels) < 50:
            background_pixels = lab[object_mask == 0]
        if len(background_pixels) < 50:
            raise ValueError("Not enough background is visible around the roll. Draw a slightly larger rectangle.")

        object_lab = np.median(object_pixels, axis=0).astype(np.float32)
        background_lab = np.median(background_pixels, axis=0).astype(np.float32)
        separation = float(np.linalg.norm(object_lab - background_lab))
        if separation < 7.0:
            raise ValueError(
                "The selected piece does not contrast enough with the visible background. "
                "Improve lighting or include clearer belt background in the rectangle."
            )

        depth_low: Optional[float] = None
        depth_high: Optional[float] = None
        if depth_mm is not None and depth_mm.shape[:2] == color_bgr.shape[:2]:
            depth_crop = depth_mm[y : y + h, x : x + w]
            values = depth_crop[(object_mask > 0) & np.isfinite(depth_crop) & (depth_crop > 0)]
            if values.size >= 40:
                depth_low = float(np.percentile(values, 5))
                depth_high = float(np.percentile(values, 95))

        contour_global = contour.copy()
        contour_global[:, 0, 0] += x
        contour_global[:, 0, 1] += y
        calibration = CalibrationData(
            area_px=area_px,
            object_lab=object_lab,
            background_lab=background_lab,
            separation=separation,
            depth_low_mm=depth_low,
            depth_high_mm=depth_high,
            selection=(x, y, w, h),
            contour_global=contour_global,
        )
        self.calibration = calibration
        return calibration

    def detect(
        self,
        color_bgr: np.ndarray,
        depth_mm: Optional[np.ndarray],
        roi: RectI,
        area_tolerance: float,
        threshold_fraction: float,
        use_depth: bool,
        depth_extra_mm: float,
        max_merged_units: int,
    ) -> tuple[list[Detection], np.ndarray]:
        calibration = self.calibration
        if calibration is None:
            return [], np.zeros(color_bgr.shape[:2], dtype=np.uint8)

        frame_h, frame_w = color_bgr.shape[:2]
        x, y, w, h = clamp_rect(roi, frame_w, frame_h)
        crop = color_bgr[y : y + h, x : x + w]
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
        lab = cv2.GaussianBlur(lab, (5, 5), 0)

        axis = calibration.object_lab - calibration.background_lab
        axis_norm = float(np.linalg.norm(axis))
        if axis_norm < 1e-6:
            return [], np.zeros(color_bgr.shape[:2], dtype=np.uint8)
        axis /= axis_norm

        projection = np.tensordot(lab - calibration.background_lab, axis, axes=([2], [0]))
        threshold = calibration.separation * float(threshold_fraction)
        mask_crop = (projection >= threshold).astype(np.uint8) * 255

        if (
            use_depth
            and depth_mm is not None
            and calibration.depth_low_mm is not None
            and calibration.depth_high_mm is not None
        ):
            depth_crop = depth_mm[y : y + h, x : x + w]
            depth_ok = (
                np.isfinite(depth_crop)
                & (depth_crop >= calibration.depth_low_mm - depth_extra_mm)
                & (depth_crop <= calibration.depth_high_mm + depth_extra_mm)
            )
            mask_crop = cv2.bitwise_and(mask_crop, depth_ok.astype(np.uint8) * 255)

        # Small kernels reduce speckle without aggressively joining close-following rolls.
        open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_crop = cv2.morphologyEx(mask_crop, cv2.MORPH_OPEN, open_kernel)
        mask_crop = cv2.morphologyEx(mask_crop, cv2.MORPH_CLOSE, close_kernel)

        contours, _ = cv2.findContours(mask_crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: list[Detection] = []
        expected = calibration.area_px
        tolerance = max(0.05, min(0.90, float(area_tolerance)))

        for contour_local in contours:
            area = float(cv2.contourArea(contour_local))
            ratio = area / max(expected, 1.0)
            if ratio < max(0.20, 1.0 - tolerance):
                continue
            if ratio > max_merged_units * (1.0 + tolerance):
                continue

            # Prefer a single-roll interpretation while it remains within the selected
            # single-piece tolerance. Beyond that, infer 2x/3x merged pieces by area.
            if ratio <= 1.0 + tolerance:
                units = 1
            else:
                units = int(np.clip(round(ratio), 2, max_merged_units))
                relative_error = abs(ratio - units) / max(1.0, float(units))
                if relative_error > tolerance:
                    continue

            moments = cv2.moments(contour_local)
            if abs(moments["m00"]) < 1e-8:
                continue
            cx_local = float(moments["m10"] / moments["m00"])
            cy_local = float(moments["m01"] / moments["m00"])
            bx, by, bw, bh = cv2.boundingRect(contour_local)

            contour_global = contour_local.copy()
            contour_global[:, 0, 0] += x
            contour_global[:, 0, 1] += y
            detections.append(
                Detection(
                    bbox=(bx + x, by + y, bw, bh),
                    centroid=(cx_local + x, cy_local + y),
                    area=area,
                    units=units,
                    contour=contour_global,
                )
            )

        full_mask = np.zeros((frame_h, frame_w), dtype=np.uint8)
        full_mask[y : y + h, x : x + w] = mask_crop
        return detections, full_mask


# -----------------------------------------------------------------------------
# Small area-aware tracker
# -----------------------------------------------------------------------------


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
                # Allow a single track to temporarily become a 2x/3x merged blob.
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
    direction: int  # +1 or -1
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

            # Use the maximum recent multiplicity so a brief merged contour at the
            # crossing line can count close-following rolls together.
            units = max(1, max(track.recent_units, default=track.current_units))
            direction = 1 if old_side < side else -1
            self.total += units
            if direction > 0:
                self.negative_to_positive += units
            else:
                self.positive_to_negative += units
            track.counted = True
            events.append(CountEvent(units, direction, crossing, track.track_id))

            # If this was a 2x/3x merged blob, mark nearby dormant tracks as consumed
            # so they do not reappear after the line and get counted a second time.
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


# -----------------------------------------------------------------------------
# Video widget with mouse geometry selection
# -----------------------------------------------------------------------------


class VideoWidget(QWidget):
    geometry_defined = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(760, 560)
        self.setMouseTracking(True)
        self._image = QImage()
        self._mode: Optional[str] = None
        self._start: Optional[QPoint] = None
        self._current: Optional[QPoint] = None

    def set_bgr_frame(self, frame_bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format.Format_RGB888)
        self._image = image.copy()
        self.update()

    def begin_definition(self, mode: str) -> None:
        self._mode = mode
        self._start = None
        self._current = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def cancel_definition(self) -> None:
        self._mode = None
        self._start = None
        self._current = None
        self.unsetCursor()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(22, 22, 22))
        target = self._target_rect()
        if not self._image.isNull():
            painter.drawPixmap(target, QPixmap.fromImage(self._image))

        if self._mode and self._start is not None and self._current is not None:
            painter.setPen(QPen(QColor(255, 230, 30), 2, Qt.PenStyle.DashLine))
            if self._mode == "line":
                painter.drawLine(self._start, self._current)
            else:
                painter.drawRect(QRect(self._start, self._current).normalized())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            self._mode
            and event.button() == Qt.MouseButton.LeftButton
            and self._target_rect().contains(event.position().toPoint())
        ):
            self._start = event.position().toPoint()
            self._current = self._start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._mode and self._start is not None:
            self._current = self._clamp_to_target(event.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._mode or self._start is None or event.button() != Qt.MouseButton.LeftButton:
            return
        self._current = self._clamp_to_target(event.position().toPoint())
        p1 = self._widget_to_image(self._start)
        p2 = self._widget_to_image(self._current)
        mode = self._mode
        self.cancel_definition()
        if p1 is None or p2 is None:
            return

        if mode == "line":
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 10:
                return
            value: object = (p1, p2)
        else:
            x1, x2 = sorted((p1[0], p2[0]))
            y1, y2 = sorted((p1[1], p2[1]))
            if x2 - x1 < 10 or y2 - y1 < 10:
                return
            value = (x1, y1, x2 - x1, y2 - y1)
        self.geometry_defined.emit(mode, value)

    def _target_rect(self) -> QRect:
        if self._image.isNull():
            return self.rect()
        scaled = self._image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        return QRect(x, y, scaled.width(), scaled.height())

    def _widget_to_image(self, point: QPoint) -> Optional[PointI]:
        if self._image.isNull():
            return None
        target = self._target_rect()
        if target.width() <= 0 or target.height() <= 0:
            return None
        x = (point.x() - target.x()) * self._image.width() / target.width()
        y = (point.y() - target.y()) * self._image.height() / target.height()
        return (
            int(np.clip(x, 0, self._image.width() - 1)),
            int(np.clip(y, 0, self._image.height() - 1)),
        )

    def _clamp_to_target(self, point: QPoint) -> QPoint:
        target = self._target_rect()
        return QPoint(
            max(target.left(), min(target.right(), point.x())),
            max(target.top(), min(target.bottom(), point.y())),
        )


# -----------------------------------------------------------------------------
# Main window
# -----------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RealSense Conveyor Roll Counter - calibrated area")
        self.resize(1180, 720)

        self.camera_thread: Optional[RealSenseThread] = None
        self.latest_color: Optional[np.ndarray] = None
        self.latest_depth: Optional[np.ndarray] = None

        self.roi: Optional[RectI] = None
        self.gate_box: Optional[RectI] = None
        self.crossing_line: Optional[LineI] = None
        self.calibration_rect: Optional[RectI] = None

        self.vision = VisionEngine()
        self.tracker = AreaTracker()
        self.counter = GateCounter()
        self.last_mask: Optional[np.ndarray] = None
        self.last_detections: list[Detection] = []
        self.last_tracks: list[Track] = []
        self.flash_events: deque[tuple[float, CountEvent]] = deque(maxlen=12)

        self.video = VideoWidget()
        self.video.geometry_defined.connect(self.on_geometry_defined)

        controls = self._build_controls()
        splitter_layout = QHBoxLayout()
        splitter_layout.addWidget(self.video, stretch=1)
        splitter_layout.addWidget(controls)
        central = QWidget()
        central.setLayout(splitter_layout)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Connect the camera, then define ROI, box, line, and calibration piece.")

    # ----- UI -----------------------------------------------------------------

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        camera_group = QGroupBox("Camera")
        camera_layout = QVBoxLayout(camera_group)
        self.connect_button = QPushButton("Connect RealSense")
        self.connect_button.clicked.connect(self.toggle_camera)
        self.camera_status = QLabel("Disconnected")
        self.camera_status.setWordWrap(True)
        camera_layout.addWidget(self.connect_button)
        camera_layout.addWidget(self.camera_status)
        layout.addWidget(camera_group)

        setup_group = QGroupBox("Setup order")
        setup_layout = QGridLayout(setup_group)
        self.roi_button = QPushButton("1. Draw ROI")
        self.box_button = QPushButton("2. Draw Count Box")
        self.line_button = QPushButton("3. Draw Crossing Line")
        self.calibrate_button = QPushButton("4. Calibrate Piece")
        self.roi_button.clicked.connect(lambda: self.begin_draw("roi"))
        self.box_button.clicked.connect(lambda: self.begin_draw("box"))
        self.line_button.clicked.connect(lambda: self.begin_draw("line"))
        self.calibrate_button.clicked.connect(lambda: self.begin_draw("calibrate"))
        setup_layout.addWidget(self.roi_button, 0, 0)
        setup_layout.addWidget(self.box_button, 0, 1)
        setup_layout.addWidget(self.line_button, 1, 0)
        setup_layout.addWidget(self.calibrate_button, 1, 1)
        self.setup_status = QLabel("ROI: no | Box: no | Line: no | Calibration: no")
        self.setup_status.setWordWrap(True)
        setup_layout.addWidget(self.setup_status, 2, 0, 1, 2)
        layout.addWidget(setup_group)

        calibration_group = QGroupBox("Calibration tolerances")
        calibration_layout = QFormLayout(calibration_group)

        self.area_tolerance = QSpinBox()
        self.area_tolerance.setRange(10, 80)
        self.area_tolerance.setValue(40)
        self.area_tolerance.setSuffix(" %")
        self.area_tolerance.setToolTip(
            "Allowed silhouette-area variation for one roll. Start around 35-45%."
        )

        self.threshold_fraction = QSpinBox()
        self.threshold_fraction.setRange(15, 85)
        self.threshold_fraction.setValue(45)
        self.threshold_fraction.setSuffix(" %")
        self.threshold_fraction.setToolTip(
            "Lower values detect more of the roll; higher values reject more background."
        )

        self.use_depth = QCheckBox("Use calibrated depth band")
        self.use_depth.setChecked(True)
        self.depth_extra = QSpinBox()
        self.depth_extra.setRange(0, 500)
        self.depth_extra.setValue(100)
        self.depth_extra.setSuffix(" mm")

        self.max_merged = QSpinBox()
        self.max_merged.setRange(1, 10)
        self.max_merged.setValue(3)

        self.calibration_info = QLabel("Area: not calibrated")
        self.calibration_info.setWordWrap(True)

        calibration_layout.addRow("Area tolerance:", self.area_tolerance)
        calibration_layout.addRow("Contrast threshold:", self.threshold_fraction)
        calibration_layout.addRow(self.use_depth)
        calibration_layout.addRow("Depth extra:", self.depth_extra)
        calibration_layout.addRow("Max merged rolls:", self.max_merged)
        calibration_layout.addRow(self.calibration_info)
        layout.addWidget(calibration_group)

        tracking_group = QGroupBox("Tracking")
        tracking_layout = QFormLayout(tracking_group)
        self.match_distance = QSpinBox()
        self.match_distance.setRange(20, 250)
        self.match_distance.setValue(90)
        self.match_distance.setSuffix(" px")
        self.max_missed = QSpinBox()
        self.max_missed.setRange(1, 40)
        self.max_missed.setValue(12)
        self.min_hits = QSpinBox()
        self.min_hits.setRange(1, 10)
        self.min_hits.setValue(3)
        self.hysteresis = QDoubleSpinBox()
        self.hysteresis.setRange(1.0, 40.0)
        self.hysteresis.setValue(8.0)
        self.hysteresis.setSuffix(" px")
        tracking_layout.addRow("Match distance:", self.match_distance)
        tracking_layout.addRow("Keep missed frames:", self.max_missed)
        tracking_layout.addRow("Confirm frames:", self.min_hits)
        tracking_layout.addRow("Line hysteresis:", self.hysteresis)
        layout.addWidget(tracking_group)

        count_group = QGroupBox("Count")
        
        
        
        
        
        
        count_layout = QVBoxLayout(count_group)
        self.count_value = QLabel("0")
        count_font = QFont()
        count_font.setPointSize(34)
        count_font.setBold(True)
        self.count_value.setFont(count_font)
        self.count_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.direction_value = QLabel("A→B: 0    B→A: 0")
        self.direction_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_button = QPushButton("Start Counting")
        self.start_button.setCheckable(True)
        self.start_button.toggled.connect(self.toggle_counting)
        self.reset_button = QPushButton("Reset Count")
        self.reset_button.clicked.connect(self.reset_count)
        count_layout.addWidget(self.count_value)
        count_layout.addWidget(self.direction_value)
        count_layout.addWidget(self.start_button)
        count_layout.addWidget(self.reset_button)
        layout.addWidget(count_group)

        diagnostics_group = QGroupBox("Display")
        diagnostics_layout = QVBoxLayout(diagnostics_group)
        self.show_detections = QCheckBox("Show accepted roll outlines")
        self.show_detections.setChecked(True)
        self.show_ids = QCheckBox("Show track IDs")
        self.show_ids.setChecked(False)
        self.show_mask = QCheckBox("Show binary mask inset")
        self.show_mask.setChecked(False)
        diagnostics_layout.addWidget(self.show_detections)
        diagnostics_layout.addWidget(self.show_ids)
        diagnostics_layout.addWidget(self.show_mask)
        layout.addWidget(diagnostics_group)

        clear_button = QPushButton("Clear Setup")
        clear_button.clicked.connect(self.clear_setup)
        layout.addWidget(clear_button)
        layout.addStretch(1)
        return panel

    # ----- Camera --------------------------------------------------------------

    def toggle_camera(self) -> None:   
        if self.camera_thread is not None and self.camera_thread.isRunning():
            self.disconnect_camera()
        else:
            self.connect_camera()

    def connect_camera(self) -> None:
        if self.camera_thread is not None and self.camera_thread.isRunning():
            return
        self.connect_button.setEnabled(False)
        self.camera_status.setText("Opening...")
        thread = RealSenseThread(640, 480, 30, self)
        thread.frame_ready.connect(self.on_frame)
        thread.status.connect(self.on_camera_status)
        thread.failed.connect(self.on_camera_failed)
        thread.finished.connect(self.on_camera_finished)
        self.camera_thread = thread
        thread.start()

    def disconnect_camera(self) -> None:
        thread = self.camera_thread
        if thread is None:
            return
        thread.request_stop()
        thread.wait(2500)
        self.camera_thread = None
        self.connect_button.setText("Connect RealSense")
        self.connect_button.setEnabled(True)
        self.camera_status.setText("Disconnected")

    def on_camera_status(self, text: str) -> None:
        self.camera_status.setText(text)
        if text == "RealSense connected":
            self.connect_button.setText("Disconnect Camera")
            self.connect_button.setEnabled(True)

    def on_camera_failed(self, text: str) -> None:
        self.camera_status.setText("Connection failed")
        self.connect_button.setEnabled(True)
        QMessageBox.critical(self, "RealSense error", text)

    def on_camera_finished(self) -> None:
        self.connect_button.setText("Connect RealSense")
        self.connect_button.setEnabled(True)
        if self.camera_thread is not None and not self.camera_thread.isRunning():
            self.camera_thread = None

    # ----- Setup ---------------------------------------------------------------

    def begin_draw(self, mode: str) -> None:
        if self.latest_color is None:
            QMessageBox.information(self, "No frame", "Connect the camera and wait for a video frame first.")
            return
        instructions = {
            "roi": "Drag around the complete conveyor processing region.",
            "box": "Drag a narrow count box around the intended line-crossing area.",
            "line": "Drag the crossing line across the conveyor inside the count box.",
            "calibrate": (
                "Keep one isolated roll still. Drag around it with a small border of belt visible. "
                "Orientation does not matter."
            ),
        }
        self.statusBar().showMessage(instructions[mode])
        self.video.begin_definition(mode)

    def on_geometry_defined(self, mode: str, value: object) -> None:
        self.stop_counting_for_setup()
        if mode == "roi":
            self.roi = value  # type: ignore[assignment]
            self.tracker.reset()
            self.statusBar().showMessage("ROI set. Now draw the count box.")
        elif mode == "box":
            self.gate_box = value  # type: ignore[assignment]
            self.tracker.reset()
            self.statusBar().showMessage("Count box set. Now draw the crossing line.")
        elif mode == "line":
            self.crossing_line = value  # type: ignore[assignment]
            self.tracker.reset()
            self.statusBar().showMessage("Crossing line set. Keep one roll still and calibrate it.")
        elif mode == "calibrate":
            self.calibration_rect = value  # type: ignore[assignment]
            self.perform_calibration()
        self.update_setup_status()

    def perform_calibration(self) -> None:
        if self.latest_color is None or self.calibration_rect is None:
            return
        try:
            calibration = self.vision.calibrate(
                self.latest_color,
                self.latest_depth,
                self.calibration_rect,
            )
        except Exception as exc:
            self.vision.clear_calibration()
            self.calibration_info.setText("Area: calibration failed")
            QMessageBox.warning(self, "Calibration failed", str(exc))
            self.update_setup_status()
            return

        depth_text = "depth unavailable"
        if calibration.depth_low_mm is not None and calibration.depth_high_mm is not None:
            depth_text = f"depth {calibration.depth_low_mm:.0f}-{calibration.depth_high_mm:.0f} mm"
        self.calibration_info.setText(
            f"Area: {calibration.area_px:,.0f} px²\n"
            f"Contrast separation: {calibration.separation:.1f}\n"
            f"{depth_text}"
        )
        self.tracker.reset()
        self.statusBar().showMessage(
            "Calibration complete. Remove the calibration roll, then click Start Counting."
        )
        self.update_setup_status()

    def update_setup_status(self) -> None:
        self.setup_status.setText(
            f"ROI: {'yes' if self.roi else 'no'} | "
            f"Box: {'yes' if self.gate_box else 'no'} | "
            f"Line: {'yes' if self.crossing_line else 'no'} | "
            f"Calibration: {'yes' if self.vision.calibration else 'no'}"
        )

    def clear_setup(self) -> None:
        self.start_button.setChecked(False)
        self.roi = None
        self.gate_box = None
        self.crossing_line = None
        self.calibration_rect = None
        self.vision.clear_calibration()
        self.tracker.reset()
        self.counter.reset()
        self.calibration_info.setText("Area: not calibrated")
        self.update_count_labels()
        self.update_setup_status()
        self.statusBar().showMessage("Setup cleared.")

    def stop_counting_for_setup(self) -> None:
        if self.start_button.isChecked():
            self.start_button.blockSignals(True)
            self.start_button.setChecked(False)
            self.start_button.setText("Start Counting")
            self.start_button.blockSignals(False)
        self.tracker.reset()

    def toggle_counting(self, enabled: bool) -> None:
        if enabled:
            missing = []
            if self.roi is None:
                missing.append("ROI")
            if self.gate_box is None:
                missing.append("count box")
            if self.crossing_line is None:
                missing.append("crossing line")
            if self.vision.calibration is None:
                missing.append("piece calibration")
            if missing:
                self.start_button.blockSignals(True)
                self.start_button.setChecked(False)
                self.start_button.blockSignals(False)
                QMessageBox.information(self, "Setup incomplete", "Define: " + ", ".join(missing))
                return
            self.tracker.reset()
            self.start_button.setText("Stop Counting")
            self.statusBar().showMessage("Counting enabled.")
        else:
            self.start_button.setText("Start Counting")
            self.tracker.reset()
            self.statusBar().showMessage("Counting paused.")

    def reset_count(self) -> None:
        self.counter.reset()
        self.tracker.reset()
        self.flash_events.clear()
        self.update_count_labels()
        self.statusBar().showMessage("Count reset.")

    # ----- Frame processing ----------------------------------------------------

    def on_frame(self, color_bgr: np.ndarray, depth_mm: Optional[np.ndarray]) -> None:
        self.latest_color = color_bgr
        self.latest_depth = depth_mm
        display = color_bgr.copy()
        detections: list[Detection] = []
        mask = np.zeros(color_bgr.shape[:2], dtype=np.uint8)

        if self.roi is not None and self.vision.calibration is not None:
            detections, mask = self.vision.detect(
                color_bgr,
                depth_mm,
                self.roi,
                area_tolerance=self.area_tolerance.value() / 100.0,
                threshold_fraction=self.threshold_fraction.value() / 100.0,
                use_depth=self.use_depth.isChecked(),
                depth_extra_mm=float(self.depth_extra.value()),
                max_merged_units=self.max_merged.value(),
            )

        self.last_detections = detections
        self.last_mask = mask

        if self.start_button.isChecked() and self.crossing_line and self.gate_box:
            tracks = self.tracker.update(
                detections,
                max_distance=float(self.match_distance.value()),
                max_missed=self.max_missed.value(),
            )
            events = self.counter.update(
                tracks,
                self.crossing_line,
                self.gate_box,
                min_hits=self.min_hits.value(),
                hysteresis_px=float(self.hysteresis.value()),
            )
            now = time.monotonic()
            for event in events:
                self.flash_events.append((now, event))
            self.last_tracks = tracks
            if events:
                self.update_count_labels()
        else:
            self.last_tracks = []

        self.draw_overlay(display, detections)
        self.video.set_bgr_frame(display)

    def draw_overlay(self, frame: np.ndarray, detections: list[Detection]) -> None:
        # Fixed setup geometry. These are the only always-visible overlays.
        if self.roi is not None:
            x, y, w, h = self.roi
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 180, 40), 2)
            cv2.putText(frame, "ROI", (x + 5, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 180, 40), 2)
        if self.gate_box is not None:
            x, y, w, h = self.gate_box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 215, 255), 2)
            cv2.putText(frame, "COUNT BOX", (x + 5, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 215, 255), 2)
        if self.crossing_line is not None:
            cv2.line(frame, self.crossing_line[0], self.crossing_line[1], (220, 80, 255), 3)
        if self.calibration_rect is not None and self.vision.calibration is not None:
            x, y, w, h = self.calibration_rect
            cv2.rectangle(frame, (x, y), (x + w, y + h), (80, 255, 120), 1)

        if self.show_detections.isChecked():
            for detection in detections:
                outline_color = (70, 230, 70) if detection.units == 1 else (0, 165, 255)
                cv2.drawContours(frame, [detection.contour], -1, outline_color, 2)
                bx, by, _bw, _bh = detection.bbox
                label = "roll" if detection.units == 1 else f"{detection.units} rolls"
                cv2.putText(
                    frame,
                    label,
                    (bx, max(18, by - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    outline_color,
                    2,
                )

        if self.show_ids.isChecked():
            for track in self.last_tracks:
                if not track.matched:
                    continue
                cx, cy = map(int, track.centroid)
                cv2.putText(
                    frame,
                    f"ID {track.track_id}",
                    (cx + 8, cy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 255),
                    1,
                )

        now = time.monotonic()
        while self.flash_events and now - self.flash_events[0][0] > 0.8:
            self.flash_events.popleft()
        for event_time, event in self.flash_events:
            age = now - event_time
            radius = int(18 + age * 30)
            point = tuple(map(int, event.point))
            cv2.circle(frame, point, radius, (0, 255, 255), 3)
            cv2.putText(
                frame,
                f"+{event.units}",
                (point[0] + 12, point[1] - 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 255, 255),
                3,
            )

        cv2.rectangle(frame, (8, 8), (235, 58), (20, 20, 20), -1)
        cv2.putText(
            frame,
            f"COUNT: {self.counter.total}",
            (18, 43),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
        )

        if self.show_mask.isChecked() and self.last_mask is not None:
            mask_bgr = cv2.cvtColor(self.last_mask, cv2.COLOR_GRAY2BGR)
            inset_w = min(240, frame.shape[1] // 3)
            inset_h = int(inset_w * frame.shape[0] / frame.shape[1])
            inset = cv2.resize(mask_bgr, (inset_w, inset_h), interpolation=cv2.INTER_NEAREST)
            x1 = frame.shape[1] - inset_w - 10
            y1 = 10
            frame[y1 : y1 + inset_h, x1 : x1 + inset_w] = inset
            cv2.rectangle(frame, (x1, y1), (x1 + inset_w, y1 + inset_h), (255, 255, 255), 1)

    def update_count_labels(self) -> None:
        self.count_value.setText(str(self.counter.total))
        self.direction_value.setText(
            f"A→B: {self.counter.negative_to_positive}    "
            f"B→A: {self.counter.positive_to_negative}"
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.disconnect_camera()
        event.accept()


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("RealSense Conveyor Roll Counter")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
