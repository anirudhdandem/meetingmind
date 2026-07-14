"use client";

import { useEffect, useState } from "react";
import {
  api,
  BASE,
  type GoogleOAuthStatus,
  type SettingsStatus,
  type TeamMember,
} from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  ErrorNote,
  Field,
  Input,
  Loading,
  PageHeader,
  SectionLabel,
} from "@/components/ui";
import {
  BellIcon,
  DocIcon,
  KeyIcon,
  RobotIcon,
  SparkIcon,
  UsersIcon,
  WaveIcon,
} from "@/components/icons";
import { useAuth } from "@/lib/auth";

function StatusBadge({ configured }: { configured: boolean }) {
  return configured ? (
    <Badge tone="done">Connected</Badge>
  ) : (
    <Badge tone="pending">Needs setup</Badge>
  );
}

function IntegrationCard({
  icon,
  title,
  description,
  configured,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  configured: boolean;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display text-sm font-medium text-ink">{title}</div>
          <p className="mt-0.5 text-sm text-muted">{description}</p>
        </div>
        <StatusBadge configured={configured} />
      </div>
      <div className="mt-4 space-y-2 border-t border-hairline pt-4">{children}</div>
    </Card>
  );
}

/**
 * Where the second factor stands. There is nothing to configure: the code goes to the
 * account's own address, so it is set up the moment the account exists, and there is
 * no device to lose, re-enrol, or issue backup codes against.
 *
 * Changing the password is the one security action that lives here — see PasswordCard.
 */
function SecurityCard() {
  const { me } = useAuth();

  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <KeyIcon width={18} height={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display text-sm font-medium text-ink">Two-factor authentication</div>
          <p className="mt-0.5 text-sm text-muted">
            {me ? `Signed in as ${me.email}.` : ""} Every sign-in needs a one-time code sent to
            this address.
          </p>
        </div>
        <Badge tone="done">On</Badge>
      </div>

      <div className="mt-4 border-t border-hairline pt-4">
        <p className="text-sm text-muted">
          Codes expire a few minutes after they&apos;re sent and work only once. If one arrives
          that you didn&apos;t ask for, someone knows your password — change it below.
        </p>
      </div>
    </Card>
  );
}

