"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Building2, Search, Sparkles } from "lucide-react";
import { api, type Company, type Mom } from "@/lib/api";
import { Badge, Card, Eyebrow, GlowCard, Loading, SectionLabel } from "@/components/ui";
import { Reveal, Stagger, StaggerItem } from "@/components/motion";

/* Global intelligence layer — natural-language search across company memory.
   The backend has no free-text endpoint, so we build a client-side corpus from
   each company's latest minutes and rank by term overlap. Swap `search()` for a
   server semantic endpoint when one exists. */

interface Doc {
  companyId: string;
  companyName: string;
  segment: string | null;
  mom: Mom;
  text: string;
}

const EXAMPLES = [
  "Which accounts raised pricing objections?",
  "Where was a competitor mentioned?",
  "Who asked about API integration?",
  "Which deals have budget confirmed?",
];

const STOP = new Set(["the", "a", "an", "of", "in", "to", "and", "or", "was", "is", "are", "which", "who", "what", "where", "did", "do", "have", "has", "about", "for", "with", "mentioned", "accounts", "deals"]);

function tokenize(s: string): string[] {
  return s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter((w) => w.length > 2 && !STOP.has(w));
}

function snippet(text: string, terms: string[]): string {
  const lower = text.toLowerCase();
  let at = -1;
  for (const t of terms) {
    const i = lower.indexOf(t);
    if (i >= 0 && (at < 0 || i < at)) at = i;
  }
  if (at < 0) return text.slice(0, 160) + (text.length > 160 ? "…" : "");
  const start = Math.max(0, at - 60);
  return (start > 0 ? "…" : "") + text.slice(start, start + 200).trim() + "…";
}

export default function IntelligencePage() {
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [building, setBuilding] = useState(true);
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .listCompanies()
      .then(async (comps) => {
        if (!alive) return;
        setCompanies(comps);
        const built = await Promise.all(
          comps.map(async (c) => {
            const mom = await api.getCompanyLatestMom(c.id).catch(() => null);
            if (!mom) return null;
            const text = [
              mom.raw_summary,
              mom.next_steps,
              mom.budget_signal,
              mom.decision_maker,
              ...(mom.points_discussed ?? []),
              ...(mom.pain_points ?? []),
              ...(mom.objections ?? []),
              ...(mom.action_items ?? []),
            ]
              .filter(Boolean)
              .join(". ");
            return { companyId: c.id, companyName: c.name, segment: c.segment, mom, text } as Doc;
          }),
        );
        if (alive) setDocs(built.filter(Boolean) as Doc[]);
      })
      .catch(() => {})
      .finally(() => alive && setBuilding(false));
    return () => {
      alive = false;
    };
  }, []);

  const results = useMemo(() => {
    if (!submitted.trim()) return [];
    const terms = tokenize(submitted);
    if (terms.length === 0) return [];
    return docs
      .map((d) => {
        const lower = d.text.toLowerCase();
        let score = 0;
        for (const t of terms) {
          const matches = lower.split(t).length - 1;
          score += matches;
        }
        return { doc: d, score };
      })
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .map((r) => ({ ...r, terms }));
  }, [submitted, docs]);

  function ask(q: string) {
    setQuery(q);
    setSubmitted(q);
  }

  return (
    <div className="w-full">
      <Reveal>
        <div className="mb-7">
          <Eyebrow>Global intelligence</Eyebrow>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink md:text-4xl">
            Ask anything across your <span className="gradient-text">company memory</span>
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted">
            Every meeting your bot has ever sat in, searchable in plain language. Ask about objections, competitors, budgets, or any account.
          </p>
        </div>
      </Reveal>

      <Reveal>
        <GlowCard>
          <form
            className="flex items-center gap-3 p-2.5"
            onSubmit={(e) => {
              e.preventDefault();
              setSubmitted(query);
            }}
          >
            <Search size={18} className="ml-2 shrink-0 text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="What pricing concerns did our accounts raise?"
              className="w-full bg-transparent py-2 text-sm text-ink outline-none placeholder:text-faint"
              autoFocus
            />
            <button
              type="submit"
              className="shrink-0 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white shadow-glow transition hover:bg-accent/90"
            >
              Ask
            </button>
          </form>
        </GlowCard>
      </Reveal>

      {/* example prompts */}
      {!submitted && (
        <div className="mt-5 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => ask(ex)}
              className="rounded-full border border-border bg-surface px-3.5 py-1.5 text-[13px] text-muted transition hover:border-accent/30 hover:text-ink"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      {building && <div className="mt-8"><Loading label="Indexing company memory" /></div>}

      {!building && submitted && (
        <div className="mt-8">
          {/* synthesized answer */}
          <Reveal>
            <Card className="mb-5 p-5">
              <div className="mb-2 flex items-center gap-2">
                <Sparkles size={15} className="text-accent" />
                <SectionLabel>Answer</SectionLabel>
              </div>
              <p className="text-sm leading-relaxed text-ink/90">
                {results.length === 0 ? (
                  <>I couldn’t find anything in your meeting memory matching “{submitted}”. Try different keywords, or run more meetings to grow the corpus.</>
                ) : (
                  <>
                    Found <span className="font-mono text-accent">{results.length}</span>{" "}
                    {results.length === 1 ? "account" : "accounts"} in memory relevant to “{submitted}”. The strongest match is{" "}
                    <span className="font-medium text-ink">{results[0].doc.companyName}</span>. See the supporting passages below.
                  </>
                )}
              </p>
            </Card>
          </Reveal>

          {/* result cards */}
          <Stagger className="space-y-3">
            {results.map(({ doc, terms }) => (
              <StaggerItem key={doc.companyId}>
                <Link href={`/companies/${doc.companyId}`} className="group block">
                  <div className="panel hover-ring p-5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-raised text-faint ring-1 ring-border">
                          <Building2 size={15} />
                        </span>
                        <div>
                          <span className="font-medium text-ink">{doc.companyName}</span>
                          {doc.segment && <Badge tone="neutral">{doc.segment}</Badge>}
                        </div>
                      </div>
                      <ArrowUpRight size={15} className="text-faint transition group-hover:text-accent" />
                    </div>
                    <p className="mt-3 text-[13.5px] leading-relaxed text-muted">
                      {highlight(snippet(doc.text, terms), terms)}
                    </p>
                  </div>
                </Link>
              </StaggerItem>
            ))}
          </Stagger>
        </div>
      )}
    </div>
  );
}

function highlight(text: string, terms: string[]): React.ReactNode {
  if (terms.length === 0) return text;
  const re = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  const parts = text.split(re);
  return parts.map((p, i) =>
    terms.some((t) => p.toLowerCase() === t) ? (
      <mark key={i} className="rounded bg-accent/20 px-0.5 text-accent">{p}</mark>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}
