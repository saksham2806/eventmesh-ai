
# backend/incident_api.py

from contextlib import closing
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from incident_graph import incident_graph
from ticketing_api import connect_db, check_organizer
from recovery_api import RecoveryRequest, verified_recovery
from room_utils import normalize_room
from llm_disruption import (
    interpret_with_llm,
    review_intent
)
from event_ownership import require_event_session_owner

router = APIRouter(tags=["AI Incident Orchestrator"])


class IncidentRequest(BaseModel):
    description: str = Field(
        min_length=10,
        max_length=600
    )

    disruption_type: Literal[
        "ROOM_UNAVAILABLE",
        "SESSION_CANCELLED",
        "SESSION_DELAYED"
    ]

    unavailable_room: str | None = None
    use_llm: bool = False


@router.post(
    "/ai/events/{event_id}/sessions/"
    "{session_id}/incident-report",
    dependencies=[Depends(require_event_session_owner)],
)
async def create_incident_report(
    event_id: int,
    session_id: int,
    request: IncidentRequest,
    x_organizer_key: str | None = Header(default=None)
):
    check_organizer(x_organizer_key)

    # =====================================
    # 1. READ REAL EVENTMESH DATA
    # =====================================

    with closing(connect_db()) as db:
        session = db.execute("""
            SELECT id, title, room
            FROM sessions
            WHERE event_id = ? AND id = ?
        """, (event_id, session_id)).fetchone()

        if session is None:
            raise HTTPException(
                404, "Session not found"
            )

        rooms = db.execute("""
            SELECT id, name, capacity
            FROM rooms
            WHERE event_id = ?
        """, (event_id,)).fetchall()

        reservations = db.execute("""
            SELECT
                r.id,
                r.quantity,
                r.status,
                r.expires_at,
                CASE
                    WHEN vp.paypal_capture_id IS NOT NULL
                    THEN 1 ELSE 0
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

        session_data = dict(session)
        rooms_data = [dict(r) for r in rooms]
        booking_data = [dict(r) for r in reservations]

    # =====================================
    # 2. VALIDATE ROOM OUTAGE
    # =====================================

    if request.disruption_type == "ROOM_UNAVAILABLE":
        if not request.unavailable_room:
            raise HTTPException(
                422, "unavailable_room is required"
            )

        normalized = normalize_room(
            request.unavailable_room
        )

        current = normalize_room(
            session_data["room"]
        )

        if normalized != current:
            raise HTTPException(
                422,
                "Reported unavailable room does "
                "not match the session's current room"
            )

        registered = any(
            normalize_room(room["name"]) == normalized
            for room in rooms_data
        )

        if not registered:
            raise HTTPException(
                409,
                "Current room is missing from registry"
            )

    # =====================================
    # 3. OPTIONAL LLM INTERPRETATION
    # =====================================

    llm_interpretation = None
    interpretation_warnings = []

    if request.use_llm:
        intent = await interpret_with_llm(
            description=request.description,
            session_title=session_data["title"],
            current_room=session_data["room"],
            rooms=rooms_data
        )

        llm_interpretation = review_intent(
            intent, rooms_data
        )

        expected_type = request.disruption_type

        # The existing interpreter calls delays
        # SPEAKER_DELAY; our incident API calls
        # the corresponding scenario SESSION_DELAYED.
        if expected_type == "SESSION_DELAYED":
            expected_type = "SPEAKER_DELAY"

        if (
            llm_interpretation["disruption_type"]
            != expected_type
        ):
            interpretation_warnings.append(
                "LLM interpretation differs from the "
                "organizer-selected disruption type. "
                "Review both before taking action."
            )

        if llm_interpretation["needs_review"]:
            interpretation_warnings.append(
                "LLM interpretation requires "
                "human review."
            )

    # =====================================
    # 4. GET VERIFIED RECOVERY PROPOSALS
    # =====================================

    suggestions = []

    if request.disruption_type == "ROOM_UNAVAILABLE":
        # This saves pending proposal records,
        # but DOES NOT update session schedules.
        verified = verified_recovery(
            event_id=event_id,
            session_id=session_id,
            request=RecoveryRequest(
                unavailable_room=request.unavailable_room
            )
        )

        suggestions = verified["suggestions"]

    # =====================================
    # 5. RUN THE MASTER AGENT GRAPH
    # =====================================

    result = incident_graph.invoke({
        "event_id": event_id,
        "session_id": session_id,
        "session_title": session_data["title"],
        "disruption_type": request.disruption_type,
        "description": request.description,
        "verified_suggestions": suggestions,
        "reservations": booking_data,
        "agents_executed": []
    })

    # =====================================
    # 6. RETURN THE COMBINED REPORT
    # =====================================

    return {
        "status": result["status"],
        "mode": (
            "LLM_ASSISTED"
            if request.use_llm
            else "RULE_BASED"
        ),
        "event_id": event_id,
        "session_id": session_id,
        "session_title": session_data["title"],
        "disruption_type": request.disruption_type,
        "llm_interpretation": llm_interpretation,
        "recovery_plan": result["recovery_plan"],
        "impact_report": result["impact_report"],
        "interpretation_warnings": interpretation_warnings,
        "next_action": result["next_action"],
        "requires_approval": result["requires_approval"],
        "applied": result["applied"],
        "paypal_called": result["paypal_called"],
        "message_sent": result["message_sent"],
        "agents_executed": result["agents_executed"]
    }
