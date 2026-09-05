from fastapi.testclient import TestClient

from app.main import app
from app.services.runtime import get_runtime


client = TestClient(app)


def setup_function():
    runtime = get_runtime()
    runtime.stop_counting()
    runtime.clear_setup()
    runtime.camera_error = None
    runtime.camera_status = "Disconnected"


def test_status_contract_is_frontend_friendly():
    response = client.get("/api/status/")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "camera_connected" in data
    assert "total" in data
    assert "negative_to_positive" in data
    assert "positive_to_negative" in data
    assert "roi" in data
    assert "calibrated" in data


def test_set_roi():
    response = client.post(
        "/api/setup/roi/",
        json={"x": 10, "y": 20, "width": 200, "height": 100},
    )
    assert response.status_code == 200
    assert response.json()["roi"] == {"x": 10, "y": 20, "width": 200, "height": 100}


def test_set_line_rejects_too_short_line():
    response = client.post(
        "/api/setup/crossing-line/",
        json={"x1": 10, "y1": 10, "x2": 12, "y2": 12},
    )
    assert response.status_code == 400


def test_config_uses_ui_percent_values():
    response = client.patch(
        "/api/config/",
        json={"area_tolerance": 40, "threshold_fraction": 45},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["area_tolerance"] == 40
    assert data["threshold_fraction"] == 45
