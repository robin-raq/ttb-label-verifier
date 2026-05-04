"""Vision-extraction layer.

This package owns the contract between the API layer and whichever multimodal
LLM produces a `LabelExtraction`. The contract is a structural Protocol so
that swapping providers (OpenAI public → Azure OpenAI in TTB's gov-cloud
tenant → a future Anthropic / Gemini / on-prem client) requires only adding a
new class that implements `extract(...)` — no changes to routes, comparators,
audit, or tests.

This is the production-deployment swap point referenced in
`STUDY_GUIDE.md` and `README.md → Deployment constraints`.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.extraction import LabelExtraction


@runtime_checkable
class VisionClient(Protocol):
    """Structural contract every vision client must satisfy.

    A client takes raw image bytes plus the prompt-version tag (for audit
    traceability per FR-016) and returns a validated `LabelExtraction`.
    Implementations MUST raise on transport / API failure — the API layer
    handles retry per FR-012.
    """

    async def extract(
        self, image_bytes: bytes, prompt_version: str
    ) -> LabelExtraction:
        ...


__all__ = ["VisionClient"]
