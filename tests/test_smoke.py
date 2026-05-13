"""Foundation smoke test — fails fast if the baseline is broken.

These tests exist to catch packaging mistakes (missing __init__.py, wrong
imports) and protect the few invariants every comparator depends on.
"""
from __future__ import annotations

from app.constants.ttb_warning import CANONICAL_WARNING
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
from app.schemas.extraction import FieldConfidence
from app.verdict import compute_overall_verdict


def test_canonical_warning_starts_with_prefix() -> None:
    assert CANONICAL_WARNING.startswith("GOVERNMENT WARNING:")


def test_canonical_warning_ends_with_period() -> None:
    assert CANONICAL_WARNING.endswith(".")


def test_canonical_warning_is_single_paragraph() -> None:
    assert "\n" not in CANONICAL_WARNING
    assert "\r" not in CANONICAL_WARNING


def test_canonical_warning_long_enough() -> None:
    assert len(CANONICAL_WARNING) > 200


def test_field_confidence_required_keys() -> None:
    expected = {
        "brand_name",
        "class_type",
        "abv_percent",
        "net_contents",
        "warning_text",
        "warning_prefix_all_caps",
        "warning_prefix_bold",
        "image_quality",
    }
    assert set(FieldConfidence.model_fields.keys()) == expected


def test_verdict_three_states() -> None:
    assert {v.value for v in Verdict} == {"PASS", "FAIL", "NEEDS_REVIEW"}


def test_error_codes_match_spec() -> None:
    assert {c.value for c in ErrorCode} == {
        "INVALID_IMAGE_TYPE",
        "FILE_TOO_LARGE",
        "VALIDATION_ERROR",
        "EXTRACTION_FAILED",
    }


def test_compute_overall_verdict_all_pass(make_extraction) -> None:
    fields = [
        FieldResult(name="brand", verdict=Verdict.PASS, confidence=0.94),
        FieldResult(name="abv", verdict=Verdict.PASS, confidence=0.99),
    ]
    assert compute_overall_verdict(fields, make_extraction()) is Verdict.PASS


def test_compute_overall_verdict_any_fail_wins(make_extraction) -> None:
    fields = [
        FieldResult(name="brand", verdict=Verdict.PASS, confidence=0.94),
        FieldResult(name="abv", verdict=Verdict.FAIL, confidence=0.99),
        FieldResult(name="warning", verdict=Verdict.NEEDS_REVIEW, confidence=0.7),
    ]
    assert compute_overall_verdict(fields, make_extraction()) is Verdict.FAIL


def test_compute_overall_verdict_needs_review_when_no_fail(make_extraction) -> None:
    fields = [
        FieldResult(name="brand", verdict=Verdict.PASS, confidence=0.94),
        FieldResult(name="abv", verdict=Verdict.NEEDS_REVIEW, confidence=0.7),
    ]
    assert compute_overall_verdict(fields, make_extraction()) is Verdict.NEEDS_REVIEW


def test_fr_017_image_quality_gate_downgrades_pass(make_extraction) -> None:
    """FR-017: provisional PASS + image_quality 'poor' → NEEDS_REVIEW."""
    fields = [FieldResult(name="brand", verdict=Verdict.PASS, confidence=0.94)]
    extraction = make_extraction(image_quality="poor")
    assert compute_overall_verdict(fields, extraction) is Verdict.NEEDS_REVIEW


def test_fr_017_does_not_upgrade_fail(make_extraction) -> None:
    """FR-017: image_quality 'poor' MUST NOT upgrade FAIL — wrong label stays FAIL."""
    fields = [FieldResult(name="abv", verdict=Verdict.FAIL, confidence=0.99)]
    extraction = make_extraction(image_quality="poor")
    assert compute_overall_verdict(fields, extraction) is Verdict.FAIL


def test_pydantic_models_construct() -> None:
    """Sanity check that the API schema models all instantiate cleanly."""
    req = VerifyRequest(
        brand="OLD TOM",
        class_type="Bourbon",
        abv_percent=45.0,
        net_contents="750 mL",
    )
    assert req.brand == "OLD TOM"
    resp = VerifyResponse(
        request_id="abc",
        overall_verdict=Verdict.PASS,
        fields=[FieldResult(name="brand", verdict=Verdict.PASS, confidence=0.9)],
        latency_ms=LatencyMs(vision=100, compare=5, total=120),
    )
    assert resp.overall_verdict is Verdict.PASS
    err = ErrorResponse(error=ErrorEnvelope(code=ErrorCode.FILE_TOO_LARGE, message="too big"))
    assert err.error.code is ErrorCode.FILE_TOO_LARGE
