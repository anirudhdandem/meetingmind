import Link from "next/link";
import type { CallStatus, OutcomeStatus } from "@/lib/api";

/* ---------------------------------------------------------------- surfaces */

export function Card({
  children,
  className = "",
  as: As = "div",
  hover = false,
}: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
  hover?: boolean;
}) {
  return (
    <As className={`panel ${hover ? "hover-ring" : ""} shadow-card ${className}`}>{children}</As>
  );
}

/** Card with a persistent accent-gradient hairline frame — for hero/feature panels. */
export function GlowCard({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`relative rounded-[var(--radius-card)] p-px ${className}`}>
      <div
        className="absolute inset-0 rounded-[var(--radius-card)] opacity-60"
        style={{ background: "linear-gradient(140deg, rgba(79,70,229,0.5), rgba(124,58,237,0.28) 45%, transparent 70%)" }}
        aria-hidden
      />
      <div className="panel-raised panel relative h-full rounded-[calc(var(--radius-card)-1px)]">{children}</div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  sub,
  actions,
}: {
  eyebrow?: string;
  title: string;
  sub?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink">{title}</h1>
        {sub && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">{sub}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-accent">
      {children}
    </div>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[10.5px] font-medium uppercase tracking-[0.14em] text-faint">
      {children}
    </div>
  );
}

export function Divider({ className = "" }: { className?: string }) {
  return <div className={`h-px w-full bg-border ${className}`} />;
}

/* ----------------------------------------------------------------- buttons */

type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
const BTN: Record<BtnVariant, string> = {
  primary: "bg-accent text-white hover:bg-accent/90 shadow-glow disabled:bg-accent/40",
  secondary: "border border-border bg-raised text-ink hover:border-strong hover:bg-overlay disabled:opacity-50",
  ghost: "text-muted hover:bg-raised hover:text-ink disabled:opacity-40",
  danger: "bg-danger/90 text-white hover:bg-danger disabled:bg-danger/40",
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md" }) {
  const pad = size === "sm" ? "px-3 py-1.5 text-[13px]" : "px-4 py-2 text-sm";
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:active:scale-100 ${pad} ${BTN[variant]} ${className}`}
      {...props}
    />
  );
}

/* ------------------------------------------------------------------ inputs */

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-xl border border-border bg-raised px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-faint focus:border-accent/60 focus:bg-overlay focus:ring-2 focus:ring-accent/15 ${props.className ?? ""}`}
    />
  );
}

/* ------------------------------------------------------------------ badges */

type Tone = "won" | "lost" | "pending" | "live" | "done" | "scheduled" | "failed" | "neutral" | "accent";
const TONE: Record<Tone, string> = {
  won: "bg-success/12 text-success ring-success/25",
  lost: "bg-danger/12 text-danger ring-danger/25",
  pending: "bg-warning/12 text-warning ring-warning/25",
  live: "bg-warning/12 text-warning ring-warning/30",
  done: "bg-success/12 text-success ring-success/25",
  scheduled: "bg-iris/12 text-iris ring-iris/25",
  failed: "bg-danger/12 text-danger ring-danger/25",
  neutral: "bg-raised text-muted ring-border",
  accent: "bg-accent-soft text-accent ring-accent/25",
};

