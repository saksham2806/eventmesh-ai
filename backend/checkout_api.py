
# backend/checkout_api.py

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException,Depends

from ticketing_api import connect_db, money
from event_ownership import require_reservation_owner

load_dotenv(Path(__file__).parent / ".env")

router = APIRouter(tags=["PayPal Checkout"])

PAYPAL_BASE = "https://api-m.sandbox.paypal.com"


def frontend_return_origin() -> str:
    """Fixed server-configured frontend origin for PayPal Sandbox redirects."""
    configured = os.environ.get("EVENTMESH_PUBLIC_FRONTEND_URL", "").strip()
    if not configured:
        # Hosted checkout must never send a buyer back to localhost.
        if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"):
            raise HTTPException(
                503, "Configure EVENTMESH_PUBLIC_FRONTEND_URL for hosted checkout"
            )
        return "http://localhost:3000"

    url = urlsplit(configured)
    if (
        url.username or url.password or url.query or url.fragment
        or url.path not in ("", "/") or not url.hostname
        or url.scheme != "https"
        or url.hostname in ("localhost", "127.0.0.1")
        or "." not in url.hostname
    ):
        raise HTTPException(503, "Invalid HTTPS frontend return origin")
    try:
        if url.port not in (None, 443):
            raise HTTPException(503, "Invalid HTTPS frontend return origin")
    except ValueError as exc:
        raise HTTPException(503, "Invalid HTTPS frontend return origin") from exc
    return f"https://{url.netloc}"


# --------------------------------------
# Database: link reservation to PayPal
# --------------------------------------

