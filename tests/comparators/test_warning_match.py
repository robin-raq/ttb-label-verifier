"""Tests for app.comparators.warning_match — FR-005, FR-006, FR-007, SPEC §5.3.

Uses the make_extraction fixture from conftest.py as the happy-path base.
"""
from __future__ import annotations

from collections.abc import Callable

import pytest

from app.comparators.warning_match import compare_warning
from app.constants.ttb_warning import CANONICAL_WARNING
from app.schemas.api import Verdict
from app.schemas.extraction import FieldConfidence, LabelExtraction


# ---------------------------------------------------------------------------
# Happy-path — all three sub-results PASS
# ---------------------------------------------------------------------------


class TestCompareWarningHappyPath:
    def test_all_pass_with_canonical_text(self, make_extraction: Callable[..., LabelExtraction]):
        extraction = make_extraction()
        results = compare_warning(extraction)

        assert len(results) == 3
        names = [r.name for r in results]
        assert names == ["warning_text", "warning_caps", "warning_bold"]

        for r in results:
            assert r.verdict == Verdict.PASS, f"{r.name} should be PASS, got {r.verdict}"

    def test_returns_exactly_3_field_results(self, make_extraction: Callable[..., LabelExtraction]):
        results = compare_warning(make_extraction())
        assert len(results) == 3

    def test_result_order_is_text_caps_bold(self, make_extraction: Callable[..., LabelExtraction]):
        results = compare_warning(make_extraction())
        assert results[0].name == "warning_text"
        assert results[1].name == "warning_caps"
        assert results[2].name == "warning_bold"

    def test_confidence_values_in_range(self, make_extraction: Callable[..., LabelExtraction]):
        results = compare_warning(make_extraction())
        for r in results:
            assert 0.0 <= r.confidence <= 1.0


# ---------------------------------------------------------------------------
# warning_text — typo → FAIL; whitespace-only diff → PASS
# ---------------------------------------------------------------------------


class TestWarningText:
    def test_one_char_swap_fails(self, make_extraction: Callable[..., LabelExtraction]):
        # Swap "women" → "xomen" — should fail text check
        extraction = make_extraction(
            warning_text=CANONICAL_WARNING.replace("women", "xomen")
        )
        results = compare_warning(extraction)
        text_result = next(r for r in results if r.name == "warning_text")
        assert text_result.verdict == Verdict.FAIL

    def test_typo_does_not_affect_caps_and_bold(self, make_extraction: Callable[..., LabelExtraction]):
        extraction = make_extraction(
            warning_text=CANONICAL_WARNING.replace("women", "xomen")
        )
        results = compare_warning(extraction)
        caps_result = next(r for r in results if r.name == "warning_caps")
        bold_result = next(r for r in results if r.name == "warning_bold")
        assert caps_result.verdict == Verdict.PASS
        assert bold_result.verdict == Verdict.PASS

    def test_extra_spaces_normalize_to_pass(self, make_extraction: Callable[..., LabelExtraction]):
        # Insert extra spaces — after whitespace normalization should still match
        warning_with_extra_spaces = CANONICAL_WARNING.replace(
            "According to", "According  to"
        ).replace("birth defects.", "birth  defects.")
        extraction = make_extraction(warning_text=warning_with_extra_spaces)
        results = compare_warning(extraction)
        text_result = next(r for r in results if r.name == "warning_text")
        assert text_result.verdict == Verdict.PASS

    def test_newlines_normalize_to_pass(self, make_extraction: Callable[..., LabelExtraction]):
        # Replace spaces with newlines — should normalize to single space
        warning_with_newlines = CANONICAL_WARNING.replace(
            "According to", "According\nto"
        ).replace("birth defects.", "birth\ndefects.")
        extraction = make_extraction(warning_text=warning_with_newlines)
        results = compare_warning(extraction)
        text_result = next(r for r in results if r.name == "warning_text")
        assert text_result.verdict == Verdict.PASS

    def test_low_confidence_returns_needs_review_even_if_text_matches(
        self, make_extraction: Callable[..., LabelExtraction]
    ):
        # conf = 0.94 (just below 0.95 threshold) → NEEDS_REVIEW
        extraction = make_extraction(
            field_confidence=FieldConfidence(
                brand_name=0.95,
                class_type=0.92,
                abv_percent=0.99,
                net_contents=0.96,
                warning_text=0.94,  # below 0.95
                warning_prefix_all_caps=0.99,
                warning_prefix_bold=0.97,
                image_quality=0.94,
            )
        )
        results = compare_warning(extraction)
        text_result = next(r for r in results if r.name == "warning_text")
        assert text_result.verdict == Verdict.NEEDS_REVIEW

    def test_confidence_at_threshold_passes(self, make_extraction: Callable[..., LabelExtraction]):
        # conf = 0.95 exactly → allowed through
        extraction = make_extraction(
            field_confidence=FieldConfidence(
                brand_name=0.95,
                class_type=0.92,
                abv_percent=0.99,
                net_contents=0.96,
                warning_text=0.95,
                warning_prefix_all_caps=0.99,
                warning_prefix_bold=0.97,
                image_quality=0.94,
            )
        )
        results = compare_warning(extraction)
        text_result = next(r for r in results if r.name == "warning_text")
        assert text_result.verdict == Verdict.PASS


