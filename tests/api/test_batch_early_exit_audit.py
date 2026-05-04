"""FR-013: every batch row that fails before reaching `_process_single`
still writes an audit record.

The three early-exit branches in `verify_batch.process_item` are:
  1. base64 decode of `image_b64` failed
  2. MIME / size validation rejected the image
  3. `VerifyRequest` payload parse failed (missing or invalid fields)

Without these audit writes, agents have no record that a row was even
submitted — replay against the raw POST body is the only recovery, and
the request is otherwise invisible to monitoring.
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_openai_client
from app.api.main import app


def _tiny_jpeg() -> bytes:
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )


VALID_PAYLOAD = {
    "brand": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
}


@pytest.fixture
def client(fake_openai_client, make_extraction, tmp_path):
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


def _records(audit_file) -> list[dict]:
    return [json.loads(line) for line in audit_file.read_text().splitlines() if line.strip()]


def test_base64_decode_failure_writes_audit_record(client):
    c, audit_file = client
    bad_b64 = "!!!not valid base64!!!"
    body = {"items": [{"image_b64": bad_b64, "payload": VALID_PAYLOAD}]}
    resp = c.post("/verify/batch", json=body)
    assert resp.status_code == 200, resp.text

    records = _records(audit_file)
    assert len(records) == 1, "exactly one audit record per failed row"
    rec = records[0]
    assert rec["batch_id"] is not None
    assert rec["overall_verdict"] == "FAIL"
    assert rec["extracted"] is None
    assert any(
        "base64" in (f.get("detail") or "") for f in rec["field_results"]
    ), f"expected base64-failure marker, got {rec['field_results']}"


def test_mime_validation_failure_writes_audit_record(client):
    """Submitting plain text bytes (decodes successfully but fails MIME sniff)
    must produce an audit record with the validation reason."""
    c, audit_file = client
    plain_b64 = base64.b64encode(b"this is not an image" * 50).decode()
    body = {"items": [{"image_b64": plain_b64, "payload": VALID_PAYLOAD}]}
    resp = c.post("/verify/batch", json=body)
    assert resp.status_code == 200

    records = _records(audit_file)
    assert len(records) == 1
    rec = records[0]
    assert rec["batch_id"] is not None
    assert rec["overall_verdict"] == "FAIL"
    assert rec["image_sha256"] != ""  # we DID see bytes; sha them for replay
    assert any(
        "image_validation_failed" in (f.get("detail") or "")
        for f in rec["field_results"]
    )


def test_invalid_payload_writes_audit_record(client):
    """A row with image bytes but a payload missing required fields still
    writes an audit record so the row is recoverable."""
    c, audit_file = client
    valid_jpeg_b64 = base64.b64encode(_tiny_jpeg()).decode()
    bad_payload = {"brand": "OLD TOM"}  # missing required class_type, abv, vol
    body = {"items": [{"image_b64": valid_jpeg_b64, "payload": bad_payload}]}
    resp = c.post("/verify/batch", json=body)
    assert resp.status_code == 200

    records = _records(audit_file)
    assert len(records) == 1
    rec = records[0]
    assert rec["batch_id"] is not None
    assert rec["overall_verdict"] == "FAIL"
    # Form fields preserve whatever was submitted, so an analyst can replay
    assert rec["form_fields"].get("brand") == "OLD TOM"


def test_mixed_batch_audits_each_row_independently(client):
    """A batch with one good row + one early-exit row must produce two
    audit records sharing the same batch_id."""
    c, audit_file = client
    valid_jpeg_b64 = base64.b64encode(_tiny_jpeg()).decode()
    body = {
        "items": [
            {"image_b64": "!!bad!!", "payload": VALID_PAYLOAD},
            {"image_b64": valid_jpeg_b64, "payload": VALID_PAYLOAD},
        ]
    }
    resp = c.post("/verify/batch", json=body)
    assert resp.status_code == 200

    records = _records(audit_file)
    assert len(records) == 2
    batch_ids = {r["batch_id"] for r in records}
    assert len(batch_ids) == 1, f"both records should share one batch_id, got {batch_ids}"
