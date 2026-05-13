"""HTTP API request / response Pydantic models — SPEC §3.1.

The error envelope (`ErrorResponse`) is the stable machine shape; SPEC §3.1
forbids introducing new `error.code` values without a SPEC version bump.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Verdict(StrEnum):
    """SPEC §1 — three-state verdict, never PASS/FAIL only."""

    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ErrorCode(StrEnum):
    """Stable error vocabulary. SPEC §3.1 — change requires SPEC bump."""

    INVALID_IMAGE_TYPE = "INVALID_IMAGE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


class VerifyRequest(BaseModel):
    """`payload` part of the multipart upload. SPEC §3.1."""

    model_config = ConfigDict(extra="forbid")

    brand: str
    class_type: str
    abv_percent: float
    net_contents: str
    request_id: str | None = None


class FieldResult(BaseModel):
    name: str
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    detail: str | None = None


class LatencyMs(BaseModel):
    vision: int = Field(ge=0)
    compare: int = Field(ge=0)
    total: int = Field(ge=0)


class VerifyResponse(BaseModel):
    request_id: str
    overall_verdict: Verdict
    fields: list[FieldResult]
    latency_ms: LatencyMs


class ErrorEnvelope(BaseModel):
    code: ErrorCode
    message: str


class ErrorResponse(BaseModel):
    error: ErrorEnvelope
