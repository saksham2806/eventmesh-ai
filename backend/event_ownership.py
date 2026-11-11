
import sqlite3
from pathlib import Path

from fastapi import HTTPException, Request
from organizer_auth import authenticated_organizer

from db_config import DB_PATH
def current_organizer_id(request: Request) -> str:
    organizer = authenticated_organizer(request)
    return organizer["id"]


def require_event_owner(
    request: Request,
    event_id: int
) -> str:
    organizer_id = current_organizer_id(request)

    db = sqlite3.connect(DB_PATH, timeout=10)

    try:
        event = db.execute(
            """
            SELECT id
            FROM events
            WHERE id = ?
              AND organizer_id = ?
            """,
            (event_id, organizer_id)
        ).fetchone()

        if event is None:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )

        return organizer_id

    finally:
        db.close()







def require_reservation_owner(
    request: Request,
    reservation_id: str
) -> str:
    organizer_id = current_organizer_id(request)

    db = sqlite3.connect(DB_PATH, timeout=10)

    try:
        reservation = db.execute(
            """
            SELECT r.id
            FROM reservations r
            JOIN events e
              ON e.id = r.event_id
            WHERE r.id = ?
              AND e.organizer_id = ?
            """,
            (reservation_id, organizer_id)
        ).fetchone()

        if reservation is None:
            raise HTTPException(
                status_code=404,
                detail="Reservation not found"
            )

        return organizer_id

    finally:
        db.close()


def require_proposal_owner(
    request: Request,
    proposal_id: str
) -> str:
    organizer_id = current_organizer_id(request)

    db = sqlite3.connect(DB_PATH, timeout=10)

    try:
        proposal = db.execute(
            """
            SELECT p.id
            FROM multi_recovery_proposals p
            JOIN events e
              ON e.id = p.event_id
            WHERE p.id = ?
              AND e.organizer_id = ?
            """,
            (proposal_id, organizer_id)
        ).fetchone()

        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail="Combined recovery proposal not found"
            )

        return organizer_id

    finally:
        db.close()


def require_event_session_owner(
    request: Request,
    event_id: int,
    session_id: int
) -> str:
    organizer_id = current_organizer_id(request)

    db = sqlite3.connect(DB_PATH, timeout=10)

    try:
        row = db.execute(
            """
            SELECT s.id
            FROM sessions s
            JOIN events e
              ON e.id = s.event_id
            WHERE s.id = ?
              AND s.event_id = ?
              AND e.organizer_id = ?
            """,
            (session_id, event_id, organizer_id)
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Event or session not found"
            )

        return organizer_id

    finally:
        db.close()

def require_legacy_recovery_proposal_owner(
    request: Request,
    proposal_id: str,
) -> str:
    organizer_id = current_organizer_id(request)

    db = sqlite3.connect(DB_PATH, timeout=10)

    try:
        row = db.execute(
            """
            SELECT p.id
            FROM recovery_proposals p
            JOIN events e
                ON e.id = p.event_id
            WHERE p.id = ?
              AND e.organizer_id = ?
            """,
            (proposal_id, organizer_id),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Recovery proposal not found",
            )

        return organizer_id

    finally:
        db.close()


def require_refund_proposal_owner(
    request: Request,
    proposal_id: str,
) -> str:
    organizer_id = current_organizer_id(request)

    db = sqlite3.connect(DB_PATH, timeout=10)

    try:
        row = db.execute(
            """
            SELECT p.id
            FROM refund_proposals p
            JOIN reservations r
                ON r.id = p.reservation_id
            JOIN events e
                ON e.id = r.event_id
            WHERE p.id = ?
              AND e.organizer_id = ?
            """,
            (proposal_id, organizer_id),
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Refund proposal not found",
            )

        return organizer_id

    finally:
        db.close()
