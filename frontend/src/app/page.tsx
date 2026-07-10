"use client";

import Link from "next/link";
import {
  Activity,
  Building2,
  ChevronRight,
  Clock,
  Radio,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Trophy,
} from "lucide-react";
import { api, type Outcome } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { dealStage, overviewMetrics } from "@/lib/intel";
import { Badge, Card, EmptyState, ErrorNote, Eyebrow, Loading, OutcomeBadge, RowLink, StatusBadge } from "@/components/ui";
import { Counter, Reveal, Stagger, StaggerItem } from "@/components/motion";
import { fmtDateTime, fmtDuration, fmtRelative } from "@/lib/format";

export default function OverviewPage() {
  const calls = useAsync(() => api.listCalls(), []);
  const companies = useAsync(() => api.listCompanies(), []);
  const outcomes = useAsync(() => api.listOutcomes(), []);

  const loading = calls.loading || companies.loading || outcomes.loading;
  const error = calls.error || companies.error || outcomes.error;

  const callList = calls.data ?? [];
  const companyList = companies.data ?? [];
  const outcomeList = outcomes.data ?? [];
  const m = overviewMetrics(callList, companyList, outcomeList);

  const companyName = (id: string) => companyList.find((c) => c.id === id)?.name ?? "Unknown account";

  const recentCalls = [...callList]
    .sort((a, b) => ((a.started_at ?? a.created_at) > (b.started_at ?? b.created_at) ? -1 : 1))
    .slice(0, 6);

  const outcomeForCall = new Map<string, Outcome>();
  for (const o of outcomeList) if (o.call_id && !outcomeForCall.has(o.call_id)) outcomeForCall.set(o.call_id, o);

  const latestOutcomeForCompany = new Map<string, Outcome>();
  for (const o of outcomeList) if (!latestOutcomeForCompany.has(o.company_id)) latestOutcomeForCompany.set(o.company_id, o);

  const dealsInFlight = companyList
    .filter((c) => c.kind === "external")
    .map((c) => {
      const cs = callList
        .filter((x) => x.company_id === c.id)
        .sort((a, b) => ((a.started_at ?? a.created_at) > (b.started_at ?? b.created_at) ? -1 : 1));
      const outcome = latestOutcomeForCompany.get(c.id) ?? null;
      return {
        company: c,
        outcome,
        meetingCount: cs.length,
        lastContact: cs[0]?.started_at ?? cs[0]?.created_at ?? null,
        stage: dealStage({ outcome, meetingCount: cs.length, mom: null }),
      };
    })
    .filter((d) => !d.outcome || d.outcome.status === "pending")
    .sort((a, b) => ((a.lastContact ?? "") > (b.lastContact ?? "") ? -1 : 1))
    .slice(0, 5);

  return (
    <div className="w-full">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>Revenue command center</Eyebrow>
          <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink">Overview</h1>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
            A live read on every account — meetings analyzed, deals in flight, and what the intelligence layer is surfacing right now.
          </p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Link
            href="/calls"
            className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white shadow-glow transition hover:bg-accent/90 active:scale-[0.98]"
          >
            <Radio size={16} /> Start a meeting
          </Link>
          <Link
            href="/intelligence"
            className="flex items-center gap-2 rounded-xl border border-border bg-raised px-4 py-2 text-sm font-semibold text-ink transition hover:border-strong"
          >
            <Sparkles size={16} className="text-accent" /> Ask intelligence
          </Link>
        </div>
      </div>

      {error && <div className="mb-6"><ErrorNote>Couldn’t reach the backend: {error}</ErrorNote></div>}
      {loading && <div className="mb-6"><Loading label="Syncing intelligence" /></div>}

      {/* ------------------------------------------------------- metric grid */}
      <Stagger className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Metric label="Meetings Analyzed" value={m.meetings} Icon={Activity} accent="iris" />
        <Metric label="Win Rate" value={m.winRate ?? 0} suffix="%" Icon={Target} accent="success" emphasize muted={m.winRate == null} />
        <Metric label="Deals Closed" value={m.won} Icon={Trophy} accent="accent" />
        <Metric label="Deals Lost" value={m.lost} Icon={TrendingDown} accent="danger" emphasize />
      </Stagger>

      {/* ----------------------------------------------- real-data panels */}
      <div className="mt-6 grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        {/* Recent meetings */}
        <Reveal>
          <Card className="p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-iris" />
                <h2 className="font-display text-base font-semibold text-ink">Recent meetings</h2>
              </div>
              <Link href="/calls" className="flex items-center gap-1 text-[13px] font-medium text-accent hover:underline">
                All meetings <ChevronRight size={14} />
              </Link>
            </div>
            {recentCalls.length === 0 ? (
              <EmptyState icon={<Radio size={26} />} title="No meetings yet">
                Start a meeting and it’ll show up here with its status, outcome, and minutes.
              </EmptyState>
            ) : (
              <div className="-mx-2">
                {recentCalls.map((c) => {
                  const o = outcomeForCall.get(c.id);
                  return (
                    <RowLink key={c.id} href={`/calls/${c.id}`} className="group rounded-xl">
                      <div className="flex items-center gap-3 px-2 py-2.5">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-raised text-faint ring-1 ring-border">
                          <Building2 size={15} />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium text-ink">{companyName(c.company_id)}</div>
                          <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-faint">
                            <span>{fmtDateTime(c.started_at ?? c.created_at)}</span>
                            <span className="flex items-center gap-1"><Clock size={11} /> {fmtDuration(c.started_at, c.ended_at)}</span>
                          </div>
                        </div>
                        {o ? <OutcomeBadge status={o.status} /> : <StatusBadge status={c.status} />}
                        <ChevronRight size={16} className="shrink-0 text-faint transition group-hover:translate-x-0.5 group-hover:text-muted" />
                      </div>
                    </RowLink>
                  );
                })}
              </div>
            )}
          </Card>
        </Reveal>

        {/* Deals in flight */}
        <Reveal delay={0.05}>
          <Card className="p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp size={16} className="text-accent" />
                <h2 className="font-display text-base font-semibold text-ink">Deals in flight</h2>
              </div>
              <Link href="/companies" className="flex items-center gap-1 text-[13px] font-medium text-accent hover:underline">
                All deals <ChevronRight size={14} />
              </Link>
            </div>
            {dealsInFlight.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted">No open deals right now.</p>
            ) : (
              <div className="space-y-2.5">
                {dealsInFlight.map((d) => (
                  <Link
                    key={d.company.id}
                    href={`/companies/${d.company.id}`}
                    className="group block rounded-xl border border-border bg-raised/50 p-3 transition hover:border-accent/30 hover:bg-overlay"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-ink">{d.company.name}</span>
                      <Badge tone="accent">{d.stage}</Badge>
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-faint">
                      {d.meetingCount} {d.meetingCount === 1 ? "meeting" : "meetings"} · last {fmtRelative(d.lastContact)}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Card>
        </Reveal>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- pieces */

type Accent = "accent" | "success" | "danger" | "warning" | "iris";
const ACCENT: Record<Accent, { tile: string; bar: string; val: string; wash: string; ring: string }> = {
  accent: { tile: "bg-accent-soft text-accent", bar: "from-accent to-iris", val: "text-accent", wash: "from-accent/[0.10]", ring: "group-hover:border-accent/30" },
  success: { tile: "bg-success/12 text-success", bar: "from-success to-accent", val: "text-success", wash: "from-success/[0.10]", ring: "group-hover:border-success/30" },
  danger: { tile: "bg-danger/12 text-danger", bar: "from-danger to-warning", val: "text-danger", wash: "from-danger/[0.10]", ring: "group-hover:border-danger/30" },
  warning: { tile: "bg-warning/12 text-warning", bar: "from-warning to-danger", val: "text-warning", wash: "from-warning/[0.10]", ring: "group-hover:border-warning/30" },
  iris: { tile: "bg-iris/12 text-iris", bar: "from-iris to-accent", val: "text-iris", wash: "from-iris/[0.10]", ring: "group-hover:border-iris/30" },
};

function Metric({ label, value, decimals = 0, prefix, suffix, accent, Icon, muted, emphasize }: {
  label: string;
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  accent: Accent;
  Icon: typeof Activity;
  muted?: boolean;
  emphasize?: boolean;
}) {
  const c = ACCENT[accent];
  return (
    <StaggerItem>
      <div
        className={`group relative overflow-hidden rounded-2xl border border-border bg-surface bg-gradient-to-br ${c.wash} to-transparent to-55% p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-float ${c.ring}`}
      >
        <span className={`absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r ${c.bar}`} />
        <div className="flex items-start justify-between">
          <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${c.tile} ring-1 ring-inset ring-current/10 shadow-sm transition group-hover:scale-105`}>
            <Icon size={19} />
          </span>
          {emphasize && !muted && (
            <span className={`mt-1 font-mono text-[10px] uppercase tracking-wider ${c.val} opacity-70`}>key</span>
          )}
        </div>
        <div className={`mt-4 font-mono text-[30px] font-semibold leading-none tabular-nums ${muted ? "text-faint" : c.val}`}>
          {muted ? (
            <span className="text-faint">—</span>
          ) : (
            <>
              {prefix}
              <Counter value={value} decimals={decimals} />
              {suffix}
            </>
          )}
        </div>
        <div className="mt-2 text-[13px] font-medium text-muted">{label}</div>
      </div>
    </StaggerItem>
  );
}