# ---------------------------------------------------------------------------
# warning_caps — title case prefix → FAIL; low conf → NEEDS_REVIEW
# ---------------------------------------------------------------------------


class TestWarningCaps:
    def test_title_case_prefix_fails(self, make_extraction: Callable[..., LabelExtraction]):
        # "Government Warning:" (title case) instead of "GOVERNMENT WARNING:"
        title_case_warning = CANONICAL_WARNING.replace(
            "GOVERNMENT WARNING:", "Government Warning:"
        )
        extraction = make_extraction(
            warning_text=title_case_warning,
            warning_prefix_all_caps=False,
        )
        results = compare_warning(extraction)
        caps_result = next(r for r in results if r.name == "warning_caps")
        assert caps_result.verdict == Verdict.FAIL

    def test_caps_false_flag_fails(self, make_extraction: Callable[..., LabelExtraction]):
        # Even with correct text, if warning_prefix_all_caps=False → FAIL
        extraction = make_extraction(warning_prefix_all_caps=False)
        results = compare_warning(extraction)
        caps_result = next(r for r in results if r.name == "warning_caps")
        assert caps_result.verdict == Verdict.FAIL

    def test_low_conf_caps_returns_needs_review(
        self, make_extraction: Callable[..., LabelExtraction]
    ):
        # conf = 0.94 (just below 0.95) → NEEDS_REVIEW
        extraction = make_extraction(
            field_confidence=FieldConfidence(
                brand_name=0.95,
                class_type=0.92,
                abv_percent=0.99,
                net_contents=0.96,
                warning_text=0.98,
                warning_prefix_all_caps=0.94,  # below 0.95
                warning_prefix_bold=0.97,
                image_quality=0.94,
            )
        )
        results = compare_warning(extraction)
        caps_result = next(r for r in results if r.name == "warning_caps")
        assert caps_result.verdict == Verdict.NEEDS_REVIEW

    def test_confidence_at_threshold_for_caps(
        self, make_extraction: Callable[..., LabelExtraction]
    ):
        extraction = make_extraction(
            field_confidence=FieldConfidence(
                brand_name=0.95,
                class_type=0.92,
                abv_percent=0.99,
                net_contents=0.96,
                warning_text=0.98,
                warning_prefix_all_caps=0.95,  # exactly 0.95
                warning_prefix_bold=0.97,
                image_quality=0.94,
            )
        )
        results = compare_warning(extraction)
        caps_result = next(r for r in results if r.name == "warning_caps")
        assert caps_result.verdict == Verdict.PASS


# ---------------------------------------------------------------------------
# warning_bold — bold=False → FAIL; low conf → NEEDS_REVIEW
# ---------------------------------------------------------------------------


class TestWarningBold:
    def test_bold_false_fails(self, make_extraction: Callable[..., LabelExtraction]):
        extraction = make_extraction(warning_prefix_bold=False)
        results = compare_warning(extraction)
        bold_result = next(r for r in results if r.name == "warning_bold")
        assert bold_result.verdict == Verdict.FAIL

    def test_low_conf_bold_returns_needs_review(
        self, make_extraction: Callable[..., LabelExtraction]
    ):
        # conf = 0.94 (just below 0.95) → NEEDS_REVIEW
        extraction = make_extraction(
            field_confidence=FieldConfidence(
                brand_name=0.95,
                class_type=0.92,
                abv_percent=0.99,
                net_contents=0.96,
                warning_text=0.98,
                warning_prefix_all_caps=0.99,
                warning_prefix_bold=0.94,  # below 0.95
                image_quality=0.94,
            )
        )
        results = compare_warning(extraction)
        bold_result = next(r for r in results if r.name == "warning_bold")
        assert bold_result.verdict == Verdict.NEEDS_REVIEW

    def test_confidence_at_threshold_for_bold(
        self, make_extraction: Callable[..., LabelExtraction]
    ):
        extraction = make_extraction(
            field_confidence=FieldConfidence(
                brand_name=0.95,
                class_type=0.92,
                abv_percent=0.99,
                net_contents=0.96,
                warning_text=0.98,
                warning_prefix_all_caps=0.99,
                warning_prefix_bold=0.95,  # exactly 0.95
                image_quality=0.94,
            )
        )
        results = compare_warning(extraction)
        bold_result = next(r for r in results if r.name == "warning_bold")
        assert bold_result.verdict == Verdict.PASS

    def test_bold_does_not_affect_text_or_caps(
        self, make_extraction: Callable[..., LabelExtraction]
    ):
        extraction = make_extraction(warning_prefix_bold=False)
        results = compare_warning(extraction)
        text_result = next(r for r in results if r.name == "warning_text")
        caps_result = next(r for r in results if r.name == "warning_caps")
        assert text_result.verdict == Verdict.PASS
        assert caps_result.verdict == Verdict.PASS
