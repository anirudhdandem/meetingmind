"use client";

import { useEffect, useState } from "react";
import { MailCheck } from "lucide-react";

import { Button, Card, ErrorNote, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * Second step of both signup and login: type the code we just mailed.
 *
 * Shared rather than duplicated because the server genuinely cannot tell the two apart
 * — `POST /auth/verify` redeems the code for whichever pending session holds it, and
 * a signup's code and a login's code are the same object.
 *
 * A reload lands here with no props (the pending session survives in the cookie), so
 * the address is read from `/auth/me` rather than remembered by the page that mailed it.
 */
export function CodeStep({
  email,
  resendAfter,
  onDone,
  onRestart,
}: {
  /** Where the code was sent. Falls back to the session's own address after a reload. */
  email?: string;
  /** Seconds before "Resend" is offered. The server rejects anything earlier. */
  resendAfter: number;
  onDone: () => Promise<void>;
  /** The pending session died; send the user back to the password form. */
  onRestart: () => void;
}) {
  const { me, refresh } = useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(resendAfter);

  const sentTo = email ?? me?.email;

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await api.verifyCode(code.trim());
      await onDone();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Verification failed";
      setBusy(false);
      setCode("");
      // Too many wrong codes destroys the pending session server-side; re-sync so the
      // form falls back to the password step instead of posting into a dead session.
      if (/sign in again/i.test(msg)) {
        await refresh();
        onRestart();
      }
      setError(msg);
    }
  }

  async function resend() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await api.resendCode();
      setCooldown(res.resend_after_seconds);
      setNote("A new code is on its way. The old one no longer works.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't resend the code");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <header className="mb-5 flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <MailCheck size={18} />
        </span>
        <div className="min-w-0">
          <h1 className="font-display text-base font-medium text-ink">Check your email</h1>
          <p className="truncate text-sm text-muted">
            {sentTo ? `We sent a code to ${sentTo}.` : "We sent you a sign-in code."}
          </p>
        </div>
      </header>

      <form onSubmit={submit} className="space-y-4">
        <Input
          // `one-time-code` lets browsers and iOS offer the code from the keyboard.
          autoComplete="one-time-code"
          inputMode="numeric"
          autoFocus
          required
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="123456"
          className="text-center font-mono text-lg tracking-[0.3em]"
        />

        {error && <ErrorNote>{error}</ErrorNote>}
        {note && <p className="text-sm text-success">{note}</p>}

        <Button type="submit" variant="primary" className="w-full" disabled={busy}>
          {busy ? "Verifying…" : "Verify"}
        </Button>

        <div className="text-center text-xs text-faint">
          {cooldown > 0 ? (
            <span>Didn&apos;t get it? You can resend in {cooldown}s.</span>
          ) : (
            <button
              type="button"
              onClick={resend}
              disabled={busy}
              className="text-muted underline underline-offset-2 hover:text-ink disabled:opacity-50"
            >
              Resend the code
            </button>
          )}
        </div>
      </form>
    </Card>
  );
}
