"""Company-name extraction from a calendar event — fills the company BEFORE the meeting.

Auto-joined meetings used to be filed under the ad-hoc default and a post-meeting
dialog asked a human to type the company. The calendar event already says who the
meeting is with: the title ("Blostem <> Mudra Fincorp — demo") and the external
attendees' email domains. A tiny structured-output call turns those into a clean
company name; services/company_naming.py falls back to deterministic rules when
the model is unavailable or unsure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.llm.gemini_client import generate_structured


class CompanyNameResult(BaseModel):
    """The counterparty this meeting is with, extracted from the invite."""

    company_name: str | None = Field(
        default=None,
        description="The client/prospect company's clean display name (e.g. 'Mudra "
        "Fincorp'), title-cased, without our own company, separators, or meeting "
        "words like 'demo'/'intro'/'sync'. null when the invite names no company.",
    )
    is_internal: bool = Field(
        default=False,
        description="true when this is clearly an internal meeting of our own team "
        "(standup, 1:1, review — no external company involved).",
    )


def build_prompt(
    title: str | None, external_domains: list[str], our_company: str | None
) -> str:
    us = our_company or "our company"
    domains = ", ".join(external_domains) or "(none — all attendees are internal or freemail)"
    return f"""\
You file sales meetings for {us}. From a calendar invite, name the company the
meeting is WITH (the client/prospect — never {us} itself).

Invite title: {title or "(untitled)"}
External attendee email domains: {domains}

Rules:
- Prefer a company name stated in the title; use an external domain (without its
  TLD) only when the title names no company.
- Strip meeting words (demo, intro, sync, call, catch-up, kickoff), people's
  names, dates, and separators like <>, x, |, -.
- Title-case the result, e.g. "mudra fincorp <> blostem demo" -> "Mudra Fincorp".
- If the invite is an internal team meeting, set is_internal and leave
  company_name null.
- If no company can be named at all, leave company_name null.
"""


async def extract_company_name(
    title: str | None, external_domains: list[str], our_company: str | None
) -> CompanyNameResult:
    return await generate_structured(
        build_prompt(title, external_domains, our_company), CompanyNameResult
    )
