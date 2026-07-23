"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Lock } from "lucide-react";

import { CodeStep } from "@/components/code-step";
import { BrandLockup } from "@/components/nav";
import { FORGOT_ROUTE, SIGNUP_ROUTE } from "@/components/shell";
import { Button, Card, ErrorNote, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Step = "password" | "code";

export default function LoginPage() {
  const { status, refresh } = useAuth();
  const router = useRouter();

  // A page reload mid-handshake leaves a live pending session; resume at the code
  // step rather than making the user retype a password the server already accepted.
  const [step, setStep] = useState<Step>(status === "pending" ? "code" : "password");
  const [sent, setSent] = useState<{ email: string; resendAfter: number } | null>(null);

  useEffect(() => {
    if (status === "pending") setStep("code");
  }, [status]);

  return (
    <div className="flex min-h-screen items-center justify-center px-5 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <BrandLockup />
        </div>
        {step === "password" ? (
          <PasswordStep
            onDone={(email, resendAfter) => {
              setSent({ email, resendAfter });
              setStep("code");
            }}
          />
        ) : (
          <CodeStep
            email={sent?.email}
            // After a reload we never saw the login response, so no cooldown is known.
            // Offer "Resend" immediately and let the server refuse if it's too soon.
            resendAfter={sent?.resendAfter ?? 0}
            onDone={async () => {
              await refresh();
              router.replace("/");
            }}
            onRestart={() => setStep("password")}
          />
        )}
      </div>
    </div>
  );
}

function PasswordStep({ onDone }: { onDone: (email: string, resendAfter: number) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(email.trim(), password);
      onDone(res.email, res.resend_after_seconds);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <header className="mb-5 flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <Lock size={18} />
        </span>
        <div>
          <h1 className="font-display text-base font-medium text-ink">Sign in</h1>
          <p className="text-sm text-muted">We&apos;ll email a code to confirm it&apos;s you.</p>
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
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between">
            <label htmlFor="password" className="text-xs text-muted">
              Password
            </label>
            <Link
              href={FORGOT_ROUTE}
              className="text-xs text-faint underline underline-offset-2 hover:text-ink"
            >
              Forgot?
            </Link>
          </div>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && <ErrorNote>{error}</ErrorNote>}

        <Button type="submit" variant="primary" className="w-full" disabled={busy}>
          {busy ? "Sending code…" : "Continue"}
        </Button>
      </form>

      <p className="mt-5 border-t border-hairline pt-4 text-center text-xs text-faint">
        No account yet?{" "}
        <Link href={SIGNUP_ROUTE} className="text-muted underline underline-offset-2 hover:text-ink">
          Create one
        </Link>
      </p>
    </Card>
  );
}
