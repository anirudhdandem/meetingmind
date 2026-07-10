"""Gemini client wrapper: structured generation + embeddings (async)."""

from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


@lru_cache
def _client() -> genai.Client:
    return genai.Client(api_key=get_settings().gemini_api_key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def generate_structured(prompt: str, schema: type[T]) -> T:
    """Run a prompt and parse the response into `schema` via Gemini structured output."""
    settings = get_settings()
    resp = await _client().aio.models.generate_content(
        model=settings.gemini_llm_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        ),
    )
    parsed = resp.parsed
    if isinstance(parsed, schema):
        return parsed
    # Fallback: validate raw JSON text if the SDK didn't auto-parse.
    return schema.model_validate_json(resp.text)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed(text: str, dim: int) -> list[float]:
    """Return an embedding vector of length `dim` for `text`."""
    settings = get_settings()
    resp = await _client().aio.models.embed_content(
        model=settings.gemini_embed_model,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=dim),
    )
    return list(resp.embeddings[0].values)
