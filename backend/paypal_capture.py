
# backend/paypal_capture.py

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, Header, HTTPException,Depends

from ticketing_api import connect_db, check_organizer
from checkout_api import PAYPAL_BASE, get_paypal_token
from ticket_fulfillment import apply_verified_capture
from event_ownership import require_reservation_owner


router = APIRouter(tags=["PayPal Capture"])


# =========================================
# 1. DATABASE MIGRATION
# =========================================

def initialize_capture():
    db = connect_db()

    try:
        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(checkout_orders)"
            )
        }

        if "capture_request_id" not in columns:
            db.execute("""
                ALTER TABLE checkout_orders
                ADD COLUMN capture_request_id TEXT
            """)

        if "capture_started_at" not in columns:
            db.execute("""
                ALTER TABLE checkout_orders
                ADD COLUMN capture_started_at TEXT
            """)

        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_capture_request_id
            ON checkout_orders(capture_request_id)
        """)

        db.commit()

    finally:
        db.close()


initialize_capture()


# =========================================
# 2. LOAD SAVED CHECKOUT
# =========================================

def load_checkout(reservation_id):
    db = connect_db()

    try:
        row = db.execute("""
            SELECT
                r.id,
                r.status AS reservation_status,
                r.expires_at,
                c.paypal_order_id,
                c.status AS checkout_status
            FROM reservations r
            JOIN checkout_orders c
                ON c.reservation_id = r.id
            WHERE r.id = ?
        """, (reservation_id,)).fetchone()

        if row is None or not row["paypal_order_id"]:
            raise HTTPException(
                404, "PayPal checkout order not found"
            )

        return dict(row)

    finally:
        db.close()


# =========================================
# 3. FETCH ORDER DIRECTLY FROM PAYPAL
# =========================================

async def fetch_paypal_order(
    client, token, order_id
):
    try:
        response = await client.get(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}",
            headers={
                "Authorization": f"Bearer {token}"
            }
        )

    except httpx.RequestError:
        raise HTTPException(
            502, "Could not retrieve PayPal order"
        )

    if response.status_code != 200:
        raise HTTPException(
            502, "PayPal order lookup failed"
        )

    try:
        return response.json()
    except ValueError:
        raise HTTPException(
            502, "Invalid PayPal order response"
        )


# =========================================
# 4. PROCESS VERIFIED CAPTURE
# =========================================

def finalize_capture(reservation_id, order):
    try:
        return apply_verified_capture(
            reservation_id,
            order
        )

    except (
        ValueError,
        sqlite3.IntegrityError
    ):
        # The response could not be safely fulfilled.
        # Never issue tickets in this situation.
        db = connect_db()

        try:
            db.execute("""
                UPDATE checkout_orders
                SET status = 'REVIEW_REQUIRED'
                WHERE reservation_id = ?
            """, (reservation_id,))

            db.commit()

        finally:
            db.close()

        raise HTTPException(
            409,
            "Payment requires manual verification"
        )


# =========================================
# 5. PREPARE IDEMPOTENT CAPTURE ATTEMPT
# =========================================

def prepare_capture(reservation_id):
    db = connect_db()

    try:
        db.execute("BEGIN IMMEDIATE")

        row = db.execute("""
            SELECT
                r.status AS reservation_status,
                r.expires_at,
                c.capture_request_id,
                c.capture_started_at,
                c.status AS checkout_status
            FROM reservations r
            JOIN checkout_orders c
              ON c.reservation_id = r.id
            WHERE r.id = ?
        """, (reservation_id,)).fetchone()

        if row is None:
            raise HTTPException(
                404, "Reservation not found"
            )

        now = datetime.now(timezone.utc)
        now_text = now.isoformat(timespec="seconds")

        # Do not initiate a new charge for expired seats.
        if (
            row["reservation_status"] != "PENDING_PAYMENT"
            or row["expires_at"] <= now_text
        ):
            raise HTTPException(
                409,
                "Reservation expired or unavailable"
            )

        if row["checkout_status"] == "REVIEW_REQUIRED":
            raise HTTPException(
                409, "Payment requires manual review"
            )

        # Prevent concurrent capture calls.
        if (
            row["checkout_status"] == "CAPTURE_REQUESTED"
            and row["capture_started_at"]
        ):
            started = datetime.fromisoformat(
                row["capture_started_at"]
            )

            if (now - started).total_seconds() < 60:
                raise HTTPException(
                    409,
                    "Capture already processing; reconcile first"
                )

        # Reuse the same ID for safe retries.
        request_id = (
            row["capture_request_id"]
            or uuid4().hex[:24]
        )

        db.execute("""
            UPDATE checkout_orders
            SET capture_request_id = ?,
                capture_started_at = ?,
                status = 'CAPTURE_REQUESTED'
            WHERE reservation_id = ?
        """, (
            request_id,
            now_text,
            reservation_id
        ))

        db.commit()
        return request_id

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# =========================================
# 6. CAPTURE PAYMENT
# =========================================

@router.post(
    "/checkout/reservations/{reservation_id}/capture",
    dependencies=[Depends(require_reservation_owner)]

)
async def capture_payment(
    reservation_id: str,
    x_organizer_key: str | None = Header(default=None)
):
    # Local development access only.
    # Replace with authenticated buyer sessions.
    check_organizer(x_organizer_key)

    import os

    if not (
        os.getenv("PAYPAL_CLIENT_ID")
        and os.getenv("PAYPAL_CLIENT_SECRET")
    ):
        raise HTTPException(
            503,
            "PayPal Sandbox not configured"
        )

    checkout = load_checkout(reservation_id)
    order_id = checkout["paypal_order_id"]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token = await get_paypal_token(client)

            # Always check PayPal's current order status.
            order = await fetch_paypal_order(
                client, token, order_id
            )

            # A previous attempt may already have captured.
            if order.get("status") == "COMPLETED":
                return finalize_capture(
                    reservation_id, order
                )

            if order.get("status") != "APPROVED":
                raise HTTPException(
                    409,
                    "Buyer has not approved the payment"
                )

            # Recheck the seat hold under database lock.
            request_id = prepare_capture(reservation_id)

            try:
                response = await client.post(
                    f"{PAYPAL_BASE}/v2/checkout/orders/"
                    f"{order_id}/capture",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "PayPal-Request-Id": request_id,
                        "Prefer": "return=representation"
                    },
                    json={}
                )

            except httpx.RequestError:
                # Request may have succeeded remotely.
                # Never assume a timeout means failure.
                raise HTTPException(
                    502,
                    "Capture result unknown. "
                    "Use the reconciliation endpoint."
                )

            if response.status_code not in (200, 201):
                raise HTTPException(
                    502,
                    "PayPal capture not confirmed. "
                    "Reconcile before retrying."
                )

            try:
                captured_order = response.json()
            except ValueError:
                raise HTTPException(
                    502,
                    "Capture response unreadable. "
                    "Reconcile before retrying."
                )

    except httpx.RequestError:
        raise HTTPException(
            502, "PayPal Sandbox unavailable"
        )

    # The database operation is atomic.
    # If seats are unavailable, returns REVIEW_REQUIRED.
    return finalize_capture(
        reservation_id,
        captured_order
    )


# =========================================
# 7. RECONCILE UNKNOWN CAPTURE RESULTS
# =========================================

@router.post(
    "/checkout/reservations/{reservation_id}/reconcile",
    dependencies=[Depends(require_reservation_owner)]
)
async def reconcile_payment(
    reservation_id: str,
    x_organizer_key: str | None = Header(default=None)
):
    check_organizer(x_organizer_key)

    import os

    if not (
        os.getenv("PAYPAL_CLIENT_ID")
        and os.getenv("PAYPAL_CLIENT_SECRET")
    ):
        raise HTTPException(
            503,
            "PayPal Sandbox not configured"
        )

    checkout = load_checkout(reservation_id)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token = await get_paypal_token(client)

            order = await fetch_paypal_order(
                client,
                token,
                checkout["paypal_order_id"]
            )

    except httpx.RequestError:
        raise HTTPException(
            502, "PayPal reconciliation unavailable"
        )

    if order.get("status") == "COMPLETED":
        return finalize_capture(reservation_id, order)

    return {
        "status": "NOT_CAPTURED",
        "paypal_order_status": order.get("status"),
        "payment_verified": False,
        "tickets_issued": 0
    }
