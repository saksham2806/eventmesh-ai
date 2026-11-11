
"use client";

import { useEffect, useState } from "react";

type PendingOrder = {
  reservationId: string;
  orderId: string;
};

type PaymentStatus = {
  reservation_id: string;
  reservation_status: string;
  payment_verified: boolean;
  tickets_issued: number;
  quantity: number;
};

export default function PayPalReturnNotice() {
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingOrder | null>(null);
  const [status, setStatus] = useState<PaymentStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);

  useEffect(() => {
    const url = new URL(window.location.href);
    const result = url.searchParams.get("paypal");

    if (result !== "approved" && result !== "cancelled") {
      return;
    }

    const returnedOrderId = url.searchParams.get("token");

    url.searchParams.delete("paypal");
    url.searchParams.delete("token");
    url.searchParams.delete("PayerID");

    window.history.replaceState(
      window.history.state,
      "",
      url.pathname + url.search + url.hash
    );

    if (result === "cancelled") {
      setMessage("Sandbox checkout was cancelled. No payment confirmed.");
      return;
    }

    let saved: PendingOrder | null = null;

    try {
      const raw = localStorage.getItem("eventmesh_pending_paypal");
      if (raw) saved = JSON.parse(raw) as PendingOrder;
    } catch {
      saved = null;
    }

    if (
      !saved ||
      !returnedOrderId ||
      saved.orderId !== returnedOrderId
    ) {
      setMessage(
        "PayPal returned, but this checkout could not be matched. No payment confirmed."
      );
      return;
    }

    setPending(saved);
    setMessage("Checking reservation status...");

    fetch(
      `/api/bridge/checkout/reservations/${encodeURIComponent(
        saved.reservationId
      )}/status`,
      { cache: "no-store" }
    )
      .then(async (response) => {
        if (!response.ok) throw new Error("Status unavailable");
        return (await response.json()) as PaymentStatus;
      })
      .then((data) => {
        setStatus(data);

        if (data.payment_verified) {
          setMessage("Payment verified. Ticket status is shown below.");
        } else {
          setMessage(
            "PayPal returned successfully. Payment capture is still pending."
          );
        }
      })
      .catch(() => {
        setMessage(
          "Could not check the reservation. Verify the backend before proceeding."
        );
      });
  }, []);

  async function completeCheckout() {
    if (!pending || busy || attempted) return;

    setAttempted(true);
    setBusy(true);
    setMessage("Completing the authorized Sandbox checkout...");

    try {
      const response = await fetch("/api/sandbox-checkout/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pending),
      });

      const result = await response.json();

      if (!response.ok) {
        setMessage(
          result.detail ||
          "Checkout outcome unknown. Reconciliation required."
        );
        return;
      }

      const updated = result as PaymentStatus;
      setStatus(updated);

      if (
        updated.reservation_status === "PAID" &&
        updated.payment_verified &&
        updated.tickets_issued === updated.quantity
      ) {
        localStorage.removeItem("eventmesh_pending_paypal");
        setMessage(
          `Sandbox payment verified! ${updated.tickets_issued} ticket(s) issued.`
        );
      } else {
        setMessage(
          "Ticket confirmation is incomplete. Manual review required."
        );
      }
    } catch {
      setMessage(
        "Checkout result unknown. Do not retry capture until reconciled."
      );
    } finally {
      setBusy(false);
    }
  }

  if (!message) return null;

  const canComplete =
    pending &&
    status?.reservation_status === "PENDING_PAYMENT" &&
    !status.payment_verified &&
    !attempted;

  return (
    <section className="panel" style={{ padding: 24, marginBottom: 20 }}>
      <h2>PayPal Sandbox — Checkout Confirmation</h2>

      <p style={{ marginTop: 12 }} role="status">
        {message}
      </p>

      {status && (
        <div style={{ marginTop: 16 }}>
          <p>Reservation: {status.reservation_status}</p>
          <p>Payment verified: {status.payment_verified ? "Yes" : "No"}</p>
          <p>Tickets issued: {status.tickets_issued}</p>
        </div>
      )}

      {canComplete && (
        <button
          type="button"
          className="btn primary"
          disabled={busy}
          style={{ marginTop: 16 }}
          onClick={() => void completeCheckout()}
        >
          {busy ? "Processing..." : "Complete Sandbox Checkout"}
        </button>
      )}

      <p className="hint" style={{ marginTop: 16 }}>
        Sandbox demonstration only (no real money). Payment and tickets are
        confirmed only after backend verification.
      </p>
    </section>
  );
}
