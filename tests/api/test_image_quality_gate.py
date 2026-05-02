"""FR-017: image_quality == "poor" gates PASS → NEEDS_REVIEW.

SPEC §1 + §7.5 case 8:
- If all comparators would produce PASS but image_quality is "poor",
  overall verdict must be NEEDS_REVIEW.
- If a field already FAILs, FAIL is not upgraded to NEEDS_REVIEW.
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


def test_poor_quality_with_passing_comparators_gives_needs_review(
    fake_openai_client, make_extraction, tiny_png
):
    """SPEC §7.5 case 8 + FR-017: poor image + passing comparators → NEEDS_REVIEW."""
    fake_openai_client.extraction = make_extraction(image_quality="poor")
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["overall_verdict"] == "NEEDS_REVIEW"


def test_poor_quality_does_not_upgrade_fail(fake_openai_client, make_extraction, tiny_png):
    """FR-017: poor image_quality + FAIL field → overall stays FAIL (not NEEDS_REVIEW)."""
    # ABV mismatch will cause a FAIL
    fake_openai_client.extraction = make_extraction(
        abv_percent=45.0,
        image_quality="poor",
    )
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    payload_abv_mismatch = json.dumps({
        "brand": "OLD TOM DISTILLERY",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv_percent": 99.0,  # will cause FAIL
        "net_contents": "750 mL",
    })

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": payload_abv_mismatch},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["overall_verdict"] == "FAIL"


def test_good_quality_with_passing_comparators_gives_pass(
    fake_openai_client, make_extraction, tiny_png
):
    """Sanity: good image_quality + passing comparators → PASS."""
    fake_openai_client.extraction = make_extraction(image_quality="good")
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["overall_verdict"] == "PASS"
