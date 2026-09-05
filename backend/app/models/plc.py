from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_REGISTER_RE = re.compile(r"^D(\d+)$", re.IGNORECASE)


class PLCConnectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    protocol: Literal["modbus_tcp"] = "modbus_tcp"
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    slave_id: int = Field(ge=0, le=247)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("PLC host cannot be empty")
        return value


class PLCAddresses(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    stop: str
    speed: str
    current_count: str
    target_count: str

    @field_validator("start", "stop", "speed", "current_count", "target_count")
    @classmethod
    def validate_register(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _REGISTER_RE.fullmatch(normalized):
            raise ValueError("Address must use D-register format, for example D7 or D20")
        register = int(normalized[1:])
        if not 0 <= register <= 65535:
            raise ValueError("D-register number must be between 0 and 65535")
        return normalized


class SlowdownRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0, le=65535)
    speed: int = Field(ge=0, le=65535)


class SpeedControlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_speed: int = Field(ge=0, le=65535)
    target_count: int = Field(ge=1, le=65535)
    slowdown_rules: list[SlowdownRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rules(self) -> "SpeedControlConfig":
        seen: set[int] = set()
        for rule in self.slowdown_rules:
            if rule.count in seen:
                raise ValueError(f"Duplicate slowdown rule count: {rule.count}")
            seen.add(rule.count)
        self.slowdown_rules.sort(key=lambda item: item.count)
        return self


class PLCConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plc: PLCConnectionConfig
    addresses: PLCAddresses
    speed_control: SpeedControlConfig


class PLCConnectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: Optional[bool] = None
    protocol: Optional[Literal["modbus_tcp"]] = None
    host: Optional[str] = Field(default=None, min_length=1, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    slave_id: Optional[int] = Field(default=None, ge=0, le=247)

    @field_validator("host")
    @classmethod
    def normalize_host(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("PLC host cannot be empty")
        return value


class PLCAddressesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: Optional[str] = None
    stop: Optional[str] = None
    speed: Optional[str] = None
    current_count: Optional[str] = None
    target_count: Optional[str] = None

    @field_validator("start", "stop", "speed", "current_count", "target_count")
    @classmethod
    def validate_register(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not _REGISTER_RE.fullmatch(normalized):
            raise ValueError("Address must use D-register format, for example D7 or D20")
        register = int(normalized[1:])
        if not 0 <= register <= 65535:
            raise ValueError("D-register number must be between 0 and 65535")
        return normalized


class SpeedControlPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_speed: Optional[int] = Field(default=None, ge=0, le=65535)
    target_count: Optional[int] = Field(default=None, ge=1, le=65535)
    slowdown_rules: Optional[list[SlowdownRule]] = None


class PLCConfigUpdate(BaseModel):
    """Partial PUT payload. Only supplied fields are merged into the persisted config."""

    model_config = ConfigDict(extra="forbid")

    plc: Optional[PLCConnectionPatch] = None
    addresses: Optional[PLCAddressesPatch] = None
    speed_control: Optional[SpeedControlPatch] = None


class PLCSpeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed: int = Field(ge=0, le=65535)
