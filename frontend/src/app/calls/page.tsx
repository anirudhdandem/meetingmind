"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, CalendarClock, Check, ChevronRight, Copy, Radio, Building2, Clock } from "lucide-react";
import { api, type Call, type CalendarEvent, type Company, type GoogleOAuthStatus, type Outcome, type Transcript } from "@/lib/api";
import { Button, Card, EmptyState, ErrorNote, Input, Loading, OutcomeBadge, PageHeader, StatusBadge, Badge } from "@/components/ui";
import { AuroraBg, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { fmtDateTime, fmtDuration } from "@/lib/format";
import { dealStage } from "@/lib/intel";

const ACTIVE = new Set(["scheduled", "in_progress"]);

export default function MeetingsPage() {
  const router = useRouter();
  const [calls, setCalls] = useState<Call[] | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [schedule, setSchedule] = useState<CalendarEvent[]>([]);
  const [botEmail, setBotEmail] = useState<string | null>(null);
  const [botOAuth, setBotOAuth] = useState<GoogleOAuthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [companyInput, setCompanyInput] = useState("");
  const [url, setUrl] = useState("");
  const [starting, setStarting] = useState(false);

  async function load() {
    const [c, comp, outs, sched] = await Promise.all([
      api.listCalls(),
      api.listCompanies().catch(() => []),
      api.listOutcomes().catch(() => []),
      api.autoJoinSchedule().catch(() => []),
    ]);
    setCalls(c);
    setCompanies(comp);
    setOutcomes(outs);
    setSchedule(sched);
  }

  useEffect(() => {
    load().catch((e) => setError(String(e)));
    // The invite address + whether the bot's Google connection can see its
    // calendar — both drive the auto-join guidance below. Best-effort.
    api.getSettingsStatus().then((s) => setBotEmail(s.bot.account_email)).catch(() => {});
    api.getGoogleStatus("bot").then(setBotOAuth).catch(() => {});
  }, []);

  const hasActive = !!calls?.some((c) => ACTIVE.has(c.status));
  useEffect(() => {
    if (!hasActive) return;
    const t = setInterval(() => load().catch(() => {}), 5000);
    return () => clearInterval(t);
  }, [hasActive]);

  // The auto-join poller ticks server-side every minute; keep the schedule fresh
  // even when nothing is being recorded yet.
  useEffect(() => {
    const t = setInterval(() => api.autoJoinSchedule().then(setSchedule).catch(() => {}), 30000);
    return () => clearInterval(t);
  }, []);

  const companyName = useMemo(() => {
    const m = new Map(companies.map((c) => [c.id, c.name]));
    return (id: string) => m.get(id) ?? "Unknown company";
  }, [companies]);

  const meetingsByCompany = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of calls ?? []) m.set(c.company_id, (m.get(c.company_id) ?? 0) + 1);
    return m;
  }, [calls]);

  const outcomeFor = useMemo(() => {
    const m = new Map<string, Outcome>();
    for (const o of outcomes) if (o.call_id && !m.has(o.call_id)) m.set(o.call_id, o);
    return (callId: string) => m.get(callId);
  }, [outcomes]);

  async function start() {
    const meetingUrl = url.trim();
    const company = companyInput.trim();
    if (!company || !meetingUrl || starting) return;
    setStarting(true);
    setError(null);
    try {
      const call = await api.startCall(meetingUrl, company);
      router.push(`/calls/${call.id}`);
    } catch (e) {
      setError(String(e));
      setStarting(false);
    }
  }

  const active = calls?.filter((c) => ACTIVE.has(c.status)) ?? [];
  const past = calls?.filter((c) => !ACTIVE.has(c.status)) ?? [];

  return (
    <div className="w-full">
      <PageHeader
        eyebrow="Meeting intelligence"
        title="Meetings"
        sub="Invite the bot to a meeting and it joins on its own — or drop in a Meet link to start now. It transcribes live, writes the minutes, scores the call, and files it into account memory."
      />

      {/* Start bot */}
      <Card className="relative mb-8 overflow-hidden p-5">
        <AuroraBg className="opacity-60" />
        <div className="relative">
          <div className="mb-4 flex items-center gap-3">
            <span className="float flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent shadow-glow ring-1 ring-accent/20">
              <Radio size={19} />
            </span>
            <div>
              <div className="font-display text-sm font-semibold text-ink">Start a meeting</div>
              <p className="text-xs text-muted">Name the account, drop the Meet link — the bot joins.</p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-[1fr_1.5fr_auto] sm:items-end">
            <label className="block">
              <span className="mb-1.5 flex items-center gap-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
                <StepDot>1</StepDot> Company
              </span>
              <Input
                value={companyInput}
                onChange={(e) => setCompanyInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && start()}
                placeholder="Acme Corp"
                aria-label="Company name"
                className="glass"
              />
            </label>

            <label className="block">
              <span className="mb-1.5 flex items-center gap-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
                <StepDot>2</StepDot> Meeting URL
              </span>
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && start()}
                placeholder="https://meet.google.com/abc-defg-hij"
                aria-label="Google Meet URL"
                className="glass"
              />
            </label>

            <Button variant="primary" onClick={start} disabled={starting || !companyInput.trim() || !url.trim()}>
              {starting ? "Starting bot…" : "Start bot"}
              {!starting && <ArrowRight size={16} />}
            </Button>
          </div>

          <p className="mt-2.5 flex flex-wrap items-center gap-x-1 text-xs text-muted">
            Or skip this entirely: invite{" "}
            {botEmail ? <CopyEmail email={botEmail} /> : <span className="font-mono text-ink">the bot account</span>}{" "}
            to the meeting and it joins on its own when the meeting starts.
          </p>
        </div>
      </Card>

      {/* Auto-join schedule — meetings found on the bot's calendar */}
      <section className="mb-9">
        <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-faint">
          <CalendarClock size={13} /> Auto-join schedule
        </div>
        {schedule.filter((e) => e.status !== "cancelled" && e.status !== "skipped").length === 0 ? (
          <Card className="p-5">
            {botOAuth && (!botOAuth.connected || !botOAuth.has_calendar_scope) ? (
              <p className="text-sm text-warning">
                Auto-join isn&apos;t active yet — the bot&apos;s Google account{" "}
                {botOAuth.connected ? "can’t see its calendar" : "isn’t connected"}.{" "}
                <Link href="/settings" className="font-medium underline underline-offset-2">
                  Fix it in Settings
                </Link>{" "}
                and invited meetings will join themselves.
              </p>
            ) : (
              <p className="text-sm text-muted">
                No upcoming invites. Add{" "}
                {botEmail ? <CopyEmail email={botEmail} /> : <span className="font-mono text-ink">the bot&apos;s email</span>}{" "}
                as a guest to any calendar event with a Meet link — it shows up here and the bot
                joins at start time, no link pasting needed.
              </p>
            )}
          </Card>
        ) : (
          <Card className="divide-y divide-hairline p-0">
            {schedule
              .filter((e) => e.status !== "cancelled" && e.status !== "skipped")
              .map((e) => (
                <div key={e.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
                  <div className="min-w-0">
                    <div className="truncate font-medium text-ink">{e.title ?? "Untitled meeting"}</div>
                    <div className="font-mono text-[11px] text-faint">
                      {fmtDateTime(e.start_at)} · {e.meet_code}
                      {e.organizer_email ? ` · ${e.organizer_email}` : ""}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2.5">
                    <AutoJoinPill status={e.status} note={e.note} />
                    {e.status === "dispatched" && e.call_id && (
                      <Link
                        href={`/calls/${e.call_id}`}
                        className="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline"
                      >
                        Open <ChevronRight size={14} />
                      </Link>
                    )}
                  </div>
                </div>
              ))}
          </Card>
        )}
      </section>

      {error && <ErrorNote>Couldn’t reach the API: {error}</ErrorNote>}
      {!calls && !error && <Loading label="Loading meetings" />}

      {/* Active */}
      {active.length > 0 && (
        <section className="mb-9">
          <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-warning">
            <span className="live-dot h-1.5 w-1.5 rounded-full bg-warning" /> In progress
          </div>
          <div className="space-y-3">
            {active.map((c) => (
              <ActiveCall key={c.id} call={c} company={companyName(c.company_id)} />
            ))}
          </div>
        </section>
      )}

      {/* Past — card layout */}
      {calls && (
        <section>
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="font-display text-sm font-semibold text-ink">Past meetings</h2>
            {past.length > 0 && <span className="font-mono text-xs text-faint">{past.length} total</span>}
          </div>

          {past.length === 0 ? (
            <EmptyState icon={<Radio size={28} />} title="No past meetings yet">
              Once a meeting ends, it lands here with its minutes, score, deal stage, and outcome.
            </EmptyState>
          ) : (
            <Stagger className="grid gap-3.5 sm:grid-cols-2">
              {past.map((c) => {
                const stage = dealStage({ outcome: outcomeFor(c.id), meetingCount: meetingsByCompany.get(c.company_id) ?? 1 });
                return (
                  <StaggerItem key={c.id}>
                    <Link href={`/calls/${c.id}`} className="group block">
                      <div className="panel hover-ring h-full p-5">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-2.5">
                            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-raised text-faint ring-1 ring-border">
                              <Building2 size={16} />
                            </span>
                            <div>
                              <div className="font-medium text-ink">{companyName(c.company_id)}</div>
                              <div className="font-mono text-[11px] text-faint">{fmtDateTime(c.started_at ?? c.created_at)}</div>
                            </div>
                          </div>
                          {outcomeFor(c.id) ? <OutcomeBadge status={outcomeFor(c.id)!.status} /> : <StatusBadge status={c.status} />}
                        </div>

                        <div className="mt-4 flex flex-wrap items-center gap-2">
                          <Badge tone="accent">{stage}</Badge>
                          <span className="flex items-center gap-1 font-mono text-[11px] text-muted">
                            <Clock size={12} /> {fmtDuration(c.started_at, c.ended_at)}
                          </span>
                          <MinutesPill status={c.status} />
                        </div>

                        <div className="mt-4 flex items-center justify-between border-t border-hairline pt-3">
                          <span className="truncate font-mono text-[11px] text-faint">
                            {c.meeting_url ?? c.livekit_room ?? c.id.slice(0, 8)}
                          </span>
                          <span className="flex items-center gap-1 text-[12px] font-medium text-accent opacity-0 transition group-hover:opacity-100">
                            Open <ChevronRight size={14} />
                          </span>
                        </div>
                      </div>
                    </Link>
                  </StaggerItem>
                );
              })}
            </Stagger>
          )}
        </section>
      )}
    </div>
  );
}

