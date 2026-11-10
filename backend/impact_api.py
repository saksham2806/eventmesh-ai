
# backend/impact_api.py

from contextlib import closing
from typing import Literal

from fastapi import APIRouter,Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ticketing_api import connect_db, check_organizer
from impact_agents import impact_graph
from event_ownership import require_event_session_owner

router = APIRouter(tags=["AI Payment Impact"])


class ImpactRequest(BaseModel):
    disruption_type: Literal[
        "ROOM_UNAVAILABLE",
        "SESSION_CANCELLED",
        "SESSION_DELAYED"
    ]

    description: str = Field(
        min_length=5,
        max_length=300
    )


@router.post(
    "/ai/events/{event_id}/sessions/"
    "{session_id}/impact-analysis",
    dependencies=[Depends(require_event_session_owner)]
)
def analyze_event_impact(
    event_id: int,
    session_id: int,
    request: ImpactRequest,
    x_organizer_key: str | None = Header(default=None)
):
    check_organizer(x_organizer_key)

    with closing(connect_db()) as db:

        session = db.execute("""
            SELECT id, title
            FROM sessions
            WHERE id = ? AND event_id = ?
        """, (session_id, event_id)).fetchone()

        if session is None:
            raise HTTPException(
                404, "Event session not found"
            )

        rows = db.execute("""
            SELECT
                r.id,
                r.quantity,
                r.status,
                r.expires_at,

                CASE
                    WHEN vp.paypal_capture_id IS NOT NULL
                    THEN 1
                    ELSE 0
                END AS verified_capture,

                vp.amount_cents,

                (
                    SELECT COUNT(*)
                    FROM issued_tickets it
                    WHERE it.reservation_id = r.id
                      AND it.status = 'ACTIVE'
                ) AS active_ticket_count

            FROM reservations r

            LEFT JOIN verified_payments vp
                ON vp.reservation_id = r.id

            WHERE r.event_id = ?
        """, (event_id,)).fetchall()

        reservations = [
            dict(row) for row in rows
        ]

        session_title = session["title"]

    result = impact_graph.invoke({
        "event_id": event_id,
        "session_id": session_id,
        "session_title": session_title,
        "disruption_type": request.disruption_type,
        "description": request.description,
        "reservations": reservations,
        "trace": []
    })

    return {
        "status": result["status"],
        "mode": "RULE_BASED",
        "event_id": event_id,
        "session_id": session_id,
        "session_title": session_title,
        "disruption_type": request.disruption_type,
        "booking_summary": result["booking_summary"],
        "payment_recommendation": result[
            "payment_recommendation"
        ],
        "warnings": result["warnings"],
        "message_draft": result["support_draft"],
        "requires_approval": result["requires_approval"],
        "applied": result["applied"],
        "paypal_called": result["paypal_called"],
        "message_sent": result["message_sent"],
        "agents_executed": result["trace"]
    }
