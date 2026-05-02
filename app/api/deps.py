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
    """Provide the OpenAI vision client.

    In tests, this is overridden via app.dependency_overrides to inject
    FakeOpenAIClient without touching app/extraction/.

    Returns None if construction fails for any reason — most commonly the
    OPENAI_API_KEY env var is unset (e.g. local dev / CI without secrets,
    or batch-validation tests that never reach the LLM call). Routes handle
    None gracefully by returning NEEDS_REVIEW (same path as FR-012 failure).
    """
    try:
        from app.extraction.openai_vision import OpenAIVisionClient
    except ImportError:
        return None
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        return OpenAIVisionClient()
    except Exception:
        return None


# Type alias for annotated dependency
OpenAIClientDep = Annotated[object, Depends(get_openai_client)]
