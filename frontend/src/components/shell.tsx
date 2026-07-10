"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Sidebar, MobileBar, Topbar } from "@/components/nav";
import { Loading } from "@/components/ui";
import { useAuth, type AuthStatus } from "@/lib/auth";

export const LOGIN_ROUTE = "/login";
export const SIGNUP_ROUTE = "/signup";
export const FORGOT_ROUTE = "/forgot-password";

// Pages that render their own frame and must never be wrapped in the app nav.
const BARE_ROUTES = new Set<string>([LOGIN_ROUTE, SIGNUP_ROUTE, FORGOT_ROUTE]);

/** Where a given auth status is allowed to be. `null` = stay put. */
function destinationFor(status: AuthStatus, pathname: string): string | null {
  switch (status) {
    case "loading":
      return null;
    // Both auth pages own their code step, and "pending" is reachable from either —
    // a half-finished signup must not be bounced to /login, where the code it is
    // waiting for would look like it belongs to an account that doesn't exist yet.
    case "anon":
    case "pending":
      return BARE_ROUTES.has(pathname) ? null : LOGIN_ROUTE;
    case "ready":
      // Nothing left to do on the auth pages — bounce back into the app.
      return BARE_ROUTES.has(pathname) ? "/" : null;
  }
}

/**
 * Wraps every page: resolves auth state, redirects to wherever the user actually
 * belongs, and only then renders the nav chrome around the page.
 *
 * Content is never rendered before `status` resolves, so a signed-out visitor never
 * sees a flash of the dashboard.
 */
export function Shell({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const destination = destinationFor(status, pathname);

  useEffect(() => {
    if (destination) router.replace(destination);
  }, [destination, router]);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loading label="Signing you in…" />
      </div>
    );
  }

  // A redirect is queued; render nothing rather than the wrong page for a frame.
  if (destination) return null;

  if (BARE_ROUTES.has(pathname)) {
    return <main className="min-h-screen">{children}</main>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <MobileBar />
        <main className="flex-1 px-5 py-7 md:px-10 md:py-9">{children}</main>
      </div>
    </div>
  );
}
