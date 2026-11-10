
# backend/impact_agents.py

from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import StateGraph, START, END


class ImpactState(TypedDict, total=False):
    event_id: int
    session_id: int
    session_title: str
    disruption_type: str
    description: str
    reservations: list[dict]

    booking_summary: dict
    payment_recommendation: str
    warnings: list[str]
    support_draft: str
    status: str
    requires_approval: bool
    applied: bool
    paypal_called: bool
    message_sent: bool
    trace: list[str]


def active_reservation(expires_at: str) -> bool:
    try:
        expiry = datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        )
        return (
            expiry.tzinfo is not None
            and expiry > datetime.now(timezone.utc)
        )
    except (ValueError, AttributeError):
        return False


# =====================================
# AGENT 1: TICKETING IMPACT
# =====================================

def ticketing_agent(state: ImpactState):
    rows = state.get("reservations", [])

    verified_paid = [
        r for r in rows
        if r["status"] == "PAID"
        and r["verified_capture"]
    ]

    pending = [
        r for r in rows
        if r["status"] == "PENDING_PAYMENT"
        and active_reservation(r["expires_at"])
    ]

    paid_without_capture = [
        r for r in rows
        if r["status"] == "PAID"
        and not r["verified_capture"]
    ]

    captured_not_paid = [
        r for r in rows
        if r["verified_capture"]
        and r["status"] != "PAID"
    ]

    missing_tickets = sum(
        max(
            0,
            r["quantity"] - r["active_ticket_count"]
        )
        for r in verified_paid
    )

    summary = {
        "scope": "EVENT_WIDE_ONLY",
        "session_specific_impact_known": False,
        "verified_paid_reservations": len(verified_paid),
        "verified_paid_seats": sum(
            r["quantity"] for r in verified_paid
        ),
        "recorded_capture_total_usd": (
            f"{sum(int(r['amount_cents'] or 0)
            for r in verified_paid) / 100:.2f}"
        ),
        "active_pending_reservations": len(pending),
        "active_pending_seats": sum(
            r["quantity"] for r in pending
        ),
        "paid_without_verified_capture": len(
            paid_without_capture
        ),
        "captured_but_not_paid": len(
            captured_not_paid
        ),
        "missing_issued_tickets": missing_tickets
    }

    warnings = [
        "Reservations are linked to events, not "
        "individual sessions. Exact affected "
        "attendees cannot yet be identified."
    ]

    if paid_without_capture:
        warnings.append(
            "Some PAID reservations have no verified "
            "capture record. Investigate these records."
        )

    if captured_not_paid:
        warnings.append(
            "Some verified captures are not marked PAID. "
            "Payment reconciliation is required."
        )

    if missing_tickets:
        warnings.append(
            "Some paid seats do not have matching "
            "active issued tickets."
        )

    return {
        "booking_summary": summary,
        "warnings": warnings,
        "trace": state.get("trace", []) + [
            "Ticketing Impact Agent"
        ]
    }


# =====================================
# AGENT 2: PAYMENT IMPACT
# =====================================

def payment_agent(state: ImpactState):
    summary = state["booking_summary"]

    if summary["captured_but_not_paid"] > 0:
        decision = (
            "RECONCILE_PAYMENTS: Verified captures with "
            "unfulfilled reservations require review."
        )

    elif summary["verified_paid_reservations"] > 0:
        decision = (
            "MANUAL_REFUND_REVIEW: Verified event-wide "
            "payments exist, but session-specific "
            "affected bookings are not identified. "
            "Do not create refunds automatically."
        )

    else:
        decision = (
            "NO_VERIFIED_PAID_BOOKINGS: There are no "
            "verified paid reservations in the "
            "current EventMesh records."
        )

    return {
        "payment_recommendation": decision,
        "trace": state.get("trace", []) + [
            "Payment Impact Agent"
        ]
    }


# =====================================
# AGENT 3: SUPPORT AGENT
# =====================================

def support_agent(state: ImpactState):
    message = (
        "DRAFT ONLY — NOT SENT: "
        f"We are reviewing a potential change to "
        f"'{state['session_title']}'. "
        "The organizer will confirm the schedule "
        "and communicate any necessary updates."
    )

    return {
        "support_draft": message,
        "trace": state.get("trace", []) + [
            "Support Agent"
        ]
    }


# =====================================
# AGENT 4: HUMAN APPROVAL GATE
# =====================================

def approval_gate(state: ImpactState):
    return {
        "status": "IMPACT_REPORT_READY",
        "requires_approval": True,
        "applied": False,
        "paypal_called": False,
        "message_sent": False,
        "trace": state.get("trace", []) + [
            "Approval Gate"
        ]
    }


# =====================================
# LANGGRAPH ORCHESTRATION
# =====================================

builder = StateGraph(ImpactState)

builder.add_node("ticketing", ticketing_agent)
builder.add_node("payment", payment_agent)
builder.add_node("support", support_agent)
builder.add_node("approval", approval_gate)

builder.add_edge(START, "ticketing")
builder.add_edge("ticketing", "payment")
builder.add_edge("payment", "support")
builder.add_edge("support", "approval")
builder.add_edge("approval", END)

impact_graph = builder.compile()
