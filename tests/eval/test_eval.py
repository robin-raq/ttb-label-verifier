"""Eval harness — runs the full pipeline against ground-truth fixtures.

Two modes:
  * Default (CI-safe): YAML integrity + fixture generator checks only.
  * Real-LLM mode (RUN_LLM_TESTS=1): hits actual OpenAI for each fixture.

Fixture tiers (see ``eval_tier`` in each ``*.expected.yaml``):
  * ``regression`` — deterministic pass/fail; overall verdict is asserted.
  * ``informational`` — real-model probe; security/invariant checks only.

Run:
  make eval                                    # CI-safe (no tokens)
  RUN_LLM_TESTS=1 make eval-real               # paid real-model eval
  RUN_LLM_TESTS=1 pytest tests/eval/test_eval.py -v -k regression  # strict only
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from app.api.routes import _run_comparators
from app.extraction import VisionClient
from app.extraction.prompts import PROMPT_VERSION
from app.schemas.api import Verdict, VerifyRequest
from app.verdict import compute_overall_verdict

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "labels"


def _list_fixtures() -> list[Path]:
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(p for p in FIXTURES_DIR.rglob("*.png"))


def _load_expected(png_path: Path) -> dict:
    yaml_path = png_path.parent / (png_path.stem + ".expected.yaml")
    with yaml_path.open() as f:
        return yaml.safe_load(f)


def _apply_security_assertions(
    fixture_name: str,
    extraction,
    overall: Verdict,
    security: dict,
) -> None:
    """Invariant checks for informational / security probes."""
    if not security:
        return

    banned_brand = security.get("extracted_brand_not")
    if banned_brand is not None:
        assert banned_brand.upper() not in extraction.brand_name.upper(), (
            f"{fixture_name}: model extracted attacker-controlled brand "
            f"{extraction.brand_name!r} (must not contain {banned_brand!r})"
        )

    allowed = security.get("overall_verdict_in")
    if allowed is not None:
        assert overall.value in allowed, (
            f"{fixture_name}: overall {overall.value} not in allowed {allowed}"
        )

    forbidden = security.get("overall_verdict_not")
    if forbidden is not None:
        assert overall.value != forbidden, (
            f"{fixture_name}: overall must not be {forbidden}"
        )


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_TESTS") != "1",
    reason="Real-LLM eval — set RUN_LLM_TESTS=1 to enable.",
)
@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", _list_fixtures(), ids=lambda p: p.stem)
async def test_eval_against_real_openai(
    fixture: Path,
    vision_client: VisionClient,
) -> None:
    """Run extraction + comparators against real OpenAI.

    Regression fixtures: assert ``expected_overall``.
    Informational fixtures: assert ``security_assertions`` only (no strict verdict).
    """
    expected = _load_expected(fixture)
    tier = expected.get("eval_tier", "regression")
    image_bytes = fixture.read_bytes()

    extraction = await vision_client.extract(image_bytes, PROMPT_VERSION)
    req = VerifyRequest(**expected["form_fields"])
    field_results = _run_comparators(req, extraction)
    overall = compute_overall_verdict(field_results, extraction)

    _apply_security_assertions(
        fixture.name,
        extraction,
        overall,
        expected.get("security_assertions") or {},
    )

    if tier == "informational":
        return

    allowed = expected.get("expected_overall_in")
    if allowed is not None:
        assert overall.value in allowed, (
            f"{fixture.name}: expected overall in {allowed} but got {overall.value}. "
            f"Fields: {[(r.name, r.verdict.value, r.detail) for r in field_results]}"
        )
    else:
        expected_overall = Verdict(expected["expected_overall"])
        assert overall == expected_overall, (
            f"{fixture.name}: expected {expected_overall} but got {overall}. "
            f"Fields: {[(r.name, r.verdict.value, r.detail) for r in field_results]}"
        )

    expected_per_field = expected.get("expected_per_field")
    if expected_per_field:
        actual_by_name = {r.name: r.verdict.value for r in field_results}
        for name, expected_v in expected_per_field.items():
            assert actual_by_name.get(name) == expected_v, (
                f"{fixture.name}.{name}: expected {expected_v} but got "
                f"{actual_by_name.get(name)}"
            )


def test_eval_fixtures_have_expected_yaml() -> None:
    """Every PNG must have a paired expected.yaml — fails fast on bad fixtures."""
    pngs = _list_fixtures()
    assert len(pngs) >= 3, f"Need ≥3 eval fixtures, found {len(pngs)}"
    for png in pngs:
        yaml_path = png.parent / (png.stem + ".expected.yaml")
        assert yaml_path.is_file(), f"Missing {yaml_path.name} for {png.name}"
        data = yaml.safe_load(yaml_path.read_text())
        assert "form_fields" in data
        tier = data.get("eval_tier", "regression")
        if tier == "regression":
            assert "expected_overall" in data or "expected_overall_in" in data
            if "expected_overall" in data:
                assert data["expected_overall"] in ("PASS", "FAIL", "NEEDS_REVIEW")
        else:
            assert tier == "informational"
