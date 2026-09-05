from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from .geometry import RectI, PointF, clamp_rect


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
            scores.append(center_fraction - border_fraction)
        object_cluster = int(np.argmax(scores))

        raw_mask = (labels == object_cluster).astype(np.uint8) * 255
        kernel_size = max(3, min(9, (min(w, h) // 35) | 1))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        raw_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel)
        raw_mask = cv2.morphologyEx(raw_mask, cv2.MORPH_CLOSE, kernel)

        count, component_labels, stats, centroids = cv2.connectedComponentsWithStats(raw_mask, 8)
        if count <= 1:
            raise ValueError(
                "Could not isolate the roll. Draw the rectangle with some belt visible around it."
            )

        center_x, center_y = (w - 1) / 2.0, (h - 1) / 2.0
        best_label = -1
        best_score = -1.0
        for label_id in range(1, count):
            area = float(stats[label_id, cv2.CC_STAT_AREA])
            if area < 40:
                continue
            comp_cx, comp_cy = centroids[label_id]
            distance = math.hypot(comp_cx - center_x, comp_cy - center_y)
            contains_center = (
                component_labels[int(round(center_y)), int(round(center_x))] == label_id
            )
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
            raise ValueError(
                "The calibrated roll area is too small. Move the camera closer or select more accurately."
            )

        object_pixels = lab[object_mask > 0]
        background_pixels = lab[(object_mask == 0) & border_mask]
        if len(background_pixels) < 50:
            background_pixels = lab[object_mask == 0]
        if len(background_pixels) < 50:
            raise ValueError(
                "Not enough background is visible around the roll. Draw a slightly larger rectangle."
            )

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
