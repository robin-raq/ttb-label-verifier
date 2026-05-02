"""ABV comparator — FR-010, SPEC §5.4.

Pure function: no I/O, no global state.
"""
from __future__ import annotations

from app.schemas.api import FieldResult, Verdict

_CONFIDENCE_THRESHOLD = 0.80
_ABV_TOLERANCE = 0.1  # ±0.1 percentage points


def compare_abv(extracted: float | None, expected: float, conf: float) -> FieldResult:
    """FR-010. name='abv'. ±0.1 percentage points.

    Logic:
      extracted is None → NEEDS_REVIEW (reason 'extraction_null')
      conf < 0.80 → NEEDS_REVIEW
      |extracted - expected| <= 0.1 → PASS
      otherwise → FAIL
    """
    if extracted is None:
        return FieldResult(
            name="abv",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=conf,
            detail="extraction_null",
        )

    if conf < _CONFIDENCE_THRESHOLD:
        return FieldResult(
            name="abv",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=conf,
            detail=f"low_confidence:{conf:.2f}",
        )

    # Round to 10 decimal places to handle IEEE 754 floating-point representation
    # (e.g. abs(45.1 - 45.0) = 0.10000000000000142 in binary float).
    diff = round(abs(extracted - expected), 10)
    if diff <= _ABV_TOLERANCE:
        return FieldResult(
            name="abv",
            verdict=Verdict.PASS,
            confidence=conf,
        )

    return FieldResult(
        name="abv",
        verdict=Verdict.FAIL,
        confidence=conf,
        detail=f"abv_diff:{diff:.4f}>tolerance:{_ABV_TOLERANCE}",
    )
