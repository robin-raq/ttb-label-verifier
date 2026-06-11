"""Real OpenAI vision client for label extraction.

SPEC §2 FR-003, FR-016.

Designed to be a drop-in replacement for FakeOpenAIClient (tests/conftest.py):
  - Same async `extract(image_bytes, prompt_version)` signature.
  - Raises on transport/API errors — retry is Agent B2's responsibility (FR-012).
  - Calls OpenAI exactly ONCE per invocation (no internal retry).
"""
from __future__ import annotations

import base64

import filetype
from openai import AsyncOpenAI

from app.extraction.prompts import SYSTEM_PROMPT
from app.schemas.extraction import LabelExtraction

# FR-002 accepts these three MIME types. Anything else is rejected upstream by
# the API layer's _validate_image, so by the time we reach the vision client
# the bytes are guaranteed to match one of these. PNG is the safe fallback if
# magic-byte sniffing somehow returns nothing (defence-in-depth, not a real
# code path).
_ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}

# JSON schema derived directly from the Pydantic model — never hand-written.
# Drift between this schema and LabelExtraction would be caught by structured-
# output validation failures at runtime, but generating it here at import time
# ensures they always stay in sync.
_LABEL_EXTRACTION_SCHEMA: dict = LabelExtraction.model_json_schema()


class OpenAIVisionClient:
    """Real OpenAI vision client. Drop-in compatible with FakeOpenAIClient.

    Parameters
    ----------
    api_key:
        OpenAI API key. Defaults to the OPENAI_API_KEY environment variable
        (AsyncOpenAI's own default behaviour).
    model:
        Model ID to use for structured-output extraction.
    """

    # Per-call wall-clock budget (seconds). Keeps both attempts in _call_with_retry
    # within a predictable window; the route's fallback converts timeout into
    # NEEDS_REVIEW rather than an uncaught hang.
    TIMEOUT_SECONDS: float = 30.0

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-2024-08-06",
    ) -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, timeout=self.TIMEOUT_SECONDS)

    async def extract(self, image_bytes: bytes, prompt_version: str) -> LabelExtraction:
        """Single multimodal call returning a validated LabelExtraction.

        Uses OpenAI structured outputs (response_format json_schema) to
        guarantee the response matches LabelExtraction's schema.

        The ``prompt_version`` argument is forwarded so callers can assert
        which prompt revision produced a given extraction (SPEC FR-016 / audit
        log requirement §2.1).

        Raises
        ------
        openai.APIError (and subclasses)
            On any transport or server-side failure. The API layer (Agent B2)
            handles retry per FR-012. This method does NOT retry internally.
        pydantic.ValidationError
            If the model returns JSON that doesn't satisfy LabelExtraction's
            field constraints (should be rare given structured outputs, but
            possible with older model versions or schema mismatches).
        """
        b64 = base64.b64encode(image_bytes).decode("ascii")
        kind = filetype.guess(image_bytes)
        mime = kind.mime if kind and kind.mime in _ALLOWED_MIMES else "image/png"
        data_url = f"data:{mime};base64,{b64}"

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "high"},
                        }
                    ],
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "LabelExtraction",
                    "strict": True,
                    "schema": _LABEL_EXTRACTION_SCHEMA,
                },
            },
            temperature=0,  # deterministic extraction; no creative variation
        )

        raw_json: str = response.choices[0].message.content  # type: ignore[assignment]
        return LabelExtraction.model_validate_json(raw_json)
