"use client";

import { useEffect, useMemo, useState } from "react";
import { Sparkles, Swords, TrendingDown, TrendingUp } from "lucide-react";
import { api, type Call, type Company, type ComparisonReport, type RubricDelta, type Score } from "@/lib/api";
import { Button, Card, EmptyState, ErrorNote, Eyebrow, GlowCard, Input, PageHeader, Ring, SectionLabel, Spinner, Stat } from "@/components/ui";
import { MotionMeter, Reveal, Stagger, StaggerItem } from "@/components/motion";

const FIELD_LABEL: Record<string, string> = {
  engagement_score: "Engagement",
  objection_severity: "Objection severity",
  urgency_score: "Urgency",
  technical_fit_score: "Technical fit",
  overall_rating: "Overall rating",
};

/** objection severity is "lower is better", so a negative raw delta is a WIN signal. */
function isPositiveSignal(d: RubricDelta): boolean {
  return d.field === "objection_severity" ? d.delta < 0 : d.delta > 0;
}

function patternLine(d: RubricDelta): string {
  const label = FIELD_LABEL[d.field] ?? d.field.replace(/_/g, " ");
  const mag = Math.abs(d.delta).toFixed(0);
  if (d.field === "objection_severity") {
    return d.delta < 0
      ? `Won deals carried ${mag} pts less objection severity — concerns were resolved, not deferred`
      : `Lost deals spiked ${mag} pts in objection severity — pushback went unaddressed`;
  }
  return isPositiveSignal(d)
    ? `Won deals scored ${mag} pts higher on ${label.toLowerCase()}`
    : `Lost deals trailed ${mag} pts on ${label.toLowerCase()}`;
}

export default function WinLossPage() {
  const [segment, setSegment] = useState("");
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setReport(await api.getComparison(segment.trim() || undefined));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const total = report ? report.won_count + report.lost_count : 0;
  const winRate = report && total > 0 ? Math.round((report.won_count / total) * 100) : null;

  // rank deltas by magnitude; split into winning vs losing patterns
  const ranked = useMemo(
    () => (report ? [...report.deltas].sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)) : []),
    [report],
  );
  const winning = ranked.filter(isPositiveSignal);
  const losing = ranked.filter((d) => !isPositiveSignal(d));
  const maxDelta = Math.max(1, ...ranked.map((d) => Math.abs(d.delta)));

  return (
    <div className="w-full">
      <PageHeader
        eyebrow="Win / loss intelligence"
        title="Why deals are won & lost"
        sub="The patterns that separate your wins from your losses — computed from real call rubrics. The narrative only ever explains these numbers, never invents them."
        actions={
          <div className="flex items-center gap-2">
            <Input
              value={segment}
              onChange={(e) => setSegment(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && run()}
              placeholder="Segment (optional)"
              className="w-44"
            />
            <Button variant="primary" onClick={run} disabled={loading}>
              {loading ? <Spinner /> : null}
              {loading ? "Analyzing…" : "Analyze"}
            </Button>
          </div>
        }
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {report && total === 0 && !loading && (
        <EmptyState icon={<Swords size={28} />} title="Nothing to compare yet">
          Mark some calls as won or lost{report.segment ? ` in the “${report.segment}” segment` : ""}, then analyze.
        </EmptyState>
      )}

      {report && total > 0 && (
        <div className="space-y-6">
          {/* headline */}
          <Reveal>
            <GlowCard>
              <div className="grid items-center gap-6 p-6 sm:grid-cols-[auto_1fr] md:p-8">
                <Ring value={winRate} size={148} stroke={11} label="win rate" />
                <div>
                  <Eyebrow>{report.segment ? `Segment · ${report.segment}` : "All segments"}</Eyebrow>
                  <p className="font-display text-2xl font-semibold tracking-tight text-ink">
                    {report.won_count} won · {report.lost_count} lost
                  </p>
                  <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted">
                    Across {total} decided {total === 1 ? "deal" : "deals"}, here’s the rubric signature of a win — and where the losses fall short.
                  </p>
                </div>
              </div>
            </GlowCard>
          </Reveal>

          {/* diverging delta bars */}
          <Reveal>
            <Card className="p-6">
              <div className="mb-5 flex items-center justify-between">
                <SectionLabel>Rubric signature · won vs lost</SectionLabel>
                <span className="font-mono text-[11px] text-faint">won − lost</span>
              </div>
              <div className="space-y-4">
                {ranked.map((d) => (
                  <DeltaBar key={d.field} d={d} max={maxDelta} />
                ))}
              </div>
            </Card>
          </Reveal>

          {/* winning / losing patterns */}
          <div className="grid gap-5 md:grid-cols-2">
            <Reveal>
              <PatternPanel
                tone="win"
                title="Winning patterns"
                icon={<TrendingUp size={16} className="text-success" />}
                lines={winning.map(patternLine)}
                empty="No standout winning signals in this cohort yet."
              />
            </Reveal>
            <Reveal delay={0.05}>
              <PatternPanel
                tone="loss"
                title="Losing patterns"
                icon={<TrendingDown size={16} className="text-danger" />}
                lines={losing.map(patternLine)}
                empty="No clear loss drivers — wins and losses look similar."
              />
            </Reveal>
          </div>

          {/* narrative */}
          <Reveal>
            <Card className="p-6">
              <div className="mb-3 flex items-center gap-2">
                <Sparkles size={16} className="text-accent" />
                <SectionLabel>AI comparison engine</SectionLabel>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink/90">{report.narrative}</p>
            </Card>
          </Reveal>

          <Stagger className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StaggerItem><Stat label="Win rate" value={`${winRate}%`} tone="accent" /></StaggerItem>
            <StaggerItem><Stat label="Won" value={report.won_count} tone="won" /></StaggerItem>
            <StaggerItem><Stat label="Lost" value={report.lost_count} tone="lost" /></StaggerItem>
            <StaggerItem><Stat label="Segment" value={<span className="text-base">{report.segment ?? "All"}</span>} /></StaggerItem>
          </Stagger>
        </div>
      )}

      <HeadToHead />
    </div>
  );
}

