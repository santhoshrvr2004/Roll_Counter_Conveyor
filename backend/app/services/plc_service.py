from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Optional

from ..models.plc import PLCConfig
from .plc_config_service import PLCConfigService, get_plc_config_service

logger = logging.getLogger(__name__)


class PLCServiceError(RuntimeError):
    pass


ClientFactory = Callable[[str, int], Any]


class PLCService:
    """Modbus TCP PLC control without coupling PLC I/O to the vision algorithms.

    D-register values from JSON are mapped directly to Modbus holding-register
    numbers (for example D13 -> holding register address 13).
    """

    def __init__(
        self,
        config_service: PLCConfigService | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.config_service = config_service or get_plc_config_service()
        self._client_factory = client_factory
        self._lock = threading.RLock()
        self._client: Any = None
        self._connected = False
        self._config: PLCConfig = self.config_service.load()
        self._last_error: Optional[str] = None
        self._current_speed: Optional[int] = None
        self._last_count: Optional[int] = None
        self._last_action: str = "idle"
        self._target_stop_sent = False

        # Counting runs in the camera thread. PLC network I/O is therefore delegated
        # to one small worker so a slow PLC cannot stall RealSense frame processing.
        self._count_queue: queue.Queue[int] = queue.Queue(maxsize=1)
        self._shutdown = threading.Event()
        self._worker = threading.Thread(target=self._count_worker, name="PLCCountWorker", daemon=True)
        self._worker.start()

    # Lifecycle -------------------------------------------------------------

    def reload_config(self) -> PLCConfig:
        new_config = self.config_service.load()
        with self._lock:
            old_endpoint = (
                self._config.plc.protocol,
                self._config.plc.host,
                self._config.plc.port,
                self._config.plc.slave_id,
            )
            new_endpoint = (
                new_config.plc.protocol,
                new_config.plc.host,
                new_config.plc.port,
                new_config.plc.slave_id,
            )
            self._config = new_config
            self._target_stop_sent = False
            should_disconnect = self._connected and (old_endpoint != new_endpoint or not new_config.plc.enabled)

        if should_disconnect:
            logger.info("PLC connection settings changed; disconnecting existing PLC connection")
            self.disconnect()
        return new_config

    def connect(self) -> dict[str, Any]:
        config = self.reload_config()
        if not config.plc.enabled:
            raise PLCServiceError("PLC is disabled in plc_config.json")
        if config.plc.protocol != "modbus_tcp":
            raise PLCServiceError(f"Unsupported PLC protocol: {config.plc.protocol}")

        with self._lock:
            if self._connected and self._client is not None:
                return self.status()

            try:
                client = self._make_client(config.plc.host, config.plc.port)
                connected = bool(client.connect())
                if not connected:
                    try:
                        client.close()
                    except Exception:
                        pass
                    raise PLCServiceError(
                        f"Could not connect to PLC at {config.plc.host}:{config.plc.port}"
                    )
                self._client = client
                self._connected = True
                self._last_error = None
                self._last_action = "connected"
                logger.info("PLC connected to %s:%s", config.plc.host, config.plc.port)
                return self.status()
            except Exception as exc:
                self._client = None
                self._connected = False
                self._last_error = str(exc)
                logger.exception("PLC connection failed")
                if isinstance(exc, PLCServiceError):
                    raise
                raise PLCServiceError(str(exc)) from exc

    def disconnect(self) -> dict[str, Any]:
        with self._lock:
            client = self._client
            self._client = None
            self._connected = False
            self._last_action = "disconnected"
            self._current_speed = None
            self._target_stop_sent = False

        if client is not None:
            try:
                client.close()
            except Exception as exc:
                logger.warning("PLC close failed: %s", exc)
        return self.status()

    def shutdown(self) -> None:
        self._shutdown.set()
        try:
            self._count_queue.put_nowait(-1)
        except queue.Full:
            pass
        if self._worker.is_alive():
            self._worker.join(timeout=1.5)
        try:
            self.disconnect()
        except Exception:
            pass

    # Commands --------------------------------------------------------------

    def start(self) -> dict[str, Any]:
        with self._lock:
            self._write_named_register("start", 1)
            self._last_action = "start"
            self._last_error = None
            logger.info("PLC START command sent")
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            # Set speed to zero before asserting STOP. Both addresses come from JSON.
            self._write_named_register("speed", 0)
            self._current_speed = 0
            self._write_named_register("stop", 1)
            self._last_action = "stop"
            self._last_error = None
            logger.info("PLC STOP command sent")
            return self.status()

    def set_speed(self, speed: int) -> dict[str, Any]:
        speed = self._validate_register_value(speed, "speed")
        with self._lock:
            self._write_named_register("speed", speed)
            self._current_speed = speed
            self._last_action = f"speed:{speed}"
            self._last_error = None
            logger.info("PLC speed set to %s", speed)
            return self.status()

    # Automatic count/speed integration ------------------------------------

    def submit_count_update(self, count: int) -> None:
        """Queue the newest count without blocking RealSense/vision processing."""
        count = int(count)
        if count < 0:
            return
        while True:
            try:
                self._count_queue.put_nowait(count)
                return
            except queue.Full:
                try:
                    self._count_queue.get_nowait()
                except queue.Empty:
                    return

    def apply_count(self, count: int, *, force_speed: bool = False) -> dict[str, Any]:
        """Synchronize count/target registers and apply JSON-driven speed rules."""
        count = self._validate_register_value(count, "current count")
        with self._lock:
            self._config = self.config_service.load()
            config = self._config
            self._last_count = count

            if not config.plc.enabled:
                self._last_action = "auto-skipped-disabled"
                return self.status()
            if not self._connected or self._client is None:
                self._last_action = "auto-skipped-disconnected"
                return self.status()

            target = config.speed_control.target_count
            self._write_named_register("current_count", count)
            self._write_named_register("target_count", target)

            required_speed = self.calculate_required_speed(count, config)
            if force_speed or self._current_speed != required_speed:
                self._write_named_register("speed", required_speed)
                self._current_speed = required_speed
                logger.info("Auto speed update: count=%s speed=%s", count, required_speed)

            if count >= target:
                if not self._target_stop_sent:
                    self._write_named_register("stop", 1)
                    self._target_stop_sent = True
                    logger.info("Target count %s reached; STOP command sent", target)
                self._last_action = "target-stop"
            else:
                self._target_stop_sent = False
                self._last_action = f"auto-speed:{required_speed}"

            self._last_error = None
            return self.status()

    @staticmethod
    def calculate_required_speed(count: int, config: PLCConfig) -> int:
        target = config.speed_control.target_count
        if count >= target:
            return 0

        speed = config.speed_control.default_speed
        for rule in sorted(config.speed_control.slowdown_rules, key=lambda item: item.count):
            if count >= rule.count:
                speed = rule.speed
            else:
                break
        return speed

    # State -----------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            config = self._config
            return {
                "enabled": config.plc.enabled,
                "connected": self._connected,
                "protocol": config.plc.protocol,
                "host": config.plc.host,
                "port": config.plc.port,
                "slave_id": config.plc.slave_id,
                "current_speed": self._current_speed,
                "last_count": self._last_count,
                "target_count": config.speed_control.target_count,
                "last_action": self._last_action,
                "last_error": self._last_error,
            }

    # Internal --------------------------------------------------------------

    def _count_worker(self) -> None:
        while not self._shutdown.is_set():
            try:
                count = self._count_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._shutdown.is_set():
                break
            try:
                self.apply_count(count)
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
                    self._last_action = "auto-error"
                logger.exception("Automatic PLC count/speed update failed")

    def _make_client(self, host: str, port: int) -> Any:
        if self._client_factory is not None:
            return self._client_factory(host, port)
        try:
            from pymodbus.client import ModbusTcpClient
        except Exception as exc:
            raise PLCServiceError(
                "pymodbus is not installed. Run: pip install -r requirements.txt"
            ) from exc
        return ModbusTcpClient(host=host, port=port, timeout=3.0)

    def _write_named_register(self, name: str, value: int) -> None:
        self._require_connected()
        address_text = getattr(self._config.addresses, name)
        address = self._register_number(address_text)
        value = self._validate_register_value(value, name)
        result = self._write_register(address, value)
        if hasattr(result, "isError") and result.isError():
            raise PLCServiceError(f"PLC write failed for {name} ({address_text}): {result}")

    def _write_register(self, address: int, value: int) -> Any:
        assert self._client is not None
        slave_id = self._config.plc.slave_id
        method = self._client.write_register

        # pymodbus changed the unit keyword across releases. Try the supported
        # variants without pinning the backend to one minor release.
        last_type_error: Optional[TypeError] = None
        for unit_kw in ("device_id", "slave", "unit"):
            try:
                return method(address=address, value=value, **{unit_kw: slave_id})
            except TypeError as exc:
                last_type_error = exc
        if last_type_error is not None:
            raise last_type_error
        raise PLCServiceError("Unable to write Modbus register")

    def _require_connected(self) -> None:
        if not self._connected or self._client is None:
            raise PLCServiceError("PLC is not connected")

    @staticmethod
    def _register_number(address: str) -> int:
        normalized = address.strip().upper()
        if not normalized.startswith("D") or not normalized[1:].isdigit():
            raise PLCServiceError(f"Unsupported PLC register address: {address}")
        number = int(normalized[1:])
        if not 0 <= number <= 65535:
            raise PLCServiceError(f"PLC register out of range: {address}")
        return number

    @staticmethod
    def _validate_register_value(value: int, name: str) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise PLCServiceError(f"{name} must be an integer") from exc
        if not 0 <= number <= 65535:
            raise PLCServiceError(f"{name} must be between 0 and 65535")
        return number


_plc_service = PLCService()


def get_plc_service() -> PLCService:
    return _plc_service
