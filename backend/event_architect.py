
# backend/event_architect.py

import re
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from room_utils import normalize_room

START_DAY = 9 * 60
END_DAY = 18 * 60

LUNCH_START = 12 * 60 + 30
LUNCH_END = 13 * 60 + 30

WORDS = {
    "one": 1, "two": 2, "three": 3,
    "four": 4, "five": 5
}


class ArchitectState(TypedDict, total=False):
    prompt: str
    expected_attendees: int | None
    event_capacity: int
    rooms: list[dict]
    existing_sessions: list[dict]

    attendees: int | None
    tasks: list[dict]
    schedule: list[dict]
    warnings: list[str]
    status: str
    trace: list[str]
    persisted: bool
    requires_approval: bool


def clock(n: int) -> str:
    return f"{n // 60:02d}:{n % 60:02d}"


def minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


# =========================================
# AGENT 1: EVENT ARCHITECT
# =========================================

def extract_requirements(state: ArchitectState):
    text = state["prompt"].lower()

    number = re.search(
        r"\b(\d{1,5})\s+"
        r"(?:attendees|participants|people)\b",
        text
    )

    attendees = (
        state.get("expected_attendees")
        or (
            int(number.group(1))
            if number else None
        )
    )

    tasks = []

    if "keynote" in text:
        tasks.append({
            "title": "Keynote",
            "duration_minutes": 60
        })

    match = re.search(
        r"\b(\d+|one|two|three|four|five)\s+"
        r"(?:(?:technical|hands-on|coding|ai)\s+){0,2}"
        r"workshops?\b",
        text
    )

    if match:
        value = match.group(1)
        workshop_count = (
            int(value)
            if value.isdigit()
            else WORDS[value]
        )
    else:
        workshop_count = (
            1 if "workshop" in text else 0
        )

    warnings = []

    if workshop_count > 5:
        warnings.append(
            "This preview supports up to five workshops."
        )
        workshop_count = 5

    for i in range(workshop_count):
        tasks.append({
            "title": f"Technical Workshop {i + 1}",
            "duration_minutes": 90
        })

    if "judging" in text:
        tasks.append({
            "title": "Final Judging",
            "duration_minutes": 60
        })

    if not attendees:
        warnings.append(
            "Specify the number of attendees."
        )

    if not tasks:
        warnings.append(
            "Mention a keynote, workshop or judging."
        )

    if attendees and attendees > state["event_capacity"]:
        warnings.append(
            f"Requested {attendees} attendees exceeds "
            f"event capacity {state['event_capacity']}."
        )

    return {
        "attendees": attendees,
        "tasks": tasks,
        "warnings": warnings,
        "trace": state.get("trace", []) + [
            "Event Architect"
        ]
    }


# =========================================
# AGENT 2: SCHEDULING AGENT
# =========================================

def schedule_agent(state: ArchitectState):
    attendees = state.get("attendees")
    warnings = list(state.get("warnings", []))
    tasks = state.get("tasks", [])

    if (
        not attendees
        or attendees > state["event_capacity"]
        or not tasks
    ):
        return {
            "schedule": [],
            "warnings": warnings,
            "trace": state.get("trace", []) + [
                "Scheduling Agent"
            ]
        }

    eligible_rooms = sorted(
        (
            room for room in state["rooms"]
            if room["capacity"] >= attendees
        ),
        key=lambda r: (
            r["capacity"],
            r["name"].lower()
        )
    )

    if not eligible_rooms:
        warnings.append(
            "No registered room has enough capacity."
        )
        return {
            "schedule": [],
            "warnings": warnings,
            "trace": state.get("trace", []) + [
                "Scheduling Agent"
            ]
        }

    lunch = "lunch" in state["prompt"].lower()
    cursor = START_DAY
    schedule = []

    for task in tasks:
        duration = task["duration_minutes"]
        selected = None

        for start in range(
            cursor,
            END_DAY - duration + 1,
            30
        ):
            end = start + duration

            if (
                lunch
                and start < LUNCH_END
                and end > LUNCH_START
            ):
                continue

            for room in eligible_rooms:

                taken = any(
                    normalize_room(room["name"])
                    == normalize_room(other["room"])
                    and start < minutes(other["end_time"])
                    and end > minutes(other["start_time"])
                    for other in state["existing_sessions"]
                )

                if taken:
                    continue

                selected = {
                    "title": task["title"],
                    "room_id": room["id"],
                    "room": room["name"],
                    "capacity": room["capacity"],
                    "start_time": clock(start),
                    "end_time": clock(end),
                    "speaker": None
                }

                cursor = end
                break

            if selected:
                break

        if selected:
            schedule.append(selected)
        else:
            warnings.append(
                f"Could not schedule {task['title']} "
                "within 09:00–18:00."
            )

    if lunch:
        schedule.append({
            "title": "Lunch Break",
            "room_id": None,
            "room": None,
            "capacity": None,
            "start_time": "12:30",
            "end_time": "13:30",
            "speaker": None
        })

    schedule.sort(
        key=lambda session: session["start_time"]
    )

    return {
        "schedule": schedule,
        "warnings": warnings,
        "trace": state.get("trace", []) + [
            "Scheduling Agent"
        ]
    }


# =========================================
# AGENT 3: REVIEW GATE
# =========================================

def review_gate(state: ArchitectState):
    scheduled = [
        session
        for session in state.get("schedule", [])
        if session["room_id"] is not None
    ]

    all_placed = (
        len(scheduled) == len(state.get("tasks", []))
        and bool(state.get("tasks"))
    )

    if (
        all_placed
        and not state.get("warnings")
    ):
        status = "DRAFT_READY"
    else:
        status = "NEEDS_REVIEW"

    if (
        not state.get("tasks")
        or not state.get("attendees")
    ):
        status = "NEEDS_INPUT"

    return {
        "status": status,
        "persisted": False,
        "requires_approval": True,
        "trace": state.get("trace", []) + [
            "Review Gate"
        ]
    }


# =========================================
# BUILD LANGGRAPH
# =========================================

builder = StateGraph(ArchitectState)

builder.add_node(
    "event_architect", extract_requirements
)

builder.add_node(
    "scheduling_agent", schedule_agent
)

builder.add_node(
    "review_gate", review_gate
)

builder.add_edge(START, "event_architect")

builder.add_edge(
    "event_architect",
    "scheduling_agent"
)

builder.add_edge(
    "scheduling_agent",
    "review_gate"
)

builder.add_edge("review_gate", END)

architect_graph = builder.compile()
