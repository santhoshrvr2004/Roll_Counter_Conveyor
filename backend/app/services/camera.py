from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Optional

import numpy as np

FrameCallback = Callable[[np.ndarray, Optional[np.ndarray]], None]
TextCallback = Callable[[str], None]


def _safe_device_info(device: Any, rs: Any, info_name: str) -> Optional[str]:
    info = getattr(rs.camera_info, info_name, None)
    if info is None:
        return None
    try:
        if hasattr(device, "supports") and not device.supports(info):
            return None
        return str(device.get_info(info))
    except Exception:
        return None


def list_realsense_devices() -> list[dict[str, Any]]:
    """Return connected RealSense devices without opening a stream."""
    try:
        import pyrealsense2 as rs  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "pyrealsense2 is not installed or could not be loaded. "
            "Install requirements-realsense.txt first."
        ) from exc

    context = rs.context()
    result: list[dict[str, Any]] = []

    for device in context.query_devices():
        name = _safe_device_info(device, rs, "name") or "Unknown RealSense"
        serial = _safe_device_info(device, rs, "serial_number") or ""
        product_line = _safe_device_info(device, rs, "product_line")
        firmware = _safe_device_info(device, rs, "firmware_version")
        usb_type = _safe_device_info(device, rs, "usb_type_descriptor")
        result.append(
            {
                "name": name,
                "serial": serial,
                "product_line": product_line,
                "firmware_version": firmware,
                "usb_type": usb_type,
                "is_d435i": "D435I" in name.upper().replace(" ", ""),
            }
        )

    return result


class RealSenseCamera(threading.Thread):
    """Background Intel RealSense color/depth reader."""

    def __init__(
        self,
        frame_callback: FrameCallback,
        status_callback: TextCallback,
        error_callback: TextCallback,
        *,
        serial: Optional[str] = None,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
    ) -> None:
        super().__init__(name="realsense-camera", daemon=True)
        self.frame_callback = frame_callback
        self.status_callback = status_callback
        self.error_callback = error_callback
        self.requested_serial = serial
        self.width = width
        self.height = height
        self.fps = fps
        self.device_info: Optional[dict[str, Any]] = None
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    def _select_device(self, rs: Any) -> tuple[Any, dict[str, Any]]:
        context = rs.context()
        devices = list(context.query_devices())
        if not devices:
            raise RuntimeError("No Intel RealSense camera was detected.")

        candidates: list[tuple[Any, dict[str, Any]]] = []
        for device in devices:
            name = _safe_device_info(device, rs, "name") or "Unknown RealSense"
            serial = _safe_device_info(device, rs, "serial_number") or ""
            info = {
                "name": name,
                "serial": serial,
                "product_line": _safe_device_info(device, rs, "product_line"),
                "firmware_version": _safe_device_info(device, rs, "firmware_version"),
                "usb_type": _safe_device_info(device, rs, "usb_type_descriptor"),
            }
            candidates.append((device, info))

        if self.requested_serial:
            for device, info in candidates:
                if info["serial"] == self.requested_serial:
                    return device, info
            raise RuntimeError(
                f"RealSense camera with serial {self.requested_serial!r} was not found."
            )

        return candidates[0]

    def run(self) -> None:
        try:
            import pyrealsense2 as rs  # type: ignore
        except Exception as exc:
            self.error_callback(
                "pyrealsense2 is not installed or could not be loaded. "
                f"Details: {exc}"
            )
            return

        pipeline = rs.pipeline()
        started = False

        try:
            self.status_callback("Searching for Intel RealSense camera...")
            _device, info = self._select_device(rs)
            self.device_info = info

            config = rs.config()
            if info.get("serial"):
                config.enable_device(info["serial"])
            config.enable_stream(
                rs.stream.color,
                self.width,
                self.height,
                rs.format.bgr8,
                self.fps,
            )
            config.enable_stream(
                rs.stream.depth,
                self.width,
                self.height,
                rs.format.z16,
                self.fps,
            )

            self.status_callback("Opening Intel RealSense camera...")
            profile = pipeline.start(config)
            started = True

            align_to_color = rs.align(rs.stream.color)
            depth_sensor = profile.get_device().first_depth_sensor()
            depth_scale_mm = float(depth_sensor.get_depth_scale()) * 1000.0

            self.status_callback("RealSense connected")

            while not self._stop_event.is_set():
                try:
                    frames = pipeline.wait_for_frames(timeout_ms=1000)
                except RuntimeError:
                    continue

                aligned = align_to_color.process(frames)
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

                self.frame_callback(color_bgr, depth_mm)

        except Exception as exc:
            self.error_callback(f"Could not open/read the RealSense camera. {exc}")
        finally:
            if started:
                try:
                    pipeline.stop()
                except Exception:
                    pass
            self.status_callback("Camera disconnected")
