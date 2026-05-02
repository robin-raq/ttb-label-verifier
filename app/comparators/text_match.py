"""Brand and class/type comparators — SPEC §5.1, §5.2, FR-008, FR-009.

Pure functions: no I/O, no global state.
"""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

from app.schemas.api import FieldResult, Verdict

# SPEC §5.1: threshold for brand fuzzy-match (ratio is 0-100 scale from rapidfuzz)
_BRAND_RATIO_THRESHOLD = 92.0
_CONFIDENCE_THRESHOLD = 0.80

# Curly/smart quote characters → straight equivalents
_SMART_QUOTE_MAP = str.maketrans(
    "‘’“”′″",
    "''\"\"''",
)


def _normalize(text: str) -> str:
    """Normalize a string per SPEC §5.1:
    - NFKC Unicode normalization
    - Replace curly/smart quotes with straight equivalents
    - Collapse all whitespace runs to a single space and strip ends
    - Casefold
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_SMART_QUOTE_MAP)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def compare_brand(extracted: str, expected: str, conf: float) -> FieldResult:
    """SPEC §5.1, FR-008. name='brand'.

    Normalize both sides: NFKC, replace curly/smart quotes with straight,
    collapse whitespace, casefold. Use rapidfuzz.fuzz.ratio (returns 0-100;
    threshold is 92).

    Logic:
      conf < 0.80 → NEEDS_REVIEW
      ratio >= 92 → PASS (confidence = ratio/100, capped at conf)
      ratio < 92 → FAIL
    """
    if conf < _CONFIDENCE_THRESHOLD:
        return FieldResult(
            name="brand",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=conf,
            detail=f"low_confidence:{conf:.2f}",
        )

    norm_extracted = _normalize(extracted)
    norm_expected = _normalize(expected)
    ratio = fuzz.ratio(norm_extracted, norm_expected)

    if ratio >= _BRAND_RATIO_THRESHOLD:
        # Confidence is the similarity score, capped at extraction confidence
        similarity_conf = min(ratio / 100.0, conf)
        return FieldResult(
            name="brand",
            verdict=Verdict.PASS,
            confidence=similarity_conf,
        )

    return FieldResult(
        name="brand",
        verdict=Verdict.FAIL,
        confidence=conf,
        detail=f"ratio:{ratio:.1f}<{_BRAND_RATIO_THRESHOLD}",
    )


def compare_class_type(extracted: str, expected: str, conf: float) -> FieldResult:
    """SPEC §5.2, FR-009. name='class_type'. Form ⊆ label.

    Normalize identically to compare_brand on both sides.

    Logic:
      conf < 0.80 → NEEDS_REVIEW
      normalized(form) in normalized(label) → PASS
      otherwise → FAIL

    Note: extracted is the label value; expected is the form value.
    The form (expected) must be a substring of the label (extracted).
    """
    if conf < _CONFIDENCE_THRESHOLD:
        return FieldResult(
            name="class_type",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=conf,
            detail=f"low_confidence:{conf:.2f}",
        )

    norm_label = _normalize(extracted)
    norm_form = _normalize(expected)

    if norm_form in norm_label:
        return FieldResult(
            name="class_type",
            verdict=Verdict.PASS,
            confidence=conf,
        )

    return FieldResult(
        name="class_type",
        verdict=Verdict.FAIL,
        confidence=conf,
        detail="form_not_substring_of_label",
    )
