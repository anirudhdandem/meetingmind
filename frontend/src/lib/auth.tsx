"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { ApiError, api, type Me } from "@/lib/api";

/**
 * Client-side auth state, derived from a single `GET /auth/me` call.
 *
 * The session cookie is httpOnly and set by the API on its own origin, so the browser
 * can neither read it nor reason about it. Next.js middleware is therefore NOT used to
 * gate routes: it would have to guess from cookie *presence*, which is wrong the moment
 * the API is deployed on a domain that doesn't share a parent with the frontend. Asking
 * the server who you are is the only answer that's correct in every deployment.
 *
 * This guard is a UX affordance, not a security boundary. The real enforcement is
 * `require_user` on the API — every protected route 401s or 403s regardless of what
 * the browser believes.
 */
export type AuthStatus =
  | "loading" // the /auth/me round-trip is in flight
  | "anon" // no session: show the login form
  | "pending" // password accepted, emailed code still owed
  | "ready"; // password + code complete

interface AuthValue {
  status: AuthStatus;
  me: Me | null;
  /** Re-reads /auth/me. Call after any step that changes session state. */
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

function classify(me: Me): AuthStatus {
  return me.otp_pending ? "pending" : "ready";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<Me | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.me();
      setMe(next);
      setStatus(classify(next));
    } catch (e) {
      // 401 is the expected "not signed in" answer. Anything else (API down, CORS
      // misconfigured) also means we can't prove a session, so it's treated the same
      // — the login page will surface the real error when the user tries to sign in.
      if (!(e instanceof ApiError) || e.status !== 401) {
        console.error("auth: /auth/me failed", e);
      }
      setMe(null);
      setStatus("anon");
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      // Even if the request failed, drop local state — the cookie may already be gone.
      setMe(null);
      setStatus("anon");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ status, me, refresh, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
