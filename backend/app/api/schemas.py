from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RectPayload(BaseModel):
    x: int
    y: int
    width: int = Field(ge=10)
    height: int = Field(ge=10)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height


class LinePayload(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

    def as_tuple(self) -> tuple[tuple[int, int], tuple[int, int]]:
        return (self.x1, self.y1), (self.x2, self.y2)


class CameraConnectPayload(BaseModel):
    serial: Optional[str] = None


class ConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_tolerance: Optional[float] = None
    threshold_fraction: Optional[float] = None
    use_depth: Optional[bool] = None
    depth_extra_mm: Optional[float] = None
    max_merged_units: Optional[int] = None
    match_distance: Optional[float] = None
    max_missed: Optional[int] = None
    min_hits: Optional[int] = None
    hysteresis_px: Optional[float] = None
    show_detections: Optional[bool] = None
    show_ids: Optional[bool] = None
    show_mask: Optional[bool] = None
