"""FR-013 + §2.1 for the batch path: full extraction in audit records.

The single-verify path writes a complete audit record (extracted + nested
field_confidence). The batch path must achieve parity — replay and debugging
break without the extraction. SPEC §2.1 doesn't carve out an exception.
"""
from __future__ import annotations

import base64
import json
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.deps import get_openai_client


def _tiny_png() -> bytes:
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


ITEM_PAYLOAD = {
    "brand": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
}


@pytest.fixture
def batch_audit_client(fake_openai_client, make_extraction, tmp_path):
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    audit_file = tmp_path / "audit.jsonl"
    import app.audit.jsonl_logger as logger_mod
    original_path = logger_mod.AUDIT_LOG_PATH
    logger_mod.AUDIT_LOG_PATH = str(audit_file)

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, audit_file

    logger_mod.AUDIT_LOG_PATH = original_path
    app.dependency_overrides.clear()


def _post_batch(client: TestClient, n: int) -> None:
    png_b64 = base64.b64encode(_tiny_png()).decode()
    body = {"items": [{"image_b64": png_b64, "payload": ITEM_PAYLOAD}] * n}
    resp = client.post("/verify/batch", json=body)
    assert resp.status_code == 200, resp.text


def _records(audit_file) -> list[dict]:
    return [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]


_REQUIRED_AUDIT_KEYS = {
    "ts",
    "request_id",
    "batch_id",
    "image_sha256",
    "model_id",
    "prompt_version",
    "form_fields",
    "extracted",
    "field_results",
    "overall_verdict",
    "latency_ms",
}


def test_batch_audit_one_record_per_item(batch_audit_client):
    client, audit_file = batch_audit_client
    _post_batch(client, 3)
    assert len(_records(audit_file)) == 3


def test_batch_audit_record_has_required_keys(batch_audit_client):
    """SPEC §2.1 keys MUST be present on batch records too — closes the
    coverage gap where `test_audit_written.py` only asserted the single-
    verify path. A future change that drops e.g. `latency_ms` from batch
    records would have been silently undetected."""
    client, audit_file = batch_audit_client
    _post_batch(client, 2)
    for record in _records(audit_file):
        missing = _REQUIRED_AUDIT_KEYS - set(record.keys())
        assert not missing, f"Batch audit record missing keys: {missing}"


def test_batch_audit_each_record_has_extraction(batch_audit_client):
    """FR-013: batch audit records MUST include the full extraction
    (parity with single-verify path)."""
    client, audit_file = batch_audit_client
    _post_batch(client, 2)
    for record in _records(audit_file):
        assert record["extracted"] is not None, (
            "Batch audit record has extracted=None — replay/debug is broken"
        )
        assert "field_confidence" in record["extracted"]
        assert record["extracted"]["brand_name"] == "OLD TOM DISTILLERY"


def test_batch_audit_records_share_one_batch_id(batch_audit_client):
    """All audit records from one /verify/batch call share one batch_id."""
    client, audit_file = batch_audit_client
    _post_batch(client, 3)
    records = _records(audit_file)
    batch_ids = {r.get("batch_id") for r in records}
    assert len(batch_ids) == 1, f"Expected one batch_id across records, got {batch_ids}"
    only = next(iter(batch_ids))
    assert only is not None and isinstance(only, str) and len(only) >= 8


def test_single_verify_audit_has_no_batch_id_or_null(batch_audit_client):
    """Single /verify either omits batch_id or sets it to null — never reuses one."""
    client, audit_file = batch_audit_client
    png_b64 = base64.b64encode(_tiny_png()).decode()
    # post via /verify (single)
    resp = client.post(
        "/verify",
        data={"payload": json.dumps(ITEM_PAYLOAD)},
        files={"image": ("label.png", _tiny_png(), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    records = _records(audit_file)
    assert len(records) == 1
    assert records[0].get("batch_id") in (None, "")
