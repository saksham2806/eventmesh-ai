
"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export default function OrganizerAuthGate({
  children,
}: {
  children: ReactNode;
}) {
  const [state, setState] = useState<
    "checking" | "authenticated" | "error"
  >("checking");

  const [loggingOut, setLoggingOut] = useState(false);

  const [headerTarget, setHeaderTarget] =
    useState<Element | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function checkSession() {
      try {
        const response = await fetch(
          "/api/auth/organizer/me",
          {
            credentials: "same-origin",
            cache: "no-store",
            signal: controller.signal,
          }
        );

        if (controller.signal.aborted) return;

        if (response.status === 401) {
          window.location.replace("/login");
          return;
        }

        if (!response.ok) {
          throw new Error("Session check failed");
        }

        setState("authenticated");
      } catch {
        if (!controller.signal.aborted) {
          setState("error");
        }
      }
    }

    void checkSession();

    return () => controller.abort();
  }, []);

  // Find the existing dashboard header
  useEffect(() => {
    if (state !== "authenticated") return;

    const target = document.querySelector(".top-actions");
    setHeaderTarget(target);
  }, [state]);

  async function logout() {
    if (loggingOut) return;

    setLoggingOut(true);

    try {
      const response = await fetch(
        "/api/auth/organizer/logout",
        {
          method: "POST",
          credentials: "same-origin",
        }
      );

      if (!response.ok) {
        throw new Error("Logout failed");
      }

      window.location.replace("/login");
    } catch {
      alert("Could not sign out. Please try again.");
      setLoggingOut(false);
    }
  }

  if (state === "checking") {
    return (
      <main style={{ padding: 48, textAlign: "center" }}>
        Checking organizer session...
      </main>
    );
  }

  if (state === "error") {
    return (
      <main style={{ padding: 48, textAlign: "center" }}>
        <h2>Authentication service unavailable</h2>
        <p>Please check that FastAPI is running.</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
        >
          Retry
        </button>
      </main>
    );
  }

  const signOutButton = (
    <button
      type="button"
      className="organizer-signout"
      onClick={() => void logout()}
      disabled={loggingOut}
      aria-label="Sign out of organizer account"
    >
      {loggingOut ? "Signing out..." : "Sign Out"}
    </button>
  );

  return (
    <>
      {children}

      {headerTarget
        ? createPortal(signOutButton, headerTarget)
        : (
          <div className="organizer-signout-fallback">
            {signOutButton}
          </div>
        )}
    </>
  );
}
