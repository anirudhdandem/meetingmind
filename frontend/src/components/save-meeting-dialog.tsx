"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type Call, type Company, type Outcome, type OutcomeStatus, type TeamMember } from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { Modal } from "@/components/motion";
import { BuildingIcon, UsersIcon, CheckIcon } from "@/components/icons";

const DEFAULT_COMPANY = "Ad-hoc meetings";

type Kind = "external" | "internal";
type Deal = "accepted" | "rejected" | "pending";

const DEAL_OPTS: { value: Deal; label: string; hint: string; active: string }[] = [
  { value: "accepted", label: "Closed — Won", hint: "Deal landed", active: "border-success/50 bg-success/12 text-success" },
  { value: "rejected", label: "Closed — Lost", hint: "Didn't go through", active: "border-danger/50 bg-danger/12 text-danger" },
  { value: "pending", label: "Still open", hint: "In progress", active: "border-warning/50 bg-warning/12 text-warning" },
];

export function SaveMeetingDialog({
  open,
  onClose,
  call,
  company,
  companies,
  outcome,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  call: Call;
  company: Company | null;
  companies: Company[];
  outcome: Outcome | null;
  onSaved: () => void;
}) {
  const prefillExternal = company && company.kind === "external" && company.name !== DEFAULT_COMPANY;
  const prefillInternal = company && company.kind === "internal";

  const [kind, setKind] = useState<Kind>(prefillInternal ? "internal" : "external");
  const [name, setName] = useState(prefillExternal || prefillInternal ? company!.name : "");
  const [segment, setSegment] = useState(prefillExternal ? company!.segment ?? "" : "");
  const [presentedBy, setPresentedBy] = useState(prefillExternal ? company!.presented_by ?? "" : "");
  const [product, setProduct] = useState(prefillExternal ? company!.product_pitched ?? "" : "");
  const [deal, setDeal] = useState<Deal>((outcome?.status as Deal) ?? "pending");
  const [notes, setNotes] = useState(outcome?.outcome_notes ?? "");
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Re-seed when the dialog (re)opens for a different call.
  useEffect(() => {
    if (!open) return;
    setKind(prefillInternal ? "internal" : "external");
    setName(prefillExternal || prefillInternal ? company!.name : "");
    setSegment(prefillExternal ? company!.segment ?? "" : "");
    setPresentedBy(prefillExternal ? company!.presented_by ?? "" : "");
    setProduct(prefillExternal ? company!.product_pitched ?? "" : "");
    setDeal((outcome?.status as Deal) ?? "pending");
    setNotes(outcome?.outcome_notes ?? "");
    setError(null);
    // Team roster as suggestions for "Presented by" (free text still allowed).
    api.listTeam().then((rows) => setTeam(rows.filter((m) => m.active))).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, call.id]);

  const externalNames = useMemo(
    () => companies.filter((c) => c.kind === "external" && c.name !== DEFAULT_COMPANY).map((c) => c.name),
    [companies],
  );

  async function save() {
    const label = name.trim();
    if (!label) {
      setError(kind === "external" ? "Enter the company name." : "Give this meeting a label.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await api.assignCompany(call.id, {
        name: label,
        kind,
        segment: kind === "external" ? segment.trim() || null : null,
        // "" clears the stored value; undefined would leave it untouched.
        presented_by: kind === "external" ? presentedBy.trim() : undefined,
        product_pitched: kind === "external" ? product.trim() : undefined,
      });
      if (kind === "external") {
        await api.createOutcome({
          company_id: updated.company_id,
          call_id: call.id,
          status: deal as OutcomeStatus,
          outcome_notes: notes.trim() || null,
        });
      }
      onSaved();
      onClose();
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
          Save this meeting
        </div>
        <p className="mb-5 text-sm text-muted">
          File it so you can find and compare it later. The summary, minutes, and scores are kept either way.
        </p>

        {/* Meeting type toggle */}
        <div className="mb-4 grid grid-cols-2 gap-2">
          <TypeButton
            active={kind === "external"}
            onClick={() => setKind("external")}
            icon={<BuildingIcon width={16} height={16} />}
            title="With a company"
            hint="External — a deal"
          />
          <TypeButton
            active={kind === "internal"}
            onClick={() => setKind("internal")}
            icon={<UsersIcon width={16} height={16} />}
            title="Internal meeting"
            hint="Team / sync"
          />
        </div>

        {/* Name / label */}
        <label className="mb-1 block text-[13px] font-medium text-ink">
          {kind === "external" ? "Company name" : "Meeting label"}
        </label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          list={kind === "external" ? "mm-company-list" : undefined}
          placeholder={kind === "external" ? "e.g. Acme Corp" : "e.g. Weekly engineering sync"}
          autoFocus
        />
        {kind === "external" && (
          <datalist id="mm-company-list">
            {externalNames.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
        )}

        {/* External-only extras */}
        {kind === "external" ? (
          <>
            <label className="mb-1 mt-4 block text-[13px] font-medium text-ink">
              Segment <span className="font-normal text-faint">(optional)</span>
            </label>
            <Input
              value={segment}
              onChange={(e) => setSegment(e.target.value)}
              placeholder="e.g. Enterprise, SMB, Healthcare"
            />

            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-[13px] font-medium text-ink">
                  Presented by <span className="font-normal text-faint">(lead)</span>
                </label>
                <Input
                  value={presentedBy}
                  onChange={(e) => setPresentedBy(e.target.value)}
                  list="mm-team-list"
                  placeholder="Who led the pitch"
                />
                <datalist id="mm-team-list">
                  {team.map((m) => (
                    <option key={m.id} value={m.name} />
                  ))}
                </datalist>
              </div>
              <div>
                <label className="mb-1 block text-[13px] font-medium text-ink">
                  Product pitched
                </label>
                <Input
                  value={product}
                  onChange={(e) => setProduct(e.target.value)}
                  placeholder="What was pitched"
                />
              </div>
            </div>

            <div className="mb-2 mt-5 text-[13px] font-medium text-ink">Is the deal closed?</div>
            <div className="grid grid-cols-3 gap-2">
              {DEAL_OPTS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => setDeal(o.value)}
                  className={`rounded-xl border px-3 py-2.5 text-left transition ${
                    deal === o.value ? o.active : "border-border text-muted hover:bg-raised"
                  }`}
                >
                  <div className="text-[13px] font-medium">{o.label}</div>
                  <div className="text-[11px] opacity-80">{o.hint}</div>
                </button>
              ))}
            </div>

            <label className="mb-1 mt-4 block text-[13px] font-medium text-ink">
              Notes <span className="font-normal text-faint">(optional)</span>
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Why it closed the way it did…"
              className="w-full resize-none rounded-lg border border-border bg-raised px-3 py-2 text-sm text-ink outline-none transition placeholder:text-faint focus:border-accent/60 focus:ring-2 focus:ring-accent/15"
            />
          </>
        ) : (
          <p className="mt-4 rounded-lg bg-raised px-3 py-2.5 text-[13px] leading-relaxed text-muted">
            Internal meetings are saved under this label so you can reopen them anytime. Deal
            outcomes don’t apply.
          </p>
        )}

        {error && <p className="mt-4 text-sm text-danger">{error}</p>}

        <div className="mt-6 flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Later
          </Button>
          <Button variant="primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save meeting"}
            {!saving && <CheckIcon width={16} height={16} />}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function TypeButton({
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
