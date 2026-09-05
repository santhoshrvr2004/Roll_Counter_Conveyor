from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..models.plc import PLCConfig, PLCConfigUpdate

logger = logging.getLogger(__name__)


class PLCConfigError(RuntimeError):
    pass


class PLCConfigService:
    """Thread-safe persistent PLC JSON configuration manager.

    PLC-specific values are intentionally stored in JSON files, not Python constants.
    If the active file is missing or invalid, the packaged default JSON is used and
    copied back to the active path.
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        default_path: Path | str | None = None,
    ) -> None:
        app_dir = Path(__file__).resolve().parents[1]
        env_path = os.getenv("PLC_CONFIG_PATH")
        self.config_path = Path(config_path or env_path or (app_dir / "config" / "plc_config.json"))
        self.default_path = Path(default_path or (app_dir / "config" / "plc_config.default.json"))
        self._lock = threading.RLock()

    def load(self) -> PLCConfig:
        with self._lock:
            try:
                return self._read_validated(self.config_path)
            except (FileNotFoundError, json.JSONDecodeError, ValidationError, OSError) as exc:
                logger.warning("PLC config %s could not be loaded: %s", self.config_path, exc)
                self._backup_invalid_file()

                try:
                    default = self._read_validated(self.default_path)
                except (FileNotFoundError, json.JSONDecodeError, ValidationError, OSError) as default_exc:
                    raise PLCConfigError(
                        f"PLC configuration is unavailable. Active config error: {exc}; "
                        f"default config error: {default_exc}"
                    ) from default_exc

                self.save(default)
                logger.info("PLC config restored from default file %s", self.default_path)
                return default

    def save(self, config: PLCConfig | dict[str, Any]) -> PLCConfig:
        with self._lock:
            validated = config if isinstance(config, PLCConfig) else PLCConfig.model_validate(config)
            temp_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                payload = validated.model_dump(mode="json")
                temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
                os.replace(temp_path, self.config_path)
            except OSError as exc:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise PLCConfigError(f"Could not save PLC configuration: {exc}") from exc
            return validated

    def update(self, patch: PLCConfigUpdate | dict[str, Any]) -> PLCConfig:
        with self._lock:
            current = self.load()
            if isinstance(patch, PLCConfigUpdate):
                updates = patch.model_dump(exclude_none=True, mode="json")
            else:
                updates = PLCConfigUpdate.model_validate(patch).model_dump(exclude_none=True, mode="json")

            merged = self._deep_merge(current.model_dump(mode="json"), updates)
            validated = PLCConfig.model_validate(merged)
            return self.save(validated)

    def as_dict(self) -> dict[str, Any]:
        return self.load().model_dump(mode="json")

    def _read_validated(self, path: Path) -> PLCConfig:
        raw = path.read_text(encoding="utf-8")
        return PLCConfig.model_validate(json.loads(raw))

    def _backup_invalid_file(self) -> None:
        if not self.config_path.exists() or not self.config_path.is_file():
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.config_path.with_name(f"{self.config_path.name}.invalid-{stamp}.bak")
        try:
            shutil.copy2(self.config_path, backup)
            logger.warning("Invalid PLC config backed up to %s", backup)
        except OSError as exc:
            logger.warning("Could not back up invalid PLC config: %s", exc)

    @staticmethod
    def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(base)
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = PLCConfigService._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result


_config_service = PLCConfigService()


def get_plc_config_service() -> PLCConfigService:
    return _config_service
