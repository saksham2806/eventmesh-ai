
# backend/recovery_api.py

import hmac
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from room_utils import normalize_room
from event_ownership import (
    require_event_session_owner,
    require_legacy_recovery_proposal_owner,
)

load_dotenv(Path(__file__).parent / ".env")

router = APIRouter(tags=["Verified Recovery"])

DB_PATH = Path(__file__).parent / "events.db"


class RecoveryRequest(BaseModel):
    unavailable_room: str = Field(min_length=2)


def minutes(value: str) -> int:
    hours, mins = map(int, value.split(":"))
    return hours * 60 + mins


def clock(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and a_end > b_start


def is_available(existing, target, room_name, start, end):
    for booked in existing:
        conflict = overlap(
            start, end,
            minutes(booked["start_time"]),
            minutes(booked["end_time"])
        )

        same_room = (
            normalize_room(room_name)
            == normalize_room(booked["room"])
        )

        same_speaker = (
            target["speaker"].strip().casefold()
            == booked["speaker"].strip().casefold()
        )

        if conflict and (same_room or same_speaker):
            return False

    return True


def initialize_recovery_table():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS recovery_proposals (
                id TEXT PRIMARY KEY,
                event_id INTEGER NOT NULL,
                session_id INTEGER NOT NULL,

                original_room TEXT NOT NULL,
                original_start TEXT NOT NULL,
                original_end TEXT NOT NULL,

                room_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'PENDING'
            )
        """)


initialize_recovery_table()



@router.post(
    "/events/{event_id}/sessions/{session_id}/verified-recovery",
    dependencies=[Depends(require_event_session_owner)],
)

def verified_recovery(
    event_id: int,
    session_id: int,
    request: RecoveryRequest
):
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row

    try:
        db.execute("BEGIN IMMEDIATE")

        target = db.execute(
            """
            SELECT * FROM sessions
            WHERE event_id = ? AND id = ?
            """,
            (event_id, session_id)
        ).fetchone()

        if target is None:
            raise HTTPException(404, "Session not found")

        unavailable = normalize_room(request.unavailable_room)

        if normalize_room(target["room"]) != unavailable:
            raise HTTPException(
                422,
                "Unavailable room does not match session room"
            )

        rooms = db.execute(
            """
            SELECT id, name, capacity
            FROM rooms
            WHERE event_id = ?
            ORDER BY id
            """,
            (event_id,)
        ).fetchall()

        existing = db.execute(
            """
            SELECT * FROM sessions
            WHERE event_id = ? AND id != ?
            """,
            (event_id, session_id)
        ).fetchall()

        original_start = minutes(target["start_time"])
        original_end = minutes(target["end_time"])
        duration = original_end - original_start

        if duration <= 0 or duration > 540:
            raise HTTPException(422, "Invalid session duration")

        # Working hours: 09:00 to 18:00
        starts = set(
            range(540, 1080 - duration + 1, 30)
        )
        starts.add(original_start)

        starts = sorted(
            (
                s for s in starts
                if 540 <= s and s + duration <= 1080
            ),
            key=lambda s: (
                abs(s - original_start),
                s < original_start,
                s
            )
        )

        proposals = []

        for start in starts:
            end = start + duration

            for room in rooms:
                if normalize_room(room["name"]) == unavailable:
                    continue

                if not is_available(
                    existing,
                    target,
                    room["name"],
                    start,
                    end
                ):
                    continue

                proposal_id = uuid4().hex

                db.execute(
                    """
                    INSERT INTO recovery_proposals (
                        id, event_id, session_id,
                        original_room, original_start,
                        original_end, room_id,
                        start_time, end_time, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                    """,
                    (
                        proposal_id, event_id, session_id,
                        target["room"], target["start_time"],
                        target["end_time"], room["id"],
                        clock(start), clock(end)
                    )
                )

                proposals.append({
                    "proposal_id": proposal_id,
                    "room_id": room["id"],
                    "room": room["name"],
                    "start_time": clock(start),
                    "end_time": clock(end),
                    "time_shift_minutes": (
                        start - original_start
                    )
                })

                if len(proposals) == 3:
                    break

            if len(proposals) == 3:
                break

        db.commit()

        return {
            "status": (
                "PROPOSALS_READY"
                if proposals else "NO_SOLUTION"
            ),
            "session_id": session_id,
            "suggestions": proposals,
            "applied": False
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.post(
    "/recovery-proposals/{proposal_id}/approve",
    dependencies=[
        Depends(require_legacy_recovery_proposal_owner)
    ],
)

def approve_recovery(
    proposal_id: str,
    x_organizer_key: str | None = Header(default=None)
):
    expected_key = os.getenv("EVENTMESH_ORGANIZER_KEY")

    if not expected_key:
        raise HTTPException(
            503, "Organizer approval key not configured"
        )

    if not x_organizer_key or not hmac.compare_digest(
        x_organizer_key, expected_key
    ):
        raise HTTPException(403, "Organizer approval denied")

    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row

    try:
        db.execute("BEGIN IMMEDIATE")

        proposal = db.execute(
            """
            SELECT * FROM recovery_proposals
            WHERE id = ?
            """,
            (proposal_id,)
        ).fetchone()

        if proposal is None:
            raise HTTPException(404, "Proposal not found")

        if proposal["status"] != "PENDING":
            raise HTTPException(
                409, "Proposal is no longer pending"
            )

        target = db.execute(
            """
            SELECT * FROM sessions
            WHERE event_id = ? AND id = ?
            """,
            (
                proposal["event_id"],
                proposal["session_id"]
            )
        ).fetchone()

        if target is None:
            raise HTTPException(404, "Session not found")

        # Reject proposals generated from an old schedule.
        if (
            target["room"] != proposal["original_room"]
            or target["start_time"] != proposal["original_start"]
            or target["end_time"] != proposal["original_end"]
        ):
            raise HTTPException(
                409, "Schedule has changed; generate new proposals"
            )

        room = db.execute(
            """
            SELECT * FROM rooms
            WHERE id = ? AND event_id = ?
            """,
            (
                proposal["room_id"],
                proposal["event_id"]
            )
        ).fetchone()

        if room is None:
            raise HTTPException(409, "Room unavailable")

        if (
            normalize_room(room["name"])
            == normalize_room(target["room"])
        ):
            raise HTTPException(409, "Room has not changed")

        existing = db.execute(
            """
            SELECT * FROM sessions
            WHERE event_id = ? AND id != ?
            """,
            (
                proposal["event_id"],
                proposal["session_id"]
            )
        ).fetchall()

        start = minutes(proposal["start_time"])
        end = minutes(proposal["end_time"])

        if not is_available(
            existing, target, room["name"], start, end
        ):
            raise HTTPException(
                409, "New scheduling conflict detected"
            )

        db.execute(
            """
            UPDATE sessions
            SET room = ?, start_time = ?, end_time = ?
            WHERE event_id = ? AND id = ?
            """,
            (
                room["name"],
                proposal["start_time"],
                proposal["end_time"],
                proposal["event_id"],
                proposal["session_id"]
            )
        )

        db.execute(
            """
            UPDATE recovery_proposals
            SET status = 'APPROVED'
            WHERE id = ?
            """,
            (proposal_id,)
        )

        # Reject other pending proposals for this session.
        db.execute(
            """
            UPDATE recovery_proposals
            SET status = 'SUPERSEDED'
            WHERE event_id = ?
              AND session_id = ?
              AND status = 'PENDING'
            """,
            (
                proposal["event_id"],
                proposal["session_id"]
            )
        )

        db.commit()

        return {
            "status": "APPROVED",
            "session_id": proposal["session_id"],
            "new_room": room["name"],
            "start_time": proposal["start_time"],
            "end_time": proposal["end_time"]
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
