// Typed client for the Fennec backend.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type CallStatus = "scheduled" | "in_progress" | "completed" | "failed";
export type OutcomeStatus = "accepted" | "rejected" | "pending";

export type CompanyKind = "external" | "internal";

export interface Company {
  id: string;
  name: string;
  segment: string | null;
  kind: CompanyKind;
  // Who on our team led the pitch, and what was pitched (user-entered).
  presented_by: string | null;
  product_pitched: string | null;
  created_at: string;
}

export interface Call {
  id: string;
  company_id: string;
  sales_rep_id: string | null;
  meeting_platform: string;
  meeting_url: string | null;
  livekit_room: string | null;
  participants: string[] | null;
  status: CallStatus;
  scheduled_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

export type SpeakerRole = "internal" | "client" | "unknown";

export interface Transcript {
  id: string;
  speaker_label: string | null;
  // "internal" = our team, "client", "unknown", or null when not yet computed.
  role: SpeakerRole | null;
  text: string;
  start_ts: number;
  end_ts: number;
  confidence: number | null;
}

export interface Attendee {
  name: string;
  role?: string | null;
  is_decision_maker?: boolean;
}

export interface Contribution {
  name: string;
  summary: string;
}

export interface Mom {
  id: string;
  call_id: string;
  company_id: string;
  attendees: Attendee[] | null;
  points_discussed: string[] | null;
  action_items: string[] | null;
  contributions: Contribution[] | null;
  pain_points: string[] | null;
  objections: string[] | null;
  went_well: string[] | null;
  to_improve: string[] | null;
  next_steps: string | null;
  decision_maker: string | null;
  budget_signal: string | null;
  raw_summary: string | null;
  created_at: string;
}

export interface Score {
  id: string;
  call_id: string;
  engagement_score: number | null;
  objection_severity: number | null;
  urgency_score: number | null;
  technical_fit_score: number | null;
  overall_rating: number | null;
  qualitative_notes: string | null;
}

export interface Metrics {
  id: string;
  call_id: string;
  // Talk-time split (Phase 2)
  team_talk_seconds: number | null;
  client_talk_seconds: number | null;
  unknown_talk_seconds: number | null;
  team_turns: number | null;
  client_turns: number | null;
  talk_ratio: number | null;
  // Team performance (Phase 3)
  confidence_score: number | null;
  confidence_notes: string | null;
  answer_quality_score: number | null;
  answer_notes: string | null;
  client_questions: number | null;
  questions_answered: number | null;
  // Conversion probability (Phase 4)
  conversion_probability: number | null;
  conversion_notes: string | null;
}

export interface Outcome {
  id: string;
  company_id: string;
  call_id: string | null;
  status: OutcomeStatus;
  outcome_date: string | null;
  outcome_notes: string | null;
}

export interface SimilarCall {
  call_id: string | null;
  company_id: string;
  distance: number;
  source_text: string | null;
}

export interface RubricDelta {
  field: string;
  won_avg: number;
  lost_avg: number;
  delta: number;
}

export interface ComparisonReport {
  segment: string | null;
  won_count: number;
  lost_count: number;
  deltas: RubricDelta[];
  narrative: string;
}

export interface GoogleOAuthStatus {
  configured: boolean;
  connected: boolean;
  email: string | null;
  // Whether the connection carries calendar.readonly. The bot connection needs
  // it for calendar auto-join; false on a bot account connected before that
  // scope existed (fix = reconnect once).
  has_calendar_scope: boolean;
}

// A meeting discovered on the bot's own calendar — the auto-join schedule.
export type AutoJoinStatus = "pending" | "dispatched" | "missed" | "skipped" | "cancelled";

export interface CalendarEvent {
  id: string;
  google_event_id: string;
  title: string | null;
  organizer_email: string | null;
  meet_code: string;
  meeting_url: string;
  start_at: string;
  end_at: string | null;
  status: AutoJoinStatus;
  note: string | null;
  call_id: string | null;
  created_at: string;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string | null;
  active: boolean;
  // "manual" = added here in Settings; "auto" = learned from a call's analysis.
  source: string;
  created_at: string;
}

interface Integration {
  configured: boolean;
}
export interface SettingsStatus {
  bot: Integration & {
    display_name: string;
    account_email: string | null;
    password_set: boolean;
    headless: boolean;
    profile_dir: string;
  };
  transcription: Integration & { provider: string; model: string; language: string };
  llm: Integration & { provider: string; model: string; embed_model: string };
  livekit: Integration & { url: string };
  meet_api: Integration & { impersonate_subject: string | null };
  notifications: { slack_configured: boolean; email_configured: boolean };
}

export interface NotificationSettings {
  slack_webhook_url: string | null;
  notification_email: string | null;
}

// --- Auth ---

export interface Me {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
  // True when the password was accepted but the emailed code hasn't been entered yet.
  otp_pending: boolean;
}

/** Returned by both signup and login: a code is in the inbox, post it to /auth/verify. */
export interface LoginResult {
  email: string;
  name: string;
  resend_after_seconds: number;
}

/** An HTTP failure that kept its status code — the auth guard routes on it. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI's `detail` string, when the body has one. */
async function detailOf(res: Response): Promise<string | null> {
  return res
    .json()
    .then((b) => (typeof b?.detail === "string" ? b.detail : null))
    .catch(() => null);
}

async function fail(res: Response, path: string): Promise<never> {
  const detail = await detailOf(res);
  throw new ApiError(res.status, detail ?? `${res.status} ${res.statusText} for ${path}`);
}

// `credentials: "include"` on every request: the session lives in an httpOnly cookie
// set by the API on a different origin, and browsers omit it otherwise.
const CREDS: RequestInit = { credentials: "include" };

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { ...CREDS, cache: "no-store" });
  if (!res.ok) await fail(res, path);
  return res.json() as Promise<T>;
}

