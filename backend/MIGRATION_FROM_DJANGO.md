# Django → FastAPI conversion notes

The uploaded backend used Django, Django REST Framework, Django Channels, SQLite project scaffolding, and a Channels `CameraConsumer`.
This FastAPI build removes those framework-specific layers while retaining the actual conveyor algorithms.

## Replaced

- `django.urls` routes → FastAPI `APIRouter`
- DRF `@api_view` → FastAPI path operations
- `StreamingHttpResponse` → FastAPI `StreamingResponse`
- Django Channels `AsyncWebsocketConsumer` → native FastAPI `@app.websocket`
- Django ASGI setup → Uvicorn + FastAPI ASGI app
- Django CORS middleware → FastAPI `CORSMiddleware`
- Django request parsing → Pydantic request models

## Preserved

The following algorithm modules were carried over from the uploaded backend with the same core behavior:

- `geometry.py`
- `vision.py`
- `tracking.py`

`runtime.py` was cleaned up and kept as a single-process camera/count state owner.

## Important fixes made during conversion

1. Removed the duplicate unused `Runtime` class that existed at the bottom of the Django runtime file.
2. The old Django status shape was nested (`camera`, `setup`, `count`) while the React UI expects flat properties. FastAPI now exposes both forms.
3. The React sliders use `40` / `45` percentages, while the vision engine requires `0.40` / `0.45`. FastAPI converts these automatically.
4. The Django Channels consumer re-encoded raw frames to base64 for every message. FastAPI streams the already-processed runtime JPEG directly as binary WebSocket data.
5. Opening `/ws/camera/` now starts the RealSense D435i automatically, matching the frontend camera-connect flow.
6. When the last camera WebSocket closes, the RealSense pipeline is released.
7. D435i discovery is explicit; another RealSense model is not silently selected.

## Endpoint compatibility

The previous REST paths are intentionally retained so the existing `api/roll.js` method names can stay the same. The camera WebSocket remains:

```text
ws://localhost:8000/ws/camera/
```

An optional D435i serial can also be supplied:

```text
ws://localhost:8000/ws/camera/?serial=YOUR_SERIAL
```
