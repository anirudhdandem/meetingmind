"use client";

/* Motion primitives for MeetingMind — polished transitions + subtle 3D depth.
   Everything here is client-only and degrades gracefully when the user has
   "reduce motion" enabled. */

import { useEffect, useRef } from "react";
import {
  AnimatePresence,
  animate,
  motion,
  useInView,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "framer-motion";

const EASE = [0.16, 1, 0.3, 1] as const;

/* ----------------------------------------------------------- reveal on view */

export function Reveal({
  children,
  delay = 0,
  y = 14,
  className = "",
  as = "div",
}: {
  children: React.ReactNode;
  delay?: number;
  y?: number;
  className?: string;
  as?: "div" | "section" | "header" | "li" | "span";
}) {
  const reduced = useReducedMotion();
  const M = (motion as any)[as];
  return (
    <M
      initial={reduced ? false : { opacity: 0, y }}
      whileInView={reduced ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, delay, ease: EASE }}
      className={className}
    >
      {children}
    </M>
  );
}

/* --------------------------------------------------------- staggered groups */

export function Stagger({
  children,
  className = "",
  gap = 0.07,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  gap?: number;
  as?: "div" | "section" | "ul";
}) {
  const reduced = useReducedMotion();
  const M = (motion as any)[as];
  return (
    <M
      initial={reduced ? false : "hidden"}
      whileInView="show"
      viewport={{ once: true, margin: "-40px" }}
      variants={{ hidden: {}, show: { transition: { staggerChildren: gap } } }}
      className={className}
    >
      {children}
    </M>
  );
}

export function StaggerItem({
  children,
  className = "",
  y = 14,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  y?: number;
  as?: "div" | "li" | "tr";
}) {
  const M = (motion as any)[as];
  return (
    <M
      variants={{
        hidden: { opacity: 0, y },
        show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE } },
      }}
      className={className}
    >
      {children}
    </M>
  );
}

/* ----------------------------------------------------------- 3D tilt surface */

export function TiltCard({
  children,
  className = "",
  max = 7,
  lift = true,
}: {
  children: React.ReactNode;
  className?: string;
  max?: number;
  lift?: boolean;
}) {
  const reduced = useReducedMotion();
  const rx = useMotionValue(0);
  const ry = useMotionValue(0);
  const srx = useSpring(rx, { stiffness: 160, damping: 16 });
  const sry = useSpring(ry, { stiffness: 160, damping: 16 });

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    if (reduced) return;
    const r = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    ry.set(px * max);
    rx.set(-py * max);
  }
  function onLeave() {
    rx.set(0);
    ry.set(0);
  }

  return (
    <div className="scene-3d">
      <motion.div
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        style={{ rotateX: srx, rotateY: sry, transformStyle: "preserve-3d" }}
        className={`rounded-[var(--radius-card)] border border-border bg-surface shadow-card transition-shadow duration-300 ${
          lift ? "hover:shadow-lift" : ""
        } ${className}`}
      >
        {children}
      </motion.div>
    </div>
  );
}

/* --------------------------------------------------------- animated counter */

export function Counter({
  value,
  decimals = 0,
  className = "",
  duration = 0.9,
}: {
  value: number;
  decimals?: number;
  className?: string;
  duration?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-20px" });
  const reduced = useReducedMotion();
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => v.toFixed(decimals));

  useEffect(() => {
    if (!inView) return;
    if (reduced) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, { duration, ease: EASE });
    return () => controls.stop();
  }, [inView, value, reduced, duration, mv]);

  return (
    <span ref={ref} className={className}>
      <motion.span>{text}</motion.span>
    </span>
  );
}

/* ----------------------------------------------------- animated rubric meter */

export function MotionMeter({
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
  const good = invert ? 100 - v : v; // 0..100 where higher = greener
  const hue = 8 + (good / 100) * 130; // red → green
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-20px" });
  const reduced = useReducedMotion();

  return (
    <div ref={ref} className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className={`text-[13px] ${emphasis ? "font-medium text-ink" : "text-muted"}`}>
          {label}
        </span>
        <span
          className={`font-mono text-[13px] tabular-nums ${value == null ? "text-faint" : "text-ink"}`}
        >
          {value == null ? "—" : <Counter value={value} />}
          <span className="text-faint">/100</span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-raised">
        <motion.div
          className="h-full rounded-full"
          initial={{ width: 0 }}
          animate={inView ? { width: `${v}%` } : { width: 0 }}
          transition={{ duration: reduced ? 0 : 0.9, ease: EASE }}
          style={{ backgroundColor: value == null ? "transparent" : `hsl(${hue} 64% 45%)` }}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ aurora canvas */

export function AuroraBg({ className = "" }: { className?: string }) {
  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`} aria-hidden>
      <span
        className="aurora-blob"
        style={{
          width: 360,
          height: 360,
          left: "-7%",
          top: "-46%",
          background: "radial-gradient(circle, #6366f1, transparent 70%)",
        }}
      />
      <span
        className="aurora-blob"
        style={{
          width: 400,
          height: 400,
          right: "-9%",
          top: "-34%",
          background: "radial-gradient(circle, #818cf8, transparent 70%)",
          animationDelay: "-6s",
          animationDuration: "22s",
        }}
      />
      <span
        className="aurora-blob"
        style={{
          width: 320,
          height: 320,
          left: "42%",
          top: "6%",
          background: "radial-gradient(circle, #a78bfa, transparent 70%)",
          animationDelay: "-12s",
          animationDuration: "26s",
        }}
      />
    </div>
  );
}

/* -------------------------------------------------------------- modal shell */

export function Modal({
  open,
  onClose,
  children,
  className = "",
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            className={`glass relative z-10 w-full max-w-lg rounded-2xl border border-border shadow-lift ${className}`}
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.28, ease: EASE }}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
