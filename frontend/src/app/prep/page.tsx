"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle,
  CalendarClock,
  CheckSquare,
  HelpCircle,
  Sparkles,
  Swords,
  Target,
} from "lucide-react";
import { api, type Call, type Company, type Mom, type Score } from "@/lib/api";
import { Badge, Card, EmptyState, Eyebrow, GlowCard, Loading, PageHeader, SectionLabel } from "@/components/ui";
import { Reveal } from "@/components/motion";
import { dealStage, recommendations } from "@/lib/intel";
import { fmtDateTime } from "@/lib/format";

export default function PrepPage() {
  return (
    <Suspense fallback={<div className="w-full"><Loading label="Loading prep" /></div>}>
      <PrepInner />
    </Suspense>
  );
}

function PrepInner() {
  const params = useSearchParams();
  const callParam = params.get("call");

  const [calls, setCalls] = useState<Call[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selected, setSelected] = useState<string | null>(callParam);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    Promise.all([api.listCalls().catch(() => []), api.listCompanies().catch(() => [])])
      .then(([c, comp]) => {
        setCalls(c);
        setCompanies(comp);
        if (!callParam && c.length) setSelected(c[0].id);
      })
      .finally(() => setLoaded(true));
  }, [callParam]);

  const companyName = (id: string) => companies.find((c) => c.id === id)?.name ?? "Unknown account";
  const recent = useMemo(
    () => [...calls].sort((a, b) => ((a.started_at ?? a.created_at) > (b.started_at ?? b.created_at) ? -1 : 1)),
    [calls],
  );
  const selectedCall = calls.find((c) => c.id === selected) ?? null;

  return (
    <div className="w-full">
      <PageHeader
        eyebrow="AI meeting prep"
        title="Walk in ready"
        sub="A briefing for your next conversation — last meeting’s memory, what’s still open, who’s in the room, the risks to watch, and the moves the AI would make."
      />

      {!loaded && <Loading label="Loading meetings" />}
      {loaded && recent.length === 0 && (
        <EmptyState icon={<CalendarClock size={28} />} title="No meetings to prep from">
          Run a meeting first — its memory becomes the brief for the next one.
        </EmptyState>
      )}

      {loaded && recent.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          {/* meeting picker */}
          <aside className="space-y-2">
            <SectionLabel>Meetings</SectionLabel>
            <div className="scroll-thin max-h-[70vh] space-y-1.5 overflow-y-auto pr-1">
              {recent.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setSelected(c.id)}
                  className={`w-full rounded-xl border px-3.5 py-2.5 text-left transition ${
                    selected === c.id ? "border-accent/30 bg-accent-soft" : "border-border bg-surface hover:border-strong"
                  }`}
                >
                  <div className={`truncate text-sm font-medium ${selected === c.id ? "text-accent" : "text-ink"}`}>
                    {companyName(c.company_id)}
                  </div>
                  <div className="mt-0.5 font-mono text-[11px] text-faint">{fmtDateTime(c.started_at ?? c.created_at)}</div>
                </button>
              ))}
            </div>
          </aside>

          {/* brief */}
          {selectedCall ? (
            <Brief key={selectedCall.id} call={selectedCall} companyName={companyName(selectedCall.company_id)} companies={companies} />
          ) : (
            <Card className="p-8 text-center text-sm text-faint">Pick a meeting to generate its brief.</Card>
          )}
        </div>
      )}
    </div>
  );
}

function Brief({ call, companyName, companies }: { call: Call; companyName: string; companies: Company[] }) {
  const [mom, setMom] = useState<Mom | null>(null);
  const [score, setScore] = useState<Score | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getCompanyLatestMom(call.company_id).catch(() => null),
      api.getScore(call.id).catch(() => null),
    ]).then(([m, s]) => {
      setMom(m);
      setScore(s);
      setLoading(false);
    });
  }, [call.id, call.company_id]);

  if (loading) return <Card className="p-8"><Loading label="Assembling brief" /></Card>;

  const stage = dealStage({ outcome: null, meetingCount: 1, mom });
  const objections = mom?.objections ?? [];
  const pains = mom?.pain_points ?? [];
  const actions = mom?.action_items?.filter((a) => a.trim()) ?? [];
  const strategy = recommendations(score, mom);

  // Open questions derived from gaps in the real minutes.
  const openQuestions = [
    !mom?.budget_signal && "Is budget approved, and who signs off?",
    !mom?.decision_maker && "Who is the ultimate decision maker?",
    pains.length > 0 && `How critical is “${pains[0]}” to their roadmap?`,
  ].filter(Boolean) as string[];

  const competitorText = (mom?.raw_summary ?? "") + " " + (mom?.points_discussed ?? []).join(" ");
  const competitorMentioned = /competitor|vs\.?|alternative|incumbent|other vendor/i.test(competitorText);

  return (
    <div className="space-y-5">
      <Reveal>
        <GlowCard>
          <div className="flex flex-wrap items-center justify-between gap-4 p-6">
            <div>
              <Eyebrow>Brief · {companyName}</Eyebrow>
              <h2 className="font-display text-2xl font-semibold tracking-tight text-ink">{companyName}</h2>
              <p className="mt-1 font-mono text-xs text-muted">Last contact {fmtDateTime(call.started_at ?? call.created_at)}</p>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone="accent">{stage}</Badge>
              {competitorMentioned && <Badge tone="lost">Competitor in play</Badge>}
            </div>
          </div>
        </GlowCard>
      </Reveal>

      {/* last meeting summary */}
      <Section icon={<Sparkles size={15} className="text-accent" />} title="Last meeting summary">
        {mom?.raw_summary ? (
          <p className="text-sm leading-relaxed text-ink/90">{mom.raw_summary}</p>
        ) : (
          <p className="text-sm text-faint">No prior minutes for this account yet — this may be a first touch.</p>
        )}
      </Section>

      <div className="grid gap-5 md:grid-cols-2">
        <Section icon={<HelpCircle size={15} className="text-iris" />} title="Open questions">
          <BulletList items={openQuestions} dot="bg-iris" />
        </Section>
        <Section icon={<CheckSquare size={15} className="text-accent" />} title="Pending actions">
          {actions.length ? <BulletList items={actions} dot="bg-accent" /> : <Empty>No open action items.</Empty>}
        </Section>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Section icon={<AlertTriangle size={15} className="text-danger" />} title="Risks to watch">
          {objections.length || pains.length ? (
            <BulletList items={[...objections, ...pains]} dot="bg-danger" />
          ) : (
            <Empty>No flagged risks from the last conversation.</Empty>
          )}
        </Section>
        <Section icon={<Swords size={15} className="text-warning" />} title="Objections expected">
          {objections.length ? <BulletList items={objections} dot="bg-warning" /> : <Empty>None surfaced previously.</Empty>}
        </Section>
      </div>

      {/* strategy */}
      <Section icon={<Target size={15} className="text-accent" />} title="Suggested strategy">
        <BulletList items={strategy} dot="bg-accent" />
      </Section>

      <div className="flex justify-end">
        <Link href={`/calls/${call.id}`} className="text-sm font-medium text-accent hover:underline">
          Open the source meeting →
        </Link>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- pieces */

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center gap-2">
        {icon}
        <h3 className="font-display text-[15px] font-semibold text-ink">{title}</h3>
      </div>
      {children}
    </Card>
  );
}

function BulletList({ items, dot }: { items: string[]; dot: string }) {
  return (
    <ul className="space-y-2">
      {items.map((it, i) => (
        <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed text-ink/90">
          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
          {it}
        </li>
      ))}
    </ul>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-faint">{children}</p>;
}
