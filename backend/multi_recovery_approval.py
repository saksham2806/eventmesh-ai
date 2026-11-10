"""EventMesh AI 12D.4B — stored multi-issue recovery with safe approval.

Development-only authorization: uses EVENTMESH_ORGANIZER_KEY from ticketing_api.
Approval never contacts PayPal and never sends attendee communications.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException,Depends
from pydantic import BaseModel, ConfigDict, Field

from multi_incident_api import IncidentIssue, MultiIncidentRequest
from multi_incident_planner import plan_multi_disruption
from ticketing_api import check_organizer, connect_db
from event_ownership import require_event_session_owner, require_proposal_owner

router = APIRouter(tags=["AI Multi-Issue Approval"])


class SelectedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id: int = Field(ge=1)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")


class CreateCombinedProposal(MultiIncidentRequest):
    selected_candidate: SelectedCandidate


class ApproveCombinedProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_room_suitability: bool
    confirm_speaker_availability: bool
    confirm_attendee_impact_reviewed: bool


def utc_now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


def initialize_multi_recovery():
    db = connect_db()
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS multi_recovery_proposals (
                id TEXT PRIMARY KEY,
                event_id INTEGER NOT NULL,
                session_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                issues_json TEXT NOT NULL,
                required_capacity INTEGER NOT NULL,
                original_room TEXT NOT NULL,
                original_speaker TEXT,
                original_start TEXT NOT NULL,
                original_end TEXT NOT NULL,
                target_room_id INTEGER NOT NULL,
                target_start TEXT NOT NULL,
                target_end TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'PENDING', 'APPROVED', 'EXPIRED', 'SUPERSEDED'
                )),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                approved_at TEXT
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_multi_recovery_session
            ON multi_recovery_proposals(event_id, session_id, status)
        """)
        db.commit()
    finally:
        db.close()


initialize_multi_recovery()


