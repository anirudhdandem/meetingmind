"""Unit tests for the calendar auto-join helpers (no DB / no Google)."""

import datetime as dt

from app.services.auto_join import _bot_declined, _meeting_url, _parse_ts

BOT = "bot@blostem.com"


def test_parse_ts_handles_google_formats():
    assert _parse_ts("2026-07-13T10:00:00Z") == dt.datetime(
        2026, 7, 13, 10, tzinfo=dt.timezone.utc
    )
    offset = _parse_ts("2026-07-13T15:30:00+05:30")
    assert offset is not None and offset.utcoffset() == dt.timedelta(hours=5, minutes=30)
    assert _parse_ts(None) is None
    assert _parse_ts("not-a-date") is None


def test_owner_declined_works_for_a_user_calendar_too():
    # On a user-connected calendar the "self" attendee is the user, not the bot:
    # declining the meeting on their own calendar means "don't send the bot".
    user = "anirudh@blostem.com"
    event = {
        "attendees": [
            {"email": BOT, "responseStatus": "needsAction"},
            {"email": user, "self": True, "responseStatus": "declined"},
        ]
    }
    assert _bot_declined(event, user)
    assert not _bot_declined(event, BOT)


def test_bot_declined_checks_only_the_bots_own_invite():
    accepted = {"attendees": [{"email": BOT, "self": True, "responseStatus": "accepted"}]}
    declined = {"attendees": [{"email": BOT, "self": True, "responseStatus": "declined"}]}
    other_declined = {
        "attendees": [
            {"email": "human@client.com", "responseStatus": "declined"},
            {"email": BOT, "self": True, "responseStatus": "needsAction"},
        ]
    }
    assert not _bot_declined(accepted, BOT)
    assert _bot_declined(declined, BOT)
    assert not _bot_declined(other_declined, BOT)
    assert not _bot_declined({}, BOT)  # no attendees listed at all


def test_meeting_url_prefers_conference_entry_point():
    event = {
        "hangoutLink": "https://meet.google.com/abc-defg-hij",
        "conferenceData": {
            "entryPoints": [
                {"uri": "tel:+1-555-0100"},
                {"uri": "https://meet.google.com/abc-defg-hij?authuser=0"},
            ]
        },
    }
    assert _meeting_url(event, "abc-defg-hij") == "https://meet.google.com/abc-defg-hij?authuser=0"
    # Falls back to the hangoutLink, then to a URL built from the code.
    assert _meeting_url({"hangoutLink": "https://meet.google.com/abc-defg-hij"}, "abc-defg-hij") == (
        "https://meet.google.com/abc-defg-hij"
    )
    assert _meeting_url({}, "abc-defg-hij") == "https://meet.google.com/abc-defg-hij"
