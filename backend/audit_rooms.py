
import sqlite3
from pathlib import Path
from itertools import combinations

from room_utils import normalize_room

from db_config import DB_PATH
connection = sqlite3.connect(DB_PATH)
connection.row_factory = sqlite3.Row

try:
    sessions = connection.execute(
        "SELECT * FROM sessions ORDER BY event_id, id"
    ).fetchall()
finally:
    connection.close()

conflicts = 0

print("\nEVENTMESH ROOM AUDIT")
print("=" * 40)

for first, second in combinations(sessions, 2):

    if first["event_id"] != second["event_id"]:
        continue

    same_room = (
        normalize_room(first["room"])
        == normalize_room(second["room"])
    )

    overlaps = (
        first["start_time"] < second["end_time"]
        and first["end_time"] > second["start_time"]
    )

    if same_room and overlaps:
        conflicts += 1

        print("\nROOM CONFLICT DETECTED")
        print("Event:", first["event_id"])
        print(
            f"Session {first['id']}:",
            first["title"],
            first["room"]
        )
        print(
            f"Session {second['id']}:",
            second["title"],
            second["room"]
        )

print("\nTotal conflicts:", conflicts)
