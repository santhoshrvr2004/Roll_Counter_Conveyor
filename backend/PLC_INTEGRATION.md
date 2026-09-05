# PLC Integration

This PLC addition is isolated from the existing RealSense camera, calibration, detection, tracking, and gate-counting algorithms.
The only counting integration point is a non-blocking handoff after the existing `GateCounter` produces a count event.

## Files added

```text
app/
  api/
    plc.py
  config/
    __init__.py
    plc_config.json
    plc_config.default.json
  models/
    __init__.py
    plc.py
  services/
    plc_config_service.py
    plc_service.py
tests/
  test_plc.py
PLC_INTEGRATION.md
```

## Files modified

- `app/main.py` - includes the new PLC router.
- `app/services/runtime.py` - submits a changed roll count to `PLCService` and exposes PLC status. Camera/vision/tracking/counting algorithms are unchanged.
- `requirements.txt` - adds `pymodbus`.
- `README.md` - documents the PLC endpoints.

## Configuration

Active configuration: `app/config/plc_config.json`

Fallback template: `app/config/plc_config.default.json`

The active JSON is validated with Pydantic. Updates are written atomically using a temporary file and `os.replace()`. If the active JSON is missing or invalid, it is backed up when possible, the default JSON is validated, and the default is copied to the active location.

You can override the active configuration location with:

```text
PLC_CONFIG_PATH=C:\path\to\plc_config.json
```

No PLC host, port, D-register address, default speed, target count, or slowdown rule is stored as a runtime Python constant. These values come from JSON.

### D-register mapping

For `modbus_tcp`, this implementation maps `D<number>` directly to a Modbus holding-register address:

- `D7` -> holding register address `7`
- `D13` -> holding register address `13`
- `D20` -> holding register address `20`

If your PLC gateway uses a different Modbus offset/mapping, put the mapped D-register numbers required by that PLC in the JSON configuration.

## Automatic speed logic

`PLCService.calculate_required_speed()` reads the active configuration and applies the configured rules in ascending `count` order.

With the supplied JSON:

```text
0..489  -> 30
490..494 -> 20
495..496 -> 15
497..498 -> 10
499      -> 5
500+     -> 0 + STOP
```

At each real count change, the PLC worker writes:

1. Current counter value to `addresses.current_count`.
2. Configured target value to `addresses.target_count`.
3. Required speed to `addresses.speed` when the required speed changes.
4. `1` to `addresses.stop` once the target is reached.

PLC communication runs in a dedicated worker thread so a slow PLC/network request does not block the RealSense frame-processing thread.

## API endpoints

### GET `/api/plc/config`

Response:

```json
{
  "success": true,
  "message": "PLC configuration loaded",
  "data": {
    "plc": {
      "enabled": true,
      "protocol": "modbus_tcp",
      "host": "192.168.1.100",
      "port": 502,
      "slave_id": 1
    },
    "addresses": {
      "start": "D7",
      "stop": "D8",
      "speed": "D13",
      "current_count": "D20",
      "target_count": "D21"
    },
    "speed_control": {
      "default_speed": 30,
      "target_count": 500,
      "slowdown_rules": [
        {"count": 490, "speed": 20},
        {"count": 495, "speed": 15},
        {"count": 497, "speed": 10},
        {"count": 499, "speed": 5},
        {"count": 500, "speed": 0}
      ]
    }
  }
}
```

### PUT `/api/plc/config`

The PUT accepts a safe partial update. Unspecified fields are preserved.

Request:

```json
{
  "plc": {
    "host": "192.168.1.110",
    "port": 502
  },
  "speed_control": {
    "target_count": 600,
    "slowdown_rules": [
      {"count": 590, "speed": 20},
      {"count": 595, "speed": 10},
      {"count": 600, "speed": 0}
    ]
  }
}
```

Response:

```json
{
  "success": true,
  "message": "PLC configuration updated",
  "data": {"...": "full persisted configuration"}
}
```

Changing protocol/host/port/slave ID while connected deliberately disconnects the old PLC connection. Call `/api/plc/connect` again after changing connection settings.

### POST `/api/plc/connect`

Request body: none.

Response:

```json
{
  "success": true,
  "message": "PLC connected",
  "data": {
    "enabled": true,
    "connected": true,
    "protocol": "modbus_tcp",
    "host": "192.168.1.100",
    "port": 502,
    "slave_id": 1,
    "current_speed": 30,
    "last_count": 0,
    "target_count": 500,
    "last_action": "auto-speed:30",
    "last_error": null
  }
}
```

On connect, the backend synchronizes the current RealSense counter, target count, and appropriate speed to the PLC. It does not send the START command automatically.

### POST `/api/plc/disconnect`

Request body: none.

```json
{
  "success": true,
  "message": "PLC disconnected",
  "data": {"connected": false}
}
```

### POST `/api/plc/start`

Request body: none.

Writes `1` to the configured `addresses.start` D-register.

```json
{
  "success": true,
  "message": "PLC start command sent",
  "data": {"connected": true, "last_action": "start"}
}
```

### POST `/api/plc/stop`

Request body: none.

Writes speed `0` to the configured speed register, then writes `1` to the configured stop register.

```json
{
  "success": true,
  "message": "PLC stop command sent",
  "data": {"connected": true, "current_speed": 0, "last_action": "stop"}
}
```

### POST `/api/plc/speed`

Request:

```json
{
  "speed": 30
}
```

Response:

```json
{
  "success": true,
  "message": "PLC speed set to 30",
  "data": {"connected": true, "current_speed": 30, "last_action": "speed:30"}
}
```

## Existing status endpoint

`GET /api/status/` is unchanged for its existing fields and now also contains a new `plc` object. This lets the existing WebSocket JSON status messages expose PLC state without changing the camera frame protocol.

## Safety / runtime behavior

- PLC failure does not stop camera capture, detection, tracking, or counter updates.
- Automatic PLC updates are skipped when PLC is disabled or disconnected.
- Manual PLC commands return an error when there is no PLC connection.
- PLC settings are re-read from JSON during automatic count application, so saved speed-rule changes are not hardcoded in the runtime.
- Target STOP is sent once per target-reaching cycle, instead of repeatedly on every frame.