/* ---------------------------------------------------------------- pieces */

function DeltaBar({ d, max }: { d: RubricDelta; max: number }) {
  const pos = isPositiveSignal(d);
  const pct = (Math.abs(d.delta) / max) * 50; // half-width max
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-[13px]">
        <span className="text-ink">{FIELD_LABEL[d.field] ?? d.field.replace(/_/g, " ")}</span>
        <span className={`font-mono tabular-nums ${pos ? "text-success" : "text-danger"}`}>
          {d.delta >= 0 ? "+" : ""}{d.delta.toFixed(1)}
        </span>
      </div>
      <div className="relative h-2 rounded-full bg-overlay">
        <div className="absolute left-1/2 top-0 h-full w-px bg-border" />
        <div
          className={`absolute top-0 h-full rounded-full ${pos ? "bg-success" : "bg-danger"}`}
          style={pos ? { left: "50%", width: `${pct}%` } : { right: "50%", width: `${pct}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-faint">
        <span>lost {d.lost_avg.toFixed(0)}</span>
        <span>won {d.won_avg.toFixed(0)}</span>
      </div>
    </div>
  );
}

function PatternPanel({ tone, title, icon, lines, empty }: {
  tone: "win" | "loss";
  title: string;
  icon: React.ReactNode;
  lines: string[];
  empty: string;
}) {
  const ring = tone === "win" ? "border-success/25 bg-success/5" : "border-danger/25 bg-danger/5";
  const dot = tone === "win" ? "bg-success" : "bg-danger";
  return (
    <div className={`h-full rounded-[var(--radius-card)] border ${ring} p-6`}>
      <div className="mb-4 flex items-center gap-2">
        {icon}
        <h3 className="font-display text-base font-semibold text-ink">{title}</h3>
      </div>
      {lines.length === 0 ? (
        <p className="text-sm text-faint">{empty}</p>
      ) : (
        <ul className="space-y-3">
          {lines.map((l, i) => (
            <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed text-ink/90">
              <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
              {l}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ----------------------------------------------- head-to-head two-call diff */

function HeadToHead() {
  const [calls, setCalls] = useState<Call[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [scoreA, setScoreA] = useState<Score | null>(null);
  const [scoreB, setScoreB] = useState<Score | null>(null);

  useEffect(() => {
    api.listCalls().then((cs) => setCalls(cs.filter((c) => c.status === "completed"))).catch(() => {});
    api.listCompanies().then(setCompanies).catch(() => {});
  }, []);

  const name = useMemo(() => {
    const m = new Map(companies.map((c) => [c.id, c.name]));
    return (call: Call) => m.get(call.company_id) ?? call.id.slice(0, 8);
  }, [companies]);

  useEffect(() => {
    setScoreA(null);
    if (a) api.getScore(a).then(setScoreA).catch(() => setScoreA(null));
  }, [a]);
  useEffect(() => {
    setScoreB(null);
    if (b) api.getScore(b).then(setScoreB).catch(() => setScoreB(null));
  }, [b]);

  if (calls.length < 2) return null;

  return (
    <section className="mt-10">
      <Eyebrow>Head to head</Eyebrow>
      <h2 className="mb-4 font-display text-lg font-semibold text-ink">Compare two calls</h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <DiffColumn calls={calls} name={name} value={a} onChange={setA} score={scoreA} exclude={b} />
        <DiffColumn calls={calls} name={name} value={b} onChange={setB} score={scoreB} exclude={a} />
      </div>
    </section>
  );
}

function DiffColumn({ calls, name, value, onChange, score, exclude }: {
  calls: Call[];
  name: (c: Call) => string;
  value: string;
  onChange: (v: string) => void;
  score: Score | null;
  exclude: string;
}) {
  return (
    <Card className="p-5">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mb-4 w-full rounded-lg border border-border bg-raised px-3 py-2 text-sm text-ink outline-none focus:border-accent/60"
      >
        <option value="">Select a call…</option>
        {calls.filter((c) => c.id !== exclude).map((c) => (
          <option key={c.id} value={c.id}>
            {name(c)} · {new Date(c.created_at).toLocaleDateString()}
          </option>
        ))}
      </select>
      {!value ? (
        <p className="py-8 text-center text-sm text-faint">Pick a call to see its scores.</p>
      ) : !score ? (
        <p className="py-8 text-center text-sm text-faint">No score for this call.</p>
      ) : (
        <div className="space-y-3.5">
          <MotionMeter label="Engagement" value={score.engagement_score} />
          <MotionMeter label="Objection severity" value={score.objection_severity} invert />
          <MotionMeter label="Urgency" value={score.urgency_score} />
          <MotionMeter label="Technical fit" value={score.technical_fit_score} />
          <div className="border-t border-hairline pt-3.5">
            <MotionMeter label="Overall" value={score.overall_rating} emphasis />
          </div>
        </div>
      )}
    </Card>
  );
}
