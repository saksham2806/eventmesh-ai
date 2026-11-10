
# backend/paypal_webhooks.py

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, Request

from checkout_api import PAYPAL_BASE, get_paypal_token
from ticketing_api import check_organizer, connect_db

load_dotenv(Path(__file__).parent / ".env")

router = APIRouter(tags=["PayPal Webhooks"])

DB_PATH = Path(__file__).parent / "events.db"

RECONCILE_EVENT_TYPES = {
    "PAYMENT.CAPTURE.COMPLETED",
    "PAYMENT.CAPTURE.PENDING",
    "PAYMENT.CAPTURE.DENIED",
    "PAYMENT.CAPTURE.REFUNDED",
    "PAYMENT.CAPTURE.REVERSED",
}

REQUIRED_PAYPAL_HEADERS = {
    "paypal-auth-algo": "auth_algo",
    "paypal-cert-url": "cert_url",
    "paypal-transmission-id": "transmission_id",
    "paypal-transmission-sig": "transmission_sig",
    "paypal-transmission-time": "transmission_time",
}


# ==========================================
# 1. DATABASE INITIALIZATION
# ==========================================

def initialize_webhook_table(db_path=DB_PATH):
    db = sqlite3.connect(db_path, timeout=10)

    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS paypal_webhook_events (
                paypal_event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                processing_state TEXT NOT NULL,
                received_at TEXT NOT NULL
            )
        """)

        db.commit()

    finally:
        db.close()


initialize_webhook_table()


# ==========================================
# 2. STORE VERIFIED EVENTS
# ==========================================

def save_verified_event(event: dict, db_path=DB_PATH):
    """
    INTERNAL ONLY.

    Call this only AFTER verifying PayPal's
    webhook signature successfully.
    """

    event_id = event.get("id")
    event_type = event.get("event_type")

    if (
        not isinstance(event_id, str)
        or not 1 <= len(event_id) <= 200
        or not isinstance(event_type, str)
        or not 1 <= len(event_type) <= 100
    ):
        raise ValueError(
            "Missing or invalid PayPal event ID/type"
        )

    resource = event.get("resource")

    resource_id = (
        resource.get("id", "")
        if isinstance(resource, dict)
        else ""
    )

    if not isinstance(resource_id, str):
        resource_id = ""

    resource_id = resource_id[:200]

    if event_type in RECONCILE_EVENT_TYPES:
        state = "AWAITING_RECONCILIATION"
    else:
        state = "RECORDED"

    now = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    db = sqlite3.connect(db_path, timeout=10)

    try:
        db.execute("BEGIN IMMEDIATE")

        cursor = db.execute("""
            INSERT OR IGNORE INTO paypal_webhook_events (
                paypal_event_id,
                event_type,
                resource_id,
                processing_state,
                received_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            event_id,
            event_type,
            resource_id,
            state,
            now
        ))

        is_duplicate = cursor.rowcount == 0

        db.commit()

        return {
            "status": (
                "DUPLICATE"
                if is_duplicate
                else "RECORDED"
            ),
            "paypal_event_id": event_id,
            "processing_state": state
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==========================================
# 3. VERIFY SIGNATURE WITH PAYPAL
# ==========================================

async def verify_signature_with_paypal(event, headers):
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID")

    if not (
        webhook_id
        and os.getenv("PAYPAL_CLIENT_ID")
        and os.getenv("PAYPAL_CLIENT_SECRET")
    ):
        raise HTTPException(
            503,
            "PayPal webhook verification not configured"
        )

    payload = {
        destination: headers[source]
        for source, destination
        in REQUIRED_PAYPAL_HEADERS.items()
    }

    payload["webhook_id"] = webhook_id
    payload["webhook_event"] = event

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token = await get_paypal_token(client)

            response = await client.post(
                f"{PAYPAL_BASE}/v1/notifications/"
                "verify-webhook-signature",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=payload
            )

    except httpx.RequestError:
        raise HTTPException(
            503,
            "PayPal verification temporarily unavailable"
        )

    if response.status_code != 200:
        raise HTTPException(
            503,
            "PayPal verification temporarily unavailable"
        )

    try:
        verification_status = response.json().get(
            "verification_status"
        )

    except ValueError:
        raise HTTPException(
            503, "Invalid PayPal verification response"
        )

    return verification_status == "SUCCESS"


# ==========================================
# 4. PUBLIC WEBHOOK RECEIVER
# ==========================================

@router.post("/webhooks/paypal")
async def receive_paypal_webhook(request: Request):

    raw_body = await request.body()

    if len(raw_body) > 262_144:
        raise HTTPException(
            413, "Webhook payload too large"
        )

    try:
        event = json.loads(raw_body)

    except (UnicodeDecodeError, ValueError):
        raise HTTPException(
            400, "Invalid JSON payload"
        )

    if not isinstance(event, dict):
        raise HTTPException(
            400, "Expected JSON object"
        )

    # Required signature headers
    for header in REQUIRED_PAYPAL_HEADERS:
        if not request.headers.get(header):
            raise HTTPException(
                400, "Missing PayPal signature headers"
            )

    verified = await verify_signature_with_paypal(
        event,
        request.headers
    )

    if not verified:
        raise HTTPException(
            401, "Invalid PayPal webhook signature"
        )

    # The event is now authenticated.
    try:
        return save_verified_event(event)

    except ValueError:
        raise HTTPException(
            400, "Invalid verified event data"
        )


# ==========================================
# 5. ORGANIZER EVENT MONITORING
# ==========================================

@router.get("/paypal/webhooks/events")
def list_webhook_events(
    x_organizer_key: str | None = Header(default=None)
):
    # Temporary development-only authorization
    check_organizer(x_organizer_key)

    db = connect_db()

    try:
        events = db.execute("""
            SELECT
                paypal_event_id,
                event_type,
                resource_id,
                processing_state,
                received_at
            FROM paypal_webhook_events
            ORDER BY received_at DESC,
                     paypal_event_id DESC
            LIMIT 50
        """).fetchall()

        return [dict(event) for event in events]

    finally:
        db.close()
