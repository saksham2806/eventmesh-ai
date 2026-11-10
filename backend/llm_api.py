
# backend/llm_api.py

from contextlib import closing

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ticketing_api import connect_db, check_organizer
from llm_disruption import (
    interpret_with_llm,
    review_intent
)
from event_ownership import require_event_session_owner

router = APIRouter(tags=["LLM Event Intelligence"])


class DisruptionRequest(BaseModel):
    description: str = Field(
        min_length=10,
        max_length=600
    )


@router.post(
    "/ai/events/{event_id}/sessions/"
    "{session_id}/interpret-disruption",
    dependencies=[Depends(require_event_session_owner)]
)
async def interpret_disruption(
    event_id: int,
    session_id: int,
    request: DisruptionRequest,
    x_organizer_key: str | None = Header(default=None)
):
    check_organizer(x_organizer_key)

    # Read real EventMesh data
    with closing(connect_db()) as db:

        session = db.execute(
            """
            SELECT title, room
            FROM sessions
            WHERE id = ? AND event_id = ?
            """,
            (session_id, event_id)
        ).fetchone()

        if session is None:
            raise HTTPException(
                404, "Session not found"
            )

        rooms = db.execute(
            """
            SELECT id, name, capacity
            FROM rooms
            WHERE event_id = ?
            """,
            (event_id,)
        ).fetchall()

        registered_rooms = [
            dict(room) for room in rooms
        ]

        session_title = session["title"]
        current_room = session["room"]

    # Call the configured language model
    interpretation = await interpret_with_llm(
        description=request.description,
        session_title=session_title,
        current_room=current_room,
        rooms=registered_rooms
    )

    # Apply deterministic checks
    reviewed = review_intent(
        interpretation,
        registered_rooms
    )

    return {
        "status": "INTERPRETATION_READY",
        "mode": "LLM_POWERED",
        "event_id": event_id,
        "session_id": session_id,
        "current_room": current_room,
        "interpretation": reviewed,
        "verified_recovery_performed": False,
        "requires_approval": True,
        "applied": False,
        "paypal_called": False
    }
