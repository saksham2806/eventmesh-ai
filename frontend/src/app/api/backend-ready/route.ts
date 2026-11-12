
import { NextRequest, NextResponse } from "next/server";
import { getTrustedBackendOrigin } from "@/lib/trustedBackend";

function result(ready: boolean, reason: string) {
  return NextResponse.json(
    { ready, reason },
    {
      status: ready ? 200 : 503,
      headers: {
        "Cache-Control": "no-store",
      },
    }
  );
}

export async function GET(request: NextRequest) {
  const backendUrl = getTrustedBackendOrigin(request);

  if (!backendUrl) {
    return result(false, "backend_url_not_configured_or_trusted");
  }

  try {
    const response = await fetch(`${backendUrl}/health`, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      return result(
        false,
        `backend_http_${response.status}`
      );
    }

    const contentType =
      response.headers.get("content-type") ?? "";

    if (!contentType.includes("application/json")) {
      return result(false, "unexpected_health_response");
    }

    const data: unknown = await response.json();

    const healthy =
      typeof data === "object" &&
      data !== null &&
      "status" in data &&
      data.status === "healthy";

    if (!healthy) {
      return result(false, "backend_not_healthy");
    }

    return result(true, "healthy");
  } catch (error) {
    console.warn(
      "[backend-ready] Health check failed:",
      error instanceof Error ? error.name : "UnknownError"
    );

    return result(false, "backend_timeout_or_network_error");
  }
}
