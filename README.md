# RealSense Conveyor Counter — FastAPI + React

This project is the web conversion of `main1.py`.

## Folder structure

```text
counter/
├─ backend/        FastAPI + OpenCV + pyrealsense2 + tracking/counting
├─ frontend/       React + Vite single-page UI
├─ setup_windows.bat
├─ run_backend.bat
├─ run_frontend.bat
└─ run_all.bat
```

The backend keeps the original calibrated-area workflow:

1. Connect RealSense camera (RGB + aligned depth)
2. Draw ROI
3. Draw Count Box
4. Draw Crossing Line
5. Keep one isolated roll visible and draw Calibrate Piece
6. Remove the calibration roll and Start Counting

The browser UI uses REST for commands/settings and WebSocket for the live processed camera stream.

## Windows quick start

### 1. Install prerequisites

- Python 3.10–3.12 recommended for Intel `pyrealsense2` compatibility
- Node.js 20+
- Intel RealSense SDK / camera driver if required by your device
- RealSense camera connected by USB 3.x

### 2. Install everything

Double-click:

```text
setup_windows.bat
```

Or manually:

```bat
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-realsense.txt

cd ..\frontend
npm install
```

### 3. Run backend + frontend

Double-click:

```text
run_all.bat
```

Then open:

```text
http://127.0.0.1:5173
```

FastAPI docs:

```text
http://127.0.0.1:8000/docs
```

## Backend endpoints used by React

- `GET /api/status/`
- `GET /api/camera/devices/`
- `POST /api/camera/connect/`
- `POST /api/camera/disconnect/`
- `POST /api/setup/roi/`
- `POST /api/setup/gate-box/`
- `POST /api/setup/crossing-line/`
- `POST /api/calibration/`
- `POST /api/setup/clear/`
- `POST /api/counting/start/`
- `POST /api/counting/stop/`
- `POST /api/counting/reset/`
- `GET /api/config/`
- `PATCH /api/config/`
- `GET /api/snapshot.jpg`
- `GET /api/mask.jpg`
- `GET /api/stream/` (MJPEG fallback)
- `WS /ws/camera/` (main React live stream)

The WebSocket sends:

- binary messages: JPEG camera frames with the backend overlays
- JSON messages: camera/count/setup/status updates about once per second

Optional serial selection:

```text
ws://127.0.0.1:8000/ws/camera/?serial=YOUR_CAMERA_SERIAL
```

## React environment

Default frontend connection is `127.0.0.1:8000`. To change it, copy `frontend/.env.example` to `frontend/.env` and edit:

```env
VITE_API_BASE=http://192.168.1.50:8000
VITE_WS_BASE=ws://192.168.1.50:8000
```

If opening React from another machine, also update backend `CORS_ORIGINS` or `.env` as needed.

## Important production notes

- Run only **one Uvicorn worker**. The backend owns one physical RealSense pipeline and in-memory calibration/tracking/count state.
- Calibration is intentionally in memory. Recalibrate after restarting the backend unless you add persistence.
- The backend camera defaults to 640×480 at 30 FPS, matching `main1.py`.
- The project accepts any RealSense device that can provide color `bgr8` + depth `z16`; serial selection is supported.
- `backend/reference_main1.py` is included for direct comparison with the original desktop source.

## Backend tests

```bat
cd backend
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

The unit tests do not open the physical RealSense camera.
