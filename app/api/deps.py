"""Dependency injection factories — FastAPI DI layer.

`get_openai_client` is the key seam: tests override it via
`app.dependency_overrides[get_openai_client] = lambda: FakeOpenAIClient(...)`.

The real client is only instantiated in production; tests never reach this path.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from fastapi import Depends


def get_openai_client():
    """Provide the OpenAI vision client (real implementation from B3).

    In tests, this is overridden via app.dependency_overrides to inject
    FakeOpenAIClient without touching app/extraction/.

    Returns None if B3's module is not yet available. Routes handle None
    gracefully by returning NEEDS_REVIEW (same path as FR-012 failure).
    """
    # Late import so tests that don't need extraction can still run even
    # if app/extraction/openai_vision.py doesn't exist yet (B3's territory).
    try:
        from app.extraction.openai_vision import OpenAIVisionClient
        return OpenAIVisionClient()
    except ImportError:
        return None


# Type alias for annotated dependency
OpenAIClientDep = Annotated[object, Depends(get_openai_client)]
