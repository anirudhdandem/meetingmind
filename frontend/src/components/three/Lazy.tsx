"use client";

/* Client-only, lazily-loaded wrappers for the WebGL scenes. WebGL never runs
   on the server (ssr:false) and is skipped entirely for reduced-motion users,
   who get a tasteful CSS fallback instead. */

import dynamic from "next/dynamic";
import { useReducedMotion } from "framer-motion";
import type { GraphLayer } from "./IntelGraph";

/* ------------------------------------------------------------- CSS fallback */

export function OrbFallback({ className = "" }: { className?: string }) {
  return (
    <div className={`relative flex items-center justify-center ${className}`} aria-hidden>
      <div className="spin-slow absolute h-[78%] w-[78%] rounded-full opacity-40"
        style={{ background: "conic-gradient(from 0deg, transparent, rgba(99,102,241,0.6), transparent 60%)" }}
      />
      <div className="relative h-[55%] w-[55%] rounded-full"
        style={{
          background: "radial-gradient(circle at 35% 30%, #a5b4fc, #6366f1 45%, #4338ca 70%, #1e1b4b)",
          boxShadow: "0 0 80px 10px rgba(79,70,229,0.4), inset 0 0 40px rgba(255,255,255,0.25)",
        }}
      />
      <div className="float absolute h-2 w-2 rounded-full bg-iris" style={{ top: "18%", right: "24%" }} />
      <div className="float absolute h-1.5 w-1.5 rounded-full bg-accent" style={{ bottom: "22%", left: "20%", animationDelay: "-2s" }} />
    </div>
  );
}

function GraphFallback({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center justify-center ${className}`} aria-hidden>
      <div className="h-32 w-32 rounded-full border border-accent/30 bg-accent-soft blur-[1px]" />
    </div>
  );
}

/* ------------------------------------------------------------- lazy scenes */

const Orb = dynamic(() => import("./RevenueOrb"), { ssr: false, loading: () => <OrbFallback className="h-full w-full" /> });
const Graph = dynamic(() => import("./IntelGraph"), { ssr: false, loading: () => <GraphFallback className="h-full w-full" /> });

export function OrbHero({ className = "" }: { className?: string }) {
  const reduced = useReducedMotion();
  if (reduced) return <OrbFallback className={className} />;
  return <Orb className={className} />;
}

export function IntelGraph3D({ layers, className = "" }: { layers?: GraphLayer[]; className?: string }) {
  const reduced = useReducedMotion();
  if (reduced) return <GraphFallback className={className} />;
  return <Graph layers={layers} className={className} />;
}
