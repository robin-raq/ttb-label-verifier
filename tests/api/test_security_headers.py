"""FR-015: Security headers in production mode.

Tests assert that when ENV=production (or SECURE_HEADERS_ENABLED=1),
the required headers are present and CSP does not contain unsafe directives.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient


VALID_PAYLOAD = json.dumps({
    "brand": "TEST",
    "class_type": "Bourbon",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
})


@pytest.fixture
def secure_client(fake_openai_client, make_extraction, tiny_png, monkeypatch):
    """Client with production security headers enabled."""
    monkeypatch.setenv("SECURE_HEADERS_ENABLED", "1")
    monkeypatch.setenv("ENV", "production")

    # Re-import app to pick up new env vars
    # We need the security middleware to see the env at startup
    from app.api.main import app
    from app.api.deps import get_openai_client

    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, tiny_png

    app.dependency_overrides.clear()


def test_hsts_header_present(secure_client):
    """FR-015: Strict-Transport-Security must be present in production."""
    c, tiny_png = secure_client
    resp = c.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    assert "strict-transport-security" in resp.headers or "Strict-Transport-Security" in resp.headers


def test_x_content_type_options_nosniff(secure_client):
    """FR-015: X-Content-Type-Options: nosniff must be present."""
    c, tiny_png = secure_client
    resp = c.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    header = (
        resp.headers.get("x-content-type-options")
        or resp.headers.get("X-Content-Type-Options", "")
    )
    assert "nosniff" in header.lower()


def test_csp_header_present(secure_client):
    """FR-015: Content-Security-Policy must be set."""
    c, tiny_png = secure_client
    resp = c.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    csp = (
        resp.headers.get("content-security-policy")
        or resp.headers.get("Content-Security-Policy", "")
    )
    assert csp, "Content-Security-Policy header is missing"


def test_csp_no_unsafe_inline_in_production(secure_client):
    """FR-015: CSP in production MUST NOT include 'unsafe-inline'."""
    c, tiny_png = secure_client
    resp = c.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    csp = (
        resp.headers.get("content-security-policy")
        or resp.headers.get("Content-Security-Policy", "")
    ).lower()
    assert "'unsafe-inline'" not in csp, f"CSP contains 'unsafe-inline': {csp}"


def test_csp_no_unsafe_eval_in_production(secure_client):
    """FR-015: CSP in production MUST NOT include 'unsafe-eval'."""
    c, tiny_png = secure_client
    resp = c.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    csp = (
        resp.headers.get("content-security-policy")
        or resp.headers.get("Content-Security-Policy", "")
    ).lower()
    assert "'unsafe-eval'" not in csp, f"CSP contains 'unsafe-eval': {csp}"


def test_csp_img_src_allows_blob_and_data(secure_client):
    """The SPA renders file-upload + COLA-attached label previews via
    URL.createObjectURL(...), which produces `blob:...` URIs. The CSP MUST
    allow those (and `data:` for tiny inline images) on `img-src` — without
    this, every image preview is silently blocked in production."""
    c, tiny_png = secure_client
    resp = c.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    csp = (
        resp.headers.get("content-security-policy")
        or resp.headers.get("Content-Security-Policy", "")
    ).lower()
    # `img-src` directive must be explicit (otherwise it falls back to
    # `default-src 'self'` which blocks blob:).
    assert "img-src" in csp, f"img-src directive missing from CSP: {csp}"
    # Both schemes must be allowed.
    img_src = csp.split("img-src", 1)[1].split(";", 1)[0]
    assert "blob:" in img_src, f"blob: not allowed in img-src: {img_src}"
    assert "data:" in img_src, f"data: not allowed in img-src: {img_src}"


def test_referrer_policy_present(secure_client):
    """FR-015: Referrer-Policy must be set."""
    c, tiny_png = secure_client
    resp = c.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    header = (
        resp.headers.get("referrer-policy")
        or resp.headers.get("Referrer-Policy", "")
    )
    assert header, "Referrer-Policy header is missing"
