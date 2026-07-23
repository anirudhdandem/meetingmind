"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { KeyRound, MailCheck } from "lucide-react";

import { BrandLockup } from "@/components/nav";
import { LOGIN_ROUTE } from "@/components/shell";
import { Button, Card, ErrorNote, Input } from "@/components/ui";
import { api } from "@/lib/api";

const MIN_PASSWORD_LEN = 12;

type Step = "email" | "reset";

/**
 * Recover a forgotten password with a code mailed to the account's address.
 *
 * Unlike login and signup, nothing here depends on a session cookie — the code is held
 * against the user row, so the address is carried in each request. That is what lets
 * someone request the code on a phone and finish on a laptop.
 */
export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [resendAfter, setResendAfter] = useState(0);

  return (
    <div className="flex min-h-screen items-center justify-center px-5 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <BrandLockup />
        </div>
        {step === "email" ? (
          <EmailStep
            email={email}
            setEmail={setEmail}
            onDone={(seconds) => {
              setResendAfter(seconds);
              setStep("reset");
            }}
          />
        ) : (
          <ResetStep
            email={email}
            resendAfter={resendAfter}
            onDone={() => router.replace(LOGIN_ROUTE)}
          />
        )}
      </div>
    </div>
  );
}

function EmailStep({
  email,
  setEmail,
  onDone,
}: {
  email: string;
  setEmail: (v: string) => void;
  onDone: (resendAfter: number) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.forgotPassword(email.trim());
      onDone(res.resend_after_seconds);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send a reset code");
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <header className="mb-5 flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <KeyRound size={18} />
        </span>
        <div>
          <h1 className="font-display text-base font-medium text-ink">Reset your password</h1>
          <p className="text-sm text-muted">We&apos;ll email you a code to set a new one.</p>
        </div>
      </header>

      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="email" className="text-xs text-muted">
            Work email
          </label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@blostem.com"
          />
        </div>

        {error && <ErrorNote>{error}</ErrorNote>}

        <Button type="submit" variant="primary" className="w-full" disabled={busy}>
          {busy ? "Sending code…" : "Send reset code"}
        </Button>
      </form>

      <p className="mt-5 border-t border-hairline pt-4 text-center text-xs text-faint">
        Remembered it?{" "}
        <Link href={LOGIN_ROUTE} className="text-muted underline underline-offset-2 hover:text-ink">
          Sign in
        </Link>
      </p>
    </Card>
  );
}

function ResetStep({
  email,
  resendAfter,
  onDone,
}: {
  email: string;
  resendAfter: number;
  onDone: () => void;
}) {
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(resendAfter);

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LEN;

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (tooShort) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await api.resetPassword(email, code.trim(), password);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reset your password");
      setCode("");
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await api.forgotPassword(email);
      setCooldown(res.resend_after_seconds);
      setNote("If that address has an account, a new code is on its way.");
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
          {/* Deliberately conditional: the API never confirms the address is registered. */}
          <p className="truncate text-sm text-muted">
            If {email} has an account, a code is on its way.
          </p>
        </div>
      </header>

      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="code" className="text-xs text-muted">
            Reset code
          </label>
          <Input
            id="code"
            autoComplete="one-time-code"
            inputMode="numeric"
            autoFocus
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="123456"
            className="text-center font-mono text-lg tracking-[0.3em]"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="password" className="text-xs text-muted">
            New password
          </label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p className={`text-xs ${tooShort ? "text-danger" : "text-faint"}`}>
            At least {MIN_PASSWORD_LEN} characters.
          </p>
        </div>

        {error && <ErrorNote>{error}</ErrorNote>}
        {note && <p className="text-sm text-success">{note}</p>}

        <Button type="submit" variant="primary" className="w-full" disabled={busy || tooShort}>
          {busy ? "Resetting…" : "Set new password"}
        </Button>

        <p className="text-center text-xs text-faint">
          Resetting signs you out on every device.
        </p>

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
