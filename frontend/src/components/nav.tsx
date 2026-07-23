"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Radio,
  Building2,
  Swords,
  Sparkles,
  Search,
  Settings,
  Command,
  LogOut,
} from "lucide-react";

import { useAuth } from "@/lib/auth";

/* ------------------------------------------------------------- navigation IA */

type Item = {
  href: string;
  label: string;
  match: (p: string) => boolean;
  Icon: typeof LayoutDashboard;
};

const PRIMARY: Item[] = [
  { href: "/", label: "Overview", match: (p) => p === "/", Icon: LayoutDashboard },
  { href: "/calls", label: "Meetings", match: (p) => p.startsWith("/calls"), Icon: Radio },
  { href: "/companies", label: "Companies", match: (p) => p.startsWith("/companies"), Icon: Building2 },
  { href: "/compare", label: "Outcomes", match: (p) => p.startsWith("/compare"), Icon: Swords },
  { href: "/prep", label: "Meeting Prep", match: (p) => p.startsWith("/prep"), Icon: Sparkles },
  { href: "/intelligence", label: "Ask Intelligence", match: (p) => p.startsWith("/intelligence"), Icon: Search },
];

const SECONDARY: Item[] = [
  { href: "/settings", label: "Settings", match: (p) => p.startsWith("/settings"), Icon: Settings },
];

/* --------------------------------------------------------------------- brand */

export function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      {/* The mark's outer arc and eyes are navy, so it needs a light tile to read
          against the dark sidebar — same tile in both modes keeps the two navs
          identical. */}
      <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-white shadow-[0_6px_18px_-6px_rgba(15,23,42,0.45)]">
        {/* unoptimized: the production image has no `sharp`, and Next's optimizer
            hard-fails without it. A 30px static PNG needs no resizing anyway. */}
        <Image
          src="/fennec-mark.png"
          alt=""
          width={30}
          height={30}
          priority
          unoptimized
          className="relative"
        />
      </span>
      <span className="flex flex-col leading-none">
        <span className={`font-display text-[16px] font-semibold tracking-tight ${dark ? "text-white" : "text-ink"}`}>
          Fennec
        </span>
        {/* Tighter tracking than the old two-word tagline: at 0.18em this one runs
            past the 260px sidebar rail. */}
        <span className={`mt-0.5 whitespace-nowrap font-mono text-[9.5px] uppercase tracking-[0.13em] ${dark ? "text-white/40" : "text-faint"}`}>
          AI Meeting Intelligence
        </span>
      </span>
    </Link>
  );
}

/** The full logo lockup (mark + wordmark + tagline), for the auth pages where the
 *  brand is the only thing on screen. Navy artwork on transparency — light frames
 *  only, which is what the auth shell renders. */
export function BrandLockup() {
  return (
    <Link href="/" aria-label="Fennec">
      <Image src="/fennec-logo.png" alt="Fennec — AI Meeting Intelligence" width={190} height={186} priority unoptimized />
    </Link>
  );
}

/* ------------------------------------------------------------------- sidebar */

export function Sidebar() {
  return (
    <aside className="sidebar sticky top-0 hidden h-screen w-[260px] shrink-0 flex-col px-4 py-6 lg:flex">
      <div className="px-2">
        <Brand dark />
      </div>

      <div className="mt-10 px-3 font-mono text-[10px] uppercase tracking-[0.2em] text-white/30">
        Workspace
      </div>
      <RailNav items={PRIMARY} className="mt-4" />

      <div className="mt-auto">
        <RailNav items={SECONDARY} />
        <SystemStatus />
      </div>
    </aside>
  );
}