async function send<T>(method: "POST" | "PUT", path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...CREDS,
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  // Surface FastAPI's `detail` (e.g. "already recording 2 meetings") over a bare status.
  if (!res.ok) await fail(res, path);
  // 204s (logout, password change) carry no body.
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => send<T>("POST", path, body);
const put = <T>(path: string, body: unknown) => send<T>("PUT", path, body);

async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { ...CREDS, method: "DELETE" });
  if (!res.ok) await fail(res, path);
}

export const api = {
  // auth
  me: () => get<Me>("/auth/me"),
  signup: (email: string, name: string, password: string) =>
    post<LoginResult>("/auth/signup", { email, name, password }),
  login: (email: string, password: string) => post<LoginResult>("/auth/login", { email, password }),
  verifyCode: (code: string) => post<Me>("/auth/verify", { code }),
  resendCode: () => post<{ resend_after_seconds: number }>("/auth/resend", {}),
  logout: () => post<void>("/auth/logout", {}),
  changePassword: (current_password: string, new_password: string) =>
    post<void>("/auth/password", { current_password, new_password }),
  forgotPassword: (email: string) =>
    post<{ resend_after_seconds: number }>("/auth/password/forgot", { email }),
  resetPassword: (email: string, code: string, new_password: string) =>
    post<void>("/auth/password/reset", { email, code, new_password }),
  // calls
  listCalls: () => get<Call[]>("/calls"),
  getCall: (id: string) => get<Call>(`/calls/${id}`),
  getTranscript: (id: string) => get<Transcript[]>(`/calls/${id}/transcript`),
  getMom: (id: string) => get<Mom>(`/calls/${id}/mom`),
  getScore: (id: string) => get<Score>(`/calls/${id}/score`),
  getMetrics: (id: string) => get<Metrics>(`/calls/${id}/metrics`),
  getCallOutcome: (id: string) => get<Outcome>(`/calls/${id}/outcome`),
  getSimilar: (id: string, limit = 5) =>
    get<SimilarCall[]>(`/retrieval/similar?call_id=${id}&limit=${limit}`),
  processCall: (id: string) => post<Mom>(`/calls/${id}/process`, {}),
  importTranscript: (id: string) => post<Mom>(`/calls/${id}/import-transcript`, {}),
  startCall: (meeting_url: string, company_name?: string) =>
    post<Call>(`/calls/start`, { meeting_url, company_name }),
  // meetings on the bot's calendar it will join automatically (invite the bot's
  // email to a meeting and it shows up here)
  autoJoinSchedule: () => get<CalendarEvent[]>(`/calls/auto-join`),
  stopCall: (id: string) => post<Call>(`/calls/${id}/stop`, {}),
  assignCompany: (
    id: string,
    body: {
      name: string;
      kind: CompanyKind;
      segment?: string | null;
      presented_by?: string | null;
      product_pitched?: string | null;
    },
  ) => post<Call>(`/calls/${id}/company`, body),
  // companies
  listCompanies: () => get<Company[]>("/companies"),
  createCompany: (body: {
    name: string;
    segment?: string | null;
    kind?: CompanyKind;
    presented_by?: string | null;
    product_pitched?: string | null;
  }) => post<Company>("/companies", body),
  getCompanyLatestMom: (companyId: string) =>
    get<Mom>(`/retrieval/company/${companyId}/latest-mom`),
  // outcomes
  listOutcomes: (status?: OutcomeStatus) =>
    get<Outcome[]>(`/retrieval/outcomes${status ? `?status=${status}` : ""}`),
  createOutcome: (body: {
    company_id: string;
    call_id?: string | null;
    status: OutcomeStatus;
    outcome_date?: string | null;
    outcome_notes?: string | null;
  }) => post<Outcome>(`/outcomes`, body),
  // comparison
  getComparison: (segment?: string) =>
    get<ComparisonReport>(`/comparison${segment ? `?segment=${encodeURIComponent(segment)}` : ""}`),
  // team roster
  listTeam: () => get<TeamMember[]>("/team"),
  addTeamMember: (body: { name: string; email?: string | null }) =>
    post<TeamMember>("/team", body),
  removeTeamMember: (id: string) => del(`/team/${id}`),
  // google oauth: purpose "calendar" (organizer's calendar) or "bot" (the bot's
  // own Meet account — used to resolve participant emails after each call)
  getGoogleStatus: (purpose: "calendar" | "bot" = "calendar") =>
    get<GoogleOAuthStatus>(`/oauth/google/status?purpose=${purpose}`),
  disconnectGoogle: (purpose: "calendar" | "bot" = "calendar") =>
    del(`/oauth/google?purpose=${purpose}`),
  // settings
  getSettingsStatus: () => get<SettingsStatus>("/settings/status"),
  getNotifications: () => get<NotificationSettings>("/settings/notifications"),
  saveNotifications: (body: NotificationSettings) =>
    put<NotificationSettings>("/settings/notifications", body),
};

export { BASE };
