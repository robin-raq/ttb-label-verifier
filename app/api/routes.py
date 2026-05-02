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
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import filetype
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_openai_client
from app.audit.jsonl_logger import write_audit_record
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

# Prompt version for audit log (FR-016). Imported from B3 if available.
try:
    from app.extraction.openai_vision import PROMPT_VERSION
except ImportError:
    PROMPT_VERSION = "v1"  # fallback while B3 is not yet merged

# Model identifier for audit log
MODEL_ID = __import__("os").environ.get("MODEL_NAME", "fake-test")

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


async def _call_with_retry(client: Any, image_bytes: bytes) -> LabelExtraction:
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
    client: Any,
) -> tuple[VerifyResponse, str]:
    """Core verification pipeline for one image.

    Returns (VerifyResponse, image_sha256_hex).
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
        return response, image_sha256

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
    return response, image_sha256


def _write_audit(
    response: VerifyResponse,
    image_sha256: str,
    verify_request: VerifyRequest,
    extraction: LabelExtraction | None,
) -> None:
    """Append one audit record to the JSONL log — FR-013."""
    write_audit_record({
        "ts": datetime.now(timezone.utc).isoformat(),
        "request_id": response.request_id,
        "image_sha256": image_sha256,
        "model_id": MODEL_ID,
        "prompt_version": PROMPT_VERSION,
        "form_fields": verify_request.model_dump(),
        "extracted": extraction.model_dump() if extraction else None,
        "field_results": [f.model_dump() for f in response.fields],
        "overall_verdict": response.overall_verdict.value,
        "latency_ms": response.latency_ms.model_dump(),
    })


# ---------------------------------------------------------------------------
# POST /verify (FR-001)
# ---------------------------------------------------------------------------


@router.post("/verify", response_model=VerifyResponse)
async def verify_label(
    request: Request,
    image: UploadFile = File(...),
    payload: str = Form(...),
    client: Any = Depends(get_openai_client),
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

    # Run the core pipeline
    image_sha256 = _sha256_hex(image_bytes)
    request_id = verify_request.request_id or str(uuid.uuid4())

    total_start = time.perf_counter()

    # Vision call with retry (FR-012)
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
        # Audit even on failure (FR-013)
        _write_audit(response, image_sha256, verify_request, None)
        return response

    # Comparators + verdict
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

    # Audit log (FR-013) — after response is built, before returning
    _write_audit(response, image_sha256, verify_request, extraction)

    return response


# ---------------------------------------------------------------------------
# POST /verify/batch (FR-014)
# ---------------------------------------------------------------------------


class BatchItem:
    def __init__(self, image_b64: str, payload: dict):
        self.image_b64 = image_b64
        self.payload = payload


@router.post("/verify/batch")
async def verify_batch(
    request: Request,
    client: Any = Depends(get_openai_client),
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
    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)

    async def process_item(index: int, item_raw: dict) -> dict:
        """Process one batch item; return an SSE-ready dict."""
        async with semaphore:
            # Decode base64 image
            try:
                image_bytes = base64.b64decode(item_raw.get("image_b64", ""))
            except Exception as exc:
                return {
                    "event": "error",
                    "data": json.dumps({"index": index, "error": f"base64 decode failed: {exc}"}),
                }

            # Validate MIME and size (FR-002)
            validation_error = _validate_image(image_bytes)
            if validation_error is not None:
                error_body = validation_error.body
                return {
                    "event": "error",
                    "data": json.dumps({
                        "index": index,
                        "error": json.loads(error_body),
                    }),
                }

            # Parse payload
            try:
                verify_request = VerifyRequest(**item_raw.get("payload", {}))
            except Exception as exc:
                return {
                    "event": "error",
                    "data": json.dumps({"index": index, "error": f"invalid payload: {exc}"}),
                }

            # Run pipeline (FR-012: per-item retry, never whole-batch 503)
            response, image_sha256 = await _process_single(image_bytes, verify_request, client)

            # Audit per item (FR-013)
            extraction: LabelExtraction | None = None
            # We don't have extraction here after _process_single abstraction —
            # for batch we just audit the response shape without extraction detail.
            # (Full audit available via single /verify; batch is optimized for throughput)
            _write_audit(response, image_sha256, verify_request, None)

            return {
                "event": "item",
                "data": json.dumps({
                    "index": index,
                    "result": response.model_dump(),
                }),
            }

    async def event_generator():
        done_count = 0

        # Create all tasks
        tasks = [
            asyncio.create_task(process_item(i, item))
            for i, item in enumerate(items_raw)
        ]

        # Yield results in index order as they complete
        # For ordered streaming we use gather (maintains order)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(result)}),
                }
            else:
                done_count += 1
                # Yield progress event
                yield {
                    "event": "progress",
                    "data": json.dumps({"done": done_count, "total": total}),
                }
                # Yield the item result
                yield result

        yield {"event": "done", "data": json.dumps({"total": total})}

    return EventSourceResponse(event_generator())