def initialize_checkout():
    db = connect_db()
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS checkout_orders (
                reservation_id TEXT PRIMARY KEY
                    REFERENCES reservations(id),
                paypal_request_id TEXT NOT NULL UNIQUE,
                paypal_order_id TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'CREATING'
            )
        """)
        db.commit()
    finally:
        db.close()


initialize_checkout()


# --------------------------------------
# Validate an existing reservation
# --------------------------------------

def get_reservation(db, reservation_id):
    row = db.execute("""
        SELECT
            r.id,
            r.event_id,
            r.quantity,
            r.status,
            r.expires_at,
            t.name AS ticket_name,
            t.price_cents
        FROM reservations r
        JOIN ticket_types t
          ON r.ticket_type_id = t.id
        WHERE r.id = ?
    """, (reservation_id,)).fetchone()

    if row is None:
        raise HTTPException(404, "Reservation not found")

    if row["status"] != "PENDING_PAYMENT":
        raise HTTPException(
            409, "Reservation is not pending payment"
        )

    now = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    if row["expires_at"] <= now:
        raise HTTPException(
            409, "Reservation expired. Reserve again."
        )

    return row


# --------------------------------------
# Preview checkout without PayPal
# --------------------------------------


@router.get(
    "/checkout/reservations/{reservation_id}/preview",
    dependencies=[Depends(require_reservation_owner)]
)

def checkout_preview(reservation_id: str):
    db = connect_db()

    try:
        row = get_reservation(db, reservation_id)

        total = row["quantity"] * row["price_cents"]

        return {
            "reservation_id": reservation_id,
            "ticket_name": row["ticket_name"],
            "quantity": row["quantity"],
            "currency": "USD",
            "total": money(total),
            "reservation_expires_at": row["expires_at"],
            "payment_status": "NOT_PAID",
            "provider": "PAYPAL_SANDBOX",
            "checkout_available": bool(
                os.getenv("PAYPAL_CLIENT_ID")
                and os.getenv("PAYPAL_CLIENT_SECRET")
            )
        }

    finally:
        db.close()


# --------------------------------------
# Get a PayPal OAuth access token
# --------------------------------------

async def get_paypal_token(client):
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise HTTPException(
            503, "PayPal Sandbox not configured"
        )

    response = await client.post(
        f"{PAYPAL_BASE}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"}
    )

    if response.status_code != 200:
        raise HTTPException(
            502, "PayPal authentication failed"
        )

    token = response.json().get("access_token")

    if not token:
        raise HTTPException(
            502, "PayPal token missing"
        )

    return token


# --------------------------------------
# Create a PayPal sandbox order
# --------------------------------------

@router.post(
    "/checkout/reservations/{reservation_id}/paypal-order",
    dependencies=[Depends(require_reservation_owner)]
)
async def create_paypal_order(reservation_id: str):
    db = connect_db()

    try:
        db.execute("BEGIN IMMEDIATE")

        row = get_reservation(db, reservation_id)

        total_cents = (
            row["price_cents"] * row["quantity"]
        )

        # Return a safe, explicit development status
        # when no PayPal credentials are configured.
        if not (
            os.getenv("PAYPAL_CLIENT_ID")
            and os.getenv("PAYPAL_CLIENT_SECRET")
        ):
            db.commit()
            return {
                "status": "NOT_CONFIGURED",
                "reservation_id": reservation_id,
                "currency": "USD",
                "amount": money(total_cents),
                "payment_created": False
            }

        existing = db.execute(
            """
            SELECT * FROM checkout_orders
            WHERE reservation_id = ?
            """,
            (reservation_id,)
        ).fetchone()

        if existing and existing["paypal_order_id"]:
            db.commit()
            return {
                "status": "ORDER_CREATED",
                "reservation_id": reservation_id,
                "paypal_order_id": existing["paypal_order_id"],
                "payment_captured": False
            }

        if existing:
            request_id = existing["paypal_request_id"]
        else:
            request_id = uuid4().hex[:24]

            db.execute(
                """
                INSERT INTO checkout_orders (
                    reservation_id,
                    paypal_request_id,
                    status
                )
                VALUES (?, ?, 'CREATING')
                """,
                (reservation_id, request_id)
            )

        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # Network calls happen outside the SQLite transaction.
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            return_origin = frontend_return_origin()
            token = await get_paypal_token(client)

            response = await client.post(
                f"{PAYPAL_BASE}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "PayPal-Request-Id": request_id,
                    "Prefer": "return=representation"
                },
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{
                        "reference_id": reservation_id,
                        "custom_id": reservation_id,
                        "description": (
                            "EventMesh event ticket"
                        ),
                        "amount": {
                            "currency_code": "USD",
                            "value": money(total_cents)
                        }
                    }],
                    "payment_source": {
                        "paypal": {
                            "experience_context": {
                                "shipping_preference": "NO_SHIPPING",
                                "landing_page": "LOGIN",
                                "user_action": "CONTINUE",
                                "return_url": f"{return_origin}/?paypal=approved",
                                "cancel_url": f"{return_origin}/?paypal=cancelled"
                            }
                        }
                    }
                }
            )

    except httpx.RequestError:
        raise HTTPException(
            502, "Could not reach PayPal Sandbox"
        )

    if response.status_code not in (200, 201):
        raise HTTPException(
            502, "PayPal order creation failed"
        )

    order = response.json()
    paypal_order_id = order.get("id")

    approval_url = next(
        (
            link.get("href")
            for link in order.get("links", [])
            if link.get("rel") in ("payer-action", "approve")
            and isinstance(link.get("href"), str)
            and link["href"].startswith(
                "https://www.sandbox.paypal.com/"
            )
        ),
        None
    )

    if not paypal_order_id:
        raise HTTPException(
            502, "PayPal order ID missing"
        )

    # Save the real PayPal order ID.
    db = connect_db()

    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """
            UPDATE checkout_orders
            SET paypal_order_id = ?,
                status = 'CREATED'
            WHERE reservation_id = ?
              AND paypal_request_id = ?
            """,
            (
                paypal_order_id,
                reservation_id,
                request_id
            )
        )
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return {
        "status": "ORDER_CREATED",
        "reservation_id": reservation_id,
        "paypal_order_id": paypal_order_id,
        "approval_url": approval_url,
        "amount": money(total_cents),
        "currency": "USD",
        "payment_captured": False
    }
