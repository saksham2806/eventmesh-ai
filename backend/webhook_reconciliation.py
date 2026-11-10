
"""Safe reconciliation of authenticated PayPal webhook events."""

import re
import sqlite3
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, HTTPException

import paypal_webhooks
from checkout_api import PAYPAL_BASE, get_paypal_token
from ticketing_api import check_organizer

router = APIRouter(tags=["Webhook Reconciliation"])

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"


def connect():
    db = sqlite3.connect(paypal_webhooks.DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


async def fetch_capture(capture_id):
    if PAYPAL_BASE.rstrip("/") != SANDBOX_BASE:
        raise HTTPException(503, "Sandbox-only reconciliation")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token = await get_paypal_token(client)

            response = await client.get(
                f"{SANDBOX_BASE}/v2/payments/captures/"
                f"{quote(capture_id, safe='')}",
                headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.RequestError:
        raise HTTPException(503, "PayPal temporarily unavailable")

    if response.status_code != 200:
        raise HTTPException(502, "PayPal capture lookup failed")

    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, "Invalid PayPal response")

    if not isinstance(data, dict):
        raise HTTPException(502, "Unexpected PayPal response")

    return data


def local_payment(db, capture_id):
    return db.execute("""
        SELECT
            r.status AS reservation_status,
            r.quantity,
            v.amount_cents,
            v.currency,
            c.status AS checkout_status,
            (
                SELECT COUNT(*)
                FROM issued_tickets t
                WHERE t.reservation_id = r.id
            ) AS tickets_issued
        FROM verified_payments v
        JOIN reservations r
            ON r.id = v.reservation_id
        JOIN checkout_orders c
            ON c.reservation_id = v.reservation_id
        WHERE v.paypal_capture_id = ?
    """, (capture_id,)).fetchone()


def locally_complete(payment, remote_cents, currency):
    return (
        payment is not None
        and payment["reservation_status"] == "PAID"
        and payment["checkout_status"] == "CAPTURED"
        and payment["currency"] == currency == "USD"
        and Decimal(payment["amount_cents"]) == remote_cents
        and payment["tickets_issued"] == payment["quantity"]
    )


@router.post("/paypal/webhooks/events/{event_id}/reconcile")
async def reconcile_webhook(
    event_id: str,
    x_organizer_key: str | None = Header(default=None)
):
    check_organizer(x_organizer_key)

    db = connect()
    try:
        event = db.execute("""
            SELECT *
            FROM paypal_webhook_events
            WHERE paypal_event_id = ?
        """, (event_id,)).fetchone()

        if event is None:
            raise HTTPException(404, "Webhook event not found")

        event_type = event["event_type"]
        capture_id = event["resource_id"]

        if event["processing_state"] == "RECONCILED":
            return {
                "status": "ALREADY_RECONCILED",
                "paypal_called": False
            }

        # Other event types need their own specialized handling.
        if event_type != "PAYMENT.CAPTURE.COMPLETED":
            return {
                "status": "NEEDS_MANUAL_REVIEW",
                "event_type": event_type,
                "money_movement_initiated": False
            }

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", capture_id):
            raise HTTPException(409, "Invalid capture ID")

    finally:
        db.close()

    # Independently verify the capture with PayPal.
    remote = await fetch_capture(capture_id)

    if remote.get("id") != capture_id:
        raise HTTPException(409, "Capture ID mismatch")

    if remote.get("status") != "COMPLETED":
        return {
            "status": "NEEDS_MANUAL_REVIEW",
            "reason": "Remote capture is not completed",
            "money_movement_initiated": False
        }

    amount = remote.get("amount", {})

    try:
        remote_cents = Decimal(str(amount["value"])) * 100
    except (KeyError, TypeError, InvalidOperation):
        raise HTTPException(409, "Invalid remote amount")

    currency = amount.get("currency_code")

    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")

        current = db.execute("""
            SELECT *
            FROM paypal_webhook_events
            WHERE paypal_event_id = ?
        """, (event_id,)).fetchone()

        if (
            current is None
            or current["resource_id"] != capture_id
            or current["event_type"] != "PAYMENT.CAPTURE.COMPLETED"
        ):
            raise HTTPException(409, "Webhook record changed")

        if current["processing_state"] == "RECONCILED":
            db.commit()
            return {
                "status": "ALREADY_RECONCILED",
                "paypal_called": True
            }

        payment = local_payment(db, capture_id)

        if payment is None:
            db.commit()
            return {
                "status": "WAITING_FOR_LOCAL_PAYMENT",
                "money_movement_initiated": False
            }

        if (
            payment["currency"] != currency
            or Decimal(payment["amount_cents"]) != remote_cents
        ):
            raise HTTPException(409, "Payment amount mismatch")

        if not locally_complete(payment, remote_cents, currency):
            db.commit()
            return {
                "status": "WAITING_FOR_LOCAL_FINALIZATION",
                "money_movement_initiated": False
            }

        db.execute("""
            UPDATE paypal_webhook_events
            SET processing_state = 'RECONCILED'
            WHERE paypal_event_id = ?
              AND processing_state = 'AWAITING_RECONCILIATION'
        """, (event_id,))

        db.commit()

        return {
            "status": "RECONCILED",
            "capture_verified": True,
            "tickets_already_issued": payment["tickets_issued"],
            "money_movement_initiated": False
        }

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
