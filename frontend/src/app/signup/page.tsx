"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { UserPlus } from "lucide-react";

import { CodeStep } from "@/components/code-step";
import { Brand } from "@/components/nav";
import { LOGIN_ROUTE } from "@/components/shell";
import { Button, Card, ErrorNote, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const MIN_PASSWORD_LEN = 12;

type Step = "details" | "code";

export default function SignupPage() {
  const { status, refresh } = useAuth();
  const router = useRouter();

  // Signing up leaves the same pending session a login does, so a reload resumes at
  // the code step instead of trying to create the account a second time.
  const [step, setStep] = useState<Step>(status === "pending" ? "code" : "details");
  const [sent, setSent] = useState<{ email: string; resendAfter: number } | null>(null);

  useEffect(() => {
    if (status === "pending") setStep("code");
  }, [status]);

  return (
    <div className="flex min-h-screen items-center justify-center px-5 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Brand />
        </div>
        {step === "details" ? (
          <DetailsStep
            onDone={(email, resendAfter) => {
              setSent({ email, resendAfter });
              setStep("code");
            }}
          />
        ) : (
          <CodeStep
            email={sent?.email}
            resendAfter={sent?.resendAfter ?? 0}
            onDone={async () => {
              await refresh();
              router.replace("/");
            }}
            onRestart={() => setStep("details")}
          />
        )}
      </div>
    </div>
  );
}

function DetailsStep({ onDone }: { onDone: (email: string, resendAfter: number) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Mirrors the server's floor. The check here is a courtesy — the API enforces it.
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LEN;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (tooShort) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.signup(email.trim(), name.trim(), password);
      onDone(res.email, res.resend_after_seconds);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create your account");
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <header className="mb-5 flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <UserPlus size={18} />
        </span>
        <div>
          <h1 className="font-display text-base font-medium text-ink">Create your account</h1>
          <p className="text-sm text-muted">MeetingMind is restricted to your team&apos;s domain.</p>
        </div>
      </header>

      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="name" className="text-xs text-muted">
            Full name
          </label>
          <Input
            id="name"
            autoComplete="name"
            required
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ada Lovelace"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="email" className="text-xs text-muted">
            Work email
          </label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@blostem.com"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="password" className="text-xs text-muted">
            Password
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

        <Button type="submit" variant="primary" className="w-full" disabled={busy || tooShort}>
          {busy ? "Sending code…" : "Create account"}
        </Button>
      </form>

      <p className="mt-5 border-t border-hairline pt-4 text-center text-xs text-faint">
        Already have an account?{" "}
        <Link href={LOGIN_ROUTE} className="text-muted underline underline-offset-2 hover:text-ink">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