function AutoJoinPill({ status, note }: { status: CalendarEvent["status"]; note: string | null }) {
  if (status === "pending")
    return <span className="font-mono text-[11px] text-warning">Will join</span>;
  if (status === "dispatched")
    return <span className="font-mono text-[11px] text-success">Bot joined</span>;
  return (
    <span className="font-mono text-[11px] text-faint" title={note ?? undefined}>
      Missed
    </span>
  );
}

/** The bot's invite address, click-to-copy — the one thing users must know to use auto-join. */
function CopyEmail({ email }: { email: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(email);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (http, permissions) — the address is still visible to select */
    }
  }

  return (
    <button
      onClick={copy}
      title="Copy email"
      className="inline-flex items-center gap-1 rounded border border-hairline bg-raised px-1.5 py-0.5 font-mono text-[11px] text-ink transition hover:border-accent/40"
    >
      {email}
      {copied ? <Check size={11} className="text-success" /> : <Copy size={11} className="text-faint" />}
    </button>
  );
}

function StepDot({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-accent-soft text-[10px] font-semibold text-accent ring-1 ring-accent/20">
      {children}
    </span>
  );
}

function MinutesPill({ status }: { status: Call["status"] }) {
  if (status === "completed") return <span className="font-mono text-[11px] text-success">Minutes ready</span>;
  if (status === "failed") return <span className="font-mono text-[11px] text-faint">No minutes</span>;
  return <span className="font-mono text-[11px] text-warning">Pending</span>;
}

