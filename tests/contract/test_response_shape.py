"""Contract tests: 200 and 4xx response shapes — SPEC §3.1.

These tests assert that the HTTP response bodies conform to the schemas
documented in SPEC §3.1. They use the FastAPI TestClient and dependency
overrides to inject the fake OpenAI client.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_openai_client
from app.api.main import app


@pytest.fixture
def client(fake_openai_client, make_extraction, tiny_png):
    """TestClient with FakeOpenAIClient wired in."""
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, tiny_png
    app.dependency_overrides.clear()


def test_200_response_has_required_keys(client):
    """SPEC §3.1 VerifyResponse shape."""
    c, tiny_png = client
    resp = c.post(
        "/verify",
        data={"payload": json.dumps({
            "brand": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "abv_percent": 45.0,
            "net_contents": "750 mL",
        })},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "request_id" in body
    assert "overall_verdict" in body
    assert "fields" in body
    assert "latency_ms" in body
    # overall_verdict must be one of the three states
    assert body["overall_verdict"] in {"PASS", "FAIL", "NEEDS_REVIEW"}
    # fields is a list
    assert isinstance(body["fields"], list)
    # latency_ms has expected sub-keys
    latency = body["latency_ms"]
    assert "vision" in latency
    assert "compare" in latency
    assert "total" in latency


def test_200_field_entries_have_required_keys(client):
    """Each FieldResult in fields[] must have name, verdict, confidence."""
    c, tiny_png = client
    resp = c.post(
        "/verify",
        data={"payload": json.dumps({
            "brand": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "abv_percent": 45.0,
            "net_contents": "750 mL",
        })},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    assert resp.status_code == 200
    for field_entry in resp.json()["fields"]:
        assert "name" in field_entry
        assert "verdict" in field_entry
        assert "confidence" in field_entry
        assert field_entry["verdict"] in {"PASS", "FAIL", "NEEDS_REVIEW"}
        assert 0.0 <= field_entry["confidence"] <= 1.0


def test_400_error_envelope_shape(client):
    """SPEC §3.1 ErrorResponse shape for 4xx."""
    c, tiny_png = client
    # Upload a non-image to trigger INVALID_IMAGE_TYPE
    resp = c.post(
        "/verify",
        data={"payload": json.dumps({
            "brand": "TEST",
            "class_type": "Bourbon",
            "abv_percent": 45.0,
            "net_contents": "750 mL",
        })},
        files={"image": ("file.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    error = body["error"]
    assert "code" in error
    assert "message" in error
    assert isinstance(error["code"], str)
    assert isinstance(error["message"], str)


def test_413_error_envelope_shape(client):
    """SPEC §3.1 ErrorResponse shape for 413 (oversize)."""
    c, tiny_png = client
    big_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024 + 1)
    resp = c.post(
        "/verify",
        data={"payload": json.dumps({
            "brand": "TEST",
            "class_type": "Bourbon",
            "abv_percent": 45.0,
            "net_contents": "750 mL",
        })},
        files={"image": ("big.png", big_image, "image/png")},
    )
    assert resp.status_code == 413
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "FILE_TOO_LARGE"
