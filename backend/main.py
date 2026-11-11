
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from room_utils import normalize_room

from datetime import date
from pathlib import Path
import sqlite3

from fastapi import HTTPException
from pydantic import BaseModel, Field
import sqlite3

from pydantic import BaseModel, Field
from recovery_api import router as recovery_router

from paypal_sandbox import router as paypal_router
from ticketing_api import router as ticketing_router
from checkout_api import router as checkout_router
from ticket_fulfillment import router as fulfillment_router
from paypal_capture import router as capture_router
from paypal_webhooks import router as webhook_router
from webhook_reconciliation import router as webhook_reconciliation_router
from refund_api import router as refund_router
from refund_reconciliation import router as refund_reconciliation_router
from refund_execution import router as refund_execution_router
from agent_api import router as agent_router
from architect_api import router as architect_router
from impact_api import router as impact_router
from llm_api import router as llm_router
from incident_api import router as incident_router
from multi_incident_api import router as multi_incident_router
from auto_incident_api import router as auto_incident_router
from multi_recovery_approval import router as multi_recovery_approval_router
from organizer_auth import router as organizer_auth_router
from fastapi import FastAPI, HTTPException, Request, Depends
from event_ownership import current_organizer_id, require_event_owner

# Create our FastAPI application
app = FastAPI(
    title="EventMesh AI",
    description="The Self-Healing Event Operating System",
    version="1.0.0"
)

# Allow our future Next.js frontend to communicate
# with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET","POST"],
    allow_headers=["*"],
)


# Home endpoint
@app.get("/")
def home():
    return {
        "message": "Welcome to EventMesh AI!",
        "status": "running"
    }


# Health check endpoint
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "EventMesh AI Backend"
    }






# Database file location
from db_config import DB_PATH
# Define the information needed to create an event
class EventCreate(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = ""
    event_date: date
    venue: str = Field(min_length=2)
    capacity: int = Field(gt=0)


# Create the database table if it doesn't exist
def initialize_database():
    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                event_date TEXT NOT NULL,
                venue TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                organizer_id TEXT REFERENCES organizer_accounts(id)
            )
        """)
        # Legacy databases may predate organizer ownership. Add only the
        # column/index here. Existing unowned records must be assigned by
        # an explicit owner-aware migration; never claim them automatically.
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(events)"
            )
        }
        if "organizer_id" not in columns:
            connection.execute(
                "ALTER TABLE events ADD COLUMN organizer_id TEXT "
                "REFERENCES organizer_accounts(id)"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_organizer_id "
            "ON events(organizer_id)"
        )
        connection.commit()
    finally:
        connection.close()


initialize_database()



# Create an event for the logged-in organizer
@app.post("/events", status_code=201)
def create_event(event: EventCreate, request: Request):

    organizer_id = current_organizer_id(request)

    connection = sqlite3.connect(DB_PATH)

    try:
        cursor = connection.execute(
            """
            INSERT INTO events (
                title,
                description,
                event_date,
                venue,
                capacity,
                organizer_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.title,
                event.description,
                event.event_date.isoformat(),
                event.venue,
                event.capacity,
                organizer_id,
            ),
        )

        connection.commit()

        return {
            "id": cursor.lastrowid,
            **event.model_dump(mode="json"),
        }

    finally:
        connection.close()




# API to retrieve only the logged-in organizer's events
@app.get("/events")
def get_events(request: Request):

    # Identify the organizer from the authenticated session.
    organizer_id = current_organizer_id(request)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                description,
                event_date,
                venue,
                capacity
            FROM events
            WHERE organizer_id = ?
            ORDER BY id DESC
            """,
            (organizer_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()



class SessionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    speaker: str = Field(min_length=2, max_length=100)
    room: str = Field(min_length=2, max_length=100)

    # Time format: HH:MM (24-hour clock)
    start_time: str = Field(
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )
    end_time: str = Field(
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )


def initialize_sessions_table():
    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                speaker TEXT NOT NULL,
                room TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                FOREIGN KEY (event_id)
                    REFERENCES events(id),
                CHECK (start_time < end_time)
            )
        """)
        connection.commit()
    finally:
        connection.close()


initialize_sessions_table()



@app.post(
    "/events/{event_id}/sessions",
    status_code=201,
    dependencies=[Depends(require_event_owner)]
)

