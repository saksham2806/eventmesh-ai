
import { createHmac, timingSafeEqual } from "node:crypto";

export const CHECKOUT_COOKIE = "eventmesh_sandbox_checkout";

type CheckoutSession = {
  reservationId: string;
  orderId: string;
  expiresAt: number;
};

const validId = /^[A-Za-z0-9-]{1,100}$/;

export function signCheckoutSession(
  reservationId: string,
  orderId: string,
  secret: string
): string {
  if (!validId.test(reservationId) || !validId.test(orderId)) {
    throw new Error("Invalid checkout identifiers");
  }

  const session: CheckoutSession = {
    reservationId,
    orderId,
    expiresAt: Date.now() + 40 * 60 * 1000,
  };

  const payload = Buffer.from(JSON.stringify(session))
    .toString("base64url");

  const signature = createHmac("sha256", secret)
    .update(payload)
    .digest("base64url");

  return `${payload}.${signature}`;
}

export function verifyCheckoutSession(
  value: string | undefined,
  secret: string
): CheckoutSession | null {
  if (!value || value.length > 1500) return null;

  const parts = value.split(".");
  if (parts.length !== 2) return null;

  const [payload, signature] = parts;

  const expected = createHmac("sha256", secret)
    .update(payload)
    .digest("base64url");

  const actualBytes = Buffer.from(signature);
  const expectedBytes = Buffer.from(expected);

  if (
    actualBytes.length !== expectedBytes.length ||
    !timingSafeEqual(actualBytes, expectedBytes)
  ) {
    return null;
  }

  try {
    const data: unknown = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8")
    );

    if (!data || typeof data !== "object") return null;

    const session = data as Partial<CheckoutSession>;

    if (
      typeof session.reservationId !== "string" ||
      typeof session.orderId !== "string" ||
      typeof session.expiresAt !== "number" ||
      !validId.test(session.reservationId) ||
      !validId.test(session.orderId) ||
      !Number.isFinite(session.expiresAt) ||
      session.expiresAt <= Date.now()
    ) {
      return null;
    }

    return session as CheckoutSession;
  } catch {
    return null;
  }
}
