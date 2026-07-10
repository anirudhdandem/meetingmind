"""Routes: retrieval layer (spec step 11) + outcome ingestion (step 9)."""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.embeddings import embedder
from app.models.call import Call
from app.models.company import Company
from app.models.mom import Mom
from app.models.outcome import LeadOutcome, OutcomeStatus
from app.schemas.analysis import MomOut, OutcomeCreate, OutcomeOut, SimilarCall

router = APIRouter(tags=["retrieval"])


@router.get("/retrieval/company/{company_id}/latest-mom", response_model=MomOut)
async def latest_mom_for_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    """'Same company' memory: exact SQL filter, most recent MOM (spec step 7)."""
    mom = (
        await db.execute(
            select(Mom).where(Mom.company_id == company_id).order_by(Mom.created_at.desc())
        )
    ).scalars().first()
    if mom is None:
        raise HTTPException(404, "no MOM for this company yet")
    return mom


@router.get("/retrieval/similar", response_model=list[SimilarCall])
async def similar_calls(
    call_id: uuid.UUID = Query(..., description="anchor call to find neighbours for"),
    limit: int = Query(5, ge=1, le=20),
    cross_company_only: bool = Query(True, description="exclude the anchor's own company"),
    db: AsyncSession = Depends(get_session),
):
    """'Calls like this one': pgvector cosine search over company memory."""
    mom = (await db.execute(select(Mom).where(Mom.call_id == call_id))).scalars().first()
    if mom is None or not mom.raw_summary:
        raise HTTPException(404, "anchor call has no processed summary to compare")

    exclude = mom.company_id if cross_company_only else None
    neighbours = await embedder.query_similar(db, mom.raw_summary, limit=limit, exclude_company_id=exclude)
    return [
        SimilarCall(
            call_id=row.call_id,
            company_id=row.company_id,
            distance=round(dist, 4),
            source_text=row.source_text,
        )
        for row, dist in neighbours
    ]


@router.get("/retrieval/outcomes", response_model=list[OutcomeOut])
async def outcomes_by_cohort(
    segment: str | None = Query(None),
    status: OutcomeStatus | None = Query(None),
    db: AsyncSession = Depends(get_session),
):
    """Won vs lost cohort for a segment (spec step 11, third lookup)."""
    stmt = select(LeadOutcome).join(Company, Company.id == LeadOutcome.company_id)
    if segment is not None:
        stmt = stmt.where(Company.segment == segment)
    if status is not None:
        stmt = stmt.where(LeadOutcome.status == status)
    rows = (await db.execute(stmt.order_by(LeadOutcome.created_at.desc()))).scalars().all()
    return rows


# --- outcome ingestion (filled by CRM/human, spec step 9) --------------------
@router.post("/outcomes", response_model=OutcomeOut, status_code=201)
async def create_outcome(payload: OutcomeCreate, db: AsyncSession = Depends(get_session)):
    if await db.get(Company, payload.company_id) is None:
        raise HTTPException(404, "company not found")
    if payload.call_id is not None and await db.get(Call, payload.call_id) is None:
        raise HTTPException(404, "call not found")
    # Stamp the close date automatically once a deal is marked won/lost.
    outcome_date = payload.outcome_date
    if outcome_date is None and payload.status != OutcomeStatus.pending:
        outcome_date = datetime.datetime.now(datetime.timezone.utc)
    outcome = LeadOutcome(
        company_id=payload.company_id,
        call_id=payload.call_id,
        status=payload.status,
        outcome_date=outcome_date,
        outcome_notes=payload.outcome_notes,
    )
    db.add(outcome)
    await db.commit()
    await db.refresh(outcome)
    return outcome
