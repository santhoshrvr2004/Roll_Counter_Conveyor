# FastAPI Conveyor Roll Counter — Intel RealSense

This project is the FastAPI replacement for the uploaded Django/Channels backend.
The OpenCV calibration, detection, area-aware tracking, gate counting, and RealSense depth alignment are preserved.

## Architecture

```text
React (roll.js)
   |
   | REST
   +---- GET/PATCH/POST http://localhost:8000/api/...
   |
   | WebSocket (camera connection + live JPEG frames)
   +---- ws://localhost:8000/ws/camera/
                    |
                    v
             FastAPI + Uvicorn
                    |
                    v
             CounterRuntime
              /          \
     pyrealsense2       OpenCV
          |                |
     RealSense RGB+Depth   vision/tracking/count
```

## Important camera behavior

Opening `ws://localhost:8000/ws/camera/` automatically starts the selected RealSense camera.
The server sends processed camera frames as **binary JPEG WebSocket messages** and sends JSON status messages approximately once per second.
When the last camera WebSocket disconnects, the RealSense pipeline is stopped and released.

The REST camera connect/disconnect endpoints are also retained for compatibility.

## Install

Recommended: use the same machine where the Intel RealSense camera is physically connected.

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-realsense.txt
python run.py
```

### Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-realsense.txt
python run.py
```

Server:

```text
http://localhost:8000
```

Swagger/OpenAPI:

```text
http://localhost:8000/docs
```

Camera WebSocket:

```text
ws://localhost:8000/ws/camera/
```

Use **one Uvicorn worker** because one process owns the physical RealSense camera and all in-memory counting/calibration state.

## REST API

| Method | URL | Purpose |
|---|---|---|
| GET | `/api/status/` | Full live state + frontend-friendly flat fields |
| GET | `/api/camera/devices/` | List connected RealSense devices |
| POST | `/api/camera/connect/` | Connect RealSense (optional `{ "serial": "..." }`) |
| POST | `/api/camera/disconnect/` | Disconnect RealSense |
| POST | `/api/setup/roi/` | Set ROI |
| POST | `/api/setup/gate-box/` | Set count gate box |
| POST | `/api/setup/crossing-line/` | Set crossing line |
| POST | `/api/setup/clear/` | Clear geometry/calibration/count |
| POST | `/api/calibration/` | Calibrate one isolated piece |
| POST | `/api/counting/start/` | Start counting |
| POST | `/api/counting/stop/` | Stop counting |
| POST | `/api/counting/reset/` | Reset counts |
| GET | `/api/config/` | Read UI-friendly configuration |
| PATCH | `/api/config/` | Update configuration |
| GET | `/api/stream/` | Optional MJPEG compatibility stream |
| GET | `/api/snapshot.jpg` | Latest processed frame |
| GET | `/api/mask.jpg` | Latest binary detection mask |

## Payloads

ROI / gate box / calibration:

```json
{
  "x": 40,
  "y": 60,
  "width": 500,
  "height": 320
}
```

Crossing line:

```json
{
  "x1": 300,
  "y1": 100,
  "x2": 300,
  "y2": 380
}
```

Configuration example. Percent settings use the same values as the React sliders:

```json
{
  "area_tolerance": 40,
  "threshold_fraction": 45,
  "use_depth": true,
  "depth_extra_mm": 100,
  "max_merged_units": 3,
  "match_distance": 90,
  "max_missed": 12,
  "min_hits": 3,
  "hysteresis_px": 8
}
```

## React `roll.js`

Your WebSocket URL remains:

```js
const CAMERA_WS_URL = "ws://localhost:8000/ws/camera/";
```

The FastAPI server sends frames as binary JPEG data. Your existing `roll.js` already handles `ArrayBuffer`/`Blob`, so no base64 conversion is required on the backend.

## Run tests

Install pytest if needed:

```bash
pip install pytest httpx
pytest -q
```

Hardware-dependent RealSense opening is intentionally not performed by the unit tests.
