"""LabelExtraction Pydantic models — SPEC §4.

Used as both:
  - The OpenAI structured-output schema (single multimodal call).
  - The deserialized type that downstream comparators consume.

The eight required `field_confidence` keys are enforced by Pydantic itself —
a missing key raises ValidationError at parse time, which the API layer
maps to NEEDS_REVIEW per SPEC §4.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FieldConfidence(BaseModel):
    """Per-field self-reported model confidence. SPEC §4 — all keys required."""

    model_config = ConfigDict(extra="forbid")

    brand_name: float = Field(ge=0.0, le=1.0)
    class_type: float = Field(ge=0.0, le=1.0)
    abv_percent: float = Field(ge=0.0, le=1.0)
    net_contents: float = Field(ge=0.0, le=1.0)
    warning_text: float = Field(ge=0.0, le=1.0)
    warning_prefix_all_caps: float = Field(ge=0.0, le=1.0)
    warning_prefix_bold: float = Field(ge=0.0, le=1.0)
    image_quality: float = Field(ge=0.0, le=1.0)


class LabelExtraction(BaseModel):
    """Vision-model output. SPEC §4."""

    model_config = ConfigDict(extra="forbid")

    brand_name: str
    class_type: str
    abv_percent: float | None
    net_contents: str
    warning_text: str
    warning_prefix_all_caps: bool
    warning_prefix_bold: bool
    image_quality: Literal["good", "poor"]
    field_confidence: FieldConfidence
