"""FR-012: OpenAI transport failure handling.

When the vision client raises on both attempts:
- Response MUST be HTTP 200 (not 503).
- overall_verdict MUST be NEEDS_REVIEW (not PASS or FAIL).
- At least one FieldResult must carry extraction_failed as detail.

The FakeOpenAIClient.raises is set to an exception; the route code
retries once and then returns a graceful degraded response.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.deps import get_openai_client
from app.api.main import app

VALID_PAYLOAD = json.dumps({
    "brand": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
})


def test_openai_failure_returns_200(fake_openai_client, tiny_png):
    """FR-012: exhausted retries → HTTP 200 (never 503)."""
    fake_openai_client.raises = RuntimeError("OpenAI is down")
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200


def test_openai_failure_returns_needs_review(fake_openai_client, tiny_png):
    """FR-012: exhausted retries → overall_verdict NEEDS_REVIEW."""
    fake_openai_client.raises = RuntimeError("OpenAI is down")
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    body = resp.json()
    assert body["overall_verdict"] == "NEEDS_REVIEW"


def test_openai_failure_has_extraction_failed_detail(fake_openai_client, tiny_png):
    """FR-012: at least one field result carries extraction_failed detail."""
    fake_openai_client.raises = ConnectionError("Network error")
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    body = resp.json()
    details = [f.get("detail", "") or "" for f in body["fields"]]
    assert any("extraction_failed" in d for d in details), (
        f"Expected 'extraction_failed' in at least one field detail. Got: {details}"
    )


def test_openai_failure_not_silent_pass(fake_openai_client, tiny_png):
    """FR-012: extraction failure MUST NOT produce PASS verdict."""
    fake_openai_client.raises = TimeoutError("Timeout")
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert resp.json()["overall_verdict"] != "PASS"
