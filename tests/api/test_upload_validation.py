"""FR-002: MIME sniff and file-size validation — SPEC §7.5 cases 4 & 5.

Tests:
- Wrong MIME type → 400 INVALID_IMAGE_TYPE.
- Oversize payload (>10 MiB) → 413 FILE_TOO_LARGE.
- Accepted MIME types (jpeg, png, webp) are not rejected.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.deps import get_openai_client

MAX_BYTES = 10 * 1024 * 1024  # 10 MiB

VALID_PAYLOAD = json.dumps({
    "brand": "TEST BRAND",
    "class_type": "Bourbon",
    "abv_percent": 40.0,
    "net_contents": "750 mL",
})


@pytest.fixture
def client(fake_openai_client, make_extraction):
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_text_file_rejected_400(client):
    """SPEC §7.5 case 4: invalid MIME → 400 INVALID_IMAGE_TYPE."""
    resp = client.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("file.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "INVALID_IMAGE_TYPE"


def test_pdf_rejected_400(client):
    """PDF is not a whitelisted image type."""
    resp = client.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("file.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_IMAGE_TYPE"


def test_oversize_rejected_413(client):
    """SPEC §7.5 case 5: >10 MiB → 413 FILE_TOO_LARGE."""
    # We need bytes > 10 MiB. Use a PNG header so MIME check passes first,
    # then size check fires.
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_BYTES + 1)
    resp = client.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("big.png", big, "image/png")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_png_accepted(client):
    """Valid PNG under size limit should not be rejected for MIME/size."""
    # tiny valid PNG bytes that filetype can sniff as PNG
    import struct
    import zlib

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
    png = sig + ihdr_full + idat_full + iend_full

    resp = client.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.png", png, "image/png")},
    )
    # Should not be a MIME or size rejection
    assert resp.status_code not in {400, 413}


def test_jpeg_magic_bytes_accepted(client):
    """JPEG magic bytes should pass MIME check."""
    # JPEG starts with FF D8 FF
    jpeg_like = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JFIF-ish
    resp = client.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.jpg", jpeg_like, "image/jpeg")},
    )
    assert resp.status_code not in {400, 413}


def test_webp_magic_bytes_accepted(client):
    """WebP RIFF header (VP8 lossy) should pass MIME check."""
    # Full RIFF....WEBPVP8  header required for filetype to sniff correctly
    webp = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 50
    resp = client.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("label.webp", webp, "image/webp")},
    )
    assert resp.status_code not in {400, 413}


def test_exact_10mib_accepted(client):
    """Exactly 10 MiB should be accepted (boundary: strictly greater than is rejected)."""
    # PNG header + exactly enough zeros to make 10 MiB total
    header = b"\x89PNG\r\n\x1a\n"
    payload_size = MAX_BYTES - len(header)
    exact = header + b"\x00" * payload_size
    resp = client.post(
        "/verify",
        data={"payload": VALID_PAYLOAD},
        files={"image": ("exact.png", exact, "image/png")},
    )
    # Should NOT be rejected for size (though might fail other ways)
    assert resp.status_code != 413
