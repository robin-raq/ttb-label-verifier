"""Dependency injection factories — FastAPI DI layer.

`get_openai_client` is the key seam: tests override it via
`app.dependency_overrides[get_openai_client] = lambda: FakeOpenAIClient(...)`.

The real client is only instantiated in production; tests never reach this path.

Provider switching (FR future / `STUDY_GUIDE.md` Decision #14): the
`VISION_PROVIDER` env var selects which `VisionClient` implementation runs.
Default is `openai` (public api.openai.com). `azure` is reserved for the
production deploy inside TTB's gov-cloud tenant — see
`README.md → Deployment constraints`.
"""
from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends

from app.extraction import VisionClient


def get_vision_client() -> VisionClient | None:
    """Provide the active VisionClient implementation based on env config.

    Returns None on any construction failure (no API key, missing module,
    etc.) so the route layer can degrade to NEEDS_REVIEW gracefully — the
    same path FR-012 takes on transient transport failure.

    The provider is chosen by `VISION_PROVIDER` (default 'openai'). To add a
    new provider, drop a `<Name>VisionClient` class into `app/extraction/`
    that satisfies the `VisionClient` Protocol and add a branch here.
    """
    provider = os.getenv("VISION_PROVIDER", "openai").lower()

    if provider == "openai":
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

    if provider == "azure":
        # Reserved for TTB gov-cloud deploy. The Protocol lives in
        # app/extraction/__init__.py — drop AzureOpenAIVisionClient next to
        # OpenAIVisionClient and uncomment the import below.
        raise NotImplementedError(
            "VISION_PROVIDER=azure not yet wired. Implement "
            "app/extraction/azure_openai_vision.py:AzureOpenAIVisionClient "
            "satisfying the VisionClient Protocol, then add the branch here."
        )

    raise ValueError(
        f"Unknown VISION_PROVIDER={provider!r}. Expected one of: openai, azure."
    )


# Back-compat alias: existing routes / test overrides reference
# `get_openai_client` by identity. Both names resolve to the same function
# object so `app.dependency_overrides[get_openai_client]` still works.
get_openai_client = get_vision_client


# Type alias for annotated dependency
VisionClientDep = Annotated[VisionClient | None, Depends(get_vision_client)]
OpenAIClientDep = VisionClientDep  # back-compat
