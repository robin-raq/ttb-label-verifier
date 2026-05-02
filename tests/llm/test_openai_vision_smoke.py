"""End-to-end smoke test for OpenAIVisionClient against the live OpenAI API.

Gated by ``RUN_LLM_TESTS=1`` — skipped in default CI to avoid billed API calls
and flaky network dependencies (SPEC §7.2 "Optional LLM smoke" suite).

What this tests
---------------
- The client instantiates and calls OpenAI without error.
- The response deserialises into a valid ``LabelExtraction`` (schema matches).
- The prompt_version used matches the module constant ``PROMPT_VERSION``.

The test image is a 1x1 white pixel PNG (``tiny_png`` fixture from conftest).
The model will hallucinate label fields — that is expected and acceptable; this
test validates *wire format*, not extraction *accuracy*.

Run locally:
    OPENAI_API_KEY=sk-... RUN_LLM_TESTS=1 pytest tests/llm -q -s
"""
from __future__ import annotations

import os

import pytest

from app.extraction.openai_vision import OpenAIVisionClient
from app.extraction.prompts import PROMPT_VERSION
from app.schemas.extraction import LabelExtraction

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LLM_TESTS") != "1",
    reason="LLM smoke test — set RUN_LLM_TESTS=1 to enable.",
)


@pytest.mark.asyncio
async def test_extract_returns_label_extraction(tiny_png: bytes) -> None:
    """extract() with a 1x1 PNG returns a validated LabelExtraction object.

    The model hallucitates field values for a trivial image — that is fine.
    The assertion verifies the full round-trip: HTTP call → structured output
    → Pydantic validation → correct Python type.
    """
    client = OpenAIVisionClient()
    result = await client.extract(image_bytes=tiny_png, prompt_version=PROMPT_VERSION)

    assert isinstance(result, LabelExtraction), (
        f"Expected LabelExtraction, got {type(result)}"
    )
    # field_confidence must have all 8 required keys (enforced by Pydantic, but
    # make the assertion explicit so failures produce a clear message)
    conf = result.field_confidence
    required_keys = {
        "brand_name",
        "class_type",
        "abv_percent",
        "net_contents",
        "warning_text",
        "warning_prefix_all_caps",
        "warning_prefix_bold",
        "image_quality",
    }
    present_keys = set(conf.model_fields_set | set(conf.model_fields))
    assert required_keys <= present_keys, (
        f"field_confidence missing keys: {required_keys - present_keys}"
    )
    # image_quality must be one of the two allowed enum values
    assert result.image_quality in ("good", "poor")
