"""Isolated SQLite tests for Milestone 12D.4B. No PayPal calls."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from fastapi import HTTPException

import multi_recovery_approval as api
from multi_incident_api import IncidentIssue


class MultiRecoveryApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "safe_recovery_test.db"
        self.connect_patch = patch.object(api, "connect_db", side_effect=self.connect)
        self.auth_patch = patch.object(api, "check_organizer", side_effect=self.require_key)
        self.connect_patch.start()
        self.auth_patch.start()
        self.addCleanup(self.connect_patch.stop)
        self.addCleanup(self.auth_patch.stop)
        # Cleanup patches BEFORE the temporary DB directory is removed.
        self.addCleanup(self.tmp.cleanup)
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE events (id INTEGER PRIMARY KEY, capacity INTEGER NOT NULL);
                CREATE TABLE sessions (
                    id INTEGER PRIMARY KEY, event_id INTEGER, title TEXT,
                    speaker TEXT, room TEXT, start_time TEXT, end_time TEXT
                );
                CREATE TABLE rooms (
                    id INTEGER PRIMARY KEY, event_id INTEGER, name TEXT,
                    capacity INTEGER NOT NULL
                );
                INSERT INTO events VALUES (2,50);
                INSERT INTO rooms VALUES (1,2,'Hall A',100);
                INSERT INTO rooms VALUES (2,2,'Hall D',40);
                INSERT INTO rooms VALUES (3,2,'Hall B',40);
                INSERT INTO sessions VALUES (
                    2,2,'AI Keynote','Rahul','Hall D','10:00','11:00'
                );
                INSERT INTO sessions VALUES (
                    3,2,'Workshop','Priya','Hall B','10:30','11:30'
                );
            """)
        api.initialize_multi_recovery()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def require_key(key):
        if key != "demo-organizer-key":
            raise HTTPException(403, "Unauthorized")

    def proposal_body(self, start="10:45", end="11:45"):
        return api.CreateCombinedProposal(
            description="Hall D is unavailable and keynote speaker is 45 minutes late",
            issues=[
                IncidentIssue(type="ROOM_UNAVAILABLE", room="Hall D"),
                IncidentIssue(type="SPEAKER_DELAY", delay_minutes=45),
            ],
            expected_attendees=30,
            selected_candidate=api.SelectedCandidate(
                room_id=1, start_time=start, end_time=end
            ),
        )

    def create(self):
        return api.create_combined_proposal(
            2, 2, self.proposal_body(), x_organizer_key="demo-organizer-key"
        )

    def approve(self, pid, **overrides):
        confirmations = {
            "confirm_room_suitability": True,
            "confirm_speaker_availability": True,
            "confirm_attendee_impact_reviewed": True,
        }
        confirmations.update(overrides)
        return api.approve_combined_proposal(
            pid, api.ApproveCombinedProposal(**confirmations),
            x_organizer_key="demo-organizer-key",
        )

    def test_approval_changes_schedule_once(self):
        pid = self.create()["proposal_id"]
        result = self.approve(pid)
        self.assertEqual(result["status"], "APPROVED")
        self.assertFalse(result["paypal_called"])
        with closing(self.connect()) as db:
            row = db.execute("SELECT room,start_time,end_time FROM sessions WHERE id=2").fetchone()
            self.assertEqual(tuple(row), ("Hall A", "10:45", "11:45"))
        with self.assertRaises(HTTPException) as ctx:
            self.approve(pid)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_request_is_reused(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertTrue(second["reused"])

    def test_changed_session_rejected(self):
        pid = self.create()["proposal_id"]
        with closing(self.connect()) as db:
            db.execute("UPDATE sessions SET start_time='10:30' WHERE id=2")
            db.commit()
        with self.assertRaises(HTTPException) as ctx:
            self.approve(pid)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_new_room_conflict_rejected(self):
        pid = self.create()["proposal_id"]
        with closing(self.connect()) as db:
            db.execute("INSERT INTO sessions VALUES (4,2,'Another','Other','Hall A','10:30','11:45')")
            db.commit()
        with self.assertRaises(HTTPException) as ctx:
            self.approve(pid)
        self.assertEqual(ctx.exception.status_code, 409)
        with closing(self.connect()) as db:
            self.assertEqual(db.execute("SELECT room FROM sessions WHERE id=2").fetchone()[0], "Hall D")

    def test_capacity_changed_rejected(self):
        pid = self.create()["proposal_id"]
        with closing(self.connect()) as db:
            db.execute("UPDATE rooms SET capacity=20 WHERE id=1")
            db.commit()
        with self.assertRaises(HTTPException) as ctx:
            self.approve(pid)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_expired_proposal_rejected(self):
        pid = self.create()["proposal_id"]
        with closing(self.connect()) as db:
            db.execute("UPDATE multi_recovery_proposals SET expires_at=? WHERE id=?",
                       ("2020-01-01T00:00:00+00:00", pid))
            db.commit()
        with self.assertRaises(HTTPException) as ctx:
            self.approve(pid)
        self.assertEqual(ctx.exception.status_code, 409)
        with closing(self.connect()) as db:
            status = db.execute("SELECT status FROM multi_recovery_proposals WHERE id=?", (pid,)).fetchone()[0]
            self.assertEqual(status, "EXPIRED")

    def test_unconfirmed_assumptions_rejected(self):
        pid = self.create()["proposal_id"]
        with self.assertRaises(HTTPException) as ctx:
            self.approve(pid, confirm_speaker_availability=False)
        self.assertEqual(ctx.exception.status_code, 422)
        with closing(self.connect()) as db:
            self.assertEqual(db.execute("SELECT room FROM sessions WHERE id=2").fetchone()[0], "Hall D")

    def test_invalid_selection_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            api.create_combined_proposal(2,2,self.proposal_body("10:15", "11:15"),
                                        x_organizer_key="demo-organizer-key")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_cancelled_session_cannot_be_rescheduled(self):
        req = self.proposal_body()
        req.issues = [IncidentIssue(type="SESSION_CANCELLED")]
        with self.assertRaises(HTTPException) as ctx:
            api.create_combined_proposal(2,2,req,
                                        x_organizer_key="demo-organizer-key")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_organizer_authorization_required(self):
        with self.assertRaises(HTTPException) as ctx:
            api.create_combined_proposal(2,2,self.proposal_body(),
                                        x_organizer_key="invalid")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_get_proposal(self):
        pid = self.create()["proposal_id"]
        data = api.get_combined_proposal(pid, x_organizer_key="demo-organizer-key")
        self.assertEqual(data["status"], "PENDING")
        self.assertEqual(data["selected_candidate"]["start_time"], "10:45")
        self.assertFalse(data["paypal_called"])


if __name__ == "__main__":
    unittest.main()
