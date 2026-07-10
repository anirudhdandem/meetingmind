"""Gemini embeddings + pgvector upsert/query for company memory."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm import gemini_client
from app.models.embedding import EMBED_DIM, CompanyMemory

log = get_logger(__name__)


async def embed_text(text: str) -> list[float]:
    return await gemini_client.embed(text, dim=EMBED_DIM)


async def store_memory(
    session: AsyncSession,
    company_id: uuid.UUID,
    call_id: uuid.UUID | None,
    source_text: str,
) -> CompanyMemory:
    """Embed `source_text` and persist it as a company_memory row."""
    vector = await embed_text(source_text)
    row = CompanyMemory(
        company_id=company_id,
        call_id=call_id,
        embedding=vector,
        source_text=source_text,
    )
    session.add(row)
    await session.flush()
    log.info("Stored company_memory for company=%s call=%s", company_id, call_id)
    return row


async def query_similar(
    session: AsyncSession,
    query_text: str,
    limit: int = 5,
    exclude_company_id: uuid.UUID | None = None,
) -> list[tuple[CompanyMemory, float]]:
    """Cosine-distance search across all company memory (spec step 11, 'calls like this one').

    Returns (row, distance) pairs ordered nearest-first. Optionally excludes the query's own
    company so "similar" means other companies, not the same account.
    """
    vector = await embed_text(query_text)
    distance = CompanyMemory.embedding.cosine_distance(vector).label("distance")
    stmt = select(CompanyMemory, distance)
    if exclude_company_id is not None:
        stmt = stmt.where(CompanyMemory.company_id != exclude_company_id)
    stmt = stmt.order_by(distance).limit(limit)

    result = await session.execute(stmt)
    return [(row, dist) for row, dist in result.all()]
