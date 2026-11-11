
import hmac
import os
import sqlite3

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel, Field
from event_ownership import require_event_owner

load_dotenv(Path(__file__).parent / ".env")

router = APIRouter(tags=["Ticketing"])

from db_config import DB_PATH
# =====================================
# 1. REQUEST MODELS
# =====================================

class TicketTypeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    price_usd: Decimal = Field(
        gt=0, max_digits=8, decimal_places=2
    )
    capacity: int = Field(ge=1)


class ReservationCreate(BaseModel):
    ticket_type_id: int
    quantity: int = Field(ge=1, le=5)


def connect_db():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


# =====================================
# 2. DATABASE TABLES
# =====================================

def initialize_ticketing():
    db = connect_db()

    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS ticket_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES events(id),
                name TEXT NOT NULL COLLATE NOCASE,
                price_cents INTEGER NOT NULL CHECK(price_cents > 0),
                capacity INTEGER NOT NULL CHECK(capacity > 0),
                UNIQUE(event_id, name)
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES events(id),
                ticket_type_id INTEGER NOT NULL
                    REFERENCES ticket_types(id),
                quantity INTEGER NOT NULL
                    CHECK(quantity BETWEEN 1 AND 5),
                status TEXT NOT NULL CHECK(
                    status IN (
                        'PENDING_PAYMENT',
                        'PAID',
                        'EXPIRED',
                        'CANCELLED'
                    )
                ),
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

        db.commit()
    finally:
        db.close()


initialize_ticketing()


# =====================================
# 3. HELPERS
# =====================================

def check_organizer(key):
    expected = os.getenv("EVENTMESH_ORGANIZER_KEY")

    if not expected:
        raise HTTPException(
            503, "Organizer key not configured"
        )

    if not key or not hmac.compare_digest(key, expected):
        raise HTTPException(403, "Unauthorized")


def occupied_seats(db, event_id, now, ticket_type_id=None):
    query = """
        SELECT COALESCE(SUM(quantity), 0)
        FROM reservations
        WHERE event_id = ?
          AND (
              status = 'PAID'
              OR (
                  status = 'PENDING_PAYMENT'
                  AND expires_at > ?
              )
          )
    """

    values = [event_id, now]

    if ticket_type_id is not None:
        query += " AND ticket_type_id = ?"
        values.append(ticket_type_id)

    return int(db.execute(query, values).fetchone()[0])


# =====================================
# 4. CREATE TICKET CATEGORY
# =====================================


@router.post(
    "/events/{event_id}/ticket-types",
    status_code=201,
    dependencies=[Depends(require_event_owner)]
)

def create_ticket_type(
    event_id: int,
    ticket: TicketTypeCreate,
    x_organizer_key: str | None = Header(default=None)
):
    check_organizer(x_organizer_key)

    name = ticket.name.strip()

    if len(name) < 2:
        raise HTTPException(422, "Invalid ticket name")

    db = connect_db()

    try:
        db.execute("BEGIN IMMEDIATE")

        event = db.execute(
            "SELECT capacity FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        if event is None:
            raise HTTPException(404, "Event not found")

        existing_capacity = db.execute(
            """
            SELECT COALESCE(SUM(capacity), 0)
            FROM ticket_types WHERE event_id = ?
            """,
            (event_id,)
        ).fetchone()[0]

        if existing_capacity + ticket.capacity > event["capacity"]:
            raise HTTPException(
                409,
                "Ticket categories exceed event capacity"
            )

        price_cents = int(ticket.price_usd * 100)

        try:
            cursor = db.execute(
                """
                INSERT INTO ticket_types
                (event_id, name, price_cents, capacity)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event_id,
                    name,
                    price_cents,
                    ticket.capacity
                )
            )
        except sqlite3.IntegrityError:
            raise HTTPException(
                409, "Ticket category already exists"
            )

        db.commit()

        return {
            "id": cursor.lastrowid,
            "event_id": event_id,
            "name": name,
            "price_usd": money(price_cents),
            "capacity": ticket.capacity
        }

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =====================================
# 5. LIST TICKET CATEGORIES
# =====================================


@router.get(
    "/events/{event_id}/ticket-types",
    dependencies=[Depends(require_event_owner)]
)

def list_ticket_types(event_id: int):
    db = connect_db()

    try:
        event = db.execute(
            "SELECT id FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        if event is None:
            raise HTTPException(404, "Event not found")

        rows = db.execute(
            """
            SELECT * FROM ticket_types
            WHERE event_id = ?
            ORDER BY id
            """,
            (event_id,)
        ).fetchall()

        now = datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds")

        result = []

        for row in rows:
            occupied = occupied_seats(
                db, event_id, now, row["id"]
            )

            result.append({
                "id": row["id"],
                "name": row["name"],
                "price_usd": money(row["price_cents"]),
                "capacity": row["capacity"],
                "available": row["capacity"] - occupied
            })

        return result

    finally:
        db.close()


# =====================================
# 6. RESERVE TICKETS
# =====================================


@router.post(
    "/events/{event_id}/reservations",
    status_code=201,
    dependencies=[Depends(require_event_owner)]
)

def reserve_tickets(
    event_id: int,
    request: ReservationCreate
):
    db = connect_db()

    try:
        # Prevent simultaneous reservations
        # from overselling the same seats.
        db.execute("BEGIN IMMEDIATE")

        event = db.execute(
            "SELECT capacity FROM events WHERE id = ?",
            (event_id,)
        ).fetchone()

        ticket = db.execute(
            """
            SELECT * FROM ticket_types
            WHERE id = ? AND event_id = ?
            """,
            (request.ticket_type_id, event_id)
        ).fetchone()

        if event is None or ticket is None:
            raise HTTPException(
                404, "Event or ticket category not found"
            )

        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat(timespec="seconds")

        expires_at = (
            now_dt + timedelta(minutes=45)
        ).isoformat(timespec="seconds")

        # Release expired reservations.
        db.execute(
            """
            UPDATE reservations
            SET status = 'EXPIRED'
            WHERE status = 'PENDING_PAYMENT'
              AND expires_at <= ?
            """,
            (now,)
        )

        category_occupied = occupied_seats(
            db, event_id, now, ticket["id"]
        )

        total_occupied = occupied_seats(
            db, event_id, now
        )

        if category_occupied + request.quantity > ticket["capacity"]:
            raise HTTPException(
                409, "Not enough tickets in this category"
            )

        if total_occupied + request.quantity > event["capacity"]:
            raise HTTPException(
                409, "Event capacity exceeded"
            )

        reservation_id = uuid4().hex

        db.execute(
            """
            INSERT INTO reservations (
                id, event_id, ticket_type_id,
                quantity, status, expires_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reservation_id,
                event_id,
                ticket["id"],
                request.quantity,
                "PENDING_PAYMENT",
                expires_at,
                now
            )
        )

        db.commit()

        total_cents = (
            ticket["price_cents"] * request.quantity
        )

        return {
            "reservation_id": reservation_id,
            "status": "PENDING_PAYMENT",
            "quantity": request.quantity,
            "total_usd": money(total_cents),
            "expires_at": expires_at,
            "payment_created": False
        }

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
