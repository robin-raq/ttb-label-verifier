"""Tests for app.comparators.numeric_match — FR-010, SPEC §5.4.

Covers ABV ±0.1 percentage point tolerance plus null/low-confidence paths.
"""
from __future__ import annotations

from app.comparators.numeric_match import compare_abv
from app.schemas.api import Verdict


class TestCompareAbvPass:
    def test_exact_match(self):
        result = compare_abv(45.0, 45.0, 0.99)
        assert result.name == "abv"
        assert result.verdict == Verdict.PASS

    def test_within_tolerance_above(self):
        result = compare_abv(45.05, 45.0, 0.99)
        assert result.verdict == Verdict.PASS

    def test_within_tolerance_below(self):
        result = compare_abv(44.95, 45.0, 0.99)
        assert result.verdict == Verdict.PASS

    def test_at_upper_boundary(self):
        # 45.1 vs 45.0 — difference = 0.1 exactly — should PASS (<=0.1)
        result = compare_abv(45.1, 45.0, 0.99)
        assert result.verdict == Verdict.PASS

    def test_at_lower_boundary(self):
        # 44.9 vs 45.0 — difference = 0.1 exactly — should PASS (<=0.1)
        result = compare_abv(44.9, 45.0, 0.99)
        assert result.verdict == Verdict.PASS

    def test_confidence_set_on_pass(self):
        result = compare_abv(45.0, 45.0, 0.95)
        assert 0.0 <= result.confidence <= 1.0


class TestCompareAbvFail:
    def test_outside_tolerance(self):
        # 45.5 vs 45.0 — difference = 0.5 > 0.1 — FAIL
        result = compare_abv(45.5, 45.0, 0.99)
        assert result.verdict == Verdict.FAIL

    def test_just_outside_upper_boundary(self):
        # 45.10001 vs 45.0 — fractionally above boundary
        # Consistent rule: abs diff > 0.1 → FAIL
        result = compare_abv(45.10001, 45.0, 0.99)
        assert result.verdict == Verdict.FAIL

    def test_very_different_abv(self):
        result = compare_abv(80.0, 45.0, 0.99)
        assert result.verdict == Verdict.FAIL

    def test_name_is_abv(self):
        result = compare_abv(45.5, 45.0, 0.99)
        assert result.name == "abv"


class TestCompareAbvNeedsReview:
    def test_extracted_none_returns_needs_review(self):
        result = compare_abv(None, 45.0, 0.99)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_extracted_none_reason_extraction_null(self):
        result = compare_abv(None, 45.0, 0.99)
        assert result.detail is not None
        assert "extraction_null" in result.detail

    def test_low_confidence_returns_needs_review(self):
        result = compare_abv(45.0, 45.0, 0.79)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_low_confidence_even_exact_match(self):
        result = compare_abv(45.0, 45.0, 0.50)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_confidence_at_threshold(self):
        # Exactly 0.80 should pass through to comparator
        result = compare_abv(45.0, 45.0, 0.80)
        assert result.verdict == Verdict.PASS

    def test_confidence_stored_on_result(self):
        result = compare_abv(45.0, 45.0, 0.79)
        assert 0.0 <= result.confidence <= 1.0

    def test_none_checked_before_confidence(self):
        # extracted is None AND conf < 0.80 — None check is first per spec contract
        result = compare_abv(None, 45.0, 0.79)
        assert result.verdict == Verdict.NEEDS_REVIEW
        assert result.detail is not None
        assert "extraction_null" in result.detail
