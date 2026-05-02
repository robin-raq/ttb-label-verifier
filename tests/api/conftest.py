"""Shared fixtures for API tests.

Resets the slowapi rate-limiter storage before each test so rate limits
from one test don't bleed into the next.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi in-memory storage before each test."""
    from app.api.main import limiter
    try:
        limiter._storage.reset()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    yield
