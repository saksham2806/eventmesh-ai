
import { NextRequest } from "next/server";
import { getTrustedBackendOrigin } from "@/lib/trustedBackend";

export async function POST(request: NextRequest) {
  // Keep public signup disabled until production
  // registration safeguards are implemented.
  if (process.env.NODE_ENV === "production") {
    return Response.json(
      { detail: "Public registration is not enabled" },
      {
        status: 403,
        headers: { "Cache-Control": "no-store" },
      }
    );
  }

  const backend = getTrustedBackendOrigin(request);

  if (!backend) {
    return Response.json(
      { detail: "Invalid backend configuration" },
      {
        status: 503,
        headers: { "Cache-Control": "no-store" },
      }
    );
  }

  const body = await request.text();

  if (body.length > 4096) {
    return Response.json(
      { detail: "Registration request too large" },
      {
        status: 413,
        headers: { "Cache-Control": "no-store" },
      }
    );
  }

  try {
    const upstream = await fetch(
      `${backend}/auth/organizer/register`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(15000),
      }
    );

    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      { detail: "Registration server unavailable" },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      }
    );
  }
}
