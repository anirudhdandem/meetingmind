"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Building2, Check, ChevronRight, Lightbulb, Sparkles, Network, Users } from "lucide-react";
import { api, type Call, type Company, type Mom, type Outcome, type Score } from "@/lib/api";
import { Badge, Card, Chip, EmptyState, ErrorNote, Field, GlowCard, Loading, OutcomeBadge, Ring, RowLink, SectionLabel, StatusBadge } from "@/components/ui";
import { Reveal } from "@/components/motion";
import {
  DEAL_STAGES,
  dealHealth,
  dealStage,
  healthLabel,
  recommendations,
  stageIndex,
} from "@/lib/intel";
import { fmtDateTime, fmtDuration } from "@/lib/format";

export default function CompanyIntelligencePage() {
  const { id } = useParams<{ id: string }>();
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const [calls, setCalls] = useState<Call[]>([]);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [mom, setMom] = useState<Mom | null>(null);
  const [score, setScore] = useState<Score | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.listCompanies().catch(() => [] as Company[]),
      api.listCalls().catch(() => [] as Call[]),
      api.listOutcomes().catch(() => [] as Outcome[]),
      api.getCompanyLatestMom(id).catch(() => null),
    ])
      .then(([comp, c, outs, m]) => {
        setCompanies(comp);
        setCalls(c.filter((x) => x.company_id === id));
        setOutcomes(outs);
        setMom(m);
      })
      .catch((e) => setError(String(e)));
  }, [id]);

  const company = useMemo(() => companies?.find((c) => c.id === id) ?? null, [companies, id]);

  const sortedCalls = useMemo(
    () =>
      [...calls].sort((a, b) => {
        const aw = a.started_at ?? a.created_at;
        const bw = b.started_at ?? b.created_at;
        return aw > bw ? -1 : aw < bw ? 1 : 0;
      }),
    [calls],
  );

  const outcomeFor = useMemo(() => {
    const m = new Map<string, Outcome>();
    for (const o of outcomes) if (o.call_id && !m.has(o.call_id)) m.set(o.call_id, o);
    return (callId: string) => m.get(callId);
  }, [outcomes]);

  const companyOutcomes = outcomes.filter((o) => o.company_id === id);
  const won = companyOutcomes.filter((o) => o.status === "accepted").length;
  const lost = companyOutcomes.filter((o) => o.status === "rejected").length;
  const latestOutcome = companyOutcomes[0] ?? null;
  const lastContact = sortedCalls[0]?.started_at ?? sortedCalls[0]?.created_at ?? null;

  // derived intelligence
  const relationshipScore = useMemo(
    () => Math.max(0, Math.min(100, 50 + won * 18 - lost * 14 + Math.min(calls.length, 6) * 4)),
    [won, lost, calls.length],
  );
  const stage = dealStage({ outcome: latestOutcome, meetingCount: calls.length, mom });

  // Rubric health + next-best-actions from the most recent scored call (merged in
  // from the former Deals page).
  useEffect(() => {
    const latest = sortedCalls.find((c) => c.status === "completed") ?? sortedCalls[0] ?? null;
    if (!latest) return;
    let live = true;
    api.getScore(latest.id).then((s) => live && setScore(s)).catch(() => live && setScore(null));
    return () => {
      live = false;
    };
  }, [sortedCalls]);

  const dealH = dealHealth(score);
  const dealHl = healthLabel(dealH);
  const recs = recommendations(score, mom);

  if (error) return <div className="w-full"><ErrorNote>Couldn’t reach the API: {error}</ErrorNote></div>;
  if (!companies) return <div className="w-full"><Loading label="Loading company intelligence" /></div>;

  if (!company) {
    return (
      <div className="w-full space-y-6">
        <BackLink />
        <EmptyState icon={<Building2 size={28} />} title="Company not found">
          This account doesn’t exist or has no record yet.
        </EmptyState>
      </div>
    );
  }

  const isExternal = company.kind === "external";
  const openActionItems = mom?.action_items?.filter((a) => a.trim()) ?? [];
  const painChips = [
    ...(mom?.pain_points ?? []).map((t) => ({ text: t, tone: "pending" as const })),
    ...(mom?.objections ?? []).map((t) => ({ text: t, tone: "lost" as const })),
  ];

  return (
    <div className="w-full space-y-6">
      <BackLink />

      {/* ---------------------------------------------------------- hero */}
      <Reveal>
        <GlowCard>
          <div className="grid gap-6 p-6 md:grid-cols-[1.5fr_auto] md:p-8">
            <div>
              <div className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-accent">
                {isExternal ? "Account intelligence" : "Internal workspace"}
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">{company.name}</h1>
                {!isExternal && <Badge tone="scheduled">Internal</Badge>}
              </div>
              <p className="mt-1.5 font-mono text-xs text-muted">
                {company.segment ?? "No segment"} · {calls.length} {calls.length === 1 ? "meeting" : "meetings"} · last contact{" "}
                {lastContact ? fmtDateTime(lastContact) : "—"}
              </p>

              {isExternal && (
                <div className="mt-6 grid grid-cols-2 gap-4">
                  <HeroFig icon={<Network size={15} />} label="Deal stage" value={stage} tone="text-ink" />
                  <HeroFig icon={<Users size={15} />} label="Record" value={`${won}W · ${lost}L`} tone="text-ink" />
                </div>
              )}
            </div>

            {isExternal && (
              <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-raised/40 px-6 py-4">
                <Ring value={relationshipScore} size={120} label="relationship" />
              </div>
            )}
          </div>
        </GlowCard>
      </Reveal>

      {/* ------------------------------------------- relationship timeline */}
      {isExternal && (
        <Reveal>
          <Card className="p-6">
            <div className="mb-5 flex items-center gap-2">
              <Network size={16} className="text-accent" />
              <h2 className="font-display text-base font-semibold text-ink">Relationship timeline</h2>
            </div>
            <StageTimeline current={stage} />
          </Card>
        </Reveal>
      )}

      {/* ----------------------------------------------- AI summary */}
      <Reveal>
        <Card className="p-6">
            <div className="mb-4 flex items-center gap-2">
              <Sparkles size={16} className="text-accent" />
              <h2 className="font-display text-base font-semibold text-ink">AI company summary</h2>
            </div>
            {!mom ? (
              <p className="text-sm text-faint">No minutes recorded for this company yet.</p>
            ) : (
              <div className="space-y-4 text-sm">
                {mom.raw_summary && <p className="whitespace-pre-wrap leading-relaxed text-ink/90">{mom.raw_summary}</p>}
                <div className="space-y-1.5 border-t border-hairline pt-4">
                  <Field label="Next steps" value={mom.next_steps} />
                  <Field label="Decision maker" value={mom.decision_maker} />
                  <Field label="Budget signal" value={mom.budget_signal} />
                </div>
                {openActionItems.length > 0 && (
                  <div className="border-t border-hairline pt-4">
                    <SectionLabel>Open action items</SectionLabel>
                    <ul className="mt-2 space-y-1.5">
                      {openActionItems.map((item, i) => (
                        <li key={i} className="flex gap-2 text-sm text-ink">
                          <Check size={16} className="mt-0.5 shrink-0 text-accent" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {painChips.length > 0 && (
                  <div className="border-t border-hairline pt-4">
                    <SectionLabel>Watch for</SectionLabel>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {painChips.map((c, i) => (
                        <Chip key={i} tone={c.tone}>{c.text}</Chip>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
        </Card>
      </Reveal>

      {/* --------------------------------------- deal signal + next actions */}
      {isExternal && (
        <Reveal>
          <Card className="p-6">
            <div className="mb-5 flex items-center gap-2">
              <Lightbulb size={16} className="text-warning" />
              <h2 className="font-display text-base font-semibold text-ink">Deal signal &amp; next actions</h2>
            </div>
            <div className="grid gap-6 md:grid-cols-[auto_1fr] md:items-center">
              <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-raised/40 px-6 py-4">
                <Ring value={dealH} size={104} label="deal health" />
                <div className="mt-3">
                  <Badge tone={dealHl.tone}>{dealHl.label}</Badge>
                </div>
              </div>
              <div>
                <SectionLabel>AI recommends</SectionLabel>
                <ul className="mt-2.5 space-y-2">
                  {recs.map((rec, i) => (
                    <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed text-muted">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </Card>
        </Reveal>
      )}

      {/* ------------------------------------------------ historical memory */}
      <section>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-display text-sm font-semibold text-ink">Historical memory</h2>
          {sortedCalls.length > 0 && <span className="font-mono text-xs text-faint">{sortedCalls.length} meetings</span>}
        </div>
        {sortedCalls.length === 0 ? (
          <EmptyState icon={<Building2 size={28} />} title="No meetings yet">
            When a meeting with this company ends, it lands here.
          </EmptyState>
        ) : (
          <Card className="overflow-hidden">
            {sortedCalls.map((c) => {
              const outcome = outcomeFor(c.id);
              return (
                <RowLink key={c.id} href={`/calls/${c.id}`} className="group border-b border-hairline last:border-0">
                  <div className="flex items-center gap-3 px-5 py-3.5">
                    <div className="flex-1">
                      <div className="font-mono text-xs text-muted">{fmtDateTime(c.started_at ?? c.created_at)}</div>
                      <div className="mt-0.5 font-mono text-xs text-faint">{fmtDuration(c.started_at, c.ended_at)}</div>
                    </div>
                    <StatusBadge status={c.status} />
                    {outcome && <OutcomeBadge status={outcome.status} />}
                    <ChevronRight size={16} className="text-faint transition group-hover:translate-x-0.5 group-hover:text-muted" />
                  </div>
                </RowLink>
              );
            })}
          </Card>
        )}
      </section>
    </div>
  );
}

/* ---------------------------------------------------------------- pieces */

function BackLink() {
  return (
    <Link href="/companies" className="inline-flex items-center gap-1.5 text-sm text-muted transition hover:text-ink">
      <ArrowLeft size={16} /> All companies
    </Link>
  );
}

function HeroFig({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: string }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
        <span className="text-faint">{icon}</span> {label}
      </div>
      <div className={`mt-1.5 font-mono text-xl font-semibold tabular-nums ${tone}`}>{value}</div>
    </div>
  );
}

function StageTimeline({ current }: { current: string }) {
  const idx = stageIndex(current as (typeof DEAL_STAGES)[number]);
  return (
    <div className="flex items-center">
      {DEAL_STAGES.map((s, i) => {
        const done = i < idx;
        const active = i === idx;
        return (
          <div key={s} className="flex flex-1 items-center last:flex-none">
            <div className="flex flex-col items-center gap-2">
              <span
                className={`relative flex h-3.5 w-3.5 items-center justify-center rounded-full transition ${
                  active ? "bg-accent" : done ? "bg-accent/60" : "bg-overlay ring-1 ring-border"
                }`}
              >
                {active && <span className="ping-ring absolute inset-0 rounded-full text-accent/50" />}
              </span>
              <span className={`font-mono text-[10.5px] uppercase tracking-wide ${active ? "text-accent" : done ? "text-muted" : "text-faint"}`}>
                {s}
              </span>
            </div>
            {i < DEAL_STAGES.length - 1 && (
              <div className={`mx-1 mb-5 h-px flex-1 ${i < idx ? "bg-accent/50" : "bg-border"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
