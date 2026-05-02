"""Shared pytest fixtures for the whole project.

Phase A provides:
  * `fake_openai_client` — drop-in vision client double; tests configure
    `.extraction` (return value) or `.raises` (exception) before invocation.
    Required by SPEC §7.5 ("MUST use injectable fake client").
  * `make_extraction` — factory producing a valid LabelExtraction with
    sensible defaults; per-test overrides via kwargs.
  * `tiny_png` — smallest valid PNG byte buffer for upload tests.

Phase B agents may add more fixtures here (or in `tests/<area>/conftest.py`)
but MUST NOT remove or rename these — integration tests depend on them.
"""
from __future__ import annotations

import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.schemas.extraction import FieldConfidence, LabelExtraction


@dataclass
class FakeOpenAIClient:
    """Inject this in place of the real OpenAI vision client.

    Configure `extraction` to control what the call returns, or `raises` to
    simulate transport failure (FR-012 retry path).
    """

    extraction: LabelExtraction | None = None
    raises: Exception | None = None
    call_log: list[dict[str, Any]] = field(default_factory=list)

    async def extract(self, image_bytes: bytes, prompt_version: str) -> LabelExtraction:
        self.call_log.append(
            {"size": len(image_bytes), "prompt_version": prompt_version}
        )
        if self.raises is not None:
            raise self.raises
        if self.extraction is None:
            raise RuntimeError(
                "FakeOpenAIClient.extraction must be set before invocation. "
                "Tests should configure either `.extraction` or `.raises`."
            )
        return self.extraction


@pytest.fixture
def fake_openai_client() -> FakeOpenAIClient:
    return FakeOpenAIClient()


@pytest.fixture
def make_extraction() -> Callable[..., LabelExtraction]:
    """Factory for valid LabelExtraction objects with sensible defaults.

    Use kwargs to override any field. The default extraction matches the
    take-home doc's distilled-spirits example (OLD TOM DISTILLERY).
    """

    def _factory(**overrides: Any) -> LabelExtraction:
        # Match the TTB sample exactly so the canonical-warning happy path works.
        defaults: dict[str, Any] = {
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "abv_percent": 45.0,
            "net_contents": "750 mL",
            "warning_text": (
                "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
                "not drink alcoholic beverages during pregnancy because of the risk of "
                "birth defects. (2) Consumption of alcoholic beverages impairs your "
                "ability to drive a car or operate machinery, and may cause health problems."
            ),
            "warning_prefix_all_caps": True,
            "warning_prefix_bold": True,
            "image_quality": "good",
            "field_confidence": FieldConfidence(
                brand_name=0.95,
                class_type=0.92,
                abv_percent=0.99,
                net_contents=0.96,
                warning_text=0.98,
                warning_prefix_all_caps=0.99,
                warning_prefix_bold=0.97,
                image_quality=0.94,
            ),
        }
        defaults.update(overrides)
        return LabelExtraction(**defaults)

    return _factory


@pytest.fixture
def tiny_png() -> bytes:
    """Minimal valid 1x1 PNG. Used by upload-validation tests (FR-002)."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_chunk = b"IHDR" + ihdr
    ihdr_full = (
        struct.pack(">I", len(ihdr))
        + ihdr_chunk
        + struct.pack(">I", zlib.crc32(ihdr_chunk))
    )
    raw = b"\x00\xff\xff\xff"
    comp = zlib.compress(raw)
    idat_chunk = b"IDAT" + comp
    idat_full = (
        struct.pack(">I", len(comp))
        + idat_chunk
        + struct.pack(">I", zlib.crc32(idat_chunk))
    )
    iend_chunk = b"IEND"
    iend_full = (
        struct.pack(">I", 0) + iend_chunk + struct.pack(">I", zlib.crc32(iend_chunk))
    )
    return sig + ihdr_full + idat_full + iend_full
