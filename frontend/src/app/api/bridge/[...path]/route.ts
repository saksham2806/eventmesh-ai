
import { NextRequest, NextResponse } from "next/server";
import {
  CHECKOUT_COOKIE,
  signCheckoutSession,
} from "@/lib/sandboxSession";
import { getTrustedBackendOrigin } from "@/lib/trustedBackend";

// Organizer login session cookie.
const ORGANIZER_COOKIE = "eventmesh_organizer_session";

// Allowed GET requests.
const getRoutes = [
  /^health$/,
  /^events$/,

  /^refunds\/eligibility\/[a-zA-Z0-9-]+$/,

  /^paypal\/webhooks\/events$/,
  /^events\/\d+\/(sessions|rooms|ticket-types)$/,
  /^checkout\/reservations\/[a-zA-Z0-9-]+\/(preview|status)$/,
  /^ai\/multi-recovery-proposals\/[a-f0-9]+$/,
];

// Allowed POST requests.
const postRoutes = [
  /^events$/,
  /^events\/\d+\/(sessions|rooms|ticket-types|reservations)$/,
  /^checkout\/reservations\/[a-zA-Z0-9-]+\/paypal-order$/,
  /^ai\/events\/\d+\/sessions\/\d+\/(multi-incident-preview|auto-incident-preview|multi-recovery-proposals)$/,
  /^ai\/multi-recovery-proposals\/[a-f0-9]+\/approve$/,
];

function errorResponse(detail: string, status: number) {
  return NextResponse.json(
    { detail },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
      },
    }
  );
}

// Only use the local FastAPI backend.


// Check the organizer session using FastAPI.
async function requireOrganizerSession(
  request: NextRequest,
  backendOrigin: string
): Promise<NextResponse | null> {
  const token = request.cookies.get(ORGANIZER_COOKIE)?.value;

  if (!token || token.length > 512) {
    return errorResponse("Organizer login required", 401);
  }

  try {
    const response = await fetch(
      `${backendOrigin}/auth/organizer/me`,
      {
        method: "GET",
        headers: {
          Cookie: `${ORGANIZER_COOKIE}=${encodeURIComponent(token)}`,
        },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(
          process.env.NODE_ENV === "production" ? 90000 : 10000
        ),
      }
    );

    if (response.status === 401 || response.status === 403) {
      return errorResponse(
        "Organizer session invalid or expired",
        401
      );
    }

    if (!response.ok) {
      return errorResponse(
        "Authentication service unavailable",
        502
      );
    }

    // Returning null means authentication succeeded.
    return null;
  } catch {
    return errorResponse(
      "Could not verify organizer session",
      502
    );
  }
}

// Main API bridge.
async function bridge(
  request: NextRequest,
  path: string[],
  method: "GET" | "POST"
) {
  // Keep this bridge local-only.

  // Production stays disabled until explicitly approved.
  if (
    process.env.NODE_ENV === "production" &&
    process.env.EVENTMESH_ENABLE_PRODUCTION_BRIDGE !== "true"
  ) {
    return errorResponse(
      "Production API bridge not enabled",
      403
    );
  }

  // Local development may only run on localhost.
  if (
    process.env.NODE_ENV !== "production" &&
    !["localhost", "127.0.0.1"].includes(
      request.nextUrl.hostname
    )
  ) {
    return errorResponse(
      "Local development bridge disabled",
      403
    );
  }

  const route = path.join("/");

  // Allow only explicitly approved endpoints.
  const allowedRoutes =
    method === "GET" ? getRoutes : postRoutes;

  if (!allowedRoutes.some((pattern) => pattern.test(route))) {
    return errorResponse(
      "Endpoint not available through the dashboard",
      404
    );
  }

  // Prevent cross-origin POST requests.
  if (
    method === "POST" &&
    request.headers.get("origin") !== request.nextUrl.origin
  ) {
    return errorResponse("Invalid request origin", 403);
  }

  const backendOrigin = getTrustedBackendOrigin(request);

  if (!backendOrigin) {
    return errorResponse(
      "Invalid local backend configuration",
      503
    );
  }

  // SECURITY: Check login before forwarding the request.
  const authError = await requireOrganizerSession(
    request,
    backendOrigin
  );

  if (authError) {
    return authError;
  }

  const organizerToken = request.cookies.get(
  ORGANIZER_COOKIE
)?.value;

if (!organizerToken) {
  return errorResponse("Organizer login required", 401);
}

  // Keep the organizer key on the server only.
  const key = process.env.EVENTMESH_ORGANIZER_KEY;

  if (!key) {
    return errorResponse(
      "Configure EVENTMESH_ORGANIZER_KEY in frontend/.env.local",
      503
    );
  }

  let body: string | undefined;

  if (method === "POST") {
    try {
      body = await request.text();
    } catch {
      return errorResponse("Could not read request body", 400);
    }

    if (body.length > 16000) {
      return errorResponse("Request too large", 413);
    }
  }

  try {

    // Forward the authorized request to FastAPI.
    const upstream = await fetch(
      `${backendOrigin}/${route}`,
      {
        method,
        headers: {
          ...(body !== undefined
            ? { "content-type": "application/json" }
            : {}),
          "x-organizer-key": key,
          Cookie: `${ORGANIZER_COOKIE}=${encodeURIComponent(
            organizerToken
          )}`,
        },
        body,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(
          process.env.NODE_ENV === "production" ? 90000 : 28000
        ),
      }
    );


    const value = await upstream.text();

    const result = new NextResponse(value, {
      status: upstream.status,
      headers: {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
      },
    });

    // Preserve the existing PayPal Sandbox checkout flow.
    // Bind a successful order to a signed checkout cookie.
    if (
      method === "POST" &&
      upstream.ok &&
      /^checkout\/reservations\/[a-zA-Z0-9-]+\/paypal-order$/.test(
        route
      )
    ) {
      try {
        const data = JSON.parse(value) as Record<
          string,
          unknown
        >;

        const orderId = [
          data.paypal_order_id,
          data.order_id,
          data.id,
        ].find(
          (item): item is string =>
            typeof item === "string" &&
            /^[A-Za-z0-9-]{1,100}$/.test(item)
        );

        const reservationId = path[2];

        if (orderId && reservationId) {
          result.cookies.set(
            CHECKOUT_COOKIE,
            signCheckoutSession(
              reservationId,
              orderId,
              key
            ),
            {
              httpOnly: true,
              sameSite: "lax",
              secure: request.nextUrl.protocol === "https:",
              path: "/",
              maxAge: 40 * 60,
            }
          );
        }
      } catch {
        // Do not create a checkout session
        // from an invalid PayPal response.
      }
    }

    return result;
  } catch {
    return errorResponse(
      "Could not contact FastAPI. Check that the backend is running.",
      502
    );
  }
}

// Handle GET requests.
export async function GET(
  request: NextRequest,
  context: {
    params: Promise<{ path: string[] }>;
  }
) {
  return bridge(
    request,
    (await context.params).path,
    "GET"
  );
}

// Handle POST requests.
export async function POST(
  request: NextRequest,
  context: {
    params: Promise<{ path: string[] }>;
  }
) {
  return bridge(
    request,
    (await context.params).path,
    "POST"
  );
}
