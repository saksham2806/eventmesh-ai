
# backend/incident_graph.py

from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from agent_graph import recovery_graph
from impact_agents import impact_graph


class IncidentState(TypedDict, total=False):
    event_id: int
    session_id: int
    session_title: str
    disruption_type: str
    description: str
    verified_suggestions: list[dict]
    reservations: list[dict]

    recovery_plan: dict
    impact_report: dict
    next_action: str
    status: str
    requires_approval: bool
    applied: bool
    paypal_called: bool
    message_sent: bool
    agents_executed: list[str]


# ======================================
# 1. RECOVERY WORKFLOW
# ======================================

def run_recovery_agents(state: IncidentState):
    if state["disruption_type"] == "ROOM_UNAVAILABLE":
        result = recovery_graph.invoke({
            "session_id": state["session_id"],
            "suggestions": state.get(
                "verified_suggestions", []
            ),
            "trace": []
        })

        plan = {
            "recommendation": result.get(
                "recommendation"
            ),
            "alternatives": result.get(
                "ranked_suggestions", []
            ),
            "reason": result["decision_reason"],
            "message_draft": result["message_draft"],
            "agents_executed": result["trace"]
        }

    else:
        plan = {
            "recommendation": None,
            "alternatives": [],
            "reason": (
                "Automatic room recovery is not "
                "available for this disruption type. "
                "Organizer scheduling review is required."
            ),
            "message_draft": None,
            "agents_executed": []
        }

    return {
        "recovery_plan": plan,
        "agents_executed": [
            "Recovery Workflow"
        ]
    }


# ======================================
# 2. TICKETING AND PAYMENT IMPACT
# ======================================

def run_impact_agents(state: IncidentState):
    impact_type = (
        "SESSION_DELAYED"
        if state["disruption_type"] == "SESSION_DELAYED"
        else state["disruption_type"]
    )

    result = impact_graph.invoke({
        "event_id": state["event_id"],
        "session_id": state["session_id"],
        "session_title": state["session_title"],
        "disruption_type": impact_type,
        "description": state["description"],
        "reservations": state.get(
            "reservations", []
        ),
        "trace": []
    })

    return {
        "impact_report": {
            "booking_summary": result["booking_summary"],
            "payment_recommendation": result[
                "payment_recommendation"
            ],
            "warnings": result["warnings"],
            "message_draft": result["support_draft"],
            "agents_executed": result["trace"]
        },
        "agents_executed": (
            state.get("agents_executed", [])
            + ["Ticketing & Payment Workflow"]
        )
    }


# ======================================
# 3. INCIDENT COORDINATOR
# ======================================

def coordinate_incident(state: IncidentState):
    recovery = state["recovery_plan"]
    impact = state["impact_report"]

    recommendation = recovery.get("recommendation")

    if recommendation:
        next_action = (
            "Review the recommended recovery proposal "
            f"{recommendation['proposal_id']} and approve "
            "it using the existing organizer approval API."
        )
        status = "RECOVERY_AND_IMPACT_READY"

    else:
        next_action = (
            "Organizer must review the disruption "
            "manually. No schedule recovery has been "
            "selected."
        )
        status = "IMPACT_REVIEW_READY"

    summary = impact["booking_summary"]

    if summary["captured_but_not_paid"] > 0:
        next_action += (
            " Investigate unfulfilled verified "
            "captures before taking financial action."
        )

    if summary["verified_paid_reservations"] > 0:
        next_action += (
            " Review possible attendee impact before "
            "considering any refund proposals."
        )

    return {
        "status": status,
        "next_action": next_action,
        "requires_approval": True,
        "applied": False,
        "paypal_called": False,
        "message_sent": False,
        "agents_executed": (
            state.get("agents_executed", [])
            + ["Incident Coordinator", "Approval Gate"]
        )
    }


# ======================================
# 4. BUILD MASTER WORKFLOW
# ======================================

builder = StateGraph(IncidentState)

builder.add_node(
    "recovery_workflow",
    run_recovery_agents
)

builder.add_node(
    "impact_workflow",
    run_impact_agents
)

builder.add_node(
    "coordinator",
    coordinate_incident
)

builder.add_edge(START, "recovery_workflow")
builder.add_edge(
    "recovery_workflow", "impact_workflow"
)
builder.add_edge(
    "impact_workflow", "coordinator"
)
builder.add_edge("coordinator", END)

incident_graph = builder.compile()
