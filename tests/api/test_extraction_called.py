"""FR-003: Vision client is called exactly once per /verify request.

The FakeOpenAIClient.call_log tracks invocations. After a successful
POST /verify, the log must contain exactly one entry.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.deps import get_openai_client

VALID_PAYLOAD = json.dumps({
    "brand": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
})


def test_extraction_called_once(fake_openai_client, make_extraction, tiny_png):
    """FR-003: OpenAI vision client called exactly once per request."""
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert len(fake_openai_client.call_log) == 1


def test_extraction_receives_image_bytes(fake_openai_client, make_extraction, tiny_png):
    """FR-003: The call includes the image bytes (non-zero size)."""
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    call = fake_openai_client.call_log[0]
    assert call["size"] > 0


def test_extraction_receives_prompt_version(fake_openai_client, make_extraction, tiny_png):
    """FR-016: prompt_version is passed to the vision client."""
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    call = fake_openai_client.call_log[0]
    assert "prompt_version" in call
    assert isinstance(call["prompt_version"], str)
    assert call["prompt_version"]  # non-empty
