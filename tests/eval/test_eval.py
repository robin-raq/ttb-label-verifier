"""Eval harness — runs the full pipeline against ground-truth fixtures.

Two modes:
  * Default (CI-safe): uses frozen mocked extractions in `tests/fixtures/extractions/`
    so no OpenAI tokens are spent. Verifies pipeline wiring end-to-end.
  * Real-LLM mode (RUN_LLM_TESTS=1): hits actual OpenAI for each fixture.

Each PNG fixture has a sibling `.expected.yaml` with form_fields and
expected verdicts. Tests assert the overall verdict matches; per-field
assertions are tolerant where prompted (some fixtures intentionally test
edge cases where the model's specific reading is OK to vary).

Run: `make eval` (default mocked) or `RUN_LLM_TESTS=1 pytest tests/eval -q`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from app.schemas.api import Verdict

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "labels"


def _list_fixtures() -> list[Path]:
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(p for p in FIXTURES_DIR.glob("*.png"))


def _load_expected(png_path: Path) -> dict:
    yaml_path = png_path.with_suffix("").with_suffix(".expected.yaml")
    # png_path is "01_happy_old_tom.png"; with_suffix("") → "01_happy_old_tom"
    # then .with_suffix(".expected.yaml") → "01_happy_old_tom.expected.yaml"
    yaml_path = png_path.parent / (png_path.stem + ".expected.yaml")
    with yaml_path.open() as f:
        return yaml.safe_load(f)


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_TESTS") != "1",
    reason="Real-LLM eval — set RUN_LLM_TESTS=1 to enable.",
)
@pytest.mark.parametrize("fixture", _list_fixtures(), ids=lambda p: p.stem)
def test_eval_against_real_openai(fixture: Path) -> None:
    """Hit the real OpenAI vision client and run the full comparator pipeline.

    Asserts overall verdict matches expected. Per-field assertions only fire
    when the fixture's expected.yaml supplies them (some fixtures are
    tolerant by design — see fixtures/labels/README.md).
    """
    from app.api.routes import _run_comparators
    from app.extraction.openai_vision import OpenAIVisionClient
    from app.extraction.prompts import PROMPT_VERSION
    from app.schemas.api import VerifyRequest
    from app.verdict import compute_overall_verdict

    expected = _load_expected(fixture)
    image_bytes = fixture.read_bytes()

    client = OpenAIVisionClient()
    import asyncio
    extraction = asyncio.run(client.extract(image_bytes, PROMPT_VERSION))

    req = VerifyRequest(**expected["form_fields"])
    field_results = _run_comparators(req, extraction)
    overall = compute_overall_verdict(field_results, extraction)

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
        assert "expected_overall" in data
        assert data["expected_overall"] in ("PASS", "FAIL", "NEEDS_REVIEW")