/** Change password. Succeeding here signs out every other session server-side. */
function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [flash, setFlash] = useState<{ ok: boolean; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const tooShort = next.length > 0 && next.length < 12;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFlash(null);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setFlash({ ok: true, msg: "Password changed. Other devices have been signed out." });
    } catch (err) {
      setFlash({ ok: false, msg: err instanceof Error ? err.message : "Failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <KeyIcon width={18} height={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display text-sm font-medium text-ink">Password</div>
          <p className="mt-0.5 text-sm text-muted">
            Changing it signs you out everywhere else. At least 12 characters.
          </p>
        </div>
      </div>

      <form onSubmit={submit} className="mt-4 space-y-3 border-t border-hairline pt-4">
        <Input
          type="password"
          autoComplete="current-password"
          required
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          placeholder="Current password"
        />
        <Input
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          value={next}
          onChange={(e) => setNext(e.target.value)}
          placeholder="New password"
        />
        {tooShort && <p className="text-xs text-faint">At least 12 characters.</p>}
        <Button type="submit" variant="secondary" disabled={busy || !current || next.length < 12}>
          {busy ? "Saving…" : "Change password"}
        </Button>
        {flash && (
          <p className={`text-sm ${flash.ok ? "text-success" : "text-danger"}`}>{flash.msg}</p>
        )}
      </form>
    </Card>
  );
}

function GoogleAccountCard({
  purpose,
  title,
  optional,
  description,
  connectLabel,
}: {
  purpose: "calendar" | "bot";
  title: string;
  optional?: boolean;
  description: React.ReactNode;
  connectLabel: string;
}) {
  const [st, setSt] = useState<GoogleOAuthStatus | null>(null);
  const [flash, setFlash] = useState<{ ok: boolean; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setSt(await api.getGoogleStatus(purpose));
    } catch {
      /* leave as null */
    }
  }

  useEffect(() => {
    refresh();
    // Surface the outcome of the OAuth redirect (only for this card's purpose).
    const q = new URLSearchParams(window.location.search);
    const p = q.get("google");
    const forPurpose = q.get("purpose") ?? "calendar";
    if (p && forPurpose === purpose) {
      if (p === "connected") setFlash({ ok: true, msg: "Connected." });
      else if (p === "bot_mismatch")
        setFlash({
          ok: false,
          msg: "Connected — but this is NOT the account the bot joins meetings with (BOT_GOOGLE_ACCOUNT_EMAIL). Participant lookup won’t work until they match.",
        });
      else setFlash({ ok: false, msg: "Couldn’t connect. Please try again." });
      window.history.replaceState({}, "", window.location.pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function disconnect() {
    setBusy(true);
    try {
      await api.disconnectGoogle(purpose);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <DocIcon width={18} height={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display text-sm font-medium text-ink">
            {title} {optional && <span className="text-faint">(optional)</span>}
          </div>
          <p className="mt-0.5 text-sm text-muted">{description}</p>
        </div>
        <StatusBadge configured={!!st?.connected} />
      </div>

      <div className="mt-4 space-y-3 border-t border-hairline pt-4">
        {st && !st.configured ? (
          <p className="text-sm text-faint">
            Server isn’t set up for this yet — add <span className="font-mono">GOOGLE_OAUTH_CLIENT_ID</span>{" "}
            and <span className="font-mono">GOOGLE_OAUTH_CLIENT_SECRET</span> to the backend env.
          </p>
        ) : st?.connected ? (
          <div className="space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-sm text-ink">
                Connected as <span className="font-medium">{st.email}</span>
              </span>
              <Button variant="ghost" onClick={disconnect} disabled={busy}>
                {busy ? "Disconnecting…" : "Disconnect"}
              </Button>
            </div>
            {purpose === "bot" && !st.has_calendar_scope && (
              <p className="text-sm text-warning">
                This connection was made before calendar auto-join existed, so the bot can’t
                see its meeting invites yet.{" "}
                <button
                  className="font-medium underline underline-offset-2"
                  onClick={() =>
                    (window.location.href = `${BASE}/oauth/google/start?purpose=bot`)
                  }
                >
                  Reconnect once
                </button>{" "}
                to grant calendar access — then invited meetings are joined automatically.
              </p>
            )}
          </div>
        ) : (
          <Button
            variant="primary"
            onClick={() => (window.location.href = `${BASE}/oauth/google/start?purpose=${purpose}`)}
          >
            {connectLabel}
          </Button>
        )}
        {flash && (
          <p className={`text-sm ${flash.ok ? "text-success" : "text-danger"}`}>{flash.msg}</p>
        )}
      </div>
    </Card>
  );
}

function TeamRosterCard() {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    // Inactive rows are kept server-side as "do not re-learn" corrections; hide them here.
    api.listTeam().then((rows) => setMembers(rows.filter((m) => m.active))).catch(() => {});
  }, []);

  async function add() {
    if (!name.trim()) return;
    setAdding(true);
    setErr(null);
    try {
      const m = await api.addTeamMember({ name: name.trim(), email: email.trim() || null });
      setMembers((prev) => [m, ...prev]);
      setName("");
      setEmail("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setAdding(false);
    }
  }

  async function remove(id: string) {
    const prev = members;
    setMembers((p) => p.filter((m) => m.id !== id)); // optimistic
    try {
      await api.removeTeamMember(id);
    } catch {
      setMembers(prev); // roll back on failure
    }
  }

  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <UsersIcon width={18} height={18} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display text-sm font-medium text-ink">Internal team roster</div>
          <p className="mt-0.5 text-sm text-muted">
            Meetings tell your side from the client&apos;s by matching speaker names against this
            roster. It fills itself from verified evidence — teammates whose company email is
            confirmed on a call are added automatically (marked{" "}
            <span className="font-mono text-xs">meet</span>) — so nobody has to be registered up
            front. Add or remove people here to correct or pre-seed it.
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-3 border-t border-hairline pt-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[10rem] flex-1 space-y-1.5">
            <span className="text-xs text-muted">Name (as shown in meetings)</span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder="Anirudh Dandem"
              aria-label="Team member name"
            />
          </div>
          <div className="min-w-[10rem] flex-1 space-y-1.5">
            <span className="text-xs text-muted">Email (optional)</span>
            <Input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder="anirudh@blostem.com"
              aria-label="Team member email"
            />
          </div>
          <Button variant="primary" onClick={add} disabled={adding || !name.trim()}>
            {adding ? "Adding…" : "Add"}
          </Button>
        </div>
        {err && <p className="text-sm text-danger">{err}</p>}

        {members.length === 0 ? (
          <p className="py-3 text-sm text-faint">
            No teammates yet. They&apos;ll appear here automatically as calls are analyzed, or
            you can add people ahead of time.
          </p>
        ) : (
          <ul className="divide-y divide-hairline">
            {members.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent-soft font-mono text-[10px] font-semibold text-accent">
                    {m.name.trim().charAt(0).toUpperCase() || "?"}
                  </span>
                  <div>
                    <div className="flex items-center gap-1.5 text-sm text-ink">
                      {m.name}
                      {m.source !== "manual" && (
                        <span
                          className="rounded border border-hairline px-1 py-px font-mono text-[10px] text-faint"
                          title={
                            m.source === "meet"
                              ? "Email-verified from a meeting's participant list"
                              : "Learned from an internal meeting's attendees"
                          }
                        >
                          {m.source}
                        </span>
                      )}
                    </div>
                    {m.email && <div className="font-mono text-xs text-faint">{m.email}</div>}
                  </div>
                </div>
                <button
                  onClick={() => remove(m.id)}
                  className="rounded-md px-2 py-1 text-xs text-muted transition hover:bg-raised hover:text-danger"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

export default function SettingsPage() {
  const [status, setStatus] = useState<SettingsStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slack, setSlack] = useState("");
  const [email, setEmail] = useState("");
  const [savingNotif, setSavingNotif] = useState(false);
  const [savedNotif, setSavedNotif] = useState(false);
  const [notifError, setNotifError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSettingsStatus()
      .then(setStatus)
      .catch((e) => setError(String(e)));
    api
      .getNotifications()
      .then((n) => {
        setSlack(n.slack_webhook_url ?? "");
        setEmail(n.notification_email ?? "");
      })
      .catch(() => {});
  }, []);

  async function saveNotifications() {
    setSavingNotif(true);
    setSavedNotif(false);
    setNotifError(null);
    try {
      const saved = await api.saveNotifications({
        slack_webhook_url: slack.trim() || null,
        notification_email: email.trim() || null,
      });
      setSlack(saved.slack_webhook_url ?? "");
      setEmail(saved.notification_email ?? "");
      setSavedNotif(true);
      // Reflect the new connected/disconnected state in the badges.
      setStatus((s) =>
        s
          ? {
              ...s,
              notifications: {
                slack_configured: !!saved.slack_webhook_url,
                email_configured: !!saved.notification_email,
              },
            }
          : s,
      );
    } catch (e) {
      setNotifError(String(e));
    } finally {
      setSavingNotif(false);
    }
  }

  return (
    <div className="w-full">
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        sub="Connection status for the services that make MeetingMind work. Values come from the server's environment."
      />

      {error && <ErrorNote>Couldn’t reach the API: {error}</ErrorNote>}

      <div className="mb-8">
        <SectionLabel>Your account</SectionLabel>
        <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SecurityCard />
          <PasswordCard />
        </div>
      </div>

      <div className="mb-8">
        <SectionLabel>Meeting sides — who’s us vs the client</SectionLabel>
        <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <GoogleAccountCard
            purpose="bot"
            title="Bot account — participant identity"
            connectLabel="Connect bot account"
            description={
              <>
                Connect the Google account the bot joins meetings with. After each call it reads
                the real participant list and resolves signed-in attendees to verified emails —
                your domain means your team, everything else the client. No registration needed;
                the bot account should be on your company domain.
              </>
            }
          />
          <TeamRosterCard />
          <GoogleAccountCard
            purpose="calendar"
            title="Google Calendar"
            optional
            connectLabel="Connect Google Calendar"
            description={
              <>
                Connect your calendar and the bot auto-joins <em>every</em> Meet meeting on it —
                no invite needed. Heads-up: when the bot isn&apos;t an invited guest it knocks and
                waits to be let in (it gives up after a few minutes if nobody admits it). Also
                used to detect sides from invites by email domain.
              </>
            }
          />
        </div>
      </div>

      {!status && !error && <Loading label="Loading settings" />}

      {status && (
        <>
          <SectionLabel>Integrations</SectionLabel>
          <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <IntegrationCard
              icon={<RobotIcon width={18} height={18} />}
              title="Meeting bot"
              description="The Google account that joins your meetings and captures audio."
              configured={status.bot.configured}
            >
              <Field label="Display name" value={status.bot.display_name} />
              <Field
                label="Account email"
                value={status.bot.account_email ?? "Not set"}
              />
              <Field
                label="Password saved"
                value={status.bot.password_set ? "Yes" : "No"}
              />
              <Field
                label="Runs headless"
                value={status.bot.headless ? "Yes" : "No"}
              />
              <Field label="Profile folder" value={status.bot.profile_dir} />
            </IntegrationCard>

            <IntegrationCard
              icon={<WaveIcon width={18} height={18} />}
              title="Transcription"
              description="Turns meeting audio into a diarized transcript."
              configured={status.transcription.configured}
            >
              <Field label="Provider" value={status.transcription.provider} />
              <Field label="Model" value={status.transcription.model} />
              <Field label="Language" value={status.transcription.language} />
            </IntegrationCard>

            <IntegrationCard
              icon={<SparkIcon width={18} height={18} />}
              title="Language model"
              description="Writes the minutes, scores the call, and explains your deal insights."
              configured={status.llm.configured}
            >
              <Field label="Provider" value={status.llm.provider} />
              <Field label="Model" value={status.llm.model} />
              <Field label="Embedding model" value={status.llm.embed_model} />
            </IntegrationCard>

            <IntegrationCard
              icon={<KeyIcon width={18} height={18} />}
              title="Realtime audio"
              description="Streams the bot's captured audio for live transcription."
              configured={status.livekit.configured}
            >
              <Field label="URL" value={status.livekit.url} />
            </IntegrationCard>

            <IntegrationCard
              icon={<DocIcon width={18} height={18} />}
              title="Meet transcripts API"
              description="Optional: pulls Google Meet's own transcript after a call, no bot needed."
              configured={status.meet_api.configured}
            >
              <Field
                label="Impersonate subject"
                value={status.meet_api.impersonate_subject ?? "Not set"}
              />
            </IntegrationCard>
          </div>

          <div className="mt-8">
            <SectionLabel>Alerts</SectionLabel>
            <Card className="mt-3 p-5">
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
                  <BellIcon width={18} height={18} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="font-display text-sm font-medium text-ink">
                    Notifications
                  </div>
                  <p className="mt-0.5 text-sm text-muted">
                    Get told the moment minutes are ready or the bot can’t join.
                  </p>
                </div>
              </div>
              <div className="mt-4 space-y-4 border-t border-hairline pt-4">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-ink">Slack</span>
                    {status.notifications.slack_configured ? (
                      <Badge tone="done">Connected</Badge>
                    ) : (
                      <Badge tone="neutral">Not configured</Badge>
                    )}
                  </div>
                  <Input
                    value={slack}
                    onChange={(e) => {
                      setSlack(e.target.value);
                      setSavedNotif(false);
                    }}
                    placeholder="https://hooks.slack.com/…"
                    aria-label="Slack webhook URL"
                  />
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-ink">Email</span>
                    {status.notifications.email_configured ? (
                      <Badge tone="done">Connected</Badge>
                    ) : (
                      <Badge tone="neutral">Not configured</Badge>
                    )}
                  </div>
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      setSavedNotif(false);
                    }}
                    placeholder="you@company.com"
                    aria-label="Notification email"
                  />
                </div>
                {notifError && <p className="text-sm text-danger">{notifError}</p>}
                <div className="flex items-center justify-end gap-3">
                  {savedNotif && <span className="text-xs text-success">Saved</span>}
                  <Button variant="primary" onClick={saveNotifications} disabled={savingNotif}>
                    {savingNotif ? "Saving…" : "Save notifications"}
                  </Button>
                </div>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
