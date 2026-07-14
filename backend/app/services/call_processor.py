"""Call-end orchestration: concat transcript -> Gemini MOM+scores -> persist -> embed.

This is the single paid step in the pipeline, fired once when the LiveKit room closes.
"""

from __future__ import annotations

import datetime
import re
import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.embeddings import embedder
from app.llm import analysis
from app.models.call import Call, CallStatus
from app.models.company import Company
from app.models.metrics import CallMetrics
from app.models.mom import Mom
from app.models.score import CallScore
from app.models.transcript import CallTranscript
from app.services import (
    batch_transcription,
    meet_identity,
    metrics,
    participant_roles,
    speaker_attribution,
)

log = get_logger(__name__)


def recording_path(call_id: uuid.UUID) -> Path:
    """Where the bot writes (and the processor reads) a call's full-fidelity WAV."""
    return Path(get_settings().recordings_dir) / f"{call_id}.wav"


async def _rebuild_transcript_from_recording(
    session: AsyncSession, call_id: uuid.UUID
) -> int:
    """Replace the call's live (streaming) chunks with a complete batch transcript.

    The live streaming agent is best-effort and can drop words. Re-transcribing the
    full recording in one pass is what guarantees every word reaches the MOM. If the
    recording is missing or the batch call fails, we keep whatever live chunks exist.
    Returns the number of authoritative utterances written (0 = fell back to live).
    """
    wav = recording_path(call_id)
    if not wav.exists():
        log.warning("No recording at %s; using live streaming chunks for %s", wav, call_id)
        return 0
    try:
        utterances = await batch_transcription.transcribe_file(wav)
    except Exception:
        log.exception("Batch transcription failed for %s; falling back to live chunks", call_id)
        return 0
    if not utterances:
        log.warning("Batch transcript empty for %s; falling back to live chunks", call_id)
        return 0

    # Batch result is authoritative: drop any partial live chunks, insert the full set.
    await session.execute(delete(CallTranscript).where(CallTranscript.call_id == call_id))
    for u in utterances:
        session.add(
            CallTranscript(
                call_id=call_id,
                speaker_label=u.speaker_label,
                text=u.text,
                start_ts=u.start_ts,
                end_ts=u.end_ts,
                confidence=u.confidence,
            )
        )
    await session.flush()
    log.info(
        "Rebuilt transcript for %s from recording: %d utterances (replaced live chunks)",
        call_id,
        len(utterances),
    )
    return len(utterances)


def format_transcript(chunks: list[CallTranscript]) -> str:
    """Render ordered chunks for the LLM.

    A label that's still a bare diarization index ("0","1") is shown as "Speaker N";
    a label already resolved to a real name (via the active-speaker timeline) is shown
    as that name — so the LLM's summary/contributions inherit ground-truth names for
    the speakers we're certain about and only has to reason about the rest.
    """
    lines = []
    for c in chunks:
        label = c.speaker_label
        if label is None:
            speaker = "Speaker ?"
        elif str(label).isdigit():
            speaker = f"Speaker {label}"
        else:
            speaker = str(label)
        lines.append(f"[{c.start_ts:.1f}s] {speaker}: {c.text}")
    return "\n".join(lines)


# UI-control tokens Meet appends to a roster row when scraped (e.g. "Alice devices more_vert").
_ROSTER_JUNK = ("devices", "more_vert", "More actions", "frame_person", "present_to_all")


def clean_roster(raw: list[str] | None, bot_hints: set[str]) -> list[str]:
    """Turn the messy scraped Meet roster into clean human names.

    Drops the bot's own entry (the "(You)" row and anything matching the bot account/
    display name), strips trailing Meet UI tokens, and de-duplicates. Returns real
    attendee names suitable to feed the LLM and store as MOM attendees.
    """
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, str):
            continue
        if "(You)" in item:  # the bot is the viewer, so its own row is marked "(You)"
            continue
        name = item
        for junk in _ROSTER_JUNK:
            idx = name.find(junk)
            if idx != -1:
                name = name[:idx]
        name = name.strip(" , ")
        low = name.lower()
        if not name or len(name) > 60 or low in seen:
            continue
        if any(h and h in low for h in bot_hints):  # the bot account / notetaker
            continue
        seen.add(low)
        out.append(name)
    return out


