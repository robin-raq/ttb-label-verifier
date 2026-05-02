"""Net contents (volume) comparator — FR-011, SPEC §5.4.

Parses mL, L, fl oz strings and compares after converting to millilitres.
Pure function: no I/O, no global state.
"""
from __future__ import annotations

import re

from app.schemas.api import FieldResult, Verdict

_CONFIDENCE_THRESHOLD = 0.80
_VOLUME_TOLERANCE_ML = 1.0  # ±1.0 mL absolute difference
_FL_OZ_TO_ML = 29.5735  # exact conversion constant per SPEC FR-011


def _parse_ml(volume_str: str) -> float | None:
    """Parse a volume string and return its value in millilitres.

    Supports:
      - "750 mL", "750mL", "750ML", "750 ml" → 750.0 mL
      - "0.75 L", "0.75 l", "0.75L" → 750.0 mL
      - "25.36 fl oz", "25.36 fl. oz", "25.36 oz" → 749.984... mL

    Returns None if the string cannot be parsed.
    """
    text = volume_str.strip()

    # Try mL: "750 mL", "750mL", "750 ml", "750ML" (no space OK)
    ml_match = re.match(r"^(\d+(?:\.\d+)?)\s*ml$", text, re.IGNORECASE)
    if ml_match:
        return float(ml_match.group(1))

    # Try litres: "0.75 L", "0.75L", "0.75 l"
    l_match = re.match(r"^(\d+(?:\.\d+)?)\s*l$", text, re.IGNORECASE)
    if l_match:
        return float(l_match.group(1)) * 1000.0

    # Try fl oz: "25.36 fl oz", "25.36 fl. oz", "25.36 oz"
    floz_match = re.match(
        r"^(\d+(?:\.\d+)?)\s*(?:fl\.?\s*oz|oz)$", text, re.IGNORECASE
    )
    if floz_match:
        return float(floz_match.group(1)) * _FL_OZ_TO_ML

    return None


def compare_volume(extracted: str, expected: str, conf: float) -> FieldResult:
    """FR-011 / SPEC §5.4. name='net_contents'.

    Parse mL, L, fl oz on both sides; convert to mL float. 1 fl oz = 29.5735 mL.

    Logic:
      conf < 0.80 → NEEDS_REVIEW
      either parse fails → NEEDS_REVIEW (reason 'parse_failed')
      |label_mL - form_mL| <= 1.0 → PASS
      otherwise → FAIL
    """
    if conf < _CONFIDENCE_THRESHOLD:
        return FieldResult(
            name="net_contents",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=conf,
            detail=f"low_confidence:{conf:.2f}",
        )

    label_ml = _parse_ml(extracted)
    form_ml = _parse_ml(expected)

    if label_ml is None or form_ml is None:
        failed_side = "extracted" if label_ml is None else "expected"
        return FieldResult(
            name="net_contents",
            verdict=Verdict.NEEDS_REVIEW,
            confidence=conf,
            detail=f"parse_failed:{failed_side}",
        )

    diff = abs(label_ml - form_ml)
    if diff <= _VOLUME_TOLERANCE_ML:
        return FieldResult(
            name="net_contents",
            verdict=Verdict.PASS,
            confidence=conf,
        )

    return FieldResult(
        name="net_contents",
        verdict=Verdict.FAIL,
        confidence=conf,
        detail=f"volume_diff:{diff:.3f}mL>tolerance:{_VOLUME_TOLERANCE_ML}mL",
    )
