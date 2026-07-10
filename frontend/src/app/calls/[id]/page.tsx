"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  api,
  type Call,
  type Company,
  type Metrics,
  type Mom,
  type Outcome,
  type OutcomeStatus,
  type Score,
  type SimilarCall,
  type SpeakerRole,
  type Transcript,
} from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  Chip,
  ErrorNote,
  Eyebrow,
  Field,
  Loading,
  Ring,
  SectionLabel,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { Counter, MotionMeter, Reveal } from "@/components/motion";
import { SaveMeetingDialog } from "@/components/save-meeting-dialog";
import {
  ArrowLeftIcon,
  DocIcon,
  UsersIcon,
  CheckIcon,
  ChevronRightIcon,
  BuildingIcon,
  SparkIcon,
} from "@/components/icons";
import { fmtClock, fmtDateTime, fmtDuration, fmtSeconds } from "@/lib/format";
import { dealHealth, healthLabel, risk, sentiment } from "@/lib/intel";

export default function CallDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [call, setCall] = useState<Call | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [transcript, setTranscript] = useState<Transcript[]>([]);
  const [mom, setMom] = useState<Mom | null>(null);
  const [score, setScore] = useState<Score | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [processing, setProcessing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);
  const [savingOutcome, setSavingOutcome] = useState<OutcomeStatus | null>(null);
  const [similar, setSimilar] = useState<SimilarCall[] | null>(null);
  const [findingSimilar, setFindingSimilar] = useState(false);
  const [similarError, setSimilarError] = useState<string | null>(null);
  const [showSave, setShowSave] = useState(false);
  const [pendingSave, setPendingSave] = useState(false);

  const companyObj = companies.find((x) => x.id === call?.company_id) ?? null;
  const company = companyObj?.name ?? null;

  async function load() {
    const c = await api.getCall(id);
    setCall(c);
    setTranscript(await api.getTranscript(id).catch(() => []));
    setMom(await api.getMom(id).catch(() => null));
    setScore(await api.getScore(id).catch(() => null));
    setMetrics(await api.getMetrics(id).catch(() => null));
    setOutcome(await api.getCallOutcome(id).catch(() => null));
    api.listCompanies().then(setCompanies).catch(() => {});
    return c;
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // After the user summarizes, prompt them to file the meeting once the minutes land.
  useEffect(() => {
    if (pendingSave && mom) {
      setShowSave(true);
      setPendingSave(false);
    }
  }, [pendingSave, mom]);

  // Poll while the bot is live, or just after it ends until the minutes land.
  useEffect(() => {
    if (!call) return;
    const waiting =
      call.status === "scheduled" ||
      call.status === "in_progress" ||
      (call.status === "completed" && !mom);
    if (!waiting) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [call?.status, mom]);

  async function process() {
    setProcessing(true);
    setActionError(null);
    try {
      await api.processCall(id);
      await load();
      setPendingSave(true); // open the save prompt once minutes are loaded
    } catch (e) {
      setActionError(String(e));
    } finally {
      setProcessing(false);
    }
  }

  // Pull Google Meet's own transcript (no bot) and analyze — for meetings that
  // Meet transcribed itself. Requires the Meet API service account on the server.
  async function importMeetTranscript() {
    setImporting(true);
    setActionError(null);
    try {
      await api.importTranscript(id);
      await load();
      setPendingSave(true);
    } catch (e) {
      setActionError(String(e));
    } finally {
      setImporting(false);
    }
  }

  async function endMeeting() {
    setEnding(true);
    setPendingSave(true); // minutes arrive via polling; the prompt opens then
    try {
      await api.stopCall(id);
      await load();
    } finally {
      setEnding(false);
    }
  }

  async function recordOutcome(status: OutcomeStatus) {
    if (!call) return;
    setSavingOutcome(status);
    try {
      setOutcome(await api.createOutcome({ company_id: call.company_id, call_id: id, status }));
    } finally {
      setSavingOutcome(null);
    }
  }

  async function findSimilar() {
    setFindingSimilar(true);
    setSimilarError(null);
    try {
      setSimilar(await api.getSimilar(id));
    } catch (e) {
      setSimilarError(String(e));
    } finally {
      setFindingSimilar(false);
    }
  }

  const live = call?.status === "in_progress" || call?.status === "scheduled";
  // True from the moment the user ends/analyzes until the minutes land — covers the
  // server-side MOM generation window that we wait on via polling.
  const analyzing = !mom && (pendingSave || processing || importing || ending);

  if (!call) return <Loading label="Loading call" />;

  const attendeeNames =
    mom?.attendees?.map((a) => a.name).filter(Boolean) ??
    (call.participants as string[] | null) ??
    [];

  const roleCounts = transcript.reduce(
    (acc, t) => {
      const k = t.role === "internal" ? "internal" : t.role === "client" ? "client" : "unknown";
      acc[k] += 1;
      return acc;
    },
    { internal: 0, client: 0, unknown: 0 },
  );

  return (
    <div className="w-full space-y-6 rise">
      <Link
        href="/calls"
        className="inline-flex items-center gap-1.5 text-sm text-muted transition hover:text-ink"
      >
        <ArrowLeftIcon width={16} height={16} /> All meetings
      </Link>

      {/* Header */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Eyebrow>{call.meeting_platform} meeting</Eyebrow>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">
              {company ?? "…"}
            </h1>
            {companyObj?.kind === "internal" && <Badge tone="scheduled">Internal</Badge>}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-muted">
            <span>{fmtDateTime(call.started_at ?? call.created_at)}</span>
            <span className="text-faint">·</span>
            <span>
              {call.started_at
                ? `${live ? "running " : ""}${fmtDuration(call.started_at, call.ended_at)}`
                : "not started"}
            </span>
            {attendeeNames.length > 0 && (
              <>
                <span className="text-faint">·</span>
                <span className="inline-flex items-center gap-1">
                  <UsersIcon width={13} height={13} /> {attendeeNames.length} attendees
                </span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <StatusBadge status={call.status} />
          {!live && mom && (
            <Button variant="secondary" onClick={() => setShowSave(true)}>
              <BuildingIcon width={15} height={15} /> Save details
            </Button>
          )}
          {live ? (
            <Button variant="danger" onClick={endMeeting} disabled={ending}>
              {ending ? <Spinner /> : null}
              {ending ? "Ending…" : "End meeting & summarize"}
            </Button>
          ) : (
            <>
              {transcript.length === 0 && (
                <Button
                  variant="ghost"
                  onClick={importMeetTranscript}
                  disabled={importing || processing}
                  title="Pull Google Meet's own transcript (no bot needed) and analyze"
                >
                  {importing ? <Spinner /> : <DocIcon width={15} height={15} />}
                  {importing ? "Importing…" : "Import transcript"}
                </Button>
              )}
              <Button variant="secondary" onClick={process} disabled={processing || importing}>
                {processing ? <Spinner /> : null}
                {processing ? "Analyzing…" : mom ? "Re-run analysis" : "Run analysis"}
              </Button>
            </>
          )}
        </div>
      </header>

      {actionError && <ErrorNote>{actionError}</ErrorNote>}

      {/* Deal outcome — external meetings only */}
      {companyObj?.kind !== "internal" && (
        <Card className="flex flex-wrap items-center justify-between gap-4 p-4">
          <div>
            <SectionLabel>Deal status</SectionLabel>
            <p className="mt-1 text-sm text-muted">
              {outcome ? (
                <>
                  Recorded as <OutcomeWord status={outcome.status} />. This feeds your Deal
                  Insights.
                </>
              ) : (
                "Mark whether the deal closed so this call counts in your Deal Insights."
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <OutcomeBtn label="Won" tone="won" current={outcome?.status} value="accepted" busy={savingOutcome} onClick={recordOutcome} />
            <OutcomeBtn label="Lost" tone="lost" current={outcome?.status} value="rejected" busy={savingOutcome} onClick={recordOutcome} />
            <OutcomeBtn label="Open" tone="pending" current={outcome?.status} value="pending" busy={savingOutcome} onClick={recordOutcome} />
          </div>
        </Card>
      )}

      <Reveal as="div" className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Scorecard */}
        <Card className="p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <SectionLabel>Deal health</SectionLabel>
            {score?.overall_rating != null && (
              <span className="font-mono text-sm font-semibold text-ink">
                <Counter value={score.overall_rating} />
                <span className="text-faint">/100</span>
              </span>
            )}
          </div>
          {score ? (
            <div className="space-y-3.5">
              {(() => {
                const health = dealHealth(score);
                const hl = healthLabel(health);
                return (
                  <div className="flex items-center gap-4 rounded-xl border border-border bg-raised/50 p-4">
                    <Ring value={health} size={104} label="health" />
                    <div className="min-w-0 space-y-2">
                      <Badge tone={hl.tone}>{hl.label}</Badge>
                      <div className="flex gap-4">
                        <MiniStat label="Sentiment" value={sentiment(score)} />
                        <MiniStat label="Risk" value={risk(score)} invert />
                      </div>
                    </div>
                  </div>
                );
              })()}
              <div className="pt-1"><SectionLabel>Rubric</SectionLabel></div>
              <MotionMeter label="Engagement" value={score.engagement_score} />
              <MotionMeter label="Objection severity" value={score.objection_severity} invert />
              <MotionMeter label="Urgency" value={score.urgency_score} />
              <MotionMeter label="Technical fit" value={score.technical_fit_score} />
              <div className="border-t border-hairline pt-3.5">
                <MotionMeter label="Overall" value={score.overall_rating} emphasis />
              </div>
              {score.qualitative_notes && (
                <p className="border-t border-hairline pt-3 text-[13px] leading-relaxed text-muted">
                  {score.qualitative_notes}
                </p>
              )}
            </div>
          ) : analyzing ? (
            <div className="flex flex-col items-center gap-3 py-10 text-center">
              <Spinner size={36} className="text-accent" />
              <p className="text-xs text-faint">Scoring the meeting…</p>
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-faint">
              {live ? "Scored after the meeting ends." : "Not scored yet."}
            </p>
          )}
        </Card>

        {/* Minutes */}
        <Card className="p-5 lg:col-span-3">
          <div className="mb-4 flex items-center justify-between">
            <SectionLabel>Minutes of meeting</SectionLabel>
            {mom ? (
              <Badge tone="done">Ready</Badge>
            ) : analyzing ? (
              <Badge tone="scheduled" dot>Processing</Badge>
            ) : live ? (
              <Badge tone="live" dot>Live</Badge>
            ) : null}
          </div>
          {mom ? (
            <div className="space-y-5 text-sm">
              {mom.raw_summary && (
                <p className="leading-relaxed text-ink/90">{mom.raw_summary}</p>
              )}

              <MomList label="Attendees" empty="None identified.">
                {mom.attendees?.map((a, i) => (
                  <li key={i} className="flex items-center gap-2 text-ink">
                    <span className="h-1 w-1 rounded-full bg-faint" />
                    {a.name}
                    {a.role && <span className="text-faint">— {a.role}</span>}
                    {a.is_decision_maker && (
                      <Badge tone="scheduled">decision maker</Badge>
                    )}
                  </li>
                ))}
              </MomList>

              <MomList label="Points discussed" empty="None captured.">
                {mom.points_discussed?.map((p, i) => (
                  <li key={i} className="flex gap-2 text-ink">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-faint" />
                    {p}
                  </li>
                ))}
              </MomList>

              <MomList label="Action items — what's next" empty="None.">
                {mom.action_items?.map((a, i) => (
                  <li key={i} className="flex gap-2 text-ink">
                    <CheckIcon width={15} height={15} className="mt-0.5 shrink-0 text-accent" />
                    {a}
                  </li>
                ))}
              </MomList>

              {mom.contributions && mom.contributions.length > 0 && (
                <div className="border-t border-hairline pt-4">
                  <SectionLabel>Who said what</SectionLabel>
                  <div className="mt-2 space-y-3">
                    {mom.contributions.map((c, i) => (
                      <div key={i}>
                        <div className="flex items-center gap-2">
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent-soft font-mono text-[10px] font-semibold text-accent">
                            {initials(c.name)}
                          </span>
                          <span className="font-medium text-ink">{c.name}</span>
                        </div>
                        <p className="mt-1 pl-7 leading-relaxed text-muted">{c.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {((mom.pain_points?.length ?? 0) > 0 || (mom.objections?.length ?? 0) > 0) && (
                <div className="grid grid-cols-1 gap-4 border-t border-hairline pt-4 sm:grid-cols-2">
                  {mom.pain_points && mom.pain_points.length > 0 && (
                    <ChipGroup label="Pain points" items={mom.pain_points} tone="pending" />
                  )}
                  {mom.objections && mom.objections.length > 0 && (
                    <ChipGroup label="Objections" items={mom.objections} tone="lost" />
                  )}
                </div>
              )}

              {((mom.went_well?.length ?? 0) > 0 || (mom.to_improve?.length ?? 0) > 0) && (
                <div className="border-t border-hairline pt-4">
                  <div className="mb-2.5 flex items-center gap-2">
                    <SparkIcon width={15} height={15} className="text-accent" />
                    <SectionLabel>How the meeting went</SectionLabel>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <RetroCard
                      title="What went well"
                      items={mom.went_well}
                      accent="emerald"
                    />
                    <RetroCard
                      title="What to improve"
                      items={mom.to_improve}
                      accent="amber"
                    />
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 gap-2 border-t border-hairline pt-4 sm:grid-cols-2">
                <Field label="Decision maker" value={mom.decision_maker} />
                <Field label="Budget signal" value={mom.budget_signal} />
                {mom.next_steps && (
                  <div className="sm:col-span-2">
                    <Field label="Next steps" value={mom.next_steps} />
                  </div>
                )}
              </div>
            </div>
          ) : analyzing ? (
            <div className="flex flex-col items-center gap-4 py-12 text-center">
              <Spinner size={44} className="text-accent" />
              <div>
                <p className="text-sm font-medium text-ink">Generating minutes…</p>
                <p className="mt-1 text-xs text-faint">
                  The AI is summarizing the meeting. This usually takes a moment.
                </p>
              </div>
            </div>
          ) : (
            <p className="py-10 text-center text-sm text-faint">
              {live
                ? "The minutes are written when you end the meeting."
                : "Not analyzed yet. Run analysis to generate the minutes."}
            </p>
          )}
        </Card>
      </Reveal>

      {/* Team performance — talk-time split, confidence, answers, conversion */}
      {metrics && (
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <SectionLabel>Team performance</SectionLabel>
            <span className="font-mono text-xs text-faint">our team vs client</span>
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Talk time */}
            <div className="space-y-3 lg:col-span-2">
              <SectionLabel>Talk time</SectionLabel>
              {metrics.talk_ratio != null ? (
                <>
                  <TalkBar
                    team={metrics.team_talk_seconds ?? 0}
                    client={metrics.client_talk_seconds ?? 0}
                  />
                  <div className="flex flex-wrap gap-8">
                    <TalkStat
                      meta={roleMeta("internal")}
                      seconds={metrics.team_talk_seconds ?? 0}
                      turns={metrics.team_turns ?? 0}
                      pct={Math.round((metrics.talk_ratio ?? 0) * 100)}
                    />
                    <TalkStat
                      meta={roleMeta("client")}
                      seconds={metrics.client_talk_seconds ?? 0}
                      turns={metrics.client_turns ?? 0}
                      pct={Math.round((1 - (metrics.talk_ratio ?? 0)) * 100)}
                    />
                  </div>
                </>
              ) : (
                <p className="py-4 text-sm text-faint">
                  Roles weren&apos;t identified for this call, so talk time can&apos;t be split by
                  side. (Needs the meeting&apos;s calendar invite to classify attendees.)
                </p>
              )}
            </div>
            {/* Conversion odds */}
            <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-border bg-raised/50 p-4">
              <SectionLabel>Conversion odds</SectionLabel>
              <Ring value={metrics.conversion_probability ?? 0} size={112} label="convert" />
              <span className="font-mono text-lg font-semibold tabular-nums text-ink">
                <Counter value={metrics.conversion_probability ?? 0} />
                <span className="text-faint">%</span>
              </span>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-x-8 gap-y-4 border-t border-hairline pt-4 sm:grid-cols-2">
            <div className="space-y-2">
              <MotionMeter label="Pitch confidence" value={metrics.confidence_score} />
              {metrics.confidence_notes && (
                <p className="text-[13px] leading-relaxed text-muted">{metrics.confidence_notes}</p>
              )}
            </div>
            <div className="space-y-2">
              <MotionMeter label="Answer quality" value={metrics.answer_quality_score} />
              {metrics.client_questions != null && (
                <p className="font-mono text-xs text-faint">
                  Answered {metrics.questions_answered ?? 0}/{metrics.client_questions} client
                  questions
                </p>
              )}
              {metrics.answer_notes && (
                <p className="text-[13px] leading-relaxed text-muted">{metrics.answer_notes}</p>
              )}
            </div>
          </div>
          {metrics.conversion_notes && (
            <p className="mt-4 border-t border-hairline pt-3 text-[13px] leading-relaxed text-muted">
              <span className="font-medium text-ink">Conversion outlook — </span>
              {metrics.conversion_notes}
            </p>
          )}
        </Card>
      )}

      {/* Transcript ledger */}
      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <SectionLabel>Transcript</SectionLabel>
          <div className="flex items-center gap-3 font-mono text-xs text-faint">
            {roleCounts.internal > 0 && (
              <RoleLegend meta={roleMeta("internal")} count={roleCounts.internal} />
            )}
            {roleCounts.client > 0 && (
              <RoleLegend meta={roleMeta("client")} count={roleCounts.client} />
            )}
            <span>{transcript.length} segments</span>
          </div>
        </div>
        {transcript.length === 0 ? (
          <p className="py-8 text-center text-sm text-faint">
            {live ? "Listening… speech will appear here." : "No transcript captured."}
          </p>
        ) : (
          <div className="scroll-thin max-h-[28rem] space-y-px overflow-y-auto">
            {transcript.map((t) => {
              const rm = roleMeta(t.role);
              return (
                <div
                  key={t.id}
                  className="flex gap-4 rounded-md px-2 py-1.5 text-sm hover:bg-raised"
                >
                  <span className="w-14 shrink-0 pt-0.5 text-right font-mono text-xs tabular-nums text-faint">
                    {fmtSeconds(t.start_ts)}
                  </span>
                  <span
                    className="flex w-28 shrink-0 items-center gap-1.5 pt-0.5"
                    title={`${speakerName(t.speaker_label) ?? "—"} · ${rm.label}`}
                  >
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${rm.dot}`} />
                    <span className={`truncate text-xs font-medium ${rm.text}`}>
                      {speakerName(t.speaker_label) ?? "—"}
                    </span>
                  </span>
                  <span className="text-ink/90">{t.text}</span>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Similar calls — cross-company memory */}
      <Card className="p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <DocIcon width={16} height={16} className="text-muted" />
            <SectionLabel>Similar calls across companies</SectionLabel>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={findSimilar}
            disabled={findingSimilar || !mom}
            title={mom ? undefined : "Analyze the call first to build its summary"}
          >
            {findingSimilar ? <Spinner /> : null}
            {findingSimilar ? "Searching…" : "Find similar"}
          </Button>
        </div>
        {similarError && <p className="text-sm text-danger">{similarError}</p>}
        {!similarError && similar === null && (
          <p className="text-sm text-faint">
            {mom
              ? "Search past calls for ones that resemble this conversation."
              : "Available once the call has been analyzed."}
          </p>
        )}
        {similar?.length === 0 && <p className="text-sm text-faint">No similar calls found.</p>}
        {similar && similar.length > 0 && (
          <div className="space-y-2">
            {similar.map((s, i) => {
              const score = (
                <span className="shrink-0 rounded-md bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">
                  {(1 - s.distance).toFixed(2)}
                </span>
              );
              const text = (
                <span className="line-clamp-2 flex-1 text-muted">
                  {s.source_text ?? "(no summary)"}
                </span>
              );
              // The neighbour's own call may have been deleted/re-filed; with no
              // call_id there's nowhere to navigate, so render a static row.
              return s.call_id ? (
                <Link
                  key={i}
                  href={`/calls/${s.call_id}`}
                  className="group flex items-start gap-3 rounded-lg border border-border p-3 text-sm transition hover:bg-raised"
                >
                  {score}
                  {text}
                  <ChevronRightIcon
                    width={15}
                    height={15}
                    className="mt-0.5 shrink-0 text-faint group-hover:text-muted"
                  />
                </Link>
              ) : (
                <div
                  key={i}
                  className="flex items-start gap-3 rounded-lg border border-border p-3 text-sm"
                >
                  {score}
                  {text}
                  <span className="mt-0.5 shrink-0 font-mono text-[11px] text-faint">memory only</span>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {call && (
        <SaveMeetingDialog
          open={showSave}
          onClose={() => setShowSave(false)}
          call={call}
          company={companyObj}
          companies={companies}
          outcome={outcome}
          onSaved={load}
        />
      )}
    </div>
  );
}

/* — local helpers — */

function MiniStat({ label, value, invert = false }: { label: string; value: number | null; invert?: boolean }) {
  const tone = value == null ? "text-faint" : invert ? (value > 55 ? "text-danger" : "text-muted") : value >= 60 ? "text-success" : "text-warning";
  return (
    <div>
      <div className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-faint">{label}</div>
      <div className={`font-mono text-lg font-semibold tabular-nums ${tone}`}>{value ?? "—"}</div>
    </div>
  );
}

function RetroCard({
  title,
  items,
  accent,
}: {
  title: string;
  items: string[] | null;
  accent: "emerald" | "amber";
}) {
  if (!items || items.length === 0) return null;
  const ring = accent === "emerald" ? "border-success/25 bg-success/8" : "border-warning/25 bg-warning/8";
  const dot = accent === "emerald" ? "bg-success" : "bg-warning";
  const head = accent === "emerald" ? "text-success" : "text-warning";
  return (
    <div className={`rounded-xl border ${ring} p-3.5`}>
      <div className={`mb-2 text-[12px] font-semibold ${head}`}>{title}</div>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-ink/90">
            <span className={`mt-1.5 h-1 w-1 shrink-0 rounded-full ${dot}`} />
            {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Diarization labels are numeric ("0","1"); once mapped they hold the real name. */
function speakerName(label: string | null): string | null {
  if (label == null) return null;
  return /^\d+$/.test(label) ? `S${label}` : label;
}

type RoleMeta = { label: string; text: string; dot: string };

/** Visual treatment for a speaker's side: our team vs the client. */
function roleMeta(role: SpeakerRole | null): RoleMeta {
  switch (role) {
    case "internal":
      return { label: "Our team", text: "text-accent", dot: "bg-accent" };
    case "client":
      return { label: "Client", text: "text-cyan-300", dot: "bg-cyan-400" };
    default:
      return { label: "Unknown", text: "text-muted", dot: "bg-faint" };
  }
}

function TalkBar({ team, client }: { team: number; client: number }) {
  const total = team + client || 1;
  const teamPct = (team / total) * 100;
  return (
    <div className="flex h-3 w-full overflow-hidden rounded-full bg-raised" title="Talk-time split">
      <div className="bg-accent transition-all" style={{ width: `${teamPct}%` }} />
      <div className="bg-cyan-400 transition-all" style={{ width: `${100 - teamPct}%` }} />
    </div>
  );
}

function TalkStat({
  meta,
  seconds,
  turns,
  pct,
}: {
  meta: RoleMeta;
  seconds: number;
  turns: number;
  pct: number;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-xs text-muted">
        <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
        {meta.label}
      </div>
      <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-ink">
        {fmtClock(seconds)} <span className="text-sm text-faint">· {pct}%</span>
      </div>
      <div className="font-mono text-[11px] text-faint">{turns} turns</div>
    </div>
  );
}

function RoleLegend({ meta, count }: { meta: RoleMeta; count: number }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      <span className={meta.text}>
        {meta.label} {count}
      </span>
    </span>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

function OutcomeWord({ status }: { status: OutcomeStatus }) {
  const map = {
    accepted: ["Won", "text-success"],
    rejected: ["Lost", "text-danger"],
    pending: ["Pending", "text-warning"],
  } as const;
  const [text, cls] = map[status];
  return <span className={`font-medium ${cls}`}>{text}</span>;
}

function OutcomeBtn({
  label,
  tone,
  value,
  current,
  busy,
  onClick,
}: {
  label: string;
  tone: "won" | "lost" | "pending";
  value: OutcomeStatus;
  current?: OutcomeStatus;
  busy: OutcomeStatus | null;
  onClick: (s: OutcomeStatus) => void;
}) {
  const active = current === value;
  const activeCls =
    tone === "won"
      ? "bg-success text-white"
      : tone === "lost"
        ? "bg-danger text-white"
        : "bg-warning text-white";
  return (
    <button
      onClick={() => onClick(value)}
      disabled={busy !== null}
      className={`rounded-lg px-3 py-1.5 text-[13px] font-medium transition disabled:opacity-50 ${
        active ? activeCls : "border border-border text-muted hover:bg-raised hover:text-ink"
      }`}
    >
      {busy === value ? "Saving…" : label}
    </button>
  );
}

function MomList({
  label,
  empty,
  children,
}: {
  label: string;
  empty: string;
  children?: React.ReactNode;
}) {
  const arr = Array.isArray(children) ? children : children ? [children] : [];
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      {arr.length > 0 ? (
        <ul className="mt-2 space-y-1.5">{children}</ul>
      ) : (
        <p className="mt-1 text-[13px] text-faint">{empty}</p>
      )}
    </div>
  );
}

function ChipGroup({
  label,
  items,
  tone,
}: {
  label: string;
  items: string[];
  tone: "pending" | "lost";
}) {
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {items.map((it, i) => (
          <Chip key={i} tone={tone}>
            {it}
          </Chip>
        ))}
      </div>
    </div>
  );
}
