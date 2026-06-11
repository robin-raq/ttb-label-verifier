"""Deterministic checks on eval fixture definitions — no OpenAI tokens."""
from __future__ import annotations

from app.constants.ttb_warning import CANONICAL_WARNING
from tests.fixtures.labels.generate_fixtures import EM_DASH_WARNING


def test_em_dash_warning_differs_from_canonical() -> None:
    """adv_01 renders punctuation that is visibly and programmatically distinct."""
    assert EM_DASH_WARNING != CANONICAL_WARNING
    assert "\u2014" in EM_DASH_WARNING, "expected U+2014 em dash in rendered warning"
    assert "\u2014" not in CANONICAL_WARNING
