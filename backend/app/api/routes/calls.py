"""Routes: companies, calls, transcripts, manual call processing."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.call import Call, CallStatus
from app.models.company import Company
from app.models.embedding import CompanyMemory
from app.models.metrics import CallMetrics
from app.models.mom import Mom
from app.models.outcome import LeadOutcome
from app.models.score import CallScore
from app.models.transcript import CallTranscript
from app.schemas.analysis import MetricsOut, MomOut, OutcomeOut, ScoreOut
from app.schemas.calls import (
    AssignCompany,
    CallCreate,
    CallOut,
    CallStart,
    CompanyCreate,
    CompanyOut,
    TranscriptOut,
)
from app.services import call_processor

router = APIRouter(tags=["calls"])


# --- companies ---------------------------------------------------------------
@router.post("/companies", response_model=CompanyOut, status_code=201)
async def create_company(payload: CompanyCreate, db: AsyncSession = Depends(get_session)):
    company = Company(
        name=payload.name,
        segment=payload.segment,
        kind=payload.kind,
        presented_by=(payload.presented_by or "").strip() or None,
        product_pitched=(payload.product_pitched or "").strip() or None,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@router.get("/companies", response_model=list[CompanyOut])
async def list_companies(db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(Company).order_by(Company.created_at.desc()))).scalars().all()
    return rows


# --- calls -------------------------------------------------------------------
@router.post("/calls", response_model=CallOut, status_code=201)
async def create_call(payload: CallCreate, db: AsyncSession = Depends(get_session)):
    if await db.get(Company, payload.company_id) is None:
        raise HTTPException(404, "company not found")
    call = Call(
        company_id=payload.company_id,
        sales_rep_id=payload.sales_rep_id,
        meeting_platform=payload.meeting_platform,
        meeting_url=payload.meeting_url,
        scheduled_at=payload.scheduled_at,
        livekit_room=f"mm-{uuid.uuid4().hex[:12]}",
        status=CallStatus.scheduled,
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)
    return call


DEFAULT_COMPANY_NAME = "Ad-hoc meetings"


async def _get_or_create_company(
    db: AsyncSession, name: str, kind: str = "external", segment: str | None = None
) -> Company:
    company = (
        await db.execute(
            select(Company).where(Company.name == name, Company.kind == kind)
        )
    ).scalars().first()
    if company is None:
        company = Company(name=name, kind=kind, segment=segment)
        db.add(company)
        await db.flush()
    elif segment is not None and company.segment != segment:
        company.segment = segment
    return company


@router.post("/calls/start", response_model=CallOut, status_code=201)
async def start_call(payload: CallStart, db: AsyncSession = Depends(get_session)):
    """Paste a meeting URL → create the call and launch the bot immediately.

    No company/call setup needed beforehand: a default company is reused so the
    frontend only has to send the URL. Multiple meetings can be recorded at once
    (up to `max_concurrent_bots`); past that, this returns 429 without creating
    a dangling call.
    """
    from app.bot import manager

    if not manager.has_capacity():
        raise HTTPException(
            429,
            f"already recording {manager.active_count()} meetings — "
            "end one first or raise MAX_CONCURRENT_BOTS",
        )

    company = await _get_or_create_company(db, payload.company_name or DEFAULT_COMPANY_NAME)
    call = Call(
        company_id=company.id,
        meeting_platform=payload.meeting_platform,
        meeting_url=payload.meeting_url,
        livekit_room=f"mm-{uuid.uuid4().hex[:12]}",
        status=CallStatus.scheduled,
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    manager.start_bot(call.id)
    return call


@router.post("/calls/{call_id}/stop", response_model=CallOut)
async def stop_call(
    call_id: uuid.UUID,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """End the meeting: the bot leaves and the MOM pipeline runs on the captured chunks.

    Returns immediately; summarization runs in the background and the frontend polls
    for the MOM. Works whether the bot runs in this process or was started elsewhere.
    """
    from app.bot import manager

    call = await db.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "call not found")
    background.add_task(manager.stop_and_finalize, call_id)
    return call


@router.post("/calls/{call_id}/company", response_model=CallOut)
async def assign_company(
    call_id: uuid.UUID,
    payload: AssignCompany,
    db: AsyncSession = Depends(get_session),
):
    """Re-file a call under the company it was actually with (or an internal label).

    Called from the post-summary prompt. Re-points the call and everything derived
    from it (minutes, embedded memory, recorded outcomes) at the chosen company so
    future "same company" recall and won/lost analysis stay correct.
    """
    call = await db.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "call not found")

    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "company name / label is required")
    kind = "internal" if payload.kind == "internal" else "external"

    company = await _get_or_create_company(db, name, kind=kind, segment=payload.segment)
    # Pitch details from the save dialog: None = untouched, "" = clear, text = set.
    if payload.presented_by is not None:
        company.presented_by = payload.presented_by.strip() or None
    if payload.product_pitched is not None:
        company.product_pitched = payload.product_pitched.strip() or None
    if company.id != call.company_id:
        old_id = call.company_id
        call.company_id = company.id
        # Keep derived rows pointing at the same company so retrieval stays consistent.
        for model in (Mom, CompanyMemory, LeadOutcome):
            rows = (
                await db.execute(select(model).where(model.call_id == call_id))
            ).scalars().all()
            for row in rows:
                row.company_id = company.id
        # Drop the now-orphaned ad-hoc company if nothing else references it.
        await _gc_company(db, old_id)

    await db.commit()
    await db.refresh(call)
    return call


async def _gc_company(db: AsyncSession, company_id: uuid.UUID) -> None:
    """Delete a company that no longer has any calls (e.g. the default ad-hoc bucket)."""
    if company_id is None:
        return
    still_used = (
        await db.execute(select(Call.id).where(Call.company_id == company_id).limit(1))
    ).first()
    if still_used is None:
        company = await db.get(Company, company_id)
        if company is not None and company.name == DEFAULT_COMPANY_NAME:
            await db.delete(company)


@router.get("/calls", response_model=list[CallOut])
async def list_calls(db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(Call).order_by(Call.created_at.desc()))).scalars().all()
    return rows


@router.get("/calls/{call_id}", response_model=CallOut)
async def get_call(call_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    call = await db.get(Call, call_id)
    if call is None:
        raise HTTPException(404, "call not found")
    return call


@router.get("/calls/{call_id}/transcript", response_model=list[TranscriptOut])
async def get_transcript(call_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    rows = (
        await db.execute(
            select(CallTranscript)
            .where(CallTranscript.call_id == call_id)
            .order_by(CallTranscript.start_ts)
        )
    ).scalars().all()
    return rows


@router.get("/calls/{call_id}/mom", response_model=MomOut)
async def get_mom(call_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    mom = (await db.execute(select(Mom).where(Mom.call_id == call_id))).scalars().first()
    if mom is None:
        raise HTTPException(404, "MOM not found (call may not be processed yet)")
    return mom


@router.get("/calls/{call_id}/score", response_model=ScoreOut)
async def get_score(call_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    score = (await db.execute(select(CallScore).where(CallScore.call_id == call_id))).scalars().first()
    if score is None:
        raise HTTPException(404, "score not found (call may not be processed yet)")
    return score


@router.get("/calls/{call_id}/metrics", response_model=MetricsOut)
async def get_metrics(call_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    """Team performance metrics: talk-time split, confidence, answer quality, conversion."""
    m = (
        await db.execute(select(CallMetrics).where(CallMetrics.call_id == call_id))
    ).scalars().first()
    if m is None:
        raise HTTPException(404, "metrics not found (call may not be processed yet)")
    return m


@router.get("/calls/{call_id}/outcome", response_model=OutcomeOut)
async def get_call_outcome(call_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    """Latest won/lost/pending outcome recorded for this call (404 if none yet)."""
    outcome = (
        await db.execute(
            select(LeadOutcome)
            .where(LeadOutcome.call_id == call_id)
            .order_by(LeadOutcome.created_at.desc())
        )
    ).scalars().first()
    if outcome is None:
        raise HTTPException(404, "no outcome recorded for this call yet")
    return outcome


@router.post("/calls/{call_id}/process", response_model=MomOut)
async def process_call_now(call_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    """Manually run the call-end pipeline (useful for testing without the webhook)."""
    mom = await call_processor.process_call(db, call_id)
    if mom is None:
        raise HTTPException(400, "could not process call (no transcript or call missing)")
    return mom


@router.post("/calls/{call_id}/import-transcript", response_model=MomOut)
async def import_transcript_and_process(
    call_id: uuid.UUID, db: AsyncSession = Depends(get_session)
):
    """Pull the meeting's transcript from the Google Meet REST API, then analyze.

    Use after the meeting has ended and was transcribed by Meet. No bot/browser
    is involved — this reads the conference transcript via the service account.
    """
    from app.services.transcript_import import import_transcript

    n = await import_transcript(db, call_id)
    if n == 0:
        raise HTTPException(
            400,
            "no transcript available yet — meeting hasn't ended, wasn't transcribed, "
            "or the service account lacks access",
        )
    mom = await call_processor.process_call(db, call_id)
    if mom is None:
        raise HTTPException(400, "imported transcript but analysis failed")
    return mom
