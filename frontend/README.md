# RealSense Conveyor Counter — Frontend (CRA, plain React + CSS)

Redesigned dashboard for the FastAPI conveyor counter backend. The UI was rebuilt to match the reference design using **only React, JSX, and plain CSS** (Grid/Flexbox + CSS variables). No Tailwind, Bootstrap, Material UI, Ant Design, styled-components, CSS-in-JS, or TypeScript.

All functional logic from the previous frontend is preserved unchanged:

- REST API client (`src/api.js`) — status, devices, ROI, gate box, crossing line, calibration, clear setup, start/stop/reset counting, config PATCH
- Binary JPEG WebSocket stream from `/ws/camera/` with blob-URL frame handling
- Canvas drawing overlay for ROI / Count Box / Crossing Line / Calibrate, mapped to image coordinates
- Config edit-on-change + patch-on-blur behavior for all detection/tracking/display settings

## Layout

- Header (title, setup/counting chips, refresh, camera state)
- Three equal-width statistic cards spanning the full width: **B → A**, **Live detections**, **Active tracks** (the A → B card was removed from this row; it remains inside Production Count)
- Two-column workspace: large **Live Camera** panel (left) and a right column with **Production Count** (top, aligned with the camera panel), **Camera** + **Setup workflow** side by side, and **Settings** (Detection / Tracking / Display tabs) below

Responsive at 1920 / 1600 / 1440 / 1366 / 1280 / 1024 px; panels stack below ~1100 px.

## Backend expected

- REST: `http://127.0.0.1:8000`
- WebSocket: `ws://127.0.0.1:8000/ws/camera/`

To point at another backend, copy `.env.example` to `.env`:

```env
REACT_APP_API_BASE=http://127.0.0.1:8000
REACT_APP_WS_BASE=ws://127.0.0.1:8000
```

Endpoints used (unchanged from the original frontend):

| Action | Endpoint |
| --- | --- |
| Status | `GET /api/status/` |
| Device list | `GET /api/camera/devices/` |
| Disconnect camera | `POST /api/camera/disconnect/` |
| Set ROI | `POST /api/setup/roi/` |
| Set count box | `POST /api/setup/gate-box/` |
| Set crossing line | `POST /api/setup/crossing-line/` |
| Calibrate | `POST /api/calibration/` |
| Clear setup | `POST /api/setup/clear/` |
| Start / stop / reset | `POST /api/counting/start/`, `/stop/`, `/reset/` |
| Update config | `PATCH /api/config/` |
| Live frames | `WS /ws/camera/?serial=...` |

## Install and run

```bash
npm install
npm start
```

CRA serves the UI at `http://localhost:3000`.

Production build:

```bash
npm run build
```

## Preserved workflow

1. Connect RealSense
2. Draw ROI
3. Draw Count Box
4. Draw Crossing Line
5. Calibrate one isolated piece
6. Remove the calibration piece
7. Start Counting
