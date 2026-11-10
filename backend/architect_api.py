
# backend/architect_api.py

from contextlib import closing

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from event_architect import architect_graph
from ticketing_api import connect_db, check_organizer
from event_ownership import require_event_owner

router = APIRouter(tags=["Event Architect AI"])


class ArchitectRequest(BaseModel):
    prompt: str = Field(
        min_length=20,
        max_length=1500
    )

    expected_attendees: int | None = Field(
        default=None,
        ge=1
    )


@router.post("/ai/events/{event_id}/architect/preview",
             dependencies=[Depends(require_event_owner)],
)
def preview_event_architecture(
    event_id: int,
    request: ArchitectRequest,
    x_organizer_key: str | None = Header(default=None)
):
    check_organizer(x_organizer_key)

    with closing(connect_db()) as db:
        event = db.execute(
            "SELECT id, capacity FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        if event is None:
            raise HTTPException(
                404, "Event not found"
            )

        rooms = db.execute(
            """
            SELECT id, name, capacity
            FROM rooms
            WHERE event_id = ?
            """,
            (event_id,)
        ).fetchall()

        existing = db.execute(
            """
            SELECT room, start_time, end_time
            FROM sessions
            WHERE event_id = ?
            """,
            (event_id,)
        ).fetchall()

        rooms_data = [dict(r) for r in rooms]
        sessions_data = [dict(s) for s in existing]
        event_capacity = event["capacity"]

    if not rooms_data:
        raise HTTPException(
            409,
            "Register event rooms before planning"
        )

    result = architect_graph.invoke({
        "prompt": request.prompt,
        "expected_attendees": request.expected_attendees,
        "event_capacity": event_capacity,
        "rooms": rooms_data,
        "existing_sessions": sessions_data,
        "trace": []
    })

    return {
        "event_id": event_id,
        "status": result["status"],
        "mode": "RULE_BASED",
        "attendees": result.get("attendees"),
        "proposed_schedule": result.get(
            "schedule", []
        ),
        "warnings": result.get("warnings", []),
        "requires_speaker_assignment": True,
        "requires_approval": True,
        "persisted": False,
        "agents_executed": result["trace"]
    }
