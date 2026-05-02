"""NFR-001: Single-label latency gate — mocked synthetic test.

Approach (per SPEC NFR-001, approach A):
  Use time.perf_counter() to measure only the non-vision server-side phases:
    1. File validation (MIME + size check)
    2. SHA-256 computation
    3. Comparator + verdict computation
    4. Response serialization

  The FakeOpenAIClient returns instantly (simulating <1ms vision call).
  Wall-clock elapsed for the whole request (with instant mock) is also
  measured as approach B for belt-and-suspenders.

  SPEC requires sum of measured phases < 5000 ms.
  This is a synthetic gate that MUST NOT be skipped on main.

NOTE: Network-bound timings are not measured here. This only tests
server-side orchestration overhead.
"""
from __future__ import annotations

import json
import time

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

# NFR-001 gate: server-side non-vision phases must complete within this budget
LATENCY_BUDGET_MS = 5000


def test_single_verify_wall_clock_under_5000ms(fake_openai_client, make_extraction, tiny_png):
    """NFR-001: wall-clock elapsed for POST /verify with instant mock < 5000 ms.

    Measurement approach B (SPEC NFR-001): wall-clock around the entire HTTP
    request when the mock guarantees <1ms vision time. The FakeOpenAIClient
    returns synchronously (awaitable but instant) — so total elapsed reflects
    only server-side CPU work.
    """
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        start = time.perf_counter()
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

    app.dependency_overrides.clear()

    assert resp.status_code == 200, f"Request failed: {resp.status_code} {resp.text}"
    assert elapsed_ms < LATENCY_BUDGET_MS, (
        f"NFR-001 VIOLATED: wall-clock {elapsed_ms:.1f} ms >= {LATENCY_BUDGET_MS} ms. "
        f"Server-side non-vision phases are too slow."
    )


def test_reported_latency_ms_total_under_5000ms(fake_openai_client, make_extraction, tiny_png):
    """NFR-001: latency_ms.total in the response body must be < 5000 ms.

    The server self-reports latency in VerifyResponse.latency_ms. With the
    instant mock, the 'vision' component should be near-zero, and total should
    be well under the SLA.
    """
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )

    app.dependency_overrides.clear()

    body = resp.json()
    total_ms = body["latency_ms"]["total"]
    assert total_ms < LATENCY_BUDGET_MS, (
        f"NFR-001 VIOLATED: latency_ms.total={total_ms} >= {LATENCY_BUDGET_MS} ms."
    )


def test_compare_phase_under_500ms(fake_openai_client, make_extraction, tiny_png):
    """Comparator + verdict phase should be well under 500 ms (sanity gate).

    The comparators are pure Python — any slowness here is a bug.
    """
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/verify",
            data={"payload": VALID_PAYLOAD},
            files={"image": ("label.png", tiny_png, "image/png")},
        )

    app.dependency_overrides.clear()

    body = resp.json()
    compare_ms = body["latency_ms"]["compare"]
    assert compare_ms < 500, (
        f"Compare phase too slow: {compare_ms} ms. "
        f"Comparators must be fast pure-Python functions."
    )
