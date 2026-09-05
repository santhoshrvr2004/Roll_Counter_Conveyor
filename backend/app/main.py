from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .api.routes import router
from .api.plc import router as plc_router
from .services.runtime import get_runtime

load_dotenv()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await asyncio.to_thread(get_runtime().shutdown)


app = FastAPI(
    title="Conveyor Roll Counter API",
    description="FastAPI backend for Intel RealSense conveyor roll counting.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    item.strip()
    for item in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if item.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(plc_router)


@app.websocket("/ws/camera/")
async def camera_websocket(websocket: WebSocket):
    """
    Open the selected RealSense camera when the React client connects and stream processed JPEG frames.

    - Frames are sent as binary JPEG messages.
    - A JSON status message is also sent about once per second.
    - Closing the final camera WebSocket releases the physical camera.
    """
    await websocket.accept()
    runtime = get_runtime()
    runtime.add_websocket_client()
    seen_version = -1
    last_status_send = 0.0
    error_sent = None

    try:
        serial = websocket.query_params.get("serial")
        await asyncio.to_thread(runtime.connect_camera, serial)
        await websocket.send_json({"type": "status", **runtime.status()})

        while True:
            version, jpeg = await asyncio.to_thread(
                runtime.wait_for_jpeg,
                seen_version,
                1.0,
            )

            if jpeg is not None and version != seen_version:
                await websocket.send_bytes(jpeg)
                seen_version = version

            now = time.monotonic()
            if now - last_status_send >= 1.0:
                current = runtime.status()
                await websocket.send_json({"type": "status", **current})
                last_status_send = now

                camera_error = current.get("camera_error")
                if camera_error and camera_error != error_sent:
                    await websocket.send_json(
                        {"type": "error", "error": camera_error, "message": camera_error}
                    )
                    error_sent = camera_error
                    await websocket.close(code=1011, reason="Camera connection failed")
                    break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json(
                {"type": "error", "error": str(exc), "message": str(exc)}
            )
        except Exception:
            pass
    finally:
        remaining = runtime.remove_websocket_client()
        if remaining == 0:
            await asyncio.to_thread(runtime.disconnect_camera)
