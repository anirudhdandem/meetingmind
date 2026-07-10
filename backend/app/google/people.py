"""Thin async client for the Google People API: resolve Meet participant IDs.

A Meet conference record identifies each signed-in participant as `users/{id}` —
an ID "interoperable with the People API". `people.get` on `people/{id}` returns
the person's profile as visible to the CALLER: for a caller on the same Workspace
domain that includes the directory profile (name + primary email), which is exactly
what internal-vs-client classification needs. External people usually resolve to
nothing (privacy) — and that's fine: not provably internal means client.

Docs: https://developers.google.com/workspace/meet/api/guides/participants
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

BASE = "https://people.googleapis.com/v1"

# Where the People API may look for the person, per the Meet API guide.
_SOURCES = (
    "READ_SOURCE_TYPE_PROFILE",
    "READ_SOURCE_TYPE_CONTACT",
    "READ_SOURCE_TYPE_OTHER_CONTACT",
)


async def resolve_person(access_token: str, user_resource: str) -> dict | None:
    """Resolve a Meet `users/{id}` resource to {"email": ..., "name": ...}.

    Returns None when the profile isn't visible to the caller (external users who
    haven't shared a profile, or callers outside the person's domain) — callers
    must treat that as "not provably internal", never as an error.
    """
    user_id = user_resource.rsplit("/", 1)[-1].strip()
    if not user_id:
        return None
    params = [
        ("personFields", "emailAddresses,names"),
        *[("sources", s) for s in _SOURCES],
    ]
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE}/people/{user_id}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        person = r.json()

    emails = person.get("emailAddresses") or []
    email = next(
        (e.get("value") for e in emails if (e.get("metadata") or {}).get("primary")),
        emails[0].get("value") if emails else None,
    )
    names = person.get("names") or []
    name = names[0].get("displayName") if names else None
    if not email:
        return None
    return {"email": email.strip().lower(), "name": name}