function RailNav({ items, className = "" }: { items: Item[]; className?: string }) {
  const pathname = usePathname() ?? "/";
  return (
    <nav className={`flex flex-col gap-2.5 ${className}`}>
      {items.map(({ href, label, match, Icon }) => {
        const active = match(pathname);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`group relative flex items-center gap-3.5 rounded-xl px-3.5 py-3.5 text-[14.5px] transition-colors outline-none focus:outline-none focus-visible:outline-none [-webkit-tap-highlight-color:transparent] ${
              active ? "text-white" : "text-white/60 hover:text-white"
            }`}
          >
            {active ? (
              <span className="absolute inset-0 -z-0 rounded-xl border border-[#a78bfa]/25 bg-[#a78bfa]/[0.1]" />
            ) : (
              <span className="absolute inset-0 -z-0 rounded-xl bg-white/0 transition-colors group-hover:bg-white/[0.05]" />
            )}
            <span
              className={`absolute left-0 top-1/2 z-10 h-6 w-[3px] -translate-y-1/2 rounded-full bg-[#a78bfa] transition-opacity ${
                active ? "opacity-100" : "opacity-0"
              }`}
            />
            <span
              className={`relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors ${
                active ? "bg-[#a78bfa]/15 text-[#a78bfa]" : "text-white/55 group-hover:text-white/90"
              }`}
            >
              <Icon size={21} strokeWidth={active ? 2.2 : 2} />
            </span>
            <span className="relative z-10 font-medium tracking-tight">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function SystemStatus() {
  return (
    <div className="relative mt-5 overflow-hidden rounded-xl border border-white/10 bg-white/[0.04] p-3.5">
      <div className="flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="ping-ring absolute inset-0 rounded-full text-[#a78bfa]/60" />
          <span className="relative h-2 w-2 rounded-full bg-[#a78bfa] live-dot" />
        </span>
        <span className="text-[12px] font-medium text-white">Bot online</span>
      </div>
      <p className="mt-1.5 text-[11.5px] leading-relaxed text-white/45">
        Joins your meetings, transcribes live, and writes the intelligence layer.
      </p>
    </div>
  );
}

/* --------------------------------------------------------------------- topbar */

export function Topbar() {
  return (
    <header className="sticky top-0 z-20 hidden items-center justify-between gap-4 border-b border-border bg-surface/80 px-10 py-3.5 backdrop-blur-xl lg:flex">
      <Link
        href="/intelligence"
        className="group flex w-full max-w-md items-center gap-2.5 rounded-xl border border-border bg-raised px-3.5 py-2 text-sm text-faint transition hover:border-strong hover:text-muted"
      >
        <Search size={15} className="text-faint group-hover:text-accent" />
        <span>Ask anything across your company memory…</span>
        <span className="ml-auto flex items-center gap-1 rounded-md border border-border px-1.5 py-0.5 font-mono text-[10px] text-faint">
          <Command size={10} /> K
        </span>
      </Link>
      <div className="flex shrink-0 items-center gap-2.5">
        <Link
          href="/calls"
          className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white shadow-glow transition hover:bg-accent-deep active:scale-[0.98]"
        >
          <Radio size={15} /> Start meeting
        </Link>
        <UserMenu />
      </div>
    </header>
  );
}

/** Who's signed in, and the way out. */
function UserMenu() {
  const { me, signOut } = useAuth();
  if (!me) return null;
  return (
    <div className="flex items-center gap-2 border-l border-border pl-2.5">
      <span
        className="max-w-[12rem] truncate text-sm text-muted"
        title={`${me.name} · ${me.email}`}
      >
        {me.name}
      </span>
      <button
        type="button"
        onClick={() => void signOut()}
        title="Sign out"
        aria-label="Sign out"
        className="flex items-center justify-center rounded-lg border border-border p-2 text-faint transition hover:border-strong hover:text-ink"
      >
        <LogOut size={15} />
      </button>
    </div>
  );
}

/* ----------------------------------------------------------------- mobile bar */

export function MobileBar() {
  const pathname = usePathname() ?? "/";
  return (
    <header className="sticky top-0 z-20 flex flex-col gap-3 border-b border-border bg-surface/90 px-5 py-3 backdrop-blur-xl lg:hidden">
      <div className="flex items-center justify-between">
        <Brand />
        <Link
          href="/intelligence"
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted"
          aria-label="Search"
        >
          <Search size={16} />
        </Link>
      </div>
      <nav className="scroll-thin -mx-1 flex items-center gap-1.5 overflow-x-auto px-1">
        {[...PRIMARY, ...SECONDARY].map(({ href, label, match, Icon }) => {
          const active = match(pathname);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] transition outline-none focus:outline-none focus-visible:outline-none [-webkit-tap-highlight-color:transparent] ${
                active ? "border border-accent/20 bg-accent-soft font-medium text-accent" : "text-muted"
              }`}
            >
              <Icon size={14} />
              {label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
