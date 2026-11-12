
"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { waitForBackend } from "../lib/waitForBackend";

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
        // Wait for FastAPI to become available.
        await waitForBackend(controller.signal);

        if (controller.signal.aborted) return;

        // Retry temporary authentication failures.
        for (let attempt = 0; attempt < 4; attempt++) {
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

            // User is not logged in.
            if (response.status === 401) {
              window.location.replace("/login");
              return;
            }

            // Authentication successful.
            if (response.ok) {
              setState("authenticated");
              return;
            }

            // Only retry temporary server errors.
            if (
              ![429, 500, 502, 503, 504].includes(
                response.status
              )
            ) {
              setState("error");
              return;
            }
          } catch {
            if (controller.signal.aborted) return;
          }

          // Wait 4 seconds before retrying.
          if (attempt < 3) {
            await new Promise<void>((resolve) => {
              setTimeout(resolve, 4000);
            });
          }

          if (controller.signal.aborted) return;
        }

        setState("error");
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
        <h2>Connecting to EventMesh AI...</h2>
        <p>
          The server may need a moment to start.
          Please keep this page open.
        </p>
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
