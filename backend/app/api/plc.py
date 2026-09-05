from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from ..models.plc import PLCConfigUpdate, PLCSpeedRequest
from ..services.plc_config_service import PLCConfigError, get_plc_config_service
from ..services.plc_service import PLCServiceError, get_plc_service
from ..services.runtime import get_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plc", tags=["PLC"])


def success(message: str, data: Any) -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def failure(exc: Exception, *, code: int = status.HTTP_400_BAD_REQUEST) -> JSONResponse:
    logger.warning("PLC API error: %s", exc)
    return JSONResponse(
        status_code=code,
        content={"success": False, "message": str(exc), "data": None},
    )


@router.get("/config")
def get_plc_config():
    try:
        data = get_plc_config_service().as_dict()
        return success("PLC configuration loaded", data)
    except PLCConfigError as exc:
        return failure(exc, code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.put("/config")
def update_plc_config(payload: PLCConfigUpdate):
    try:
        config_service = get_plc_config_service()
        updated = config_service.update(payload)
        plc_service = get_plc_service()
        plc_service.reload_config()

        # If the PLC remains connected, immediately enforce the new target/rules
        # against the current counter value. Connection changes intentionally cause
        # reload_config() to disconnect and require an explicit reconnect.
        plc_status = plc_service.status()
        if plc_status["connected"]:
            current_count = int(get_runtime().status()["total"])
            plc_service.apply_count(current_count, force_speed=True)

        return success("PLC configuration updated", updated.model_dump(mode="json"))
    except (PLCConfigError, ValueError, PLCServiceError) as exc:
        return failure(exc)


@router.post("/connect")
def connect_plc():
    try:
        plc = get_plc_service()
        plc.connect()
        current_count = int(get_runtime().status()["total"])
        data = plc.apply_count(current_count, force_speed=True)
        return success("PLC connected", data)
    except (PLCServiceError, PLCConfigError) as exc:
        return failure(exc, code=status.HTTP_503_SERVICE_UNAVAILABLE)


@router.post("/disconnect")
def disconnect_plc():
    try:
        data = get_plc_service().disconnect()
        return success("PLC disconnected", data)
    except Exception as exc:
        return failure(exc)


@router.post("/start")
def start_plc():
    try:
        data = get_plc_service().start()
        return success("PLC start command sent", data)
    except PLCServiceError as exc:
        return failure(exc, code=status.HTTP_503_SERVICE_UNAVAILABLE)


@router.post("/stop")
def stop_plc():
    try:
        data = get_plc_service().stop()
        return success("PLC stop command sent", data)
    except PLCServiceError as exc:
        return failure(exc, code=status.HTTP_503_SERVICE_UNAVAILABLE)


@router.post("/speed")
def set_plc_speed(payload: PLCSpeedRequest):
    try:
        data = get_plc_service().set_speed(payload.speed)
        return success(f"PLC speed set to {payload.speed}", data)
    except PLCServiceError as exc:
        return failure(exc, code=status.HTTP_503_SERVICE_UNAVAILABLE)
