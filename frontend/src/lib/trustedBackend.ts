
import type { NextRequest } from "next/server";

export function getTrustedBackendOrigin(
  request: NextRequest
): string | null {
  const production = process.env.NODE_ENV === "production";

  // Never expose local-development routes on another host.
  if (
    !production &&
    !["localhost", "127.0.0.1"].includes(
      request.nextUrl.hostname
    )
  ) {
    return null;
  }

  const configured =
    process.env.EVENTMESH_BACKEND_URL ||
    (production ? "" : "http://127.0.0.1:8000");

  if (!configured) return null;

  try {
    const url = new URL(configured);

    // Accept only a clean, fixed backend origin.
    if (
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash
    ) {
      return null;
    }

    if (production) {
      // Production requires an explicitly configured HTTPS backend.
      if (
        url.protocol !== "https:" ||
        !url.hostname.includes(".") ||
        ["localhost", "127.0.0.1"].includes(
          url.hostname
        ) ||
        (url.port !== "" && url.port !== "443")
      ) {
        return null;
      }
    } else {
      // Preserve your existing local development restrictions.
      if (
        url.protocol !== "http:" ||
        !["localhost", "127.0.0.1"].includes(
          url.hostname
        ) ||
        url.port !== "8000"
      ) {
        return null;
      }
    }

    return url.origin;
  } catch {
    return null;
  }
}
