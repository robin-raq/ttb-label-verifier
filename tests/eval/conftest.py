"""Eval harness fixtures — async OpenAI client with guaranteed teardown."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.extraction.openai_vision import OpenAIVisionClient


@pytest.fixture
async def vision_client() -> AsyncIterator[OpenAIVisionClient]:
    client = OpenAIVisionClient()
    try:
        yield client
    finally:
        await client._client.close()
