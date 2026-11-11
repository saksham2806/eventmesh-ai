
import sqlite3
from pathlib import Path
from room_utils import normalize_room

from db_config import DB_PATH
EVENT_ID = 2
SESSION_ID = 4
NEW_ROOM = "Hall C"

connection = sqlite3.connect(DB_PATH)
connection.row_factory = sqlite3.Row

try:
    connection.execute("BEGIN IMMEDIATE")

    target = connection.execute(
        """
        SELECT * FROM sessions
        WHERE id = ? AND event_id = ?
        """,
        (SESSION_ID, EVENT_ID)
    ).fetchone()

    if target is None:
        raise ValueError("Session not found")

    others = connection.execute(
        """
        SELECT * FROM sessions
        WHERE event_id = ?
          AND id != ?
          AND start_time < ?
          AND end_time > ?
        """,
        (
            EVENT_ID,
            SESSION_ID,
            target["end_time"],
            target["start_time"]
        )
    ).fetchall()

    for other in others:
        same_room = (
            normalize_room(other["room"])
            == normalize_room(NEW_ROOM)
        )

        same_speaker = (
            other["speaker"].strip().casefold()
            == target["speaker"].strip().casefold()
        )

        if same_room or same_speaker:
            raise ValueError(
                f"Conflict with session {other['id']}"
            )

    connection.execute(
        """
        UPDATE sessions
        SET room = ?
        WHERE id = ? AND event_id = ?
        """,
        (NEW_ROOM, SESSION_ID, EVENT_ID)
    )

    connection.commit()
    print("Session updated successfully!")
    print(f"Session {SESSION_ID} moved to {NEW_ROOM}")

except Exception:
    connection.rollback()
    raise

finally:
    connection.close()
