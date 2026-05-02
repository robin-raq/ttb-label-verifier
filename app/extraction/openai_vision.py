"""Real OpenAI vision client for label extraction.

SPEC §2 FR-003, FR-016.

Designed to be a drop-in replacement for FakeOpenAIClient (tests/conftest.py):
  - Same async `extract(image_bytes, prompt_version)` signature.
  - Raises on transport/API errors — retry is Agent B2's responsibility (FR-012).
  - Calls OpenAI exactly ONCE per invocation (no internal retry).
"""
from __future__ import annotations

import base64

from openai import AsyncOpenAI

from app.extraction.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from app.schemas.extraction import LabelExtraction

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

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-2024-08-06",
    ) -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key)

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
        data_url = f"data:image/png;base64,{b64}"

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
