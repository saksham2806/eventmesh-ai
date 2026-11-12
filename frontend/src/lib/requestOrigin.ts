import type { NextRequest } from "next/server";

/**
 * Compare browser POST Origin to our exact, configured public origin.
 * Behind Render's reverse proxy, request.nextUrl.origin may reflect an
 * internal service URL, so it is not a reliable public-origin reference.
 * Missing or unexpected origins fail closed.
 */
export function isTrustedRequestOrigin(request: NextRequest): boolean {
  const supplied = request.headers.get("origin");
  if (!supplied) return false;

  if (process.env.NODE_ENV !== "production") {
    return supplied === request.nextUrl.origin;
  }

  const configured = process.env.EVENTMESH_PUBLIC_FRONTEND_URL;
  if (!configured) return false;

  try {
    const expected = new URL(configured);
    if (
      expected.protocol !== "https:" ||
      expected.username ||
      expected.password ||
      expected.pathname !== "/" ||
      expected.search ||
      expected.hash
    ) {
      return false;
    }

    return supplied === expected.origin;
  } catch {
    return false;
  }
}
