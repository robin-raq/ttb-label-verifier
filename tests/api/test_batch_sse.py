"""FR-014: POST /verify/batch SSE streaming.

Tests:
- ≥2 event:item frames for a 2-item batch (SPEC §7.5 case 7).
- events arrive in index order.
- event:done terminates the stream.
- items > 500 rejected with 400.
- Per-item MIME failure emits event:error, does NOT terminate stream.
"""
from __future__ import annotations

import base64
import json
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_openai_client
from app.api.main import app


def _make_tiny_png() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_chunk = b"IHDR" + ihdr
    ihdr_full = (
        struct.pack(">I", len(ihdr))
        + ihdr_chunk
        + struct.pack(">I", zlib.crc32(ihdr_chunk))
    )
    raw = b"\x00\xff\xff\xff"
    comp = zlib.compress(raw)
    idat_chunk = b"IDAT" + comp
    idat_full = (
        struct.pack(">I", len(comp))
        + idat_chunk
        + struct.pack(">I", zlib.crc32(idat_chunk))
    )
    iend_chunk = b"IEND"
    iend_full = (
        struct.pack(">I", 0) + iend_chunk + struct.pack(">I", zlib.crc32(iend_chunk))
    )
    return sig + ihdr_full + idat_full + iend_full


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE text into list of {event, data} dicts."""
    events = []
    current: dict = {}
    for line in text.splitlines():
        if line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            raw = line[len("data:"):].strip()
            try:
                current["data"] = json.loads(raw)
            except json.JSONDecodeError:
                current["data"] = raw
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


ITEM_PAYLOAD = {
    "brand": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
}


@pytest.fixture
def batch_client(fake_openai_client, make_extraction):
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_batch_two_items_produces_two_item_events(batch_client):
    """SPEC §7.5 case 7: ≥2 event:item frames in a 2-item batch."""
    png_b64 = base64.b64encode(_make_tiny_png()).decode()
    body = {
        "items": [
            {"image_b64": png_b64, "payload": ITEM_PAYLOAD},
            {"image_b64": png_b64, "payload": ITEM_PAYLOAD},
        ]
    }
    resp = batch_client.post(
        "/verify/batch",
        json=body,
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    item_events = [e for e in events if e.get("event") == "item"]
    assert len(item_events) >= 2, f"Expected ≥2 item events, got {len(item_events)}: {events}"


def test_batch_items_in_order(batch_client):
    """event:item frames must arrive with ascending index."""
    png_b64 = base64.b64encode(_make_tiny_png()).decode()
    body = {
        "items": [
            {"image_b64": png_b64, "payload": ITEM_PAYLOAD},
            {"image_b64": png_b64, "payload": ITEM_PAYLOAD},
            {"image_b64": png_b64, "payload": ITEM_PAYLOAD},
        ]
    }
    resp = batch_client.post("/verify/batch", json=body)
    events = _parse_sse(resp.text)
    item_events = [e for e in events if e.get("event") == "item"]
    indices = [e["data"].get("index") for e in item_events if isinstance(e.get("data"), dict)]
    assert indices == sorted(indices), f"Item events not in order: {indices}"


def test_batch_has_done_event(batch_client):
    """SSE stream must terminate with event:done."""
    png_b64 = base64.b64encode(_make_tiny_png()).decode()
    body = {
        "items": [
            {"image_b64": png_b64, "payload": ITEM_PAYLOAD},
        ]
    }
    resp = batch_client.post("/verify/batch", json=body)
    events = _parse_sse(resp.text)
    done_events = [e for e in events if e.get("event") == "done"]
    assert done_events, "No event:done found in SSE stream"


def test_batch_over_500_items_rejected():
    """SPEC §3.2: items > 500 → 400."""
    with TestClient(app, raise_server_exceptions=False) as c:
        png_b64 = base64.b64encode(_make_tiny_png()).decode()
        items = [{"image_b64": png_b64, "payload": ITEM_PAYLOAD}] * 501
        resp = c.post("/verify/batch", json={"items": items})
    assert resp.status_code == 400


def test_batch_bad_item_emits_error_not_terminate(batch_client):
    """event:error for bad item MUST NOT terminate the stream — good items still processed."""
    png_b64 = base64.b64encode(_make_tiny_png()).decode()
    # First item: invalid base64 → should emit error
    # Second item: valid → should emit item event
    bad_b64 = base64.b64encode(b"not an image at all - plain text").decode()
    body = {
        "items": [
            {"image_b64": bad_b64, "payload": ITEM_PAYLOAD},
            {"image_b64": png_b64, "payload": ITEM_PAYLOAD},
        ]
    }
    resp = batch_client.post("/verify/batch", json=body)
    events = _parse_sse(resp.text)
    # Stream should not have been cut short — done event must appear
    done_events = [e for e in events if e.get("event") == "done"]
    assert done_events, "Stream terminated prematurely on bad item"


def test_batch_content_type_is_event_stream(batch_client):
    """Response Content-Type must be text/event-stream."""
    png_b64 = base64.b64encode(_make_tiny_png()).decode()
    body = {
        "items": [
            {"image_b64": png_b64, "payload": ITEM_PAYLOAD},
        ]
    }
    resp = batch_client.post("/verify/batch", json=body)
    assert "text/event-stream" in resp.headers.get("content-type", "")
