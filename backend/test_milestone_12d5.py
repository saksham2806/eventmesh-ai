"""EventMesh 12D.5 — real FastAPI route integration tests, isolated SQLite.

Copy this file into D:/eventmesh-ai/backend and run:
    python -m unittest test_milestone_12d5 -v

Does not contact PayPal or an LLM, or change existing event rows.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import multi_incident_api as preview_api
import multi_recovery_approval as approval_api
import impact_api
from event_ownership import (
    require_event_session_owner,
    require_proposal_owner,
)
from event_ownership import (
    require_event_session_owner,
    require_proposal_owner,
)


AUTH = "local-test-key-not-a-real-secret"
PREVIEW_URL = "/ai/events/2/sessions/2/multi-incident-preview"
CREATE_URL = "/ai/events/2/sessions/2/multi-recovery-proposals"


def issues():
    return [
        {"type": "ROOM_UNAVAILABLE", "room": "Hall D"},
        {"type": "SPEAKER_DELAY", "delay_minutes": 45},
    ]


def request_body():
    return {
        "description": "Hall D is unavailable and the keynote speaker is delayed by 45 minutes.",
        "issues": issues(),
        "expected_attendees": 30,
    }


class FullRecoveryFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="eventmesh-e2e-")
        self.db_path = Path(self.temp_dir.name) / "isolated_events.db"
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE events (id INTEGER PRIMARY KEY, capacity INTEGER NOT NULL);
                CREATE TABLE rooms (
                    id INTEGER PRIMARY KEY, event_id INTEGER, name TEXT, capacity INTEGER
                );
                CREATE TABLE sessions (
                    id INTEGER PRIMARY KEY, event_id INTEGER, title TEXT,
                    speaker TEXT, room TEXT, start_time TEXT, end_time TEXT
                );
                CREATE TABLE ticket_types (
                    id INTEGER PRIMARY KEY, event_id INTEGER, price_cents INTEGER, capacity INTEGER
                );
                CREATE TABLE reservations (
                    id TEXT PRIMARY KEY, event_id INTEGER, ticket_type_id INTEGER,
                    quantity INTEGER, status TEXT, expires_at TEXT
                );
                CREATE TABLE verified_payments (
                    reservation_id TEXT PRIMARY KEY, paypal_capture_id TEXT, amount_cents INTEGER
                );
                CREATE TABLE issued_tickets (
                    id TEXT PRIMARY KEY, reservation_id TEXT, status TEXT
                );
                INSERT INTO events VALUES (2, 50);
                INSERT INTO rooms VALUES (1, 2, 'Hall A', 100);
                INSERT INTO rooms VALUES (2, 2, 'Hall D', 40);
                INSERT INTO rooms VALUES (3, 2, 'Hall B', 40);
                INSERT INTO sessions VALUES
                    (2, 2, 'AI Keynote', 'Rahul', 'Hall D', '10:00', '11:00');
                INSERT INTO sessions VALUES
                    (3, 2, 'Workshop', 'Priya', 'Hall B', '10:30', '11:30');
            """)
        self.patches = [
            patch.object(preview_api, "connect_db", side_effect=self.connect),
            patch.object(approval_api, "connect_db", side_effect=self.connect),
            patch.object(impact_api, "connect_db", side_effect=self.connect),
            patch.object(preview_api, "check_organizer", side_effect=self.authorize),
            patch.object(approval_api, "check_organizer", side_effect=self.authorize),
            patch.object(impact_api, "check_organizer", side_effect=self.authorize),
        ]
        for p in self.patches:
            p.start()
        approval_api.initialize_multi_recovery()
        app = FastAPI()
        app.include_router(preview_api.router)
        app.include_router(approval_api.router)
        app.dependency_overrides[require_event_session_owner] = (
            lambda: "isolated-test-organizer"
        )

        app.dependency_overrides[require_proposal_owner] = (
            lambda: "isolated-test-organizer"
        )
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp_dir.cleanup()

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def authorize(key):
        if key != AUTH:
            raise HTTPException(403, "Unauthorized")

    def headers(self, valid=True):
        return {"x-organizer-key": AUTH if valid else "wrong-key"}

    def create(self):
        body = request_body()
        body["selected_candidate"] = {
            "room_id": 1, "start_time": "10:45", "end_time": "11:45"
        }
        result = self.client.post(CREATE_URL, json=body, headers=self.headers())
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def approve(self, proposal_id, valid=True, speaker=True):
        return self.client.post(
            f"/ai/multi-recovery-proposals/{proposal_id}/approve",
            headers=self.headers(valid),
            json={
                "confirm_room_suitability": True,
                "confirm_speaker_availability": speaker,
                "confirm_attendee_impact_reviewed": True,
            },
        )

    def session(self):
        with closing(self.connect()) as db:
            return dict(db.execute(
                "SELECT room, start_time, end_time FROM sessions WHERE id=2"
            ).fetchone())

    def test_01_preview_is_read_only_and_analyzes_bookings(self):
        response = self.client.post(PREVIEW_URL, json=request_body(), headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["status"], "CANDIDATES_PREVIEW")
        self.assertFalse(data["applied"])
        self.assertFalse(data["paypal_called"])
        self.assertFalse(data["message_sent"])
        self.assertFalse(data["can_approve_now"])
        self.assertIn("booking_summary", data["impact_report"])
        self.assertEqual(data["impact_report"]["booking_summary"]["verified_paid_seats"], 0)
        self.assertEqual(self.session()["room"], "Hall D")

    def test_02_full_preview_create_read_approve_and_audit(self):
        preview = self.client.post(PREVIEW_URL, json=request_body(), headers=self.headers())
        self.assertEqual(preview.status_code, 200, preview.text)
        selected = preview.json()["recovery_preview"]["candidates"]
        self.assertTrue(any(c["room_id"] == 1 and c["start_time"] == "10:45" for c in selected))
        created = self.create()
        self.assertEqual(created["status"], "PENDING")
        pid = created["proposal_id"]
        fetched = self.client.get(
            f"/ai/multi-recovery-proposals/{pid}", headers=self.headers()
        )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["status"], "PENDING")
        self.assertEqual(self.session()["room"], "Hall D")
        approved = self.approve(pid)
        self.assertEqual(approved.status_code, 200, approved.text)
        data = approved.json()
        self.assertTrue(data["applied"])
        self.assertFalse(data["paypal_called"])
        self.assertFalse(data["message_sent"])
        self.assertEqual(self.session(), {
            "room": "Hall A", "start_time": "10:45", "end_time": "11:45"
        })
        with closing(self.connect()) as db:
            # Verify room conflicts at the end of an actual approval transaction.
            rows = [dict(r) for r in db.execute(
                "SELECT room, start_time, end_time FROM sessions WHERE event_id=2"
            )]
            from room_utils import normalize_room
            for i, first in enumerate(rows):
                for second in rows[i+1:]:
                    collision = first["start_time"] < second["end_time"] and first["end_time"] > second["start_time"]
                    self.assertFalse(
                        collision and normalize_room(first["room"]) == normalize_room(second["room"]),
                        "Overlapping sessions in same logical room",
                    )

    def test_03_retry_reuses_proposal_and_double_approval_rejected(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(self.approve(first["proposal_id"]).status_code, 200)
        self.assertEqual(self.approve(first["proposal_id"]).status_code, 409)

    def test_04_unauthorized_cannot_create_read_or_approve(self):
        bad_create_body = request_body()
        bad_create_body["selected_candidate"] = {
            "room_id": 1, "start_time": "10:45", "end_time": "11:45"
        }
        bad = self.client.post(CREATE_URL, json=bad_create_body, headers=self.headers(False))
        self.assertEqual(bad.status_code, 403)
        pid = self.create()["proposal_id"]
        self.assertEqual(self.client.get(
            f"/ai/multi-recovery-proposals/{pid}", headers=self.headers(False)
        ).status_code, 403)
        self.assertEqual(self.approve(pid, valid=False).status_code, 403)
        self.assertEqual(self.session()["room"], "Hall D")

    def test_05_expired_proposal_rejected_without_moving_session(self):
        pid = self.create()["proposal_id"]
        with closing(self.connect()) as db:
            db.execute(
                "UPDATE multi_recovery_proposals SET expires_at=? WHERE id=?",
                ("2020-01-01T00:00:00+00:00", pid),
            )
            db.commit()
        self.assertEqual(self.approve(pid).status_code, 409)
        self.assertEqual(self.session()["room"], "Hall D")

    def test_06_stale_session_rejected_without_new_change(self):
        pid = self.create()["proposal_id"]
        with closing(self.connect()) as db:
            db.execute("UPDATE sessions SET start_time='10:15' WHERE id=2")
            db.commit()
        self.assertEqual(self.approve(pid).status_code, 409)
        self.assertEqual(self.session()["room"], "Hall D")

    def test_07_new_room_conflict_rejected(self):
        pid = self.create()["proposal_id"]
        with closing(self.connect()) as db:
            db.execute("INSERT INTO sessions VALUES (4,2,'Conflicting','Other','hall-A','11:00','12:00')")
            db.commit()
        self.assertEqual(self.approve(pid).status_code, 409)
        self.assertEqual(self.session()["room"], "Hall D")

    def test_08_room_capacity_rechecked_at_approval(self):
        pid = self.create()["proposal_id"]
        with closing(self.connect()) as db:
            db.execute("UPDATE rooms SET capacity=20 WHERE id=1")
            db.commit()
        self.assertEqual(self.approve(pid).status_code, 409)
        self.assertEqual(self.session()["room"], "Hall D")

    def test_09_confirmation_is_mandatory(self):
        pid = self.create()["proposal_id"]
        result = self.approve(pid, speaker=False)
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.session()["room"], "Hall D")

    def test_10_no_foreign_payment_or_ticket_records_written(self):
        pid = self.create()["proposal_id"]
        self.assertEqual(self.approve(pid).status_code, 200)
        with closing(self.connect()) as db:
            for table in ("reservations", "verified_payments", "issued_tickets"):
                count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertEqual(count, 0, f"Unexpected write to {table}")


if __name__ == "__main__":
    unittest.main()
