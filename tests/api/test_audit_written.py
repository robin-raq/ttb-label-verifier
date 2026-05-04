"""FR-013 + §2.1: Audit log record is written per request.

Tests:
- After POST /verify, exactly one JSONL line is appended.
- All required §2.1 keys are present.
- Image bytes are NOT in the record (only SHA-256).
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.deps import get_openai_client

VALID_PAYLOAD = {
    "brand": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
}

REQUIRED_AUDIT_KEYS = {
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


@pytest.fixture
def audit_client(fake_openai_client, make_extraction, tiny_png, tmp_path):
    """TestClient with audit log directed to tmp_path."""
    fake_openai_client.extraction = make_extraction()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai_client

    audit_file = tmp_path / "audit.jsonl"
    # Set the env var so the logger picks up the temp path
    import app.audit.jsonl_logger as logger_mod
    original_path = logger_mod.AUDIT_LOG_PATH
    logger_mod.AUDIT_LOG_PATH = str(audit_file)

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, tiny_png, audit_file

    logger_mod.AUDIT_LOG_PATH = original_path
    app.dependency_overrides.clear()


def test_audit_record_written(audit_client):
    """FR-013: One audit record is appended per request."""
    c, tiny_png, audit_file = audit_client
    c.post(
        "/verify",
        data={"payload": json.dumps(VALID_PAYLOAD)},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    assert audit_file.exists(), "Audit log was not created"
    lines = [l for l in audit_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 1, f"Expected 1 audit line, got {len(lines)}"


def test_audit_record_has_required_keys(audit_client):
    """§2.1: All required audit keys must be present."""
    c, tiny_png, audit_file = audit_client
    c.post(
        "/verify",
        data={"payload": json.dumps(VALID_PAYLOAD)},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    record = json.loads(audit_file.read_text().strip())
    missing = REQUIRED_AUDIT_KEYS - set(record.keys())
    assert not missing, f"Audit record missing keys: {missing}"


def test_audit_record_image_bytes_not_persisted(audit_client):
    """§2.1 + PRESEARCH §12: Image bytes MUST NOT appear in audit log."""
    c, tiny_png, audit_file = audit_client
    c.post(
        "/verify",
        data={"payload": json.dumps(VALID_PAYLOAD)},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    raw_log = audit_file.read_bytes()
    # Image bytes should not appear verbatim in the log
    # The tiny_png is small enough to check directly
    assert tiny_png not in raw_log, "Image bytes found verbatim in audit log — MUST be SHA-256 only"


def test_audit_record_has_sha256(audit_client):
    """§2.1: image_sha256 is a 64-char hex string."""
    c, tiny_png, audit_file = audit_client
    c.post(
        "/verify",
        data={"payload": json.dumps(VALID_PAYLOAD)},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    record = json.loads(audit_file.read_text().strip())
    sha = record["image_sha256"]
    assert isinstance(sha, str)
    assert len(sha) == 64
    assert all(c in "0123456789abcdef" for c in sha)


def test_audit_record_overall_verdict_valid(audit_client):
    """§2.1: overall_verdict is one of the three states."""
    c, tiny_png, audit_file = audit_client
    c.post(
        "/verify",
        data={"payload": json.dumps(VALID_PAYLOAD)},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    record = json.loads(audit_file.read_text().strip())
    assert record["overall_verdict"] in {"PASS", "FAIL", "NEEDS_REVIEW"}


def test_audit_record_form_fields_present(audit_client):
    """§2.1: form_fields mirrors the submitted VerifyRequest payload."""
    c, tiny_png, audit_file = audit_client
    c.post(
        "/verify",
        data={"payload": json.dumps(VALID_PAYLOAD)},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    record = json.loads(audit_file.read_text().strip())
    ff = record["form_fields"]
    assert ff["brand"] == VALID_PAYLOAD["brand"]
    assert ff["abv_percent"] == VALID_PAYLOAD["abv_percent"]


def test_audit_record_extracted_has_field_confidence(audit_client):
    """§2.1: extracted includes nested field_confidence per SPEC §4."""
    c, tiny_png, audit_file = audit_client
    c.post(
        "/verify",
        data={"payload": json.dumps(VALID_PAYLOAD)},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    record = json.loads(audit_file.read_text().strip())
    extracted = record["extracted"]
    assert "field_confidence" in extracted


def test_audit_file_mode_600(audit_client, tmp_path):
    """§2.1 + PRESEARCH §12: Audit log file created with mode 0o600."""
    c, tiny_png, audit_file = audit_client
    c.post(
        "/verify",
        data={"payload": json.dumps(VALID_PAYLOAD)},
        files={"image": ("label.png", tiny_png, "image/png")},
    )
    if os.name != "nt":  # skip on Windows
        mode = oct(os.stat(str(audit_file)).st_mode)[-3:]
        assert mode == "600", f"Expected mode 600, got {mode}"
