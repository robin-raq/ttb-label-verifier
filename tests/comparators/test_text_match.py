"""Tests for app.comparators.text_match — SPEC §5.1, §5.2, FR-008, FR-009.

Covers brand fuzzy-match and class/type substring rules per the §7.4 catalog.
"""
from __future__ import annotations

import pytest

from app.comparators.text_match import compare_brand, compare_class_type
from app.schemas.api import Verdict


# ---------------------------------------------------------------------------
# compare_brand — SPEC §5.1, FR-008
# ---------------------------------------------------------------------------


class TestCompareBrandPass:
    def test_identical_strings(self):
        result = compare_brand("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", 0.95)
        assert result.name == "brand"
        assert result.verdict == Verdict.PASS

    def test_case_difference(self):
        # casefold normalizes so "old tom distillery" == "OLD TOM DISTILLERY"
        result = compare_brand("old tom distillery", "OLD TOM DISTILLERY", 0.95)
        assert result.verdict == Verdict.PASS

    def test_smart_apostrophe_normalized(self):
        # STONE’S vs Stone's — smart apostrophe replaced with straight
        result = compare_brand("STONE’S GIN", "Stone's Gin", 0.95)
        assert result.verdict == Verdict.PASS

    def test_extra_whitespace_collapsed(self):
        result = compare_brand("OLD  TOM   DISTILLERY", "OLD TOM DISTILLERY", 0.95)
        assert result.verdict == Verdict.PASS

    def test_close_match_above_threshold(self):
        # "OLD TOM DISTILLERY" vs "OLD TOM DISTILERY" — one missing L
        # Ratio should be high enough (> 0.92) for PASS
        result = compare_brand("OLD TOM DISTILERY", "OLD TOM DISTILLERY", 0.95)
        assert result.verdict == Verdict.PASS

    def test_confidence_set_on_pass(self):
        result = compare_brand("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", 0.95)
        assert 0.0 <= result.confidence <= 1.0


class TestCompareBrandFail:
    def test_one_letter_typo_below_92(self):
        # Very short string with significant divergence — should produce ratio < 92
        result = compare_brand("ABCDE", "XBCDE", 0.95)
        assert result.verdict == Verdict.FAIL

    def test_completely_different_brands(self):
        result = compare_brand("TOTALLY DIFFERENT BRAND", "OLD TOM DISTILLERY", 0.95)
        assert result.verdict == Verdict.FAIL


class TestCompareBrandNeedsReview:
    def test_low_confidence_returns_needs_review(self):
        # conf < 0.80 → NEEDS_REVIEW regardless of text similarity
        result = compare_brand("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", 0.79)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_low_confidence_exactly_at_boundary(self):
        # conf = 0.79 (just below 0.80) → NEEDS_REVIEW
        result = compare_brand("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", 0.79)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_confidence_at_threshold_passes_text_check(self):
        # conf = 0.80 (exactly at threshold) → allow comparator to decide
        result = compare_brand("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", 0.80)
        assert result.verdict == Verdict.PASS

    def test_confidence_field_in_range(self):
        result = compare_brand("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", 0.79)
        assert 0.0 <= result.confidence <= 1.0

    def test_name_is_brand(self):
        result = compare_brand("X", "X", 0.90)
        assert result.name == "brand"


# ---------------------------------------------------------------------------
# compare_class_type — SPEC §5.2, FR-009
# ---------------------------------------------------------------------------


class TestCompareClassTypePass:
    def test_form_fully_contained_in_label(self):
        label = "Kentucky Straight Bourbon Whiskey, Aged 12 Years"
        form = "Bourbon"
        result = compare_class_type(label, form, 0.95)
        assert result.name == "class_type"
        assert result.verdict == Verdict.PASS

    def test_form_equals_label(self):
        # Exact match trivially satisfies form ⊆ label
        result = compare_class_type(
            "Kentucky Straight Bourbon Whiskey",
            "Kentucky Straight Bourbon Whiskey",
            0.95,
        )
        assert result.verdict == Verdict.PASS

    def test_case_insensitive_containment(self):
        # After casefold, "bourbon" should be found in label
        result = compare_class_type(
            "Kentucky Straight Bourbon Whiskey",
            "bourbon",
            0.95,
        )
        assert result.verdict == Verdict.PASS

    def test_form_is_full_phrase_in_longer_label(self):
        result = compare_class_type(
            "Kentucky Straight Bourbon Whiskey, Aged 12 Years",
            "Kentucky Straight Bourbon Whiskey",
            0.95,
        )
        assert result.verdict == Verdict.PASS

    def test_confidence_set_on_pass(self):
        result = compare_class_type("Bourbon Whiskey", "Bourbon", 0.95)
        assert 0.0 <= result.confidence <= 1.0


class TestCompareClassTypeFail:
    def test_form_not_contained_in_label(self):
        result = compare_class_type("Tequila", "Vodka", 0.95)
        assert result.verdict == Verdict.FAIL

    def test_reverse_substring_fails(self):
        # form LONGER than label — label is substring of form, not vice versa
        # Per SPEC §5.2: "form ⊆ label" — if label ⊆ form only, that's FAIL
        form = "Kentucky Straight Bourbon Whiskey, Aged 12 Years"
        label = "Kentucky Straight Bourbon Whiskey"
        result = compare_class_type(label, form, 0.95)
        assert result.verdict == Verdict.FAIL

    def test_partial_word_not_matching_full_label(self):
        # "Vodka" not in "Kentucky Straight Bourbon Whiskey"
        result = compare_class_type(
            "Kentucky Straight Bourbon Whiskey",
            "Vodka",
            0.95,
        )
        assert result.verdict == Verdict.FAIL


class TestCompareClassTypeNeedsReview:
    def test_low_confidence_returns_needs_review(self):
        result = compare_class_type("Bourbon Whiskey", "Bourbon", 0.79)
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_low_confidence_even_if_text_would_pass(self):
        result = compare_class_type(
            "Kentucky Straight Bourbon Whiskey",
            "Bourbon",
            0.75,
        )
        assert result.verdict == Verdict.NEEDS_REVIEW

    def test_confidence_at_exact_threshold(self):
        # 0.80 should be allowed through (>= 0.80)
        result = compare_class_type("Bourbon Whiskey", "Bourbon", 0.80)
        assert result.verdict == Verdict.PASS

    def test_name_is_class_type(self):
        result = compare_class_type("Bourbon", "Bourbon", 0.90)
        assert result.name == "class_type"
