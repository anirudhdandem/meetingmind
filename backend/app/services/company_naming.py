"""Name the company a meeting is with — from the calendar invite, before it starts.

The single place that owns the "which company does this call belong to" logic:

- `get_or_create_company` / `gc_default_company`: shared company bookkeeping,
  used by the manual routes, the auto-join dispatcher and the call processor.
- `company_for_event`: calendar event title + attendee emails -> a Company.
  Tries a small LLM extraction first (llm/company_name.py); when the model is
  down or unsure, falls back to deterministic rules (external attendee domain,
  then the raw title), and only then to the ad-hoc default.
- `assign_company_from_event`: processing-time backfill for calls that were
  started by hand but matched a calendar event later (the adopt flow) — they
  get the same auto-naming instead of staying in the ad-hoc bucket.

This replaces the post-meeting "which company was that?" dialog: auto-joined
meetings are filed correctly at dispatch time, with the Settings-page company
card ("Save details") kept only as a manual correction.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.models.call import Call
from app.models.company import Company

log = get_logger(__name__)

DEFAULT_COMPANY_NAME = "Ad-hoc meetings"

# Consumer mail providers — an attendee @gmail.com tells us nothing about their
# company, so these never become a company name.
_FREEMAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com",
    "hotmail.com", "live.com", "msn.com", "icloud.com", "me.com", "aol.com",
    "proton.me", "protonmail.com", "rediffmail.com", "zoho.com", "yandex.com",
}

_LLM_TIMEOUT_SECONDS = 25


async def get_or_create_company(
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


async def gc_default_company(db: AsyncSession, company_id: uuid.UUID | None) -> None:
    """Delete a company that no longer has any calls (only the ad-hoc default bucket)."""
    if company_id is None:
        return
    still_used = (
        await db.execute(select(Call.id).where(Call.company_id == company_id).limit(1))
    ).first()
    if still_used is None:
        company = await db.get(Company, company_id)
        if company is not None and company.name == DEFAULT_COMPANY_NAME:
            await db.delete(company)


def external_domains(attendee_emails: list[str] | None) -> list[str]:
    """Attendee email domains that aren't ours, the bot's, or a freemail provider."""
    s = get_settings()
    internal = {d.lower() for d in (s.internal_email_domains or [])}
    bot_email = (s.bot_google_account_email or "").strip().lower()
    seen: list[str] = []
    for email in attendee_emails or []:
        email = (email or "").strip().lower()
        if "@" not in email or email == bot_email:
            continue
        domain = email.rsplit("@", 1)[1]
        if domain in internal or domain in _FREEMAIL or domain in seen:
            continue
        seen.append(domain)
    return seen


def _name_from_domain(domain: str) -> str:
    """'mudrafincorp.co.in' -> 'Mudrafincorp' — the registrable label, capitalized."""
    label = domain.split(".", 1)[0]
    return label.capitalize() if label else domain


def fallback_company_name(
    title: str | None, ext_domains: list[str]
) -> tuple[str | None, str]:
    """Deterministic (name, kind) when the LLM can't run. None name = ad-hoc default.

    The external attendees' domain beats the title: titles are often generic
    ("Intro call") while an invited @client.com attendee is unambiguous.
    """
    if ext_domains:
        return _name_from_domain(ext_domains[0]), "external"
    title = (title or "").strip()
    if title:
        # Every attendee is internal/freemail and only the title is left; without a
        # model we can't tell "Acme demo" from "Weekly standup", so file it as an
        # external meeting under the title and let "Save details" correct it.
        return title, "external"
    return None, "external"


async def company_for_event(
    db: AsyncSession, title: str | None, attendee_emails: list[str] | None
) -> Company:
    """The Company a calendar event's meeting should be filed under."""
    ext = external_domains(attendee_emails)
    try:
        from app.llm.company_name import extract_company_name

        result = await asyncio.wait_for(
            extract_company_name(title, ext, get_settings().our_company_name),
            timeout=_LLM_TIMEOUT_SECONDS,
        )
        if result.is_internal and not ext:
            name = (title or "").strip() or "Internal meeting"
            return await get_or_create_company(db, name, kind="internal")
        name = (result.company_name or "").strip()
        if name:
            return await get_or_create_company(db, name, kind="external")
    except Exception:
        log.warning("company naming: LLM extraction failed for %r", title, exc_info=True)

    name, kind = fallback_company_name(title, ext)
    if name:
        return await get_or_create_company(db, name, kind=kind)
    return await get_or_create_company(db, DEFAULT_COMPANY_NAME)


async def assign_company_from_event(db: AsyncSession, call: Call) -> Company | None:
    """Backfill a still-unfiled call from its linked calendar event, if any.

    Covers calls that didn't exist at dispatch time (started by hand, adopted by
    the poller later). No-op when there is no linked event or naming still lands
    on the default. Returns the company the call now belongs to, or None.
    """
    from app.models.calendar_event import CalendarEvent
    from app.models.embedding import CompanyMemory
    from app.models.mom import Mom
    from app.models.outcome import LeadOutcome

    event = (
        await db.execute(select(CalendarEvent).where(CalendarEvent.call_id == call.id))
    ).scalars().first()
    if event is None:
        return None

    company = await company_for_event(db, event.title, event.attendee_emails)
    if company.name == DEFAULT_COMPANY_NAME or company.id == call.company_id:
        return None

    old_id = call.company_id
    call.company_id = company.id
    # Keep anything already derived from the call pointing at the same company.
    for model in (Mom, CompanyMemory, LeadOutcome):
        rows = (
            await db.execute(select(model).where(model.call_id == call.id))
        ).scalars().all()
        for row in rows:
            row.company_id = company.id
    await gc_default_company(db, old_id)
    log.info("company naming: filed call %s under %r", call.id, company.name)
    return company
