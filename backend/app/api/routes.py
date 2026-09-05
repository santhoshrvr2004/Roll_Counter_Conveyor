from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from .schemas import CameraConnectPayload, ConfigPatch, LinePayload, RectPayload
from ..services.runtime import get_runtime

router = APIRouter()


def ok(**extra):
    return {"ok": True, **extra}


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/")
def index():
    return {
        "name": "FastAPI Conveyor Roll Counter",
        "status": "/api/status/",
        "camera_websocket": "/ws/camera/",
        "docs": "/docs",
    }


@router.get("/api/status/")
def status_view():
    return ok(**get_runtime().status())


@router.get("/api/camera/devices/")
def camera_devices():
    try:
        return ok(devices=get_runtime().list_devices())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/camera/connect/")
def camera_connect(payload: CameraConnectPayload | None = None):
    try:
        serial = payload.serial if payload else None
        return ok(**get_runtime().connect_camera(serial=serial))
    except Exception as exc:
        raise bad_request(exc) from exc


@router.post("/api/camera/disconnect/")
def camera_disconnect():
    return ok(**get_runtime().disconnect_camera())


@router.post("/api/setup/roi/")
def setup_roi(payload: RectPayload):
    try:
        runtime = get_runtime()
        runtime.set_roi(payload.as_tuple())
        return ok(**runtime.status())
    except Exception as exc:
        raise bad_request(exc) from exc


@router.post("/api/setup/gate-box/")
def setup_gate_box(payload: RectPayload):
    try:
        runtime = get_runtime()
        runtime.set_gate_box(payload.as_tuple())
        return ok(**runtime.status())
    except Exception as exc:
        raise bad_request(exc) from exc


@router.post("/api/setup/crossing-line/")
def setup_crossing_line(payload: LinePayload):
    try:
        runtime = get_runtime()
        runtime.set_crossing_line(payload.as_tuple())
        return ok(**runtime.status())
    except Exception as exc:
        raise bad_request(exc) from exc


@router.post("/api/calibration/")
def calibrate(payload: RectPayload):
    try:
        runtime = get_runtime()
        calibration = runtime.calibrate(payload.as_tuple())
        return ok(calibration_result=calibration, **runtime.status())
    except Exception as exc:
        raise bad_request(exc) from exc


@router.post("/api/setup/clear/")
def setup_clear():
    runtime = get_runtime()
    runtime.clear_setup()
    return ok(**runtime.status())


@router.post("/api/counting/start/")
def counting_start():
    try:
        runtime = get_runtime()
        runtime.start_counting()
        return ok(**runtime.status())
    except Exception as exc:
        raise bad_request(exc) from exc


@router.post("/api/counting/stop/")
def counting_stop():
    runtime = get_runtime()
    runtime.stop_counting()
    return ok(**runtime.status())


@router.post("/api/counting/reset/")
def counting_reset():
    runtime = get_runtime()
    runtime.reset_count()
    return ok(**runtime.status())


@router.get("/api/config/")
def config_get():
    return ok(config=get_runtime().status()["config"], **get_runtime().status()["config"])


@router.patch("/api/config/")
def config_patch(payload: ConfigPatch):
    try:
        data = payload.model_dump(exclude_none=True)
        config = get_runtime().update_config(data)
        return ok(config=config, **config)
    except Exception as exc:
        raise bad_request(exc) from exc


@router.get("/api/stream/")
def stream_view():
    return StreamingResponse(
        get_runtime().mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/api/snapshot.jpg")
def snapshot_view():
    jpeg = get_runtime().snapshot_jpeg()
    if jpeg is None:
        raise HTTPException(status_code=503, detail="No camera frame is available")
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.get("/api/mask.jpg")
def mask_view():
    jpeg = get_runtime().mask_jpeg()
    if jpeg is None:
        raise HTTPException(status_code=503, detail="No detection mask is available")
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
