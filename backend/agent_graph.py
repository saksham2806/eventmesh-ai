
# backend/agent_graph.py

from typing import TypedDict

from langgraph.graph import StateGraph, START, END


class RecoveryState(TypedDict, total=False):
    session_id: int
    suggestions: list[dict]

    ranked_suggestions: list[dict]
    recommendation: dict | None
    decision_reason: str
    message_draft: str

    requires_approval: bool
    applied: bool
    trace: list[str]


# ===========================================
# AGENT 1 - SCHEDULING AGENT
# ===========================================

def scheduling_agent(state: RecoveryState):
    ranked = []

    for suggestion in state.get("suggestions", []):
        shift = int(
            suggestion["time_shift_minutes"]
        )

        ranked.append({
            **suggestion,
            "disruption_score": abs(shift)
        })

    # Prefer the smallest schedule change.
    # On ties, prefer a later slot to an
    # earlier slot, then use room name.
    ranked.sort(
        key=lambda s: (
            s["disruption_score"],
            s["time_shift_minutes"] < 0,
            s["room"].casefold()
        )
    )

    return {
        "ranked_suggestions": ranked,
        "trace": state.get("trace", []) + [
            "Scheduling Agent"
        ]
    }


# ===========================================
# AGENT 2 - RECOVERY AGENT
# ===========================================

def recovery_agent(state: RecoveryState):
    suggestions = state.get(
        "ranked_suggestions", []
    )

    if not suggestions:
        return {
            "recommendation": None,
            "decision_reason": (
                "No verified recovery alternative "
                "was available."
            ),
            "trace": state.get("trace", []) + [
                "Recovery Agent"
            ]
        }

    best = suggestions[0]
    shift = best["time_shift_minutes"]

    if shift == 0:
        reason = (
            "This proposal preserves the original "
            "session time and changes only the room."
        )
    else:
        reason = (
            f"This proposal moves the session by "
            f"{shift:+d} minutes. It has the "
            "smallest time disruption among the "
            "available proposals."
        )

    return {
        "recommendation": best,
        "decision_reason": reason,
        "trace": state.get("trace", []) + [
            "Recovery Agent"
        ]
    }


# ===========================================
# AGENT 3 - SUPPORT AGENT
# ===========================================

def support_agent(state: RecoveryState):
    best = state.get("recommendation")

    if best is None:
        message = (
            "Draft for organizer: No suitable "
            "alternative was identified. Manual "
            "scheduling review is required."
        )

    else:
        message = (
            "Draft only — not sent: "
            f"Session {state['session_id']} may "
            f"move to {best['room']} from "
            f"{best['start_time']} to "
            f"{best['end_time']}, subject to "
            "organizer approval."
        )

    return {
        "message_draft": message,
        "trace": state.get("trace", []) + [
            "Support Agent"
        ]
    }


# ===========================================
# AGENT 4 - APPROVAL GATE
# ===========================================

def approval_gate(state: RecoveryState):
    return {
        "requires_approval": (
            state.get("recommendation") is not None
        ),
        "applied": False,
        "trace": state.get("trace", []) + [
            "Approval Gate"
        ]
    }


# ===========================================
# BUILD LANGGRAPH WORKFLOW
# ===========================================

builder = StateGraph(RecoveryState)

builder.add_node(
    "scheduling_agent", scheduling_agent
)
builder.add_node(
    "recovery_agent", recovery_agent
)
builder.add_node(
    "support_agent", support_agent
)
builder.add_node(
    "approval_gate", approval_gate
)

builder.add_edge(START, "scheduling_agent")
builder.add_edge(
    "scheduling_agent", "recovery_agent"
)
builder.add_edge(
    "recovery_agent", "support_agent"
)
builder.add_edge(
    "support_agent", "approval_gate"
)
builder.add_edge("approval_gate", END)

recovery_graph = builder.compile()
