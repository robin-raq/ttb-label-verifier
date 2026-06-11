"""Timeout configuration and behaviour tests.

Covers:
1. OpenAIVisionClient is constructed with an explicit timeout (not None).
2. TimeoutError from the vision client → HTTP 200 + NEEDS_REVIEW.

The real network timeout behaviour (SDK-level abort) is exercised by the
integration test suite against a real OpenAI endpoint (RUN_LLM_TESTS=1).
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.deps import get_openai_client
from app.api.main import app
from app.extraction.openai_vision import OpenAIVisionClient

VALID_PAYLOAD = json.dumps({
    "brand": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
})


def test_openai_client_has_timeout() -> None:
    """OpenAIVisionClient must be constructed with an explicit non-None timeout."""
    client = OpenAIVisionClient(api_key="test")
    assert client._client.timeout is not None, (
        "AsyncOpenAI client timeout is None — unbounded requests risk hanging indefinitely"
    )


def test_timeout_error_returns_needs_review(fake_openai_client, tiny_png) -> None:
    """TimeoutError from vision client → HTTP 200 + NEEDS_REVIEW, never a hang."""
    fake_openai_client.raises = TimeoutError("connection timed out")
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_verdict"] == "NEEDS_REVIEW"
    details = [f.get("detail", "") or "" for f in body["fields"]]
    assert any("extraction_failed" in d for d in details)


def test_timeout_not_silent_pass(fake_openai_client, tiny_png) -> None:
    """TimeoutError MUST NOT yield a PASS verdict."""
    fake_openai_client.raises = TimeoutError("timed out")
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert resp.json()["overall_verdict"] != "PASS"
