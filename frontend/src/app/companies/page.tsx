"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Call, type Company, type CompanyKind, type Outcome, type Score } from "@/lib/api";
import { Badge, Button, Card, EmptyState, ErrorNote, Input, Loading, PageHeader } from "@/components/ui";
import { Modal } from "@/components/motion";
import { BuildingIcon, CheckIcon, ChevronRightIcon, PlusIcon, SearchIcon, UsersIcon } from "@/components/icons";
import { dealHealth, dealStage, healthLabel, type DealStage } from "@/lib/intel";
import { fmtDateTime } from "@/lib/format";

const PAGE_SIZE = 10;

interface CompanyRow {
  company: Company;
  callCount: number;
  lastContact: string | null;
  latestCall: Call | null;
  stage: DealStage;
  closed: "won" | "lost" | null;
  won: number;
  lost: number;
}

export default function CompaniesPage() {
  const router = useRouter();
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const [calls, setCalls] = useState<Call[]>([]);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  function load() {
    Promise.all([
      api.listCompanies().catch(() => [] as Company[]),
      api.listCalls().catch(() => [] as Call[]),
      api.listOutcomes().catch(() => [] as Outcome[]),
    ])
      .then(([comp, c, outs]) => {
        setCompanies(comp);
        setCalls(c);
        setOutcomes(outs);
      })
      .catch((e) => setError(String(e)));
  }

  useEffect(() => {
    load();
  }, []);

  const rows = useMemo<CompanyRow[]>(() => {
    if (!companies) return [];

    // First outcome per call_id wins (listOutcomes is newest-first).
    const outcomeByCall = new Map<string, Outcome>();
    for (const o of outcomes) if (o.call_id && !outcomeByCall.has(o.call_id)) outcomeByCall.set(o.call_id, o);
    // Latest outcome per company drives the deal stage.
    const latestOutcome = new Map<string, Outcome>();
    for (const o of outcomes) if (!latestOutcome.has(o.company_id)) latestOutcome.set(o.company_id, o);

    const callsByCompany = new Map<string, Call[]>();
    for (const c of calls) {
      const list = callsByCompany.get(c.company_id) ?? [];
      list.push(c);
      callsByCompany.set(c.company_id, list);
    }

    const out = companies.map<CompanyRow>((company) => {
      const list = (callsByCompany.get(company.id) ?? []).sort((a, b) =>
        (a.started_at ?? a.created_at) > (b.started_at ?? b.created_at) ? -1 : 1,
      );
      let lastContact: string | null = null;
      let won = 0;
      let lost = 0;
      for (const c of list) {
        const when = c.started_at ?? c.created_at;
        if (when && (!lastContact || when > lastContact)) lastContact = when;
        const o = outcomeByCall.get(c.id);
        if (o?.status === "accepted") won += 1;
        else if (o?.status === "rejected") lost += 1;
      }
      const outcome = latestOutcome.get(company.id) ?? null;
      const closed =
        outcome && outcome.status !== "pending"
          ? outcome.status === "accepted"
            ? "won"
            : "lost"
          : null;
      return {
        company,
        callCount: list.length,
        lastContact,
        latestCall: list.find((c) => c.status === "completed") ?? list[0] ?? null,
        stage: dealStage({ outcome, meetingCount: list.length, mom: null }),
        closed,
        won,
        lost,
      };
    });

    // Sort by last-contact desc; companies with no calls go last.
    out.sort((a, b) => {
      if (a.lastContact && b.lastContact) return a.lastContact > b.lastContact ? -1 : 1;
      if (a.lastContact) return -1;
      if (b.lastContact) return 1;
      return 0;
    });
    return out;
  }, [companies, calls, outcomes]);

  // Search (by company name) then paginate.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.company.name.toLowerCase().includes(q));
  }, [rows, query]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const paged = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="w-full">
      <PageHeader
        eyebrow="Relationships & pipeline"
        title="Companies"
        sub="Every account you've had a call with — each with its own deal stage, health read, and memory of minutes, scores, and outcomes that build a pre-call brief over time."
        actions={
          <Button variant="primary" onClick={() => setShowAdd(true)}>
            <PlusIcon width={16} height={16} /> Add company
          </Button>
        }
      />

      {error && <ErrorNote>Couldn’t reach the API: {error}</ErrorNote>}
      {!companies && !error && <Loading label="Loading companies" />}

      {companies && rows.length === 0 && (
        <EmptyState icon={<BuildingIcon width={28} height={28} />} title="No companies yet">
          Start a call and the company behind it shows up here with its full call history.
        </EmptyState>
      )}

      {companies && rows.length > 0 && (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="relative w-full max-w-sm">
              <SearchIcon
                width={15}
                height={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
              />
              <Input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
                placeholder="Search companies by name…"
                aria-label="Search companies"
                className="pl-9"
              />
            </div>
            <span className="font-mono text-xs text-faint">
              {filtered.length} {filtered.length === 1 ? "company" : "companies"}
            </span>
          </div>

          {filtered.length === 0 ? (
            <EmptyState icon={<SearchIcon width={28} height={28} />} title="No matches">
              No company name matches “{query.trim()}”.
            </EmptyState>
          ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <Th className="pl-5">Company</Th>
                <Th>Stage</Th>
                <Th>Health</Th>
                <Th>Presented by</Th>
                <Th>Product pitched</Th>
                <Th>Calls</Th>
                <Th>Last contact</Th>
                <Th className="pr-5 text-right">Record</Th>
              </tr>
            </thead>
            <tbody>
              {paged.map((r) => (
                <tr
                  key={r.company.id}
                  className="group cursor-pointer border-b border-hairline last:border-0 hover:bg-raised"
                  onClick={() => router.push(`/companies/${r.company.id}`)}
                >
                  <td className="py-3.5 pl-5 pr-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink">{r.company.name}</span>
                      {r.company.kind === "internal" && <Badge tone="scheduled">Internal</Badge>}
                    </div>
                    <div className="mt-0.5 font-mono text-xs text-faint">
                      {r.company.kind === "internal" ? "Internal meeting" : r.company.segment ?? "—"}
                    </div>
                  </td>
                  <td className="px-3">
                    {r.company.kind === "internal" ? (
                      <span className="font-mono text-xs text-faint">—</span>
                    ) : (
                      <Badge tone={r.closed ? r.closed : "accent"}>
                        {r.closed ? (r.closed === "won" ? "Won" : "Lost") : r.stage}
                      </Badge>
                    )}
                  </td>
                  <td className="px-3">
                    {r.company.kind === "internal" ? (
                      <span className="font-mono text-xs text-faint">—</span>
                    ) : (
                      <HealthCell callId={r.latestCall?.id ?? null} />
                    )}
                  </td>
                  <td className="px-3 text-xs text-muted">
                    {r.company.kind === "internal" || !r.company.presented_by ? (
                      <span className="font-mono text-faint">—</span>
                    ) : (
                      r.company.presented_by
                    )}
                  </td>
                  <td className="px-3 text-xs text-muted">
                    {r.company.kind === "internal" || !r.company.product_pitched ? (
                      <span className="font-mono text-faint">—</span>
                    ) : (
                      r.company.product_pitched
                    )}
                  </td>
                  <td className="px-3 font-mono text-xs text-muted">{r.callCount}</td>
                  <td className="px-3 font-mono text-xs text-muted">
                    {r.lastContact ? fmtDateTime(r.lastContact) : "—"}
                  </td>
                  <td className="py-3.5 pl-3 pr-5">
                    <div className="flex items-center justify-end gap-2">
                      {r.company.kind === "internal" ? (
                        <span className="font-mono text-xs text-faint">—</span>
                      ) : r.won > 0 || r.lost > 0 ? (
                        <span className="font-mono text-xs">
                          {r.won > 0 && <span className="text-success">{r.won}W</span>}
                          {r.won > 0 && r.lost > 0 && <span className="text-faint"> · </span>}
                          {r.lost > 0 && <span className="text-danger">{r.lost}L</span>}
                        </span>
                      ) : (
                        <span className="font-mono text-xs text-faint">—</span>
                      )}
                      <ChevronRightIcon
                        width={16}
                        height={16}
                        className="text-faint transition group-hover:translate-x-0.5 group-hover:text-muted"
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {pageCount > 1 && (
            <div className="flex items-center justify-between border-t border-hairline px-5 py-3">
              <span className="font-mono text-xs text-faint">
                {safePage * PAGE_SIZE + 1}–{Math.min((safePage + 1) * PAGE_SIZE, filtered.length)} of{" "}
                {filtered.length}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={safePage === 0}
                >
                  Previous
                </Button>
                <span className="font-mono text-xs text-muted tabular-nums">
                  {safePage + 1} / {pageCount}
                </span>
                <Button
                  variant="ghost"
                  onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                  disabled={safePage >= pageCount - 1}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </Card>
          )}
        </>
      )}

      <AddCompanyDialog
        open={showAdd}
        onClose={() => setShowAdd(false)}
        existing={companies ?? []}
        onCreated={(c) => {
          setShowAdd(false);
          router.push(`/companies/${c.id}`);
        }}
      />
    </div>
  );
}

function AddCompanyDialog({
  open,
  onClose,
  existing,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  existing: Company[];
  onCreated: (c: Company) => void;
}) {
  const [kind, setKind] = useState<CompanyKind>("external");
  const [name, setName] = useState("");
  const [segment, setSegment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setKind("external");
    setName("");
    setSegment("");
    setError(null);
  }, [open]);

  async function save() {
    const label = name.trim();
    if (!label) {
      setError(kind === "external" ? "Enter the company name." : "Give this label a name.");
      return;
    }
    if (existing.some((c) => c.kind === kind && c.name.toLowerCase() === label.toLowerCase())) {
      setError("A record with that name already exists.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await api.createCompany({
        name: label,
        kind,
        segment: kind === "external" ? segment.trim() || null : null,
      });
      onCreated(created);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose}>
      <div className="p-6">
        <div className="mb-1 font-display text-lg font-semibold tracking-tight text-ink">
          Add a company
        </div>
        <p className="mb-5 text-sm text-muted">
          Create an account ahead of your first call. Meetings you file later attach to it.
        </p>

        <div className="mb-4 grid grid-cols-2 gap-2">
          <KindButton
            active={kind === "external"}
            onClick={() => setKind("external")}
            icon={<BuildingIcon width={16} height={16} />}
            title="Company"
            hint="External — a deal"
          />
          <KindButton
            active={kind === "internal"}
            onClick={() => setKind("internal")}
            icon={<UsersIcon width={16} height={16} />}
            title="Internal"
            hint="Team / label"
          />
        </div>

        <label className="mb-1 block text-[13px] font-medium text-ink">
          {kind === "external" ? "Company name" : "Label"}
        </label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          placeholder={kind === "external" ? "e.g. Acme Corp" : "e.g. Weekly engineering sync"}
          autoFocus
        />

        {kind === "external" && (
          <>
            <label className="mb-1 mt-4 block text-[13px] font-medium text-ink">
              Segment <span className="font-normal text-faint">(optional)</span>
            </label>
            <Input
              value={segment}
              onChange={(e) => setSegment(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && save()}
              placeholder="e.g. Enterprise, SMB, Healthcare"
            />
          </>
        )}

        {error && <p className="mt-4 text-sm text-danger">{error}</p>}

        <div className="mt-6 flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} disabled={saving}>
            {saving ? "Adding…" : "Add company"}
            {!saving && <CheckIcon width={16} height={16} />}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function KindButton({
  active,
  onClick,
  icon,
  title,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left transition ${
        active ? "border-accent bg-accent-soft text-accent shadow-glow" : "border-border text-muted hover:bg-raised"
      }`}
    >
      <span className={active ? "text-accent" : "text-faint"}>{icon}</span>
      <span>
        <span className="block text-[13px] font-medium text-ink">{title}</span>
        <span className="block text-[11px] text-faint">{hint}</span>
      </span>
    </button>
  );
}

function HealthCell({ callId }: { callId: string | null }) {
  const [score, setScore] = useState<Score | null>(null);
  useEffect(() => {
    let live = true;
    if (callId) api.getScore(callId).then((s) => live && setScore(s)).catch(() => live && setScore(null));
    else setScore(null);
    return () => {
      live = false;
    };
  }, [callId]);

  const health = dealHealth(score);
  const hl = healthLabel(health);
  if (!callId || health == null) return <span className="font-mono text-xs text-faint">—</span>;
  return (
    <div className="flex items-center gap-2">
      <Badge tone={hl.tone}>{hl.label}</Badge>
      <span className="font-mono text-xs text-muted tabular-nums">{health}</span>
    </div>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={`px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-faint ${className}`}
    >
      {children}
    </th>
  );
}