def _read_context(db, event_id, session_id):
    event = db.execute(
        "SELECT id, capacity FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if event is None:
        raise HTTPException(404, "Event not found")

    session = db.execute(
        """SELECT id, title, speaker, room, start_time, end_time
           FROM sessions WHERE event_id = ? AND id = ?""",
        (event_id, session_id),
    ).fetchone()
    if session is None:
        raise HTTPException(404, "Session not found")

    rooms = db.execute(
        "SELECT id, name, capacity FROM rooms WHERE event_id = ?",
        (event_id,),
    ).fetchall()
    others = db.execute(
        """SELECT id, speaker, room, start_time, end_time FROM sessions
           WHERE event_id = ? AND id != ?""", (event_id, session_id)
    ).fetchall()
    return (
        dict(event), dict(session),
        [dict(r) for r in rooms], [dict(s) for s in others]
    )


def _get_fresh_candidate(session, rooms, others, issues, required_capacity, selected):
    try:
        plan = plan_multi_disruption(
            session=session, rooms=rooms, other_sessions=others,
            issues=issues, required_capacity=required_capacity,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, "Cannot validate recovery plan: " + str(exc)) from exc
    matching = next((c for c in plan["candidates"]
                     if c["room_id"] == selected["room_id"]
                     and c["start_time"] == selected["start_time"]
                     and c["end_time"] == selected["end_time"]), None)
    if not matching:
        raise HTTPException(
            409, "Selected room/time is no longer a valid recovery candidate"
        )
    return matching


def _snapshot_matches(session, proposal):
    return (
        session["room"] == proposal["original_room"]
        and session["speaker"] == proposal["original_speaker"]
        and session["start_time"] == proposal["original_start"]
        and session["end_time"] == proposal["original_end"]
    )


@router.post(
    "/ai/events/{event_id}/sessions/{session_id}/multi-recovery-proposals",
    dependencies=[Depends(require_event_session_owner)],
    status_code=201,
)
def create_combined_proposal(
    event_id: int,
    session_id: int,
    request: CreateCombinedProposal,
    x_organizer_key: str | None = Header(default=None),
):
    check_organizer(x_organizer_key)

    db = connect_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        event, session, rooms, others = _read_context(db, event_id, session_id)
        required_capacity = request.expected_attendees or event["capacity"]
        if required_capacity > event["capacity"]:
            raise HTTPException(422, "Expected attendees exceed event capacity")

        issues = [i.model_dump() for i in request.issues]
        selected = request.selected_candidate.model_dump()
        fresh = _get_fresh_candidate(session, rooms, others, issues,
                                     required_capacity, selected)
        issues_json = json.dumps(issues, sort_keys=True)

        # Reuse a pending proposal rather than duplicating it on retries.
        old = db.execute("""
            SELECT id, expires_at FROM multi_recovery_proposals
            WHERE event_id = ? AND session_id = ? AND status = 'PENDING'
              AND original_room = ? AND original_speaker IS ?
              AND original_start = ? AND original_end = ?
              AND issues_json = ? AND required_capacity = ?
              AND target_room_id = ? AND target_start = ? AND target_end = ?
            ORDER BY created_at DESC LIMIT 1
        """, (
            event_id, session_id, session["room"], session["speaker"],
            session["start_time"], session["end_time"], issues_json,
            required_capacity, selected["room_id"], selected["start_time"],
            selected["end_time"],
        )).fetchone()
        now = utc_now()
        if old is not None and datetime.fromisoformat(old["expires_at"]) > now:
            db.commit()
            return {
                "status": "PENDING", "proposal_id": old["id"],
                "candidate": fresh, "expires_at": old["expires_at"],
                "applied": False, "paypal_called": False, "reused": True,
            }

        proposal_id = uuid4().hex
        expires = _iso(now + timedelta(minutes=30))
        db.execute("""
            INSERT INTO multi_recovery_proposals (
                id, event_id, session_id, description, issues_json,
                required_capacity, original_room, original_speaker,
                original_start, original_end, target_room_id,
                target_start, target_end, status, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
        """, (
            proposal_id, event_id, session_id, request.description,
            issues_json, required_capacity, session["room"], session["speaker"],
            session["start_time"], session["end_time"],
            selected["room_id"], selected["start_time"],
            selected["end_time"], _iso(now), expires,
        ))
        db.commit()
        return {
            "status": "PENDING", "proposal_id": proposal_id,
            "candidate": fresh, "expires_at": expires,
            "applied": False, "paypal_called": False, "reused": False,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/ai/multi-recovery-proposals/{proposal_id}/approve",
             dependencies=[Depends(require_proposal_owner)])
def approve_combined_proposal(
    proposal_id: str,
    request: ApproveCombinedProposal,
    x_organizer_key: str | None = Header(default=None),
):
    check_organizer(x_organizer_key)
    if not (
        request.confirm_room_suitability
        and request.confirm_speaker_availability
        and request.confirm_attendee_impact_reviewed
    ):
        raise HTTPException(
            422, "Organizer must confirm room suitability, speaker availability "
                 "and attendee impact review before approval"
        )

    db = connect_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM multi_recovery_proposals WHERE id = ?",
                         (proposal_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Combined recovery proposal not found")
        proposal = dict(row)
        if proposal["status"] != "PENDING":
            raise HTTPException(409, f"Proposal is {proposal['status'].lower()}")
        if datetime.fromisoformat(proposal["expires_at"]) <= utc_now():
            db.execute("UPDATE multi_recovery_proposals SET status = 'EXPIRED' WHERE id = ?",
                       (proposal_id,))
            db.commit()
            raise HTTPException(409, "Proposal expired. Generate a new preview")

        event, session, rooms, others = _read_context(
            db, proposal["event_id"], proposal["session_id"]
        )
        if not _snapshot_matches(session, proposal):
            raise HTTPException(409, "Session changed. Generate a new proposal")
        if proposal["required_capacity"] > event["capacity"]:
            raise HTTPException(409, "Event capacity changed")

        issues = json.loads(proposal["issues_json"])
        chosen = {
            "room_id": proposal["target_room_id"],
            "start_time": proposal["target_start"],
            "end_time": proposal["target_end"],
        }
        fresh = _get_fresh_candidate(
            session, rooms, others, issues,
            proposal["required_capacity"], chosen,
        )

        updated = db.execute("""
            UPDATE sessions SET room = ?, start_time = ?, end_time = ?
            WHERE id = ? AND event_id = ? AND room = ?
              AND start_time = ? AND end_time = ?
        """, (
            fresh["room"], fresh["start_time"], fresh["end_time"],
            proposal["session_id"], proposal["event_id"],
            proposal["original_room"], proposal["original_start"],
            proposal["original_end"],
        ))
        if updated.rowcount != 1:
            raise HTTPException(409, "Session changed during approval")

        db.execute("""
            UPDATE multi_recovery_proposals
            SET status = 'APPROVED', approved_at = ? WHERE id = ?
        """, (_iso(utc_now()), proposal_id))
        db.execute("""
            UPDATE multi_recovery_proposals SET status = 'SUPERSEDED'
            WHERE event_id = ? AND session_id = ?
              AND status = 'PENDING' AND id != ?
        """, (proposal["event_id"], proposal["session_id"], proposal_id))
        db.commit()
        return {
            "status": "APPROVED", "proposal_id": proposal_id,
            "event_id": proposal["event_id"],
            "session_id": proposal["session_id"],
            "room": fresh["room"], "start_time": fresh["start_time"],
            "end_time": fresh["end_time"],
            "applied": True, "paypal_called": False, "message_sent": False,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.get("/ai/multi-recovery-proposals/{proposal_id}",
            dependencies=[Depends(require_proposal_owner)])
def get_combined_proposal(
    proposal_id: str,
    x_organizer_key: str | None = Header(default=None),
):
    check_organizer(x_organizer_key)
    db = connect_db()
    try:
        row = db.execute("SELECT * FROM multi_recovery_proposals WHERE id = ?",
                         (proposal_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Combined recovery proposal not found")
        record = dict(row)
        return {
            "proposal_id": record["id"], "status": record["status"],
            "event_id": record["event_id"], "session_id": record["session_id"],
            "issues": json.loads(record["issues_json"]),
            "required_capacity": record["required_capacity"],
            "selected_candidate": {
                "room_id": record["target_room_id"],
                "start_time": record["target_start"],
                "end_time": record["target_end"],
            },
            "expires_at": record["expires_at"],
            "approved_at": record["approved_at"],
            "paypal_called": False,
        }
    finally:
        db.close()
