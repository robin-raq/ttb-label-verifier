"""Adversarial: smart apostrophe normalization — SPEC §7.6.

Brand names like "STONE'S THROW" (straight apostrophe) vs "Stone's Throw"
(curly/smart apostrophe U+2019) should match via fuzzy normalization (B1).

This test documents the contract:
- If B1's compare_brand normalizes both to ASCII-straight before fuzzy matching,
  the result is PASS.
- If B1's implementation does NOT handle this, this test documents it as a
  known limitation and the result is NEEDS_REVIEW (not PASS, not FAIL).

SPEC §7.6: "Handled per fuzzy normalization or NEEDS_REVIEW — documented in
comparator tests."

IMPORTANT: This test relies on B1's compare_brand normalization. If B1 handles
Unicode normalization (NFKC) before fuzzy match, STONE'S == Stone's after casefold.
The curly apostrophe U+2019 NFKC-normalizes to itself (not U+0027), so extra
normalization (replacing U+2019 with U+0027) may be needed in B1.
We assert: result is PASS or NEEDS_REVIEW (never FAIL for a genuine apostrophe
variant of the same brand name).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.deps import get_openai_client


def test_smart_apostrophe_brand_not_fail(fake_openai_client, make_extraction, tiny_png):
    """Smart apostrophe variant of the same brand must be PASS or NEEDS_REVIEW, not FAIL.

    Form: "STONE'S THROW" (straight apostrophe U+0027)
    Label: "Stone’s Throw" (curly apostrophe U+2019)

    After NFKC + casefold both become "stone’s throw" vs "stone's throw".
    If B1 does additional apostrophe normalization, this is PASS.
    If B1 only does NFKC + casefold, the ratio is still very high (>0.92 with rapidfuzz).
    Either way, the verdict should not be FAIL.
    """
    # Curly/smart apostrophe in extracted brand
    fake_openai_client.extraction = make_extraction(
        brand_name="Stone’s Throw"  # U+2019 RIGHT SINGLE QUOTATION MARK
    )
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    payload = json.dumps({
        "brand": "STONE'S THROW",  # straight apostrophe
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv_percent": 45.0,
        "net_contents": "750 mL",
    })

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": payload},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    brand_field = next((f for f in body["fields"] if f["name"] == "brand"), None)
    assert brand_field is not None, "No 'brand' field in response"
    # Must be PASS or NEEDS_REVIEW — never FAIL for apostrophe variant
    assert brand_field["verdict"] != "FAIL", (
        f"Smart apostrophe brand variant produced FAIL. "
        f"Brand field: {brand_field}. "
        f"B1 normalization may need to handle U+2019 → U+0027 substitution."
    )


def test_straight_apostrophe_exact_match_passes(fake_openai_client, make_extraction, tiny_png):
    """Exact match with straight apostrophe on both sides must be PASS."""
    fake_openai_client.extraction = make_extraction(
        brand_name="STONE'S THROW"  # straight apostrophe, exact match
    )
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    payload = json.dumps({
        "brand": "STONE'S THROW",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv_percent": 45.0,
        "net_contents": "750 mL",
    })

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": payload},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
    app.dependency_overrides.clear()

    body = resp.json()
    brand_field = next((f for f in body["fields"] if f["name"] == "brand"), None)
    assert brand_field is not None
    assert brand_field["verdict"] == "PASS"
