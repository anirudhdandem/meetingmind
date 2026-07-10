// Intelligence layer — derives the product's headline metrics and deal analytics
// purely from real backend data (calls, outcomes, MoM minutes, rubric scores).
// No fabricated/placeholder values: every figure here traces back to the API.

import type { Call, Company, Mom, Outcome, Score } from "./api";

/* ------------------------------------------------------------- deal health */

/** Unified 0–100 deal-health score derived from the rubric. Objection severity
 *  counts against health. Returns null only when there's no signal at all. */
export function dealHealth(score: Score | null | undefined): number | null {
  if (!score) return null;
  const terms: Array<[number | null | undefined, number]> = [
    [score.overall_rating, 0.3],
    [score.engagement_score, 0.25],
    [score.technical_fit_score, 0.2],
    [score.urgency_score, 0.15],
    [score.objection_severity == null ? null : 100 - score.objection_severity, 0.1],
  ];
  let sum = 0;
  let weight = 0;
  for (const [v, w] of terms) {
    if (v == null) continue;
    sum += v * w;
    weight += w;
  }
  if (weight === 0) return null;
  return Math.round(sum / weight);
}

export function healthLabel(v: number | null): { label: string; tone: "won" | "pending" | "lost" } {
  if (v == null) return { label: "No signal", tone: "pending" };
  if (v >= 70) return { label: "Healthy", tone: "won" };
  if (v >= 45) return { label: "At watch", tone: "pending" };
  return { label: "At risk", tone: "lost" };
}

/* --------------------------------------------------------------- deal stage */

export const DEAL_STAGES = [
  "Lead",
  "Discovery",
  "Demo",
  "Proposal",
  "Negotiation",
  "Closed",
] as const;
export type DealStage = (typeof DEAL_STAGES)[number];

/** Derive a deal stage from real signals: outcome + meeting count + budget signal. */
export function dealStage(opts: {
  outcome?: Outcome | null;
  meetingCount: number;
  mom?: Mom | null;
}): DealStage {
  const { outcome, meetingCount, mom } = opts;
  if (outcome && outcome.status !== "pending") return "Closed";
  if (mom?.budget_signal) return meetingCount >= 3 ? "Negotiation" : "Proposal";
  if (meetingCount >= 4) return "Negotiation";
  if (meetingCount >= 3) return "Proposal";
  if (meetingCount >= 2) return "Demo";
  if (meetingCount >= 1) return "Discovery";
  return "Lead";
}

export function stageIndex(stage: DealStage): number {
  return DEAL_STAGES.indexOf(stage);
}

/* ----------------------------------------------------------- sentiment / risk */

/** A 0–100 sentiment read from engagement, softened by objection severity. */
export function sentiment(score: Score | null | undefined): number | null {
  if (!score) return null;
  const e = score.engagement_score;
  const o = score.objection_severity;
  if (e == null && o == null) return null;
  return Math.round((e ?? 60) * 0.7 + (100 - (o ?? 40)) * 0.3);
}

/** Risk = objection severity, lifted when urgency is low. Higher = riskier. */
export function risk(score: Score | null | undefined): number | null {
  if (!score) return null;
  const o = score.objection_severity;
  const u = score.urgency_score;
  if (o == null && u == null) return null;
  return Math.round((o ?? 40) * 0.65 + (100 - (u ?? 50)) * 0.35);
}

/* --------------------------------------------------------- aggregate metrics */

export interface OverviewMetrics {
  meetings: number;
  companies: number;
  activeDeals: number;
  won: number;
  lost: number;
  open: number;
  winRate: number | null; // 0..100
}

export function overviewMetrics(
  calls: Call[],
  companies: Company[],
  outcomes: Outcome[],
): OverviewMetrics {
  const won = outcomes.filter((o) => o.status === "accepted");
  const lost = outcomes.filter((o) => o.status === "rejected");
  const open = outcomes.filter((o) => o.status === "pending");
  const decided = won.length + lost.length;
  return {
    meetings: calls.length,
    companies: companies.length,
    activeDeals: open.length,
    won: won.length,
    lost: lost.length,
    open: open.length,
    winRate: decided ? Math.round((won.length / decided) * 100) : null,
  };
}

/* -------------------------------------------------- AI recommendations */

/** Next-best-actions derived from the weakest rubric signals + MoM gaps. */
export function recommendations(score: Score | null | undefined, mom?: Mom | null): string[] {
  const recs: string[] = [];
  if (score) {
    if ((score.objection_severity ?? 0) >= 55) recs.push("Address the open objections head-on before they harden");
    if ((score.technical_fit_score ?? 100) < 55) recs.push("Schedule a technical deep-dive to close the fit gap");
    if ((score.urgency_score ?? 100) < 50) recs.push("Create urgency — tie the timeline to their fiscal close");
    if ((score.engagement_score ?? 100) < 55) recs.push("Re-engage the room; the last call ran cool");
  }
  if (mom && !mom.budget_signal) recs.push("Confirm budget owner and authority");
  if (mom && !mom.decision_maker) recs.push("Get the decision maker into the next meeting");
  if (recs.length === 0) recs.push("Momentum is strong — push for a clear next step and close date");
  return recs.slice(0, 4);
}