export function Badge({
  tone = "neutral",
  dot = false,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE[tone]}`}
    >
      {dot && (
        <span className={`h-1.5 w-1.5 rounded-full bg-current ${tone === "live" ? "live-dot" : ""}`} />
      )}
      {children}
    </span>
  );
}

const CALL_STATUS: Record<CallStatus, { tone: Tone; label: string; dot?: boolean }> = {
  scheduled: { tone: "scheduled", label: "Scheduled" },
  in_progress: { tone: "live", label: "Live", dot: true },
  completed: { tone: "done", label: "Completed" },
  failed: { tone: "failed", label: "Failed" },
};

export function StatusBadge({ status }: { status: CallStatus }) {
  const s = CALL_STATUS[status];
  return (
    <Badge tone={s.tone} dot={s.dot}>
      {s.label}
    </Badge>
  );
}

const OUTCOME: Record<OutcomeStatus, { tone: Tone; label: string }> = {
  accepted: { tone: "won", label: "Won" },
  rejected: { tone: "lost", label: "Lost" },
  pending: { tone: "pending", label: "Open" },
};

export function OutcomeBadge({ status }: { status: OutcomeStatus }) {
  const o = OUTCOME[status];
  return <Badge tone={o.tone}>{o.label}</Badge>;
}

/* -------------------------------------------------------------- data atoms */

/** hsl hue 0..130 (red→green) for a 0..100 score, optionally inverted. */
export function scoreHue(value: number, invert = false): number {
  const good = invert ? 100 - value : value;
  return 8 + (good / 100) * 130;
}

/** Horizontal rubric meter — mono value, thin bar, hue tracks the score. */
export function Meter({
  label,
  value,
  invert = false,
  emphasis = false,
}: {
  label: string;
  value: number | null;
  invert?: boolean;
  emphasis?: boolean;
}) {
  const v = value ?? 0;
  const hue = scoreHue(v, invert);
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className={`text-[13px] ${emphasis ? "font-medium text-ink" : "text-muted"}`}>{label}</span>
        <span className={`font-mono text-[13px] tabular-nums ${value == null ? "text-faint" : "text-ink"}`}>
          {value == null ? "—" : value}
          <span className="text-faint">/100</span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-overlay">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${v}%`, backgroundColor: value == null ? "transparent" : `hsl(${hue} 70% 52%)` }}
        />
      </div>
    </div>
  );
}

/** Circular gauge for a single headline 0..100 score (deal health, rating). */
export function Ring({
  value,
  size = 132,
  stroke = 9,
  label,
  invert = false,
}: {
  value: number | null;
  size?: number;
  stroke?: number;
  label?: string;
  invert?: boolean;
}) {
  const v = value ?? 0;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const hue = scoreHue(v, invert);
  const color = value == null ? "var(--color-faint)" : `hsl(${hue} 70% 52%)`;
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-overlay)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (c * v) / 100}
          style={{ transition: "stroke-dashoffset 0.9s cubic-bezier(0.16,1,0.3,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono text-2xl font-semibold tabular-nums text-ink">
          {value == null ? "—" : value}
        </span>
        {label && <span className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-faint">{label}</span>}
      </div>
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "won" | "lost" | "ink" | "accent";
}) {
  const color =
    tone === "won" ? "text-success" : tone === "lost" ? "text-danger" : tone === "accent" ? "text-accent" : "text-ink";
  return (
    <div className="panel p-4">
      <SectionLabel>{label}</SectionLabel>
      <div className={`mt-2 font-mono text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="flex gap-2 text-sm">
      <span className="shrink-0 text-muted">{label}</span>
      <span className="text-ink">{value}</span>
    </div>
  );
}

export function Chip({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "lost" | "pending" | "accent";
}) {
  const c =
    tone === "lost"
      ? "bg-danger/10 text-danger ring-danger/20"
      : tone === "pending"
        ? "bg-warning/10 text-warning ring-warning/20"
        : tone === "accent"
          ? "bg-accent-soft text-accent ring-accent/20"
          : "bg-raised text-muted ring-border";
  return <span className={`rounded-md px-2 py-1 text-xs ring-1 ring-inset ${c}`}>{children}</span>;
}

/* ----------------------------------------------------------- empty / async */

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed border-border bg-surface/50 px-6 py-16 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <div className="font-display text-base font-medium text-ink">{title}</div>
      {children && <div className="mt-1.5 max-w-sm text-sm text-muted">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Spinner({ className = "", size = 16 }: { className?: string; size?: number }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="Loading"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted">
      <Spinner /> {label}…
    </div>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-danger/25 bg-danger/10 px-4 py-3 text-sm text-danger">
      {children}
    </div>
  );
}

/* --------------------------------------------------------------- card link */

export function RowLink({
  href,
  children,
  className = "",
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={`block transition hover:bg-raised focus-visible:bg-raised ${className}`}
    >
      {children}
    </Link>
  );
}
