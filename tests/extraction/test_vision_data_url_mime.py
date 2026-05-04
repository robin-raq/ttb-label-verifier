"""Vision client data URL must reflect the real image MIME (FR-002).

The data URL prefix tells GPT-4o how to decode the bytes. Hardcoding image/png
for JPEG/WebP uploads forces the model to re-derive the type from magic bytes
and is a silent source of token-count and accuracy drift.
"""
from __future__ import annotations

import base64
import struct
import zlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.extraction.openai_vision import OpenAIVisionClient


def _minimal_jpeg() -> bytes:
    # Smallest bytes that filetype.guess() will recognise as JPEG: SOI marker
    # plus an APP0/JFIF segment plus EOI. Not a renderable image — fine for
    # MIME-sniffing tests, which only inspect the first ~12 bytes.
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )


def _minimal_webp() -> bytes:
    # RIFF....WEBPVP8 header that filetype.guess() recognises as image/webp.
    payload = b"VP8 \x00\x00\x00\x00"  # bogus VP8 chunk, length zero
    return b"RIFF" + struct.pack("<I", 4 + len(payload)) + b"WEBP" + payload


def _minimal_png() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_chunk = b"IHDR" + ihdr
    ihdr_full = (
        struct.pack(">I", len(ihdr))
        + ihdr_chunk
        + struct.pack(">I", zlib.crc32(ihdr_chunk))
    )
    raw = b"\x00\xff\xff\xff"
    comp = zlib.compress(raw)
    idat_chunk = b"IDAT" + comp
    idat_full = (
        struct.pack(">I", len(comp))
        + idat_chunk
        + struct.pack(">I", zlib.crc32(idat_chunk))
    )
    iend_chunk = b"IEND"
    iend_full = (
        struct.pack(">I", 0) + iend_chunk + struct.pack(">I", zlib.crc32(iend_chunk))
    )
    return sig + ihdr_full + idat_full + iend_full


def _make_client_with_fake_response(json_payload: str) -> tuple[OpenAIVisionClient, AsyncMock]:
    """Build an OpenAIVisionClient whose internal AsyncOpenAI is a mock.

    Returns the client and the mock so tests can inspect the call args.
    """
    client = OpenAIVisionClient(api_key="test")
    mock_create = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json_payload
    mock_create.return_value = mock_response
    client._client.chat.completions.create = mock_create  # type: ignore[attr-defined]
    return client, mock_create


def _valid_extraction_json() -> str:
    # Minimal LabelExtraction-shaped JSON that Pydantic will accept.
    return (
        '{"brand_name":"X","class_type":"Y","abv_percent":40.0,'
        '"net_contents":"750 mL","warning_text":"Z",'
        '"warning_prefix_all_caps":true,"warning_prefix_bold":true,'
        '"image_quality":"good",'
        '"field_confidence":{"brand_name":0.9,"class_type":0.9,'
        '"abv_percent":0.9,"net_contents":0.9,"warning_text":0.9,'
        '"warning_prefix_all_caps":0.9,"warning_prefix_bold":0.9,'
        '"image_quality":0.9}}'
    )


def _sent_data_url(mock_create: AsyncMock) -> str:
    """Pull the data URL out of the recorded chat.completions.create call."""
    kwargs = mock_create.await_args.kwargs
    user_message = kwargs["messages"][1]
    return user_message["content"][0]["image_url"]["url"]


@pytest.mark.asyncio
async def test_jpeg_bytes_emit_image_jpeg_data_url() -> None:
    client, mock_create = _make_client_with_fake_response(_valid_extraction_json())
    await client.extract(_minimal_jpeg(), "v1")

    url = _sent_data_url(mock_create)
    assert url.startswith("data:image/jpeg;base64,"), url
    body = url.split(",", 1)[1]
    assert base64.b64decode(body) == _minimal_jpeg()


@pytest.mark.asyncio
async def test_webp_bytes_emit_image_webp_data_url() -> None:
    client, mock_create = _make_client_with_fake_response(_valid_extraction_json())
    await client.extract(_minimal_webp(), "v1")

    url = _sent_data_url(mock_create)
    assert url.startswith("data:image/webp;base64,"), url


@pytest.mark.asyncio
async def test_png_bytes_emit_image_png_data_url() -> None:
    client, mock_create = _make_client_with_fake_response(_valid_extraction_json())
    await client.extract(_minimal_png(), "v1")

    url = _sent_data_url(mock_create)
    assert url.startswith("data:image/png;base64,"), url
