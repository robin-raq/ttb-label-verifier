"""VisionClient Protocol conformance.

The Protocol is the documented seam for swapping in alternative vision
providers (Azure OpenAI in TTB's gov-cloud tenant, a hypothetical Anthropic
or Gemini client, etc.). These tests fail loudly if any production or test
client diverges from the contract.
"""
from __future__ import annotations

from app.extraction import VisionClient
from app.extraction.openai_vision import OpenAIVisionClient
from tests.conftest import FakeOpenAIClient


def test_fake_client_conforms_to_protocol() -> None:
    """The test double in conftest must satisfy the public Protocol —
    otherwise tests are exercising a different shape than production."""
    assert isinstance(FakeOpenAIClient(), VisionClient)


def test_openai_client_conforms_to_protocol() -> None:
    """The real client must satisfy the Protocol without inheriting from it
    (structural typing). Constructed with a dummy api_key so we don't hit
    the OPENAI_API_KEY env requirement."""
    client = OpenAIVisionClient(api_key="test")
    assert isinstance(client, VisionClient)
