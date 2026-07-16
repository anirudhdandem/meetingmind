"""Unit tests: per-user meeting visibility rules + calendar company naming (no DB)."""

import uuid

from app.services.auto_join import _attendee_emails
from app.services.call_visibility import _NO_EVENT, call_visible, event_visible
from app.services.company_naming import external_domains, fallback_company_name

ME = uuid.uuid4()
OTHER = uuid.uuid4()
MY_EMAILS = {"animesh@blostem.com", "animesh.personal@gmail.com"}


class FakeCall:
    def __init__(self, created_by=None):
        self.created_by_user_id = created_by


def test_call_visible_to_its_creator_only_without_an_event():
    call = FakeCall(created_by=OTHER)
    assert not call_visible(call, _NO_EVENT, MY_EMAILS, ME)
    assert call_visible(call, _NO_EVENT, {"x@y.com"}, OTHER)


def test_call_visible_via_invite_email_case_insensitively():
    call = FakeCall()
    attendees = ["Client@Acme.com", "ANIMESH@BLOSTEM.COM"]
    assert call_visible(call, [a.lower() for a in attendees], MY_EMAILS, ME)
    assert call_visible(call, attendees, MY_EMAILS, ME)  # defensive re-lowering
    assert not call_visible(call, ["client@acme.com"], MY_EMAILS, ME)


def test_legacy_rows_stay_visible_to_everyone():
    # Pre-ownership call: no creator, no event.
    assert call_visible(FakeCall(), _NO_EVENT, MY_EMAILS, ME)
    # Event synced before attendee tracking (attendee_emails NULL).
    assert call_visible(FakeCall(), None, MY_EMAILS, ME)
    assert event_visible(None, MY_EMAILS)
    assert event_visible([], MY_EMAILS)


def test_event_visible_matches_connected_google_email():
    assert event_visible(["animesh.personal@gmail.com"], MY_EMAILS)
    assert not event_visible(["someoneelse@blostem.com"], MY_EMAILS)


def test_attendee_emails_merges_and_lowercases():
    event = {
        "attendees": [{"email": "Client@Acme.com"}, {"displayName": "no email"}],
        "organizer": {"email": "Organizer@Blostem.com"},
    }
    got = _attendee_emails(event, "sweep-owner@blostem.com", ["earlier@blostem.com"])
    assert got == sorted(
        ["client@acme.com", "organizer@blostem.com", "sweep-owner@blostem.com",
         "earlier@blostem.com"]
    )


def test_external_domains_skips_internal_freemail_and_bot(monkeypatch):
    from app import config

    s = config.get_settings()
    monkeypatch.setattr(s, "internal_email_domains", ["blostem.com"])
    monkeypatch.setattr(s, "bot_google_account_email", "notetaker.bot@corpbot.com")
    emails = [
        "rep@blostem.com",           # internal
        "someone@gmail.com",         # freemail
        "notetaker.bot@corpbot.com", # the bot itself
        "dipti@mudrafincorp.com",
        "cto@mudrafincorp.com",      # duplicate domain
    ]
    assert external_domains(emails) == ["mudrafincorp.com"]


def test_fallback_prefers_external_domain_then_title():
    assert fallback_company_name("Weekly sync", ["mudrafincorp.co.in"]) == (
        "Mudrafincorp", "external",
    )
    assert fallback_company_name("Acme demo", []) == ("Acme demo", "external")
    assert fallback_company_name("   ", []) == (None, "external")