def _memory_text(mom: Mom) -> str:
    """What we embed into company_memory: summary plus the highest-signal fields."""
    parts = [mom.raw_summary or ""]
    if mom.points_discussed:
        parts.append("Points discussed: " + "; ".join(mom.points_discussed))
    if mom.action_items:
        parts.append("Action items: " + "; ".join(mom.action_items))
    if mom.pain_points:
        parts.append("Pain points: " + "; ".join(mom.pain_points))
    if mom.objections:
        parts.append("Objections: " + "; ".join(mom.objections))
    if mom.next_steps:
        parts.append("Next steps: " + mom.next_steps)
    return "\n".join(p for p in parts if p)


async def process_call(
    session: AsyncSession,
    call_id: uuid.UUID,
    manual_labels: dict[str, str] | None = None,
) -> Mom | None:
    """Run the full call-end pipeline for one call. Idempotent-ish: safe to retry.

    `manual_labels` (diarization index -> real name) forces ground-truth attribution
    for calls with no active-speaker timeline — e.g. re-processing an old recording
    where we know who actually spoke. It takes the same precedence as timeline truth.
    """
    call = await session.get(Call, call_id)
    if call is None:
        log.warning("process_call: call %s not found", call_id)
        return None

    # Idempotent: multiple triggers (bot end, LiveKit webhook, manual stop) can fire
    # for one call — only the first produces the MOM; the rest return it unchanged.
    existing = (
        await session.execute(select(Mom).where(Mom.call_id == call_id))
    ).scalars().first()
    if existing is not None:
        log.info("process_call: MOM already exists for call %s; skipping", call_id)
        return existing

    # Authoritative transcript: re-transcribe the complete recording before analysis
    # so the MOM is built from every word, not just the live streaming chunks.
    await _rebuild_transcript_from_recording(session, call_id)

    chunks = (
        await session.execute(
            select(CallTranscript)
            .where(CallTranscript.call_id == call_id)
            .order_by(CallTranscript.start_ts)
        )
    ).scalars().all()

    if not chunks:
        log.warning("process_call: no transcript for call %s; marking failed", call_id)
        call.status = CallStatus.failed
        await session.commit()
        return None

    # Real attendee names from the Meet roster, with the bot itself removed.
    s = get_settings()
    bot_hints = {(s.bot_display_name or "").strip().lower()}
    if s.bot_google_account_email:
        local = s.bot_google_account_email.split("@")[0]
        bot_hints.add(re.sub(r"\d+", "", local).strip().lower())  # "blostem3" -> "blostem"
    roster = clean_roster(call.participants, {h for h in bot_hints if h})

    # --- Role split: our team vs the client (evidence only, never LLM-decided) ---
    # Strongest first: email-verified Meet participant identity via the bot's own
    # account (works for ANY employee, no registration), then calendar attendee
    # emails, then the team roster. Loaded before the LLM call so the analysis
    # prompt can be seeded with who is CONFIRMED on which side.
    meet_participants = await meet_identity.resolve_participants(session, call)
    meet_roles = participant_roles.meet_role_map(meet_participants)
    email_roles = await participant_roles.build_email_roles(session, call)
    internal_names = await participant_roles.load_internal_names(session)
    sides = (
        participant_roles.sides_from_roster(roster, internal_names, email_roles, meet_roles)
        if participant_roles.has_signal(internal_names, email_roles, meet_roles)
        else {}
    )

    company = await session.get(Company, call.company_id)
    # kind == "internal": an internal meeting filed under a label — every attendee is
    # one of ours by definition, which also makes it a free roster-learning source.
    internal_meeting = bool(company and company.kind == "internal")
    client_company = company.name if company and not internal_meeting else None

    # --- Ground-truth speaker attribution (before the LLM) ---
    # Correlate the diarized turns against Meet's active-speaker timeline. Labels we
    # can name with confidence get relabeled NOW, so the transcript the LLM sees
    # already carries real names for them — its summary/contributions inherit those,
    # and it only has to reason about whoever the timeline couldn't resolve.
    samples, poll_interval = speaker_attribution.load_timeline(call_id)
    ground_truth = speaker_attribution.correlate_labels_to_names(
        chunks, samples, roster, poll_interval
    )
    # Manual override (re-processing a call with no timeline) is ground truth too.
    if manual_labels:
        ground_truth.update({str(k): v for k, v in manual_labels.items()})
    grounded_labels = set(ground_truth)  # original index labels resolved by ground truth
    if ground_truth:
        for c in chunks:
            if c.speaker_label is not None:
                mapped = ground_truth.get(str(c.speaker_label).strip())
                if mapped:
                    c.speaker_label = mapped
        await session.flush()
    # Talk-time stats computed AFTER relabel so labels line up with the transcript the
    # LLM sees (real names for grounded speakers, "Speaker N" for the rest).
    stats = speaker_attribution.speaking_time_stats(chunks)
    log.info(
        "process_call: analyzing call %s (%d chunks, %d attendees, %d/%d labels grounded)",
        call_id, len(chunks), len(roster), len(grounded_labels), len(stats),
    )

    transcript = format_transcript(list(chunks))
    result = await analysis.analyze(
        transcript,
        roster,
        stats,
        sides,
        our_company=s.our_company_name,
        client_company=client_company,
    )

    # LLM fallback: name only the labels the timeline could NOT resolve (still bare
    # diarization indices). Ground truth always wins; the LLM never overrides it.
    name_for: dict[str, str] = {}
    for sn in result.mom.speaker_map:
        key = re.sub(r"(?i)^speaker\s*", "", sn.label or "").strip()
        if key and key not in grounded_labels and sn.name and sn.name.strip():
            name_for[key] = sn.name.strip()
    if name_for:
        for c in chunks:
            if c.speaker_label is not None and str(c.speaker_label).isdigit():
                mapped = name_for.get(str(c.speaker_label).strip())
                if mapped:
                    c.speaker_label = mapped
        await session.flush()

    # --- Role attribution: stamp each segment now that labels hold real names ---
    # Evidence only: Meet identity > calendar emails > roster. The LLM's `sides`
    # section is used solely to seed its own performance grading — it never sets a
    # role. With no signal from any source, roles stay NULL rather than guessed.
    if internal_meeting:
        # Internal meeting: every named speaker is one of ours by definition.
        for c in chunks:
            named = c.speaker_label and not str(c.speaker_label).isdigit()
            c.role = participant_roles.INTERNAL if named else participant_roles.UNKNOWN
        await session.flush()
    elif participant_roles.has_signal(internal_names, email_roles, meet_roles):
        for c in chunks:
            c.role = participant_roles.role_for(
                c.speaker_label, internal_names, email_roles, meet_roles
            )
        await session.flush()

    # --- Self-learning roster (evidence-backed only) ---
    # Email-verified internal participants are remembered, so even calls where the
    # Meet lookup later fails (or people join anonymously) classify them by name.
    # Internal meetings register the whole attendee roster: colleagues by definition.
    if internal_meeting:
        learn = [(n, None) for n in roster]
        await participant_roles.auto_register_internal(session, learn, source="auto")
    else:
        learn = [
            (p["name"], p["email"])
            for p in meet_participants
            if p["role"] == participant_roles.INTERNAL and p["name"]
        ]
        await participant_roles.auto_register_internal(session, learn, source="meet")

    # Attendees: prefer the real roster names, enriched with role / decision-maker the LLM
    # inferred; fall back to the LLM's own list only when the roster wasn't captured.
    llm_by_name = {a.name.strip().lower(): a for a in result.mom.attendees if a.name}
    if roster:
        attendees_data = []
        for n in roster:
            match = llm_by_name.get(n.lower())
            attendees_data.append(
                {
                    "name": n,
                    "role": match.role if match else None,
                    "is_decision_maker": bool(match.is_decision_maker) if match else False,
                }
            )
    else:
        attendees_data = [a.model_dump() for a in result.mom.attendees]

    mom = Mom(
        call_id=call.id,
        company_id=call.company_id,
        attendees=attendees_data,
        points_discussed=result.mom.points_discussed,
        action_items=result.mom.action_items,
        contributions=[c.model_dump() for c in result.mom.contributions],
        pain_points=result.mom.pain_points,
        objections=result.mom.objections,
        went_well=result.mom.went_well,
        to_improve=result.mom.to_improve,
        next_steps=result.mom.next_steps,
        decision_maker=result.mom.decision_maker,
        budget_signal=result.mom.budget_signal,
        raw_summary=result.mom.raw_summary,
    )
    session.add(mom)

    score = CallScore(
        call_id=call.id,
        engagement_score=result.scores.engagement_score,
        objection_severity=result.scores.objection_severity,
        urgency_score=result.scores.urgency_score,
        technical_fit_score=result.scores.technical_fit_score,
        overall_rating=result.scores.overall_rating,
        qualitative_notes=result.scores.qualitative_notes,
    )
    session.add(score)

    # Team performance metrics: deterministic talk-time split + LLM confidence/
    # answer-quality/conversion. One row per call, alongside the MOM + score.
    tt = metrics.compute_talk_time(chunks)
    perf = result.performance
    session.add(
        CallMetrics(
            call_id=call.id,
            team_talk_seconds=tt["team_talk_seconds"],
            client_talk_seconds=tt["client_talk_seconds"],
            unknown_talk_seconds=tt["unknown_talk_seconds"],
            team_turns=tt["team_turns"],
            client_turns=tt["client_turns"],
            talk_ratio=tt["talk_ratio"],
            confidence_score=perf.confidence_score,
            confidence_notes=perf.confidence_notes,
            answer_quality_score=perf.answer_quality_score,
            answer_notes=perf.answer_notes,
            client_questions=perf.client_questions,
            questions_answered=perf.questions_answered,
            conversion_probability=perf.conversion_probability,
            conversion_notes=perf.conversion_notes,
        )
    )
    await session.flush()

    # Company memory for the next meeting (spec step 7).
    await embedder.store_memory(session, call.company_id, call.id, _memory_text(mom))

    call.status = CallStatus.completed
    if call.ended_at is None:
        call.ended_at = datetime.datetime.now(datetime.timezone.utc)

    await session.commit()
    log.info("process_call: completed call %s", call_id)
    return mom


