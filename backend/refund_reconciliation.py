"""EventMesh 11C (part 1): READ-ONLY PayPal sandbox refund reconciliation.

This module never starts a refund. It checks locally approved proposals and
reads existing refunds that were independently linked by an authorized flow.
"""

import os
import re
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, HTTPException,Depends
from event_ownership import require_refund_proposal_owner

import refund_api
from checkout_api import PAYPAL_BASE, get_paypal_token

router = APIRouter(tags=["Refund Reconciliation"])
VALID_STATES = {"PENDING", "COMPLETED", "FAILED", "CANCELLED"}


def initialize_refund_reconciliation():
    db = refund_api.connection()
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS refund_reconciliation (
                proposal_id TEXT PRIMARY KEY REFERENCES refund_proposals(id),
                paypal_refund_id TEXT NOT NULL UNIQUE,
                provider_status TEXT NOT NULL CHECK(
                    provider_status IN ('PENDING', 'COMPLETED', 'FAILED', 'CANCELLED')
                ),
                verified_at TEXT NOT NULL
            )
        """)
        db.commit()
    finally:
        db.close()


initialize_refund_reconciliation()


def get_proposal(db, proposal_id):
    row = db.execute(
        "SELECT * FROM refund_proposals WHERE id = ?", (proposal_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Refund proposal not found")
    return row


def validate_remote_refund(response: dict, proposal) -> str:
    """Accept only PayPal's authenticated GET response, NEVER browser JSON."""
    if response.get("id") != proposal["paypal_refund_id"]:
        raise ValueError("PayPal refund ID mismatch")
    status = response.get("status")
    if status not in VALID_STATES:
        raise ValueError("Unknown PayPal refund status")
    amount = response.get("amount")
    if not isinstance(amount, dict) or amount.get("currency_code") != proposal["currency"]:
        raise ValueError("Refund currency mismatch")
    try:
        cents = Decimal(str(amount["value"])) * 100
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid PayPal amount") from exc
    if cents != Decimal(proposal["amount_cents"]):
        raise ValueError("Refund amount mismatch")
    return status


@router.get("/refunds/proposals/{proposal_id}/execution-preview",    dependencies=[Depends(require_refund_proposal_owner)],
)
def refund_execution_preview(
    proposal_id: str,
    x_organizer_key: str | None = Header(default=None),
):
    refund_api.organizer_required(x_organizer_key)
    db = refund_api.connection()
    try:
        proposal = get_proposal(db, proposal_id)
        payment = refund_api.payment_record(db, proposal["reservation_id"])
        eligibility_reason = (
            refund_api.payment_eligibility_reason(payment)
            if payment else "Reservation no longer exists"
        )
        locally_consistent = (
            proposal["status"] == "APPROVED_PENDING_PAYPAL"
            and eligibility_reason is None
            and payment["paypal_capture_id"] == proposal["capture_id"]
            and proposal["currency"] == payment["currency"]
            and 0 < proposal["amount_cents"] <= payment["amount_cents"]
            and proposal["paypal_refund_id"] is None
        )
        return {
            "proposal_id": proposal_id,
            "approval_status": proposal["status"],
            "amount_usd": refund_api.usd(proposal["amount_cents"]),
            "local_checks_passed": bool(locally_consistent),
            "sandbox_credentials_configured": bool(
                os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET")
            ),
            "refund_already_submitted": proposal["paypal_refund_id"] is not None,
            "execution_enabled": False,
            "paypal_called": False,
            "note": "Preview only. PayPal capture/refund history and operator permissions must be verified before executing a refund.",
        }
    finally:
        db.close()


@router.get("/refunds/proposals/{proposal_id}/tracking",    dependencies=[Depends(require_refund_proposal_owner)],
)
def refund_tracking(
    proposal_id: str,
    x_organizer_key: str | None = Header(default=None),
):
    refund_api.organizer_required(x_organizer_key)
    db = refund_api.connection()
    try:
        proposal = get_proposal(db, proposal_id)
        tracking = db.execute(
            "SELECT provider_status, verified_at FROM refund_reconciliation WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        return {
            "proposal_id": proposal_id,
            "approval_status": proposal["status"],
            "refund_status": (
                tracking["provider_status"] if tracking
                else "AWAITING_RECONCILIATION" if proposal["paypal_refund_id"]
                else "NOT_SUBMITTED"
            ),
            "verified_at": tracking["verified_at"] if tracking else None,
        }
    finally:
        db.close()


@router.post("/refunds/proposals/{proposal_id}/reconcile",    dependencies=[Depends(require_refund_proposal_owner)],
)
async def reconcile_refund(
    proposal_id: str,
    x_organizer_key: str | None = Header(default=None),
):
    refund_api.organizer_required(x_organizer_key)
    db = refund_api.connection()
    try:
        proposal = get_proposal(db, proposal_id)
        refund_id = proposal["paypal_refund_id"]
        if refund_id is None:
            return {
                "proposal_id": proposal_id,
                "refund_status": "NOT_SUBMITTED",
                "paypal_called": False,
            }
    finally:
        db.close()

    if not (os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET")):
        raise HTTPException(503, "PayPal sandbox not configured")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", refund_id):
        raise HTTPException(409, "Invalid stored PayPal refund ID")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token = await get_paypal_token(client)
            remote = await client.get(
                f"{PAYPAL_BASE}/v2/payments/refunds/{quote(refund_id, safe='')}",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.RequestError:
        raise HTTPException(503, "PayPal refund status temporarily unavailable")

    if remote.status_code != 200:
        raise HTTPException(502, "PayPal refund lookup failed")
    try:
        payload = remote.json()
    except ValueError:
        raise HTTPException(502, "Invalid PayPal response")
    try:
        verified_status = validate_remote_refund(payload, proposal)
    except ValueError as exc:
        raise HTTPException(409, str(exc))

    db = refund_api.connection()
    try:
        db.execute("BEGIN IMMEDIATE")
        current = get_proposal(db, proposal_id)
        if current["paypal_refund_id"] != refund_id:
            raise HTTPException(409, "Refund link changed; retry reconciliation")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.execute("""
            INSERT INTO refund_reconciliation
                (proposal_id, paypal_refund_id, provider_status, verified_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(proposal_id) DO UPDATE SET
                provider_status = excluded.provider_status,
                verified_at = excluded.verified_at
            WHERE refund_reconciliation.paypal_refund_id = excluded.paypal_refund_id
        """, (proposal_id, refund_id, verified_status, now))
        db.commit()
        return {
            "proposal_id": proposal_id,
            "refund_status": verified_status,
            "verified_at": now,
            "paypal_called": True,
            "money_movement_initiated": False,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
