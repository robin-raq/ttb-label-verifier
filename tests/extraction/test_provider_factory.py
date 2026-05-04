"""`get_vision_client` env-var resolution edge cases.

The factory is the only piece of code that reads `VISION_PROVIDER`; if it
mishandles whitespace or an empty string the result is a 500 on every
request, not a graceful NEEDS_REVIEW. These tests lock the resolution rules.
"""
from __future__ import annotations

import pytest

from app.api import deps


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch):
    """Ensure no test leaks VISION_PROVIDER / OPENAI_API_KEY into the next."""
    monkeypatch.delenv("VISION_PROVIDER", raising=False)
    # Don't fail just because a real key isn't present in CI.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder")


@pytest.mark.parametrize(
    "raw_value",
    [
        "openai",
        "OpenAI",
        "OPENAI",
        " openai ",
        "openai\t",
        "\nopenai",
        "",  # explicitly empty → fall back to default 'openai'
    ],
)
def test_openai_provider_resolves_under_whitespace_and_case(monkeypatch, raw_value):
    """Whitespace, case variants, and an empty string must all resolve to
    the OpenAI branch — not raise ValueError."""
    monkeypatch.setenv("VISION_PROVIDER", raw_value)
    # Should construct (or return None on missing key) — not raise.
    client = deps.get_vision_client()
    assert client is not None  # OPENAI_API_KEY is set in fixture


def test_unknown_provider_still_raises_value_error(monkeypatch):
    """A genuinely unknown provider should fail loud; whitespace handling
    must not paper over misconfiguration."""
    monkeypatch.setenv("VISION_PROVIDER", "claude")
    with pytest.raises(ValueError, match="Unknown VISION_PROVIDER"):
        deps.get_vision_client()


def test_azure_provider_still_raises_not_implemented(monkeypatch):
    """The reserved azure branch must still surface its NotImplementedError
    (with whitespace/case tolerance) so production deploy fails loud until
    the client class is wired."""
    monkeypatch.setenv("VISION_PROVIDER", " AZURE ")
    with pytest.raises(NotImplementedError, match="azure"):
        deps.get_vision_client()
