from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.plc import PLCConfigUpdate
from app.services.plc_config_service import PLCConfigService
from app.services.plc_service import PLCService


class FakeResponse:
    def isError(self):
        return False


class FakeModbusClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.connected = False
        self.writes: list[tuple[int, int, int]] = []

    def connect(self):
        self.connected = True
        return True

    def close(self):
        self.connected = False

    def write_register(self, *, address: int, value: int, device_id: int):
        self.writes.append((address, value, device_id))
        return FakeResponse()


def write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "plc": {
                    "enabled": True,
                    "protocol": "modbus_tcp",
                    "host": "127.0.0.1",
                    "port": 502,
                    "slave_id": 1,
                },
                "addresses": {
                    "start": "D7",
                    "stop": "D8",
                    "speed": "D13",
                    "current_count": "D20",
                    "target_count": "D21",
                },
                "speed_control": {
                    "default_speed": 30,
                    "target_count": 500,
                    "slowdown_rules": [
                        {"count": 490, "speed": 20},
                        {"count": 495, "speed": 15},
                        {"count": 497, "speed": 10},
                        {"count": 499, "speed": 5},
                        {"count": 500, "speed": 0},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def test_plc_config_partial_update_is_persisted(tmp_path: Path):
    active = tmp_path / "plc_config.json"
    default = tmp_path / "plc_config.default.json"
    write_config(active)
    write_config(default)
    service = PLCConfigService(active, default)

    updated = service.update(
        PLCConfigUpdate.model_validate(
            {"plc": {"host": "192.168.10.50"}, "speed_control": {"default_speed": 35}}
        )
    )

    assert updated.plc.host == "192.168.10.50"
    assert updated.plc.port == 502
    assert updated.speed_control.default_speed == 35
    assert service.load().plc.host == "192.168.10.50"


def test_invalid_active_plc_config_falls_back_to_default(tmp_path: Path):
    active = tmp_path / "plc_config.json"
    default = tmp_path / "plc_config.default.json"
    active.write_text("{not-valid-json", encoding="utf-8")
    write_config(default)

    service = PLCConfigService(active, default)
    loaded = service.load()

    assert loaded.plc.port == 502
    assert json.loads(active.read_text(encoding="utf-8"))["speed_control"]["target_count"] == 500


def test_automatic_speed_rules_and_target_stop_come_from_json(tmp_path: Path):
    active = tmp_path / "plc_config.json"
    default = tmp_path / "plc_config.default.json"
    write_config(active)
    write_config(default)
    config_service = PLCConfigService(active, default)
    holder: dict[str, FakeModbusClient] = {}

    def factory(host: str, port: int):
        client = FakeModbusClient(host, port)
        holder["client"] = client
        return client

    plc = PLCService(config_service=config_service, client_factory=factory)
    try:
        plc.connect()
        for count in (489, 490, 495, 497, 499, 500):
            plc.apply_count(count)

        client = holder["client"]
        speed_writes = [value for address, value, _slave in client.writes if address == 13]
        assert speed_writes == [30, 20, 15, 10, 5, 0]
        assert (8, 1, 1) in client.writes  # target reached -> STOP register
        assert (20, 500, 1) in client.writes  # current_count register
        assert (21, 500, 1) in client.writes  # target_count register
    finally:
        plc.shutdown()


def test_plc_config_get_endpoint_available():
    client = TestClient(app)
    response = client.get("/api/plc/config")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["addresses"]["speed"] == "D13"