async def recover_interrupted_calls() -> None:
    """Finish calls orphaned by a crash or restart — no meeting waits on a human.

    At startup no bot can be running (the manager's registry is in-memory), so
    every call still marked scheduled/in_progress is an orphan from the previous
    process. Anything with audio on disk gets the full pipeline — a partial
    recording still yields minutes; the rest are marked failed. Auto-join events
    tied to those calls go back to pending when the meeting could still be in
    progress, so the poller sends a fresh bot within a tick.
    """
    from app.core.db import SessionLocal  # local import: avoid module-load cycles
    from app.models import calendar_event as ce
    from app.models.calendar_event import CalendarEvent

    async with SessionLocal() as db:
        stale = (
            await db.execute(
                select(Call).where(
                    Call.status.in_((CallStatus.scheduled, CallStatus.in_progress))
                )
            )
        ).scalars().all()
        if not stale:
            return
        log.warning("recovering %d call(s) interrupted by a restart", len(stale))
        now = datetime.datetime.now(datetime.timezone.utc)

        for call in stale:
            call_id = call.id
            try:
                if recording_path(call_id).exists():
                    await process_call(db, call_id)  # ends completed (or failed)
                else:
                    call.status = CallStatus.failed
                    call.ended_at = call.ended_at or now
                    await db.commit()
            except Exception:
                log.exception("recovery failed for call %s", call_id)
                await db.rollback()  # keep the session usable for the next orphan
                continue

            # If its meeting may still be running, hand it back to the poller.
            events = (
                await db.execute(
                    select(CalendarEvent).where(
                        CalendarEvent.call_id == call_id,
                        CalendarEvent.status == ce.DISPATCHED,
                    )
                )
            ).scalars().all()
            for ev in events:
                if ev.end_at is None or ev.end_at > now:
                    ev.status, ev.call_id = ce.PENDING, None
                    ev.note = "re-queued after a server restart"
            await db.commit()
