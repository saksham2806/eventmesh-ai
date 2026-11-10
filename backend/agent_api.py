
# backend/agent_api.py

from fastapi import APIRouter, Depends, Header

from agent_graph import recovery_graph

from recovery_api import (
    RecoveryRequest,
    verified_recovery
)

from ticketing_api import check_organizer
from event_ownership import require_event_session_owner


router = APIRouter(tags=["EventMesh AI Agents"])


@router.post(
    "/ai/events/{event_id}/sessions/"
    "{session_id}/recovery-plan",
    dependencies=[Depends(require_event_session_owner)],
)
def create_ai_recovery_plan(
    event_id: int,
    session_id: int,
    request: RecoveryRequest,
    x_organizer_key: str | None = Header(
        default=None
    )
):
    # Temporary local development authorization
    check_organizer(x_organizer_key)

    # Reuse the verified recovery engine.
    # This creates pending proposals in SQLite,
    # but does not apply any schedule changes.
    verified_result = verified_recovery(
        event_id=event_id,
        session_id=session_id,
        request=request
    )

    # Run the LangGraph workflow.
    result = recovery_graph.invoke({
        "session_id": session_id,
        "suggestions": verified_result[
            "suggestions"
        ],
        "trace": []
    })

    recommendation = result.get(
        "recommendation"
    )

    return {
        "status": (
            "RECOMMENDATION_READY"
            if recommendation
            else "NO_SOLUTION"
        ),
        "mode": "RULE_BASED",
        "event_id": event_id,
        "session_id": session_id,
        "recommended_proposal": recommendation,
        "reason": result["decision_reason"],
        "alternatives": result[
            "ranked_suggestions"
        ],
        "message_draft": result[
            "message_draft"
        ],
        "requires_approval": result[
            "requires_approval"
        ],
        "applied": result["applied"],
        "agents_executed": result["trace"]
    }
