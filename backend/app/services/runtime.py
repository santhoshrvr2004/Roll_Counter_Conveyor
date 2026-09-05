from __future__ import annotations

import atexit
import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Optional

import cv2
import numpy as np

from .camera import RealSenseCamera, list_realsense_devices
from .geometry import LineI, RectI
from .plc_service import get_plc_service
from .tracking import AreaTracker, CountEvent, GateCounter, Track
from .vision import Detection, VisionEngine


@dataclass(slots=True)
class RuntimeConfig:
    # Internal representation uses fractions for the two percentage settings.
    area_tolerance: float = 0.40
    threshold_fraction: float = 0.45
    use_depth: bool = True
    depth_extra_mm: float = 100.0
    max_merged_units: int = 3
    match_distance: float = 90.0
    max_missed: int = 12
    min_hits: int = 3
    hysteresis_px: float = 8.0
    show_detections: bool = True
    show_ids: bool = False
    show_mask: bool = False

    @staticmethod
    def _fraction(value: Any, low_fraction: float, high_fraction: float, name: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} has an invalid value") from exc

        # Accept both legacy fractions (0.40) and frontend percentages (40).
        if low_fraction <= number <= high_fraction:
            return number
        if low_fraction * 100.0 <= number <= high_fraction * 100.0:
            return number / 100.0
        raise ValueError(
            f"{name} must be between {low_fraction * 100:g} and {high_fraction * 100:g} percent"
        )

    def update_from_dict(self, data: dict[str, Any]) -> None:
        if "area_tolerance" in data:
            self.area_tolerance = self._fraction(
                data["area_tolerance"], 0.10, 0.80, "area_tolerance"
            )
        if "threshold_fraction" in data:
            self.threshold_fraction = self._fraction(
                data["threshold_fraction"], 0.15, 0.85, "threshold_fraction"
            )

        bool_fields = {"use_depth", "show_detections", "show_ids", "show_mask"}
        numeric_fields: dict[str, tuple[type, float | int, float | int]] = {
            "depth_extra_mm": (float, 0.0, 500.0),
            "max_merged_units": (int, 1, 10),
            "match_distance": (float, 20.0, 250.0),
            "max_missed": (int, 1, 40),
            "min_hits": (int, 1, 10),
            "hysteresis_px": (float, 1.0, 40.0),
        }

        known = {"area_tolerance", "threshold_fraction"} | bool_fields | set(numeric_fields)
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown configuration field: {sorted(unknown)[0]}")

        for key in bool_fields:
            if key not in data:
                continue
            value = data[key]
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be boolean")
            setattr(self, key, value)

        for key, (caster, low, high) in numeric_fields.items():
            if key not in data:
                continue
            try:
                converted = caster(data[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} has an invalid value") from exc
            if not low <= converted <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
            setattr(self, key, converted)

    def frontend_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["area_tolerance"] = round(self.area_tolerance * 100.0, 4)
        data["threshold_fraction"] = round(self.threshold_fraction * 100.0, 4)
        return data


def _rect_dict(rect: Optional[RectI]) -> Optional[dict[str, int]]:
    if rect is None:
        return None
    x, y, width, height = rect
    return {"x": x, "y": y, "width": width, "height": height}


def _line_dict(line: Optional[LineI]) -> Optional[dict[str, int]]:
    if line is None:
        return None
    (x1, y1), (x2, y2) = line
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


class CounterRuntime:
    """Single-process owner of one RealSense camera and the live counting state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._frame_condition = threading.Condition(self._lock)

        self.camera: Optional[RealSenseCamera] = None
        self.camera_status = "Disconnected"
        self.camera_error: Optional[str] = None
        self.websocket_clients = 0

        self.latest_color: Optional[np.ndarray] = None
        self.latest_depth: Optional[np.ndarray] = None
        self.latest_jpeg: Optional[bytes] = None
        self.latest_mask_jpeg: Optional[bytes] = None
        self.frame_version = 0

        self.roi: Optional[RectI] = None
        self.gate_box: Optional[RectI] = None
        self.crossing_line: Optional[LineI] = None
        self.calibration_rect: Optional[RectI] = None

        self.config = RuntimeConfig()
        self.vision = VisionEngine()
        self.tracker = AreaTracker()
        self.counter = GateCounter()
        self.counting = False
        self.last_detections: list[Detection] = []
        self.last_tracks: list[Track] = []
        self.last_mask: Optional[np.ndarray] = None
        self.flash_events: deque[tuple[float, CountEvent]] = deque(maxlen=12)
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=100)
        self.plc = get_plc_service()

    # Camera -----------------------------------------------------------------

    def list_devices(self) -> list[dict[str, Any]]:
        return list_realsense_devices()

    def connect_camera(self, serial: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            if self.camera is not None and self.camera.is_alive():
                return self.status()

            self.camera_error = None
            self.camera_status = "Opening..."
            self.latest_jpeg = None
            self.latest_mask_jpeg = None
            camera = RealSenseCamera(
                frame_callback=self._on_frame,
                status_callback=self._on_camera_status,
                error_callback=self._on_camera_error,
                serial=serial,
            )
            self.camera = camera
            camera.start()
            return self.status()

    def disconnect_camera(self) -> dict[str, Any]:
        with self._lock:
            camera = self.camera
            self.counting = False
            self.tracker.reset()

        if camera is not None:
            camera.request_stop()
            camera.join(timeout=3.0)

        with self._frame_condition:
            if self.camera is camera:
                self.camera = None
            self.camera_status = "Disconnected"
            self.latest_jpeg = None
            self.latest_mask_jpeg = None
            self.frame_version += 1
            self._frame_condition.notify_all()
            return self.status()

    def shutdown(self) -> None:
        try:
            self.disconnect_camera()
        except Exception:
            pass
        try:
            self.plc.shutdown()
        except Exception:
            pass

    def add_websocket_client(self) -> int:
        with self._lock:
            self.websocket_clients += 1
            return self.websocket_clients

    def remove_websocket_client(self) -> int:
        with self._lock:
            self.websocket_clients = max(0, self.websocket_clients - 1)
            return self.websocket_clients

    def _on_camera_status(self, text: str) -> None:
        with self._frame_condition:
            if text == "Camera disconnected" and self.camera_error:
                self.camera_status = "Connection failed"
            else:
                self.camera_status = text
            self._frame_condition.notify_all()

    def _on_camera_error(self, text: str) -> None:
        with self._frame_condition:
            self.camera_error = text
            self.camera_status = "Connection failed"
            self._frame_condition.notify_all()

    # Setup ------------------------------------------------------------------

    def _stop_counting_for_setup_locked(self) -> None:
        self.counting = False
        self.tracker.reset()

    def set_roi(self, rect: RectI) -> None:
        with self._lock:
            self._stop_counting_for_setup_locked()
            self.roi = rect

    def set_gate_box(self, rect: RectI) -> None:
        with self._lock:
            self._stop_counting_for_setup_locked()
            self.gate_box = rect

    def set_crossing_line(self, line: LineI) -> None:
        if math.hypot(line[1][0] - line[0][0], line[1][1] - line[0][1]) < 10:
            raise ValueError("Crossing line must be at least 10 pixels long.")
        with self._lock:
            self._stop_counting_for_setup_locked()
            self.crossing_line = line

    def calibrate(self, rect: RectI) -> dict[str, Any]:
        with self._lock:
            self._stop_counting_for_setup_locked()
            if self.latest_color is None:
                raise ValueError("No camera frame is available yet.")
            self.calibration_rect = rect
            calibration = self.vision.calibrate(self.latest_color, self.latest_depth, rect)
            self.tracker.reset()
            return self._calibration_dict(calibration)

    def clear_setup(self) -> None:
        with self._lock:
            self.counting = False
            self.roi = None
            self.gate_box = None
            self.crossing_line = None
            self.calibration_rect = None
            self.vision.clear_calibration()
            self.tracker.reset()
            self.counter.reset()
            self.flash_events.clear()
            self.recent_events.clear()
        # clear_setup also resets the existing counter, so mirror that value to PLC.
        self.plc.submit_count_update(0)

    # Counting ---------------------------------------------------------------

    def start_counting(self) -> None:
        with self._lock:
            missing: list[str] = []
            if self.roi is None:
                missing.append("ROI")
            if self.gate_box is None:
                missing.append("count box")
            if self.crossing_line is None:
                missing.append("crossing line")
            if self.vision.calibration is None:
                missing.append("piece calibration")
            if missing:
                raise ValueError("Setup incomplete. Define: " + ", ".join(missing))
            self.tracker.reset()
            self.counting = True

    def stop_counting(self) -> None:
        with self._lock:
            self.counting = False
            self.tracker.reset()

    def reset_count(self) -> None:
        with self._lock:
            self.counter.reset()
            self.tracker.reset()
            self.flash_events.clear()
            self.recent_events.clear()
        # Keep PLC current_count/speed state synchronized without blocking the API.
        self.plc.submit_count_update(0)

    # Config -----------------------------------------------------------------

    def update_config(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.config.update_from_dict(data)
            return self.config.frontend_dict()

    # Frame processing -------------------------------------------------------

    def _on_frame(self, color_bgr: np.ndarray, depth_mm: Optional[np.ndarray]) -> None:
        with self._frame_condition:
            self.latest_color = color_bgr
            self.latest_depth = depth_mm
            display = color_bgr.copy()
            detections: list[Detection] = []
            mask = np.zeros(color_bgr.shape[:2], dtype=np.uint8)

            if self.roi is not None and self.vision.calibration is not None:
                cfg = self.config
                detections, mask = self.vision.detect(
                    color_bgr,
                    depth_mm,
                    self.roi,
                    area_tolerance=cfg.area_tolerance,
                    threshold_fraction=cfg.threshold_fraction,
                    use_depth=cfg.use_depth,
                    depth_extra_mm=cfg.depth_extra_mm,
                    max_merged_units=cfg.max_merged_units,
                )

            self.last_detections = detections
            self.last_mask = mask

            if self.counting and self.crossing_line is not None and self.gate_box is not None:
                cfg = self.config
                tracks = self.tracker.update(
                    detections,
                    max_distance=cfg.match_distance,
                    max_missed=cfg.max_missed,
                )
                events = self.counter.update(
                    tracks,
                    self.crossing_line,
                    self.gate_box,
                    min_hits=cfg.min_hits,
                    hysteresis_px=cfg.hysteresis_px,
                )
                now_mono = time.monotonic()
                now_unix = time.time()
                for event in events:
                    self.flash_events.append((now_mono, event))
                    self.recent_events.appendleft(
                        {
                            "timestamp": now_unix,
                            "units": event.units,
                            "direction": event.direction,
                            "point": [event.point[0], event.point[1]],
                            "track_id": event.track_id,
                        }
                    )
                if events:
                    # Non-blocking handoff: PLC I/O runs in PLCService's worker thread,
                    # so RealSense capture/vision/tracking timing is not disturbed.
                    self.plc.submit_count_update(self.counter.total)
                self.last_tracks = list(tracks)
            else:
                self.last_tracks = []

            self._draw_overlay(display, detections)
            ok, encoded = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                self.latest_jpeg = encoded.tobytes()

            ok_mask, encoded_mask = cv2.imencode(".jpg", self.last_mask)
            if ok_mask:
                self.latest_mask_jpeg = encoded_mask.tobytes()

            self.frame_version += 1
            self._frame_condition.notify_all()

    def _draw_overlay(self, frame: np.ndarray, detections: list[Detection]) -> None:
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

        if self.config.show_detections:
            for detection in detections:
                outline_color = (70, 230, 70) if detection.units == 1 else (0, 165, 255)
                cv2.drawContours(frame, [detection.contour], -1, outline_color, 2)
                bx, by, _bw, _bh = detection.bbox
                label = "roll" if detection.units == 1 else f"{detection.units} rolls"
                cv2.putText(frame, label, (bx, max(18, by - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, outline_color, 2)

        if self.config.show_ids:
            for track in self.last_tracks:
                if not track.matched:
                    continue
                cx, cy = map(int, track.centroid)
                cv2.putText(frame, f"ID {track.track_id}", (cx + 8, cy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        now = time.monotonic()
        while self.flash_events and now - self.flash_events[0][0] > 0.8:
            self.flash_events.popleft()
        for event_time, event in self.flash_events:
            age = now - event_time
            radius = int(18 + age * 30)
            point = tuple(map(int, event.point))
            cv2.circle(frame, point, radius, (0, 255, 255), 3)
            cv2.putText(frame, f"+{event.units}", (point[0] + 12, point[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 3)

        cv2.rectangle(frame, (8, 8), (235, 58), (20, 20, 20), -1)
        cv2.putText(frame, f"COUNT: {self.counter.total}", (18, 43), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        if self.config.show_mask and self.last_mask is not None:
            mask_bgr = cv2.cvtColor(self.last_mask, cv2.COLOR_GRAY2BGR)
            inset_w = min(240, frame.shape[1] // 3)
            inset_h = int(inset_w * frame.shape[0] / frame.shape[1])
            inset = cv2.resize(mask_bgr, (inset_w, inset_h), interpolation=cv2.INTER_NEAREST)
            x1 = frame.shape[1] - inset_w - 10
            y1 = 10
            frame[y1 : y1 + inset_h, x1 : x1 + inset_w] = inset
            cv2.rectangle(frame, (x1, y1), (x1 + inset_w, y1 + inset_h), (255, 255, 255), 1)

    # Stream/status ----------------------------------------------------------

    def wait_for_jpeg(self, after_version: int, timeout: float = 1.0) -> tuple[int, Optional[bytes]]:
        with self._frame_condition:
            self._frame_condition.wait_for(
                lambda: self.frame_version != after_version or self.camera_error is not None,
                timeout=timeout,
            )
            return self.frame_version, self.latest_jpeg

    def mjpeg_stream(self) -> Iterator[bytes]:
        seen_version = -1
        while True:
            version, jpeg = self.wait_for_jpeg(seen_version, timeout=2.0)
            seen_version = version
            if jpeg is None:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"

    def snapshot_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self.latest_jpeg

    def mask_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self.latest_mask_jpeg

    def status(self) -> dict[str, Any]:
        with self._lock:
            frame_size = None
            if self.latest_color is not None:
                h, w = self.latest_color.shape[:2]
                frame_size = {"width": w, "height": h}

            calibration = self.vision.calibration
            camera_alive = self.camera is not None and self.camera.is_alive()
            camera_connected = camera_alive and self.camera_status == "RealSense connected"
            camera_device = self.camera.device_info if self.camera is not None else None

            roi = _rect_dict(self.roi)
            gate_box = _rect_dict(self.gate_box)
            crossing_line = _line_dict(self.crossing_line)
            calibration_rect = _rect_dict(self.calibration_rect)
            config = self.config.frontend_dict()

            # Flat aliases match the React roll.js / ConveyorCounter.jsx contract.
            result = {
                "camera_connected": camera_connected,
                "camera_status": self.camera_status,
                "camera_error": self.camera_error,
                "camera_device": camera_device,
                "frame_size": frame_size,
                "websocket_clients": self.websocket_clients,
                "counting": self.counting,
                "total": self.counter.total,
                "negative_to_positive": self.counter.negative_to_positive,
                "positive_to_negative": self.counter.positive_to_negative,
                "roi": roi,
                "gate_box": gate_box,
                "crossing_line": crossing_line,
                "calibration_rect": calibration_rect,
                "calibrated": calibration is not None,
                "calibration": self._calibration_dict(calibration) if calibration else None,
                "diagnostics": {
                    "detections": len(self.last_detections),
                    "tracks": len(self.last_tracks),
                },
                "config": config,
                "recent_events": list(self.recent_events)[:20],
                "plc": self.plc.status(),
            }

            # Nested fields are kept for compatibility with the previous Django API.
            result["camera"] = {
                "status": self.camera_status,
                "connected": camera_connected,
                "error": self.camera_error,
                "device": camera_device,
                "frame_size": frame_size,
            }
            result["setup"] = {
                "roi": roi,
                "gate_box": gate_box,
                "crossing_line": crossing_line,
                "calibration_rect": calibration_rect,
                "calibrated": calibration is not None,
                "calibration": result["calibration"],
            }
            result["count"] = {
                "total": self.counter.total,
                "a_to_b": self.counter.negative_to_positive,
                "b_to_a": self.counter.positive_to_negative,
            }
            return result

    @staticmethod
    def _calibration_dict(calibration: Any) -> dict[str, Any]:
        return {
            "area_px": calibration.area_px,
            "separation": calibration.separation,
            "depth_low_mm": calibration.depth_low_mm,
            "depth_high_mm": calibration.depth_high_mm,
            "selection": _rect_dict(calibration.selection),
        }


_runtime = CounterRuntime()
atexit.register(_runtime.shutdown)


def get_runtime() -> CounterRuntime:
    return _runtime
