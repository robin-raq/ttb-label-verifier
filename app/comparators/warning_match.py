"""Government Warning comparators — FR-005, FR-006, FR-007, SPEC §5.3.

Returns exactly 3 FieldResult objects: warning_text, warning_caps, warning_bold.
Pure function: no I/O, no global state.
"""
from __future__ import annotations

import re

from app.constants.ttb_warning import CANONICAL_WARNING
from app.schemas.api import FieldResult, Verdict
from app.schemas.extraction import LabelExtraction

_WARNING_CONF_THRESHOLD = 0.95
_CAPS_PREFIX_PATTERN = re.compile(r"^GOVERNMENT WARNING:")


def _normalize_warning(text: str) -> str:
    """Normalize warning text per SPEC §5.3:
    Replace runs of whitespace (including newlines) with a single space, then trim.
    """
    return re.sub(r"\s+", " ", text).strip()


def compare_warning(extraction: LabelExtraction) -> list[FieldResult]:
    """FR-005, FR-006, FR-007 / SPEC §5.3.

    Returns EXACTLY 3 FieldResult objects in this order:
      [0] warning_text  — FR-005
      [1] warning_caps  — FR-006
      [2] warning_bold  — FR-007
    """
    fc = extraction.field_confidence

    # ------------------------------------------------------------------
    # [0] warning_text — exact match after whitespace normalization
    # ------------------------------------------------------------------
    text_conf = fc.warning_text
    if text_conf < _WARNING_CONF_THRESHOLD:
        text_result = FieldResult(
            name="warning_text",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=text_conf,
            detail=f"low_confidence:{text_conf:.2f}",
        )
    else:
        normalized_extracted = _normalize_warning(extraction.warning_text)
        normalized_canonical = _normalize_warning(CANONICAL_WARNING)
        if normalized_extracted == normalized_canonical:
            text_result = FieldResult(
                name="warning_text",
                verdict=Verdict.PASS,
                confidence=text_conf,
            )
        else:
            text_result = FieldResult(
                name="warning_text",
                verdict=Verdict.FAIL,
                confidence=text_conf,
                detail="warning_text_mismatch",
            )

    # ------------------------------------------------------------------
    # [1] warning_caps — prefix must be "GOVERNMENT WARNING:" AND flag True
    # ------------------------------------------------------------------
    caps_conf = fc.warning_prefix_all_caps
    if caps_conf < _WARNING_CONF_THRESHOLD:
        caps_result = FieldResult(
            name="warning_caps",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=caps_conf,
            detail=f"low_confidence:{caps_conf:.2f}",
        )
    else:
        trimmed = extraction.warning_text.strip()
        regex_matches = bool(_CAPS_PREFIX_PATTERN.match(trimmed))
        if regex_matches and extraction.warning_prefix_all_caps:
            caps_result = FieldResult(
                name="warning_caps",
                verdict=Verdict.PASS,
                confidence=caps_conf,
            )
        else:
            caps_result = FieldResult(
                name="warning_caps",
                verdict=Verdict.FAIL,
                confidence=caps_conf,
                detail="prefix_not_all_caps",
            )

    # ------------------------------------------------------------------
    # [2] warning_bold — model flag must be True
    # ------------------------------------------------------------------
    bold_conf = fc.warning_prefix_bold
    if bold_conf < _WARNING_CONF_THRESHOLD:
        bold_result = FieldResult(
            name="warning_bold",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=bold_conf,
            detail=f"low_confidence:{bold_conf:.2f}",
        )
    elif extraction.warning_prefix_bold:
        bold_result = FieldResult(
            name="warning_bold",
            verdict=Verdict.PASS,
            confidence=bold_conf,
        )
    else:
        bold_result = FieldResult(
            name="warning_bold",
            verdict=Verdict.FAIL,
            confidence=bold_conf,
            detail="prefix_not_bold",
        )

    return [text_result, caps_result, bold_result]
