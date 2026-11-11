
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, HTTPException,Depends

from ticketing_api import connect_db

from datetime import datetime, timezone
from uuid import uuid4
from event_ownership import require_reservation_owner

router = APIRouter(tags=["Ticket Fulfillment"])

from db_config import DB_PATH
def initialize_fulfillment():
    db = connect_db()

    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS verified_payments (
                reservation_id TEXT PRIMARY KEY
                    REFERENCES reservations(id),
                paypal_order_id TEXT NOT NULL UNIQUE,
                paypal_capture_id TEXT NOT NULL UNIQUE,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                verified_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS issued_tickets (
                id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL
                    REFERENCES reservations(id),
                seat_number INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                UNIQUE(reservation_id, seat_number)
            );
        """)

        db.commit()
    finally:
        db.close()


initialize_fulfillment()


def validate_paypal_capture(
    order: dict,
    expected_order_id: str,
    reservation_id: str,
    expected_cents: int
) -> str:
    """
    Validate order data obtained directly by our backend
    from an authenticated PayPal API response.

    Never accept this data from the browser.
    Returns the verified PayPal capture ID.
    """

    if order.get("id") != expected_order_id:
        raise ValueError("PayPal order ID mismatch")

    if order.get("status") != "COMPLETED":
        raise ValueError("Order is not completed")

    units = order.get("purchase_units", [])

    if len(units) != 1:
        raise ValueError("Expected exactly one purchase unit")

    unit = units[0]

    if unit.get("custom_id") != reservation_id:
        raise ValueError("Reservation reference mismatch")

    captures = unit.get(
        "payments", {}
    ).get("captures", [])

    if len(captures) != 1:
        raise ValueError("Expected exactly one capture")

    capture = captures[0]

    if capture.get("status") != "COMPLETED":
        raise ValueError("Capture is not completed")

    capture_id = capture.get("id")

    if not capture_id:
        raise ValueError("Capture ID missing")

    amount = capture.get("amount", {})

    if amount.get("currency_code") != "USD":
        raise ValueError("Currency mismatch")

    try:
        calculated_cents = (
            Decimal(str(amount["value"])) * 100
        )

        if calculated_cents != Decimal(expected_cents):
            raise ValueError("Payment amount mismatch")

    except (KeyError, InvalidOperation):
        raise ValueError("Invalid payment amount")

    return capture_id


@router.get("/checkout/reservations/{reservation_id}/status",
            dependencies=[Depends(require_reservation_owner)]
            )
def get_ticket_payment_status(reservation_id: str):
    db = connect_db()

    try:
        reservation = db.execute(
            """
            SELECT id, status, quantity, expires_at
            FROM reservations
            WHERE id = ?
            """,
            (reservation_id,)
        ).fetchone()

        if reservation is None:
            raise HTTPException(404, "Reservation not found")

        checkout = db.execute(
            """
            SELECT paypal_order_id, status
            FROM checkout_orders
            WHERE reservation_id = ?
            """,
            (reservation_id,)
        ).fetchone()

        verified = db.execute(
            """
            SELECT paypal_capture_id
            FROM verified_payments
            WHERE reservation_id = ?
            """,
            (reservation_id,)
        ).fetchone()

        ticket_count = db.execute(
            """
            SELECT COUNT(*)
            FROM issued_tickets
            WHERE reservation_id = ?
            """,
            (reservation_id,)
        ).fetchone()[0]

        return {
            "reservation_id": reservation_id,
            "reservation_status": reservation["status"],
            "paypal_order_created": (
                checkout is not None
                and checkout["paypal_order_id"] is not None
            ),
            "payment_verified": verified is not None,
            "tickets_issued": ticket_count,
            "quantity": reservation["quantity"]
        }

    finally:
        db.close()




def apply_verified_capture(
    reservation_id: str,
    order: dict,
    db=None
) -> dict:
    """
    INTERNAL FUNCTION ONLY.

    'order' must come from an authenticated
    server-to-PayPal API response.

    NEVER call this using JSON submitted
    directly by a browser.
    """

    owns_connection = db is None

    if owns_connection:
        db = connect_db()

    try:
        db.execute("BEGIN IMMEDIATE")

        # 1. Load reservation and capacities
        row = db.execute("""
            SELECT
                r.id,
                r.event_id,
                r.ticket_type_id,
                r.quantity,
                r.status,
                t.price_cents,
                t.capacity AS category_capacity,
                e.capacity AS event_capacity
            FROM reservations r
            JOIN ticket_types t
                ON t.id = r.ticket_type_id
            JOIN events e
                ON e.id = r.event_id
            WHERE r.id = ?
        """, (reservation_id,)).fetchone()

        if row is None:
            raise ValueError("Reservation not found")

        # 2. Verify the stored PayPal order reference
        checkout = db.execute("""
            SELECT paypal_order_id
            FROM checkout_orders
            WHERE reservation_id = ?
        """, (reservation_id,)).fetchone()

        if checkout is None or not checkout["paypal_order_id"]:
            raise ValueError(
                "No PayPal order linked to reservation"
            )

        order_id = checkout["paypal_order_id"]
        expected_cents = (
            row["price_cents"] * row["quantity"]
        )

        # 3. Validate the trusted PayPal response
        capture_id = validate_paypal_capture(
            order,
            order_id,
            reservation_id,
            expected_cents
        )

        # 4. Idempotency: check existing payment
        previous = db.execute("""
            SELECT *
            FROM verified_payments
            WHERE reservation_id = ?
        """, (reservation_id,)).fetchone()

        if previous:
            if (
                previous["paypal_order_id"] != order_id
                or previous["paypal_capture_id"] != capture_id
            ):
                raise ValueError(
                    "Different payment already recorded"
                )

        else:
            now = datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds")

            db.execute("""
                INSERT INTO verified_payments (
                    reservation_id,
                    paypal_order_id,
                    paypal_capture_id,
                    amount_cents,
                    currency,
                    verified_at
                )
                VALUES (?, ?, ?, ?, 'USD', ?)
            """, (
                reservation_id,
                order_id,
                capture_id,
                expected_cents,
                now
            ))

        # 5. Never issue duplicate tickets
        issued = db.execute("""
            SELECT COUNT(*)
            FROM issued_tickets
            WHERE reservation_id = ?
        """, (reservation_id,)).fetchone()[0]

        if issued:
            if (
                row["status"] != "PAID"
                or issued != row["quantity"]
            ):
                raise ValueError(
                    "Inconsistent ticket state"
                )

            db.commit()

            return {
                "status": "ALREADY_ISSUED",
                "reservation_id": reservation_id,
                "tickets_issued": issued
            }

        # 6. Respect previous review decisions
        checkout_status = db.execute("""
            SELECT status
            FROM checkout_orders
            WHERE reservation_id = ?
        """, (reservation_id,)).fetchone()["status"]

        if checkout_status == "REVIEW_REQUIRED":
            db.commit()

            return {
                "status": "REVIEW_REQUIRED",
                "reservation_id": reservation_id,
                "tickets_issued": 0,
                "payment_verified": True
            }

        # 7. Recheck current seat availability
        now = datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds")

        occupied_condition = """
            r.id != ?
            AND r.event_id = ?
            AND (
                r.status = 'PAID'
                OR (
                    r.status = 'PENDING_PAYMENT'
                    AND r.expires_at > ?
                )
            )
        """

        category_taken = db.execute("""
            SELECT COALESCE(SUM(r.quantity), 0)
            FROM reservations r
            WHERE
        """ + occupied_condition + """
            AND r.ticket_type_id = ?
        """, (
            reservation_id,
            row["event_id"],
            now,
            row["ticket_type_id"]
        )).fetchone()[0]

        event_taken = db.execute("""
            SELECT COALESCE(SUM(r.quantity), 0)
            FROM reservations r
            WHERE
        """ + occupied_condition, (
            reservation_id,
            row["event_id"],
            now
        )).fetchone()[0]

        can_issue = (
            row["status"] in (
                "PENDING_PAYMENT",
                "EXPIRED"
            )
            and (
                category_taken + row["quantity"]
                <= row["category_capacity"]
            )
            and (
                event_taken + row["quantity"]
                <= row["event_capacity"]
            )
        )

        # 8. Payment exists, but seats cannot be issued
        if not can_issue:
            db.execute("""
                UPDATE checkout_orders
                SET status = 'REVIEW_REQUIRED'
                WHERE reservation_id = ?
            """, (reservation_id,))

            db.commit()

            return {
                "status": "REVIEW_REQUIRED",
                "reservation_id": reservation_id,
                "tickets_issued": 0,
                "payment_verified": True
            }

        # 9. Atomically mark paid and issue tickets
        db.execute("""
            UPDATE reservations
            SET status = 'PAID'
            WHERE id = ?
        """, (reservation_id,))

        for seat_number in range(
            1, row["quantity"] + 1
        ):
            db.execute("""
                INSERT INTO issued_tickets (
                    id,
                    reservation_id,
                    seat_number,
                    status
                )
                VALUES (?, ?, ?, 'ACTIVE')
            """, (
                uuid4().hex,
                reservation_id,
                seat_number
            ))

        db.execute("""
            UPDATE checkout_orders
            SET status = 'CAPTURED'
            WHERE reservation_id = ?
        """, (reservation_id,))

        db.commit()

        return {
            "status": "TICKETS_ISSUED",
            "reservation_id": reservation_id,
            "tickets_issued": row["quantity"],
            "payment_verified": True
        }

    except Exception:
        db.rollback()
        raise

    finally:
        if owns_connection:
            db.close()
