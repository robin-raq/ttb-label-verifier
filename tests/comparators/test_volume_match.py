"""Tests for app.comparators.volume_match — FR-011, SPEC §5.4.

Covers mL/L/fl-oz conversions, tolerance boundary (1.0 mL), and garbage input.
"""
from __future__ import annotations

from app.comparators.volume_match import compare_volume
from app.schemas.api import Verdict

# 1 fl oz = 29.5735 mL (spec-defined constant)
FL_OZ_TO_ML = 29.5735


class TestCompareVolumePass:
    def test_identical_ml(self):
        result = compare_volume("750 mL", "750 mL", 0.96)
        assert result.name == "net_contents"
        assert result.verdict == Verdict.PASS

    def test_litres_vs_ml(self):
        # 0.75 L == 750 mL (within 1 mL)
        result = compare_volume("0.75 L", "750 mL", 0.96)
        assert result.verdict == Verdict.PASS

    def test_fl_oz_vs_ml_round_trip(self):
        # 25.36 fl oz * 29.5735 = 749.984... mL — well within 1 mL of 750
        result = compare_volume("25.36 fl oz", "750 mL", 0.96)
        assert result.verdict == Verdict.PASS

    def test_ml_no_space_uppercase(self):
        # "750ML" — no space, uppercase — should still parse
        result = compare_volume("750ML", "750 mL", 0.96)
        assert result.verdict == Verdict.PASS

    def test_litres_lowercase(self):
        # "0.75 l" lowercase — should parse as litres
        result = compare_volume("0.75 l", "750 mL", 0.96)
        assert result.verdict == Verdict.PASS

    def test_at_tolerance_boundary_exactly_1ml(self):
        # 751 mL vs 750 mL — diff = 1.0 exactly — PASS (<=1.0)
        result = compare_volume("751 mL", "750 mL", 0.96)
        assert result.verdict == Verdict.PASS

    def test_confidence_on_pass(self):
        result = compare_volume("750 mL", "750 mL", 0.96)
        assert 0.0 <= result.confidence <= 1.0


class TestCompareVolumeFail:
    def test_500ml_vs_750ml(self):
        # 250 mL difference >> 1 mL → FAIL
        result = compare_volume("500 mL", "750 mL", 0.96)
        assert result.verdict == Verdict.FAIL

    def test_just_over_tolerance(self):
        # 751.01 mL vs 750 mL — diff just over 1.0 mL
        result = compare_volume("751.01 mL", "750 mL", 0.96)
        assert result.verdict == Verdict.FAIL

    def test_name_is_net_contents(self):
        result = compare_volume("500 mL", "750 mL", 0.96)
        assert result.name == "net_contents"


class TestCompareVolumeNeedsReview:
    def test_garbage_extracted_string(self):
        result = compare_volume("foo bar", "750 mL", 0.96)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_garbage_expected_string(self):
        result = compare_volume("750 mL", "foo bar", 0.96)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_garbage_both_strings(self):
        result = compare_volume("foo bar", "baz qux", 0.96)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_parse_failed_reason_in_detail(self):
        result = compare_volume("foo bar", "750 mL", 0.96)
        assert result.detail is not None
        assert "parse_failed" in result.detail

    def test_low_confidence_returns_needs_review(self):
        result = compare_volume("750 mL", "750 mL", 0.79)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_low_confidence_even_identical(self):
        result = compare_volume("750 mL", "750 mL", 0.50)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_confidence_at_threshold(self):
        # Exactly 0.80 passes through to comparator
        result = compare_volume("750 mL", "750 mL", 0.80)
        assert result.verdict == Verdict.PASS

    def test_confidence_stored_on_result(self):
        result = compare_volume("750 mL", "750 mL", 0.79)
        assert 0.0 <= result.confidence <= 1.0
