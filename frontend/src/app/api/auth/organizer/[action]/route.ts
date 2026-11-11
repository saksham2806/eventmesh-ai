
import { NextRequest, NextResponse } from "next/server";
import { getTrustedBackendOrigin } from "@/lib/trustedBackend";

const COOKIE = "eventmesh_organizer_session";
const SESSION_SECONDS = 12 * 60 * 60;

type Context = {
  params: Promise<{ action: string }>;
};

function reply(detail: string, status: number) {
  return NextResponse.json(
    { detail },
    {
      status,
      headers: { "Cache-Control": "no-store" },
    }
  );
}


function localBackend(request: NextRequest): string | null {
  return getTrustedBackendOrigin(request);
}



function sessionHeaders(
  request: NextRequest
): Record<string, string> {
  const token = request.cookies.get(COOKIE)?.value;

  if (!token) {
    return {};
  }

  return {
    Cookie: `${COOKIE}=${encodeURIComponent(token)}`,
  };
}


// GET /api/auth/organizer/me
export async function GET(
  request: NextRequest,
  context: Context
) {
  const { action } = await context.params;
  const backend = localBackend(request);

  if (!backend) return reply("Local auth unavailable", 403);
  if (action !== "me") return reply("Not found", 404);

  try {
    const response = await fetch(
      `${backend}/auth/organizer/me`,
      {
        headers: sessionHeaders(request),
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      }
    );

    if (response.status === 401) {
      return reply("Authentication required", 401);
    }

    if (!response.ok) {
      return reply("Authentication service unavailable", 502);
    }

    return NextResponse.json(await response.json(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return reply("Authentication service unavailable", 502);
  }
}

// POST /api/auth/organizer/login
// POST /api/auth/organizer/logout
export async function POST(
  request: NextRequest,
  context: Context
) {
  const { action } = await context.params;
  const backend = localBackend(request);

  if (!backend) return reply("Local auth unavailable", 403);

  if (request.headers.get("origin") !== request.nextUrl.origin) {
    return reply("Invalid request origin", 403);
  }

  if (action !== "login" && action !== "logout") {
    return reply("Not found", 404);
  }

  try {
    if (action === "logout") {
      const response = await fetch(
        `${backend}/auth/organizer/logout`,
        {
          method: "POST",
          headers: sessionHeaders(request),
          cache: "no-store",
          signal: AbortSignal.timeout(10000),
        }
      );

      if (!response.ok) {
        return reply("Logout service unavailable", 502);
      }

      const result = NextResponse.json(
        { authenticated: false },
        { headers: { "Cache-Control": "no-store" } }
      );

      result.cookies.set(COOKIE, "", {
        httpOnly: true,
        secure:
  process.env.NODE_ENV === "production" ||
  request.nextUrl.protocol === "https:",
        sameSite: "lax",
        path: "/",
        maxAge: 0,
      });

      return result;
    }

    if (
      !request.headers.get("content-type")
        ?.startsWith("application/json")
    ) {
      return reply("Expected JSON", 415);
    }

    const raw = await request.text();

    if (raw.length > 2048) {
      return reply("Request too large", 413);
    }

    let credentials: unknown;

    try {
      credentials = JSON.parse(raw);
    } catch {
      return reply("Invalid JSON", 400);
    }

    if (
      !credentials ||
      typeof credentials !== "object" ||
      Array.isArray(credentials)
    ) {
      return reply("Invalid login request", 400);
    }

    const { email, password } = credentials as Record<
      string,
      unknown
    >;

    if (
      typeof email !== "string" ||
      typeof password !== "string" ||
      email.length > 254 ||
      password.length > 128
    ) {
      return reply("Invalid login request", 400);
    }

    const response = await fetch(
      `${backend}/auth/organizer/login`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
        cache: "no-store",
        signal: AbortSignal.timeout(15000),
      }
    );

    if (response.status === 401) {
      return reply("Invalid email or password", 401);
    }

    if (!response.ok) {
      return reply("Login service unavailable", 502);
    }

    const setCookie = response.headers.get("set-cookie");
    const match = setCookie?.match(
      /^eventmesh_organizer_session=([^;]+)/
    );

    if (!match) {
      return reply("Session cookie unavailable", 502);
    }

    const result = NextResponse.json(
      { authenticated: true },
      { headers: { "Cache-Control": "no-store" } }
    );

    result.cookies.set(COOKIE, match[1], {
      httpOnly: true,
      secure: request.nextUrl.protocol === "https:",
      sameSite: "lax",
      path: "/",
      maxAge: SESSION_SECONDS,
    });

    return result;
  } catch {
    return reply("Authentication service unavailable", 502);
  }
}
