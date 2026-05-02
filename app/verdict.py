"""Overall-verdict precedence — SPEC §1 + FR-017.

Order of evaluation (first match wins):
  1. Any field FAIL → overall FAIL.
  2. Any field NEEDS_REVIEW → overall NEEDS_REVIEW.
  3. extraction.image_quality == "poor" → overall NEEDS_REVIEW (FR-017 gate).
  4. Otherwise → PASS.

Why FR-017 fires *after* (1) and (2): a definitively-wrong label stays FAIL
even on a bad photo. The image-quality gate only downgrades a provisional
PASS to NEEDS_REVIEW; it never upgrades a FAIL.
"""
from __future__ import annotations

from app.schemas.api import FieldResult, Verdict
from app.schemas.extraction import LabelExtraction


def compute_overall_verdict(
    field_results: list[FieldResult],
    extraction: LabelExtraction,
) -> Verdict:
    if any(r.verdict is Verdict.FAIL for r in field_results):
        return Verdict.FAIL
    if any(r.verdict is Verdict.NEEDS_REVIEW for r in field_results):
        return Verdict.NEEDS_REVIEW
    if extraction.image_quality == "poor":
        return Verdict.NEEDS_REVIEW
    return Verdict.PASS
