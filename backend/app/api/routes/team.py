"""Routes: internal-team roster (used to split speakers into our team vs the client)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.team import TeamMember
from app.schemas.team import TeamMemberCreate, TeamMemberOut

router = APIRouter(tags=["team"])


@router.get("/team", response_model=list[TeamMemberOut])
async def list_team(db: AsyncSession = Depends(get_session)):
    rows = (
        await db.execute(select(TeamMember).order_by(TeamMember.created_at.desc()))
    ).scalars().all()
    return rows


@router.post("/team", response_model=TeamMemberOut, status_code=201)
async def add_team_member(payload: TeamMemberCreate, db: AsyncSession = Depends(get_session)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "name is required")
    member = TeamMember(name=name, email=(payload.email or "").strip() or None)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/team/{member_id}", status_code=204)
async def remove_team_member(member_id: uuid.UUID, db: AsyncSession = Depends(get_session)):
    member = await db.get(TeamMember, member_id)
    if member is None:
        raise HTTPException(404, "team member not found")
    if member.source != "manual" and member.active:
        # Learned row (meet/auto): deactivate instead of delete, so the learner sees
        # the correction and can't re-add the same name on the next call.
        member.active = False
    else:
        await db.delete(member)
    await db.commit()
