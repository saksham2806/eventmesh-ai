
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "events.db"

def migrate():
    if not DB_PATH.is_file():
        raise RuntimeError("Database file not found")

    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    try:
        accounts = db.execute(
            "SELECT id FROM organizer_accounts"
        ).fetchall()

        if len(accounts) != 1:
            raise RuntimeError(
                "Expected exactly one organizer account"
            )

        organizer_id = accounts[0]["id"]

        # Create a complete backup before changing anything.
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )
        backup_path = DB_PATH.with_name(
            f"events.before_ownership_{timestamp}.db"
        )

        with sqlite3.connect(backup_path) as backup:
            db.backup(backup)

        print("Database backup:", backup_path)

        db.execute("BEGIN IMMEDIATE")

        columns = [
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(events)"
            )
        ]

        if "organizer_id" not in columns:
            db.execute("""
                ALTER TABLE events
                ADD COLUMN organizer_id TEXT
                REFERENCES organizer_accounts(id)
            """)

        # Assign existing unowned demo events to
        # the currently registered organizer.
        db.execute("""
            UPDATE events
            SET organizer_id = ?
            WHERE organizer_id IS NULL
        """, (organizer_id,))

        db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_events_organizer_id
            ON events(organizer_id)
        """)

        db.commit()

        events = db.execute("""
            SELECT id, title, organizer_id
            FROM events
            ORDER BY id
        """).fetchall()

        print("\nMIGRATION COMPLETE")

        for event in events:
            print(
                event["id"],
                "|",
                event["title"],
                "| owner:",
                event["organizer_id"]
            )

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