/* Active-call panel with a live transcript tail. */
function ActiveCall({ call, company }: { call: Call; company: string }) {
  const [tail, setTail] = useState<Transcript[]>([]);

  useEffect(() => {
    let alive = true;
    const pull = () => api.getTranscript(call.id).then((t) => alive && setTail(t.slice(-3))).catch(() => {});
    pull();
    const t = setInterval(pull, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [call.id]);

  return (
    <Card className="overflow-hidden ring-1 ring-warning/20">
      <div className="flex items-center justify-between gap-3 border-b border-warning/15 bg-warning/5 px-5 py-3">
        <div className="flex items-center gap-2.5">
          <StatusBadge status={call.status} />
          <span className="font-medium text-ink">{company}</span>
          <span className="font-mono text-xs text-muted">
            {call.status === "in_progress" ? fmtDuration(call.started_at, null) : "joining…"}
          </span>
        </div>
        <Link href={`/calls/${call.id}`} className="inline-flex items-center gap-1 text-[13px] font-medium text-accent hover:underline">
          Open <ChevronRight size={15} />
        </Link>
      </div>
      <div className="px-5 py-4">
        {tail.length === 0 ? (
          <p className="font-mono text-xs text-faint">Waiting for speech…</p>
        ) : (
          <div className="space-y-1.5">
            {tail.map((t) => (
              <div key={t.id} className="flex gap-3 text-sm">
                <span className="shrink-0 font-mono text-xs text-faint">{t.speaker_label != null ? `S${t.speaker_label}` : "—"}</span>
                <span className="text-muted">{t.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
