"""FastAPI route handlers — FR-001, FR-002, FR-012, FR-013, FR-014.

Endpoints:
  POST /verify       — single-label verification (§3.1)
  POST /verify/batch — bulk SSE streaming (§3.2, FR-014)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime

import filetype
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_openai_client
from app.audit.jsonl_logger import write_audit_record
from app.extraction import VisionClient
from app.extraction.prompts import PROMPT_VERSION
from app.schemas.api import (
    ErrorCode,
    ErrorEnvelope,
    ErrorResponse,
    FieldResult,
    LatencyMs,
    Verdict,
    VerifyRequest,
    VerifyResponse,
)
from app.schemas.extraction import LabelExtraction
from app.verdict import compute_overall_verdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MiB (FR-002)
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
BATCH_MAX_ITEMS = 500  # FR-014
BATCH_CONCURRENCY = 25  # asyncio.Semaphore value
RETRY_BACKOFF_SECS = 1  # FR-012 retry backoff

# Model identifier for audit log
MODEL_ID = os.environ.get("MODEL_NAME", "fake-test")

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_response(code: ErrorCode, message: str, status_code: int) -> JSONResponse:
    body = ErrorResponse(error=ErrorEnvelope(code=code, message=message))
    return JSONResponse(content=body.model_dump(), status_code=status_code)


def _validate_image(image_bytes: bytes) -> JSONResponse | None:
    """Return an error response if MIME or size is invalid; else None.

    FR-002: check size first (cheap), then MIME sniff.
    """
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return _error_response(
            ErrorCode.FILE_TOO_LARGE,
            f"Image exceeds the 10 MiB limit ({len(image_bytes)} bytes).",
            413,
        )
    kind = filetype.guess(image_bytes)
    if kind is None or kind.mime not in ALLOWED_MIME_TYPES:
        detected = kind.mime if kind else "unknown"
        return _error_response(
            ErrorCode.INVALID_IMAGE_TYPE,
            f"Unsupported image type '{detected}'. Accepted: {', '.join(ALLOWED_MIME_TYPES)}.",
            400,
        )
    return None


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_extraction_failed_response(request_id: str) -> VerifyResponse:
    """FR-012: return a graceful NEEDS_REVIEW response when extraction fails."""
    field = FieldResult(
        name="extraction",
        verdict=Verdict.NEEDS_REVIEW,
        confidence=0.0,
        detail="extraction_failed: vision client returned an error after retry",
    )
    return VerifyResponse(
        request_id=request_id,
        overall_verdict=Verdict.NEEDS_REVIEW,
        fields=[field],
        latency_ms=LatencyMs(vision=0, compare=0, total=0),
    )


def _run_comparators(
    request: VerifyRequest,
    extraction: LabelExtraction,
) -> list[FieldResult]:
    """Call all comparators and return the 7 FieldResult list.

    Order matches SPEC §7.5 expectation:
    brand, class_type, abv, net_contents, warning_text, warning_caps, warning_bold.
    """
    from app.comparators.numeric_match import compare_abv
    from app.comparators.text_match import compare_brand, compare_class_type
    from app.comparators.volume_match import compare_volume
    from app.comparators.warning_match import compare_warning

    return [
        compare_brand(
            extraction.brand_name,
            request.brand,
            extraction.field_confidence.brand_name,
        ),
        compare_class_type(
            extraction.class_type,
            request.class_type,
            extraction.field_confidence.class_type,
        ),
        compare_abv(
            extraction.abv_percent,
            request.abv_percent,
            extraction.field_confidence.abv_percent,
        ),
        compare_volume(
            extraction.net_contents,
            request.net_contents,
            extraction.field_confidence.net_contents,
        ),
        *compare_warning(extraction),
    ]


async def _call_with_retry(
    client: VisionClient | None, image_bytes: bytes
) -> LabelExtraction:
    """Call the vision client with one retry on failure — FR-012.

    Raises the exception if both attempts fail (or if client is None).
    The caller handles that case by returning a graceful NEEDS_REVIEW response.
    """
    if client is None:
        raise RuntimeError(
            "OpenAI vision client not available — B3 module not yet merged."
        )
    try:
        return await client.extract(image_bytes, PROMPT_VERSION)
    except Exception:
        # Retry once with bounded backoff
        await asyncio.sleep(RETRY_BACKOFF_SECS)
        return await client.extract(image_bytes, PROMPT_VERSION)


async def _process_single(
    image_bytes: bytes,
    verify_request: VerifyRequest,
    client: VisionClient | None,
) -> tuple[VerifyResponse, str, LabelExtraction | None]:
    """Core verification pipeline for one image.

    Returns (VerifyResponse, image_sha256_hex, extraction).
    The extraction is returned separately (not folded into the response) so the
    audit layer can persist it without leaking provider-specific fields onto
    the public HTTP contract. extraction is None when the vision call fails.
    Never raises — failures are captured in VerifyResponse.
    """
    request_id = verify_request.request_id or str(uuid.uuid4())
    image_sha256 = _sha256_hex(image_bytes)

    total_start = time.perf_counter()

    # --- Vision call with retry (FR-012) ---
    vision_start = time.perf_counter()
    extraction_failed = False
    extraction: LabelExtraction | None = None

    try:
        extraction = await _call_with_retry(client, image_bytes)
    except Exception:
        extraction_failed = True

    vision_ms = int((time.perf_counter() - vision_start) * 1000)

    if extraction_failed or extraction is None:
        total_ms = int((time.perf_counter() - total_start) * 1000)
        response = _build_extraction_failed_response(request_id)
        response.latency_ms = LatencyMs(vision=vision_ms, compare=0, total=total_ms)
        return response, image_sha256, None

    # --- Comparators + verdict ---
    compare_start = time.perf_counter()
    field_results = _run_comparators(verify_request, extraction)
    overall = compute_overall_verdict(field_results, extraction)
    compare_ms = int((time.perf_counter() - compare_start) * 1000)

    total_ms = int((time.perf_counter() - total_start) * 1000)
    latency = LatencyMs(vision=vision_ms, compare=compare_ms, total=total_ms)

    response = VerifyResponse(
        request_id=request_id,
        overall_verdict=overall,
        fields=field_results,
        latency_ms=latency,
    )
    return response, image_sha256, extraction


def _write_audit(
    response: VerifyResponse,
    image_sha256: str,
    verify_request: VerifyRequest,
    extraction: LabelExtraction | None,
    batch_id: str | None = None,
) -> None:
    """Append one audit record to the JSONL log — FR-013.

    batch_id is set for items processed via /verify/batch and None for
    /verify, so ops can correlate all rows from one bulk submission.
    """
    write_audit_record({
        "ts": datetime.now(UTC).isoformat(),
        "request_id": response.request_id,
        "batch_id": batch_id,
        "image_sha256": image_sha256,
        "model_id": MODEL_ID,
        "prompt_version": PROMPT_VERSION,
        "form_fields": verify_request.model_dump(),
        "extracted": extraction.model_dump() if extraction else None,
        "field_results": [f.model_dump() for f in response.fields],
        "overall_verdict": response.overall_verdict.value,
        "latency_ms": response.latency_ms.model_dump(),
    })


def _write_failure_audit(
    reason: str,
    *,
    batch_id: str,
    image_bytes: bytes | None,
    raw_payload: dict | None,
) -> None:
    """Audit record for a /verify/batch row that failed before reaching
    `_process_single` — base64 decode, MIME validation, payload parse.

    FR-013 requires one audit record per request. Without this helper the
    three early-exit branches in `verify_batch` emit error SSE frames but
    write nothing to the log, so the request is invisible at replay time.
    The record is structurally identical to a successful one (same keys,
    same shape) so JSONL consumers don't need a special case.
    """
    request_id = str(uuid.uuid4())
    image_sha256 = _sha256_hex(image_bytes) if image_bytes is not None else ""
    write_audit_record({
        "ts": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "batch_id": batch_id,
        "image_sha256": image_sha256,
        "model_id": MODEL_ID,
        "prompt_version": PROMPT_VERSION,
        "form_fields": raw_payload if isinstance(raw_payload, dict) else {},
        "extracted": None,
        "field_results": [
            {
                "name": "validation",
                "verdict": Verdict.FAIL.value,
                "confidence": 0.0,
                "detail": reason,
            }
        ],
        "overall_verdict": Verdict.FAIL.value,
        "latency_ms": {"vision": 0, "compare": 0, "total": 0},
    })


# ---------------------------------------------------------------------------
# POST /verify (FR-001)
# ---------------------------------------------------------------------------


@router.post("/verify", response_model=VerifyResponse)
async def verify_label(
    request: Request,
    image: UploadFile = File(...),
    payload: str = Form(...),
    client: VisionClient | None = Depends(get_openai_client),
) -> JSONResponse | VerifyResponse:
    """Single-label verification — FR-001, FR-002, FR-003, FR-012, FR-013."""
    # Parse the form JSON payload
    try:
        payload_data = json.loads(payload)
        verify_request = VerifyRequest(**payload_data)
    except Exception as exc:
        return _error_response(
            ErrorCode.VALIDATION_ERROR,
            f"Invalid payload JSON: {exc}",
            400,
        )

    # Read and validate image bytes (FR-002)
    image_bytes = await image.read()

    validation_error = _validate_image(image_bytes)
    if validation_error is not None:
        return validation_error

    # Single source of truth: same pipeline as /verify/batch (FR-012, FR-013).
    response, image_sha256, extraction = await _process_single(
        image_bytes, verify_request, client
    )

    # Audit log (FR-013) — written for both success and extraction failure.
    _write_audit(response, image_sha256, verify_request, extraction)

    return response


# ---------------------------------------------------------------------------
# POST /verify/batch (FR-014)
# ---------------------------------------------------------------------------


@router.post("/verify/batch")
async def verify_batch(
    request: Request,
    client: VisionClient | None = Depends(get_openai_client),
):
    """Batch verification with SSE streaming — FR-014, §3.2."""
    body = await request.json()
    items_raw = body.get("items", [])

    if len(items_raw) > BATCH_MAX_ITEMS:
        return _error_response(
            ErrorCode.VALIDATION_ERROR,
            f"Batch exceeds maximum of {BATCH_MAX_ITEMS} items ({len(items_raw)} submitted).",
            400,
        )

    total = len(items_raw)
    batch_id = str(uuid.uuid4())
    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)

    async def process_item(index: int, item_raw: dict) -> dict:
        """Process one batch item; return an SSE-ready dict."""
        async with semaphore:
            raw_payload = item_raw.get("payload") if isinstance(item_raw, dict) else None

            # Decode base64 image
            try:
                image_bytes = base64.b64decode(item_raw.get("image_b64", ""))
            except Exception as exc:
                reason = f"base64 decode failed: {exc}"
                _write_failure_audit(
                    reason, batch_id=batch_id, image_bytes=None, raw_payload=raw_payload
                )
                return {
                    "event": "error",
                    "data": json.dumps({
                        "batch_id": batch_id,
                        "index": index,
                        "error": reason,
                    }),
                }

            # Validate MIME and size (FR-002)
            validation_error = _validate_image(image_bytes)
            if validation_error is not None:
                error_body = validation_error.body
                error_envelope = json.loads(error_body)
                reason = (
                    f"image_validation_failed: "
                    f"{error_envelope.get('error', {}).get('message', 'unknown')}"
                )
                _write_failure_audit(
                    reason,
                    batch_id=batch_id,
                    image_bytes=image_bytes,
                    raw_payload=raw_payload,
                )
                return {
                    "event": "error",
                    "data": json.dumps({
                        "batch_id": batch_id,
                        "index": index,
                        "error": error_envelope,
                    }),
                }

            # Parse payload
            try:
                verify_request = VerifyRequest(**item_raw.get("payload", {}))
            except Exception as exc:
                reason = f"invalid payload: {exc}"
                _write_failure_audit(
                    reason,
                    batch_id=batch_id,
                    image_bytes=image_bytes,
                    raw_payload=raw_payload,
                )
                return {
                    "event": "error",
                    "data": json.dumps({
                        "batch_id": batch_id,
                        "index": index,
                        "error": reason,
                    }),
                }

            # Run pipeline (FR-012: per-item retry, never whole-batch 503).
            response, image_sha256, extraction = await _process_single(
                image_bytes, verify_request, client
            )

            # Audit per item (FR-013) — full extraction, parity with /verify.
            _write_audit(response, image_sha256, verify_request, extraction, batch_id=batch_id)

            return {
                "event": "item",
                "data": json.dumps({
                    "batch_id": batch_id,
                    "index": index,
                    "result": response.model_dump(),
                }),
            }

    async def event_generator():
        done_count = 0

        async def run_indexed(i: int, item_raw: dict) -> tuple[int, dict | BaseException]:
            try:
                return (i, await process_item(i, item_raw))
            except Exception as exc:
                return (i, exc)

        tasks = [
            asyncio.create_task(run_indexed(i, item))
            for i, item in enumerate(items_raw)
        ]

        # Stream as tasks finish, but emit SSE in ascending index order (SPEC tests).
        buffer: dict[int, dict | BaseException] = {}
        next_index = 0

        for finished in asyncio.as_completed(tasks):
            idx, payload = await finished
            buffer[idx] = payload
            while next_index in buffer:
                raw = buffer.pop(next_index)
                next_index += 1
                if isinstance(raw, Exception):
                    yield {
                        "event": "error",
                        "data": json.dumps({"batch_id": batch_id, "error": str(raw)}),
                    }
                else:
                    done_count += 1
                    yield {
                        "event": "progress",
                        "data": json.dumps({
                            "batch_id": batch_id,
                            "done": done_count,
                            "total": total,
                        }),
                    }
                    yield raw

        yield {
            "event": "done",
            "data": json.dumps({"batch_id": batch_id, "total": total}),
        }

    return EventSourceResponse(event_generator())
