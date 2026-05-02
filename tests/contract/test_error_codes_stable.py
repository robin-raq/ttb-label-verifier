"""Contract test: ErrorCode vocabulary is stable — SPEC §3.1.

Adding a new code without a SPEC bump is a breaking change.
This test guards the vocabulary boundary: if someone adds a new
error code the set comparison will fail, forcing them to also
update this assertion (which is the point — it creates friction
for accidental vocabulary expansion).
"""
from __future__ import annotations

from app.schemas.api import ErrorCode


def test_error_code_vocabulary_is_exactly_spec_set() -> None:
    """SPEC §3.1: error.code vocabulary is exactly these four values."""
    expected = {
        "INVALID_IMAGE_TYPE",
        "FILE_TOO_LARGE",
        "VALIDATION_ERROR",
        "EXTRACTION_FAILED",
    }
    actual = {code.value for code in ErrorCode}
    assert actual == expected, (
        f"ErrorCode vocabulary changed — SPEC minor bump required.\n"
        f"Added: {actual - expected}\n"
        f"Removed: {expected - actual}"
    )
