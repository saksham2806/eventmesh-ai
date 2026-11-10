
"""Protected PayPal Sandbox refund execution.

Disabled by default. Never automatically retries an uncertain refund.
"""

import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, HTTPException,Depends

import refund_api
from checkout_api import PAYPAL_BASE, get_paypal_token
from event_ownership import require_refund_proposal_owner

router = APIRouter(tags=["Sandbox Refund Execution"])

SANDBOX_URL = "https://api-m.sandbox.paypal.com"


def initialize_execution():
    db = refund_api.connection()
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS refund_execution_attempts (
                proposal_id TEXT PRIMARY KEY
                    REFERENCES refund_proposals(id),
                request_id TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL CHECK(
                    state IN ('SUBMITTING', 'UNKNOWN', 'SUBMITTED')
                ),
                created_at TEXT NOT NULL
            )
        """)
        db.commit()
    finally:
        db.close()


initialize_execution()


def mark_unknown(proposal_id):
    db = refund_api.connection()
    try:
        db.execute("""
            UPDATE refund_execution_attempts
            SET state = 'UNKNOWN'
            WHERE proposal_id = ? AND state = 'SUBMITTING'
        """, (proposal_id,))
        db.commit()
    finally:
        db.close()


def validate_capture(capture, proposal, payment):
    if capture.get("id") != proposal["capture_id"]:
        raise HTTPException(409, "PayPal capture ID mismatch")

    if capture.get("status") != "COMPLETED":
        raise HTTPException(
            409, "Capture is not currently refundable"
        )

    amount = capture.get("amount", {})

    try:
        cents = Decimal(str(amount["value"])) * 100
    except (KeyError, TypeError, InvalidOperation):
        raise HTTPException(409, "Invalid PayPal capture amount")

    if (
        amount.get("currency_code") != "USD"
        or cents != Decimal(payment["amount_cents"])
    ):
        raise HTTPException(409, "Capture amount mismatch")


@router.post(
    "/refunds/proposals/{proposal_id}/execute-sandbox",dependencies=[Depends(require_refund_proposal_owner)],
)
async def execute_sandbox_refund(
    proposal_id: str,
    x_organizer_key: str | None = Header(default=None),
    x_confirm_sandbox_refund: str | None = Header(default=None),
):
    refund_api.organizer_required(x_organizer_key)

    if PAYPAL_BASE.rstrip("/") != SANDBOX_URL:
        raise HTTPException(503, "Sandbox-only operation")

    if os.getenv("EVENTMESH_SANDBOX_REFUNDS_ENABLED") != "true":
        raise HTTPException(503, "Sandbox refunds disabled")

    if x_confirm_sandbox_refund != "CONFIRM_SANDBOX_REFUND":
        raise HTTPException(400, "Explicit confirmation required")

    db = refund_api.connection()
    try:
        proposal = db.execute(
            "SELECT * FROM refund_proposals WHERE id = ?",
            (proposal_id,)
        ).fetchone()

        if proposal is None:
            raise HTTPException(404, "Refund proposal not found")

        if proposal["status"] != "APPROVED_PENDING_PAYPAL":
            raise HTTPException(409, "Refund is not approved")

        if proposal["paypal_refund_id"] is not None:
            raise HTTPException(409, "Refund already submitted")

        payment = refund_api.payment_record(
            db, proposal["reservation_id"]
        )

        if (
            payment is None
            or refund_api.payment_eligibility_reason(payment)
            or payment["paypal_capture_id"] != proposal["capture_id"]
            or not 0 < proposal["amount_cents"] <= payment["amount_cents"]
        ):
            raise HTTPException(409, "Refund eligibility failed")

        request_id = proposal["paypal_request_id"]

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", proposal["capture_id"]):
            raise HTTPException(409, "Invalid capture ID")

    finally:
        db.close()

    # Independently verify the original capture with PayPal.
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            token = await get_paypal_token(client)

            captured = await client.get(
                f"{SANDBOX_URL}/v2/payments/captures/"
                f"{quote(proposal['capture_id'], safe='')}",
                headers={"Authorization": f"Bearer {token}"}
            )

            if captured.status_code != 200:
                raise HTTPException(
                    502, "Could not verify original capture"
                )

            try:
                capture_data = captured.json()
            except ValueError:
                raise HTTPException(502, "Invalid capture response")

            validate_capture(capture_data, proposal, payment)

            # Commit a single execution attempt before contacting PayPal.
            db = refund_api.connection()
            try:
                db.execute("BEGIN IMMEDIATE")

                current = db.execute(
                    "SELECT * FROM refund_proposals WHERE id = ?",
                    (proposal_id,)
                ).fetchone()

                previous = db.execute(
                    """SELECT state FROM refund_execution_attempts
                       WHERE proposal_id = ?""",
                    (proposal_id,)
                ).fetchone()

                current_payment = (
                    refund_api.payment_record(
                        db, current["reservation_id"]
                    ) if current else None
                )

                if previous:
                    raise HTTPException(
                        409, "Execution already attempted; reconcile first"
                    )

                if (
                    current is None
                    or current["status"] != "APPROVED_PENDING_PAYPAL"
                    or current["paypal_refund_id"] is not None
                    or current["capture_id"] != proposal["capture_id"]
                    or current["amount_cents"] != proposal["amount_cents"]
                    or current["paypal_request_id"] != request_id
                    or current_payment is None
                    or refund_api.payment_eligibility_reason(current_payment)
                ):
                    raise HTTPException(
                        409, "Refund state changed; execution blocked"
                    )

                db.execute("""
                    INSERT INTO refund_execution_attempts
                    (proposal_id, request_id, state, created_at)
                    VALUES (?, ?, 'SUBMITTING', ?)
                """, (
                    proposal_id,
                    request_id,
                    datetime.now(timezone.utc).isoformat()
                ))

                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

            # PayPal recommends an empty body for a full refund.
            body = {}

            if proposal["amount_cents"] < payment["amount_cents"]:
                body = {
                    "amount": {
                        "currency_code": "USD",
                        "value": refund_api.usd(
                            proposal["amount_cents"]
                        )
                    }
                }

            try:
                response = await client.post(
                    f"{SANDBOX_URL}/v2/payments/captures/"
                    f"{quote(proposal['capture_id'], safe='')}/refund",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "PayPal-Request-Id": request_id,
                        "Prefer": "return=representation"
                    },
                    json=body
                )
            except httpx.RequestError:
                mark_unknown(proposal_id)
                raise HTTPException(
                    502,
                    "Refund outcome unknown. Do not retry submission."
                )

            if response.status_code not in (200, 201):
                mark_unknown(proposal_id)
                raise HTTPException(
                    502,
                    "Refund not confirmed. Manual review required."
                )

            try:
                result = response.json()
                refund_id = result["id"]
                amount = result["amount"]

                valid = (
                    isinstance(refund_id, str)
                    and bool(re.fullmatch(
                        r"[A-Za-z0-9_-]{1,128}", refund_id
                    ))
                    and result.get("status")
                        in ("PENDING", "COMPLETED")
                    and amount.get("currency_code") == "USD"
                    and Decimal(str(amount["value"])) * 100
                        == Decimal(proposal["amount_cents"])
                )

                if not valid:
                    raise ValueError("Unexpected refund response")

            except (ValueError, KeyError, TypeError, InvalidOperation):
                mark_unknown(proposal_id)
                raise HTTPException(
                    502, "Refund requires manual reconciliation"
                )

            # Store provider refund ID atomically.
            db = refund_api.connection()
            try:
                db.execute("BEGIN IMMEDIATE")

                cursor = db.execute("""
                    UPDATE refund_proposals
                    SET paypal_refund_id = ?
                    WHERE id = ? AND paypal_refund_id IS NULL
                """, (refund_id, proposal_id))

                if cursor.rowcount != 1:
                    raise HTTPException(
                        409, "Refund link changed; manual review required"
                    )

                db.execute("""
                    UPDATE refund_execution_attempts
                    SET state = 'SUBMITTED'
                    WHERE proposal_id = ?
                      AND state = 'SUBMITTING'
                """, (proposal_id,))

                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

            return {
                "proposal_id": proposal_id,
                "paypal_refund_id": refund_id,
                "refund_status": result["status"],
                "amount_usd": refund_api.usd(
                    proposal["amount_cents"]
                ),
                "requires_reconciliation": True
            }

    except httpx.RequestError:
        raise HTTPException(
            503, "PayPal Sandbox temporarily unavailable"
        )
