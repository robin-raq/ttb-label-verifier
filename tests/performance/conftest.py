"""Reset slowapi storage before each performance test."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from app.api.main import limiter
    try:
        limiter._storage.reset()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    yield
