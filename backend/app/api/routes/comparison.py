"""Routes: comparative analysis (spec step 10)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.analysis import ComparisonReport
from app.services import comparison_service

router = APIRouter(tags=["comparison"])


@router.get("/comparison", response_model=ComparisonReport)
async def compare(
    segment: str | None = Query(None, description="restrict to a company segment"),
    db: AsyncSession = Depends(get_session),
):
    """Why did deals win vs lose: programmatic rubric deltas + grounded Gemini narrative."""
    return await comparison_service.compare(db, segment)
