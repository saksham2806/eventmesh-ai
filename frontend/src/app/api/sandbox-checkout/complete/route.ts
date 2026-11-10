
import { NextRequest, NextResponse } from "next/server";
import {
  CHECKOUT_COOKIE,
  verifyCheckoutSession,
} from "@/lib/sandboxSession";



type PaymentStatus = {
  reservation_id: string;
  reservation_status: string;
  payment_verified: boolean;
  tickets_issued: number;
  quantity: number;
};

function reply(detail: string, status: number) {
  return NextResponse.json(
    { detail },
    { status, headers: { "Cache-Control": "no-store" } }
  );
}

export async function POST(request: NextRequest) {
  // This endpoint is exclusively for a localhost Sandbox demo.
  if (
    process.env.NODE_ENV === "production" ||
    !["localhost", "127.0.0.1"].includes(
      request.nextUrl.hostname
    )
  ) {
    return reply("Local Sandbox route disabled", 403);
  }

  if (request.headers.get("origin") !== request.nextUrl.origin) {
    return reply("Invalid request origin", 403);
  }

  if (
    !request.headers.get("content-type")
      ?.startsWith("application/json")
  ) {
    return reply("Expected JSON", 415);
  }

  const secret = process.env.EVENTMESH_ORGANIZER_KEY;

  if (!secret) {
    return reply("Server authentication not configured", 503);
  }

  const session = verifyCheckoutSession(
    request.cookies.get(CHECKOUT_COOKIE)?.value,
    secret
  );

  if (!session) {
    return reply("Checkout session missing or expired", 403);
  }
  const organizerToken = request.cookies.get(
    "eventmesh_organizer_session"
  )?.value;

  if (!organizerToken || organizerToken.length > 512) {
    return reply("Organizer login required", 401);
  }

  const organizerCookie =
    `eventmesh_organizer_session=${encodeURIComponent(organizerToken)}`;


  let body: { reservationId?: string; orderId?: string };

  try {
    const raw = await request.text();
    if (raw.length > 512) return reply("Request too large", 413);
    const parsed: unknown = JSON.parse(raw);

    if (
      !parsed ||
      typeof parsed !== "object" ||
      Array.isArray(parsed)
    ) {
      return reply("Invalid checkout request", 400);
    }

    body = parsed as {
      reservationId?: string;
      orderId?: string;
    };
  } catch {
    return reply("Invalid JSON request", 400);
  }

  if (
    body.reservationId !== session.reservationId ||
    body.orderId !== session.orderId
  ) {
    return reply("Checkout session mismatch", 403);
  }

  const backendUrl =
    process.env.EVENTMESH_BACKEND_URL ||
    "http://127.0.0.1:8000";

  let base: URL;

  try {
    base = new URL(backendUrl);
  } catch {
    return reply("Invalid backend configuration", 503);
  }

  if (
    base.protocol !== "http:" ||
    !["localhost", "127.0.0.1"].includes(base.hostname) ||
    base.port !== "8000" ||
    base.pathname !== "/"
  ) {
    return reply("Local backend configuration required", 503);
  }

  const endpoint =
    `${base.origin}/checkout/reservations/` +
    encodeURIComponent(session.reservationId);

  try {

    const beforeResponse = await fetch(`${endpoint}/status`, {
      headers: {
        "x-organizer-key": secret,
        Cookie: organizerCookie,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });


    if (!beforeResponse.ok) {
      return reply("Reservation status unavailable", 502);
    }

    const before = (await beforeResponse.json()) as PaymentStatus;

    // Already completed: never submit a second capture.
    if (
      before.reservation_status === "PAID" &&
      before.payment_verified &&
      before.tickets_issued === before.quantity
    ) {
      return NextResponse.json(before);
    }

    if (
      before.reservation_status !== "PENDING_PAYMENT" ||
      before.payment_verified
    ) {
      return reply("Reservation needs manual review", 409);
    }

    // The existing FastAPI endpoint independently verifies
    // PayPal approval, the order, reservation hold, and capture.
    const captureResponse = await fetch(`${endpoint}/capture`, {
      method: "POST",
      headers: {
        "x-organizer-key": secret,
        "content-type": "application/json",
        Cookie: organizerCookie,
      },
      body: "{}",
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
    });

    if (!captureResponse.ok) {
      return reply(
        "Capture not confirmed. Do not retry; reconcile the order.",
        409
      );
    }


    const afterResponse = await fetch(`${endpoint}/status`, {
      headers: {
        "x-organizer-key": secret,
        Cookie: organizerCookie,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });


    if (!afterResponse.ok) {
      return reply(
        "Capture response received, but ticket status is unknown. Reconcile first.",
        502
      );
    }

    const after = (await afterResponse.json()) as PaymentStatus;

    if (
      after.reservation_status !== "PAID" ||
      !after.payment_verified ||
      after.tickets_issued !== after.quantity
    ) {
      return reply(
        "Payment/ticket records need manual reconciliation",
        409
      );
    }

    const result = NextResponse.json(after, {
      headers: { "Cache-Control": "no-store" },
    });

    result.cookies.set(CHECKOUT_COOKIE, "", {
      path: "/",
      maxAge: 0,
    });

    return result;
  } catch {
    return reply(
      "Checkout outcome unknown. Do not retry capture until reconciled.",
      502
    );
  }
}