def create_session(event_id: int, session: SessionCreate):

    if session.start_time >= session.end_time:
        raise HTTPException(
            status_code=422,
            detail="End time must be after start time"
        )

    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row

    try:
        # Lock for a consistent conflict check + insertion
        connection.execute("BEGIN IMMEDIATE")

        event = connection.execute(
            "SELECT id FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        if not event:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )

        # Two sessions overlap when:
        # existing.start < new.end AND
        # existing.end > new.start
        conflict = connection.execute(
            """
            SELECT * FROM sessions
            WHERE event_id = ?
              AND start_time < ?
              AND end_time > ?
              AND (
                  room = ? COLLATE NOCASE
                  OR speaker = ? COLLATE NOCASE
              )
            LIMIT 1
            """,
            (
                event_id,
                session.end_time,
                session.start_time,
                session.room.strip(),
                session.speaker.strip(),
            )
        ).fetchone()

        if conflict:
            same_room = (
                conflict["room"].casefold()
                == session.room.strip().casefold()
            )

            reason = (
                "Room conflict" if same_room
                else "Speaker conflict"
            )

            raise HTTPException(
                status_code=409,
                detail=(
                    f"{reason}: overlaps with "
                    f"'{conflict['title']}'"
                )
            )

        cursor = connection.execute(
            """
            INSERT INTO sessions (
                event_id, title, speaker, room,
                start_time, end_time
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session.title.strip(),
                session.speaker.strip(),
                session.room.strip(),
                session.start_time,
                session.end_time,
            )
        )

        connection.commit()

        return {
            "id": cursor.lastrowid,
            "event_id": event_id,
            **session.model_dump()
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()



@app.get(
    "/events/{event_id}/sessions",
    dependencies=[Depends(require_event_owner)]
)

def get_sessions(event_id: int):
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        event = connection.execute(
            "SELECT id FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        if not event:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )

        rows = connection.execute(
            """
            SELECT * FROM sessions
            WHERE event_id = ?
            ORDER BY start_time ASC
            """,
            (event_id,)
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


# ==========================================
# EVENTMESH - SELF-HEALING RECOVERY ENGINE
# ==========================================

class RecoveryRequest(BaseModel):
    unavailable_room: str = Field(min_length=2)
    candidate_rooms: list[str] = Field(
        min_length=1,
        max_length=20
    )


def time_to_minutes(value: str) -> int:
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def minutes_to_time(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"



@app.post(
    "/events/{event_id}/sessions/{session_id}/recovery",
    dependencies=[Depends(require_event_owner)],
)


def suggest_recovery(
    event_id: int,
    session_id: int,
    request: RecoveryRequest
):
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        target = connection.execute(
            """
            SELECT * FROM sessions
            WHERE id = ? AND event_id = ?
            """,
            (session_id, event_id)
        ).fetchone()

        if target is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found"
            )

        unavailable = request.unavailable_room.strip().casefold()

        if target["room"].strip().casefold() != unavailable:
            raise HTTPException(
                status_code=422,
                detail="Unavailable room must match the session room"
            )

        existing = connection.execute(
            """
            SELECT * FROM sessions
            WHERE event_id = ? AND id != ?
            """,
            (event_id, session_id)
        ).fetchall()

        # Remove unavailable and duplicate room names.
        rooms = []
        seen = set()

        for name in request.candidate_rooms:
            room = name.strip()
            key = room.casefold()

            if room and key != unavailable and key not in seen:
                rooms.append(room)
                seen.add(key)

        original_start = time_to_minutes(target["start_time"])
        original_end = time_to_minutes(target["end_time"])
        duration = original_end - original_start

        # MVP operates from 09:00 to 18:00.
        opening = 9 * 60
        closing = 18 * 60

        possible_starts = set(
            range(opening, closing - duration + 1, 30)
        )

        # Include original time even when not on a
        # half-hour boundary.
        possible_starts.add(original_start)

        possible_starts = [
            start for start in possible_starts
            if opening <= start
            and start + duration <= closing
        ]

        # Prefer times closest to the original.
        # For equal distance, prefer a later slot.
        possible_starts.sort(
            key=lambda start: (
                abs(start - original_start),
                start < original_start
            )
        )

        suggestions = []

        for start in possible_starts:
            end = start + duration

            for room in rooms:
                conflict_found = False

                for booked in existing:
                    booked_start = time_to_minutes(
                        booked["start_time"]
                    )
                    booked_end = time_to_minutes(
                        booked["end_time"]
                    )

                    overlaps = (
                        start < booked_end
                        and end > booked_start
                    )

                    same_room = (
                        room.casefold()
                        == booked["room"].strip().casefold()
                    )

                    same_speaker = (
                        target["speaker"].strip().casefold()
                        == booked["speaker"].strip().casefold()
                    )

                    if overlaps and (same_room or same_speaker):
                        conflict_found = True
                        break

                if not conflict_found:
                    suggestions.append({
                        "room": room,
                        "start_time": minutes_to_time(start),
                        "end_time": minutes_to_time(end),
                        "time_shift_minutes": (
                            start - original_start
                        )
                    })

                if len(suggestions) >= 3:
                    break

            if len(suggestions) >= 3:
                break

        return {
            "session_id": session_id,
            "session_title": target["title"],
            "problem": (
                f"Room {request.unavailable_room} unavailable"
            ),
            "status": (
                "PROPOSALS_READY"
                if suggestions else "NO_SOLUTION"
            ),
            "suggestions": suggestions,
            "applied": False
        }

    finally:
        connection.close()


# ========================================
# EVENTMESH AI - ROOM REGISTRY
# ========================================

class RoomCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    capacity: int = Field(gt=0)


def initialize_rooms_table():
    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                room_key TEXT NOT NULL,
                capacity INTEGER NOT NULL CHECK(capacity > 0),

                FOREIGN KEY (event_id)
                    REFERENCES events(id),

                UNIQUE(event_id, room_key)
            )
        """)
        connection.commit()

    finally:
        connection.close()


initialize_rooms_table()


@app.post(
    "/events/{event_id}/rooms",
    status_code=201,
    dependencies=[Depends(require_event_owner)]
)

def create_room(event_id: int, room: RoomCreate):

    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("BEGIN IMMEDIATE")

        # Check that the event exists
        event = connection.execute(
            "SELECT id FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        if event is None:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )

        room_name = room.name.strip()
        room_key = normalize_room(room_name)

        if not room_key:
            raise HTTPException(
                status_code=422,
                detail="Invalid room name"
            )

        # Prevent duplicate room registrations
        existing = connection.execute(
            """
            SELECT id FROM rooms
            WHERE event_id = ? AND room_key = ?
            """,
            (event_id, room_key)
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="Room already registered"
            )

        cursor = connection.execute(
            """
            INSERT INTO rooms
            (event_id, name, room_key, capacity)
            VALUES (?, ?, ?, ?)
            """,
            (
                event_id,
                room_name,
                room_key,
                room.capacity
            )
        )

        connection.commit()

        return {
            "id": cursor.lastrowid,
            "event_id": event_id,
            "name": room_name,
            "capacity": room.capacity
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


@app.get(
    "/events/{event_id}/rooms",
    dependencies=[Depends(require_event_owner)]
)

def get_rooms(event_id: int):

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        event = connection.execute(
            "SELECT id FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        if event is None:
            raise HTTPException(
                status_code=404,
                detail="Event not found"
            )

        rooms = connection.execute(
            """
            SELECT id, event_id, name, capacity
            FROM rooms
            WHERE event_id = ?
            ORDER BY name COLLATE NOCASE
            """,
            (event_id,)
        ).fetchall()

        return [dict(room) for room in rooms]

    finally:
        connection.close()


app.include_router(recovery_router)
app.include_router(paypal_router)
app.include_router(ticketing_router)
app.include_router(checkout_router)
app.include_router(fulfillment_router)
app.include_router(capture_router)
app.include_router(webhook_router)
app.include_router(webhook_reconciliation_router)
app.include_router(refund_router)
app.include_router(refund_reconciliation_router)
app.include_router(refund_execution_router)
app.include_router(agent_router)
app.include_router(architect_router)
app.include_router(impact_router)
app.include_router(llm_router)
app.include_router(incident_router)
app.include_router(multi_incident_router)
app.include_router(auto_incident_router)
app.include_router(multi_recovery_approval_router)
app.include_router(organizer_auth_router)
