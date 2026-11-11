import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

from paypal_webhooks import list_webhook_events


class WebhookOrganizerIsolationTests(unittest.TestCase):

    def test_organizers_only_see_their_own_webhooks(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "test-webhooks.db"

            with closing(sqlite3.connect(db_path)) as db:
                db.executescript("""
                    CREATE TABLE events (
                        id INTEGER PRIMARY KEY,
                        organizer_id TEXT
                    );

                    CREATE TABLE reservations (
                        id TEXT PRIMARY KEY,
                        event_id INTEGER
                    );

                    CREATE TABLE checkout_orders (
                        reservation_id TEXT,
                        paypal_order_id TEXT
                    );

                    CREATE TABLE verified_payments (
                        reservation_id TEXT,
                        paypal_order_id TEXT,
                        paypal_capture_id TEXT
                    );

                    CREATE TABLE refund_proposals (
                        reservation_id TEXT,
                        capture_id TEXT,
                        paypal_refund_id TEXT
                    );

                    CREATE TABLE paypal_webhook_events (
                        paypal_event_id TEXT,
                        event_type TEXT,
                        resource_id TEXT,
                        processing_state TEXT,
                        received_at TEXT
                    );

                    INSERT INTO events VALUES
                        (1, 'org-a'),
                        (2, 'org-b');

                    INSERT INTO reservations VALUES
                        ('res-a', 1),
                        ('res-b', 2);

                    INSERT INTO checkout_orders VALUES
                        ('res-a', 'order-a'),
                        ('res-b', 'order-b');

                    INSERT INTO verified_payments VALUES
                        ('res-a', 'order-a', 'capture-a'),
                        ('res-b', 'order-b', 'capture-b');

                    INSERT INTO refund_proposals VALUES
                        ('res-a', 'capture-a', 'refund-a'),
                        ('res-b', 'capture-b', 'refund-b');

                    INSERT INTO paypal_webhook_events VALUES
                        ('event-a1', 'TEST', 'order-a', 'RECORDED', '2026-01-01'),
                        ('event-a2', 'TEST', 'capture-a', 'RECORDED', '2026-01-02'),
                        ('event-a3', 'TEST', 'refund-a', 'RECORDED', '2026-01-03'),
                        ('event-b1', 'TEST', 'order-b', 'RECORDED', '2026-01-04'),
                        ('event-b2', 'TEST', 'capture-b', 'RECORDED', '2026-01-05'),
                        ('event-b3', 'TEST', 'refund-b', 'RECORDED', '2026-01-06'),
                        ('unknown', 'TEST', 'unknown-id', 'RECORDED', '2026-01-07');
                """)

            def test_connection():
                db = sqlite3.connect(db_path)
                db.row_factory = sqlite3.Row
                return db

            expected_results = {
                "org-a": {"event-a1", "event-a2", "event-a3"},
                "org-b": {"event-b1", "event-b2", "event-b3"},
            }

            for organizer_id, expected_ids in expected_results.items():
                with self.subTest(organizer=organizer_id):
                    with patch(
                        "paypal_webhooks.current_organizer_id",
                        return_value=organizer_id,
                    ), patch(
                        "paypal_webhooks.connect_db",
                        side_effect=test_connection,
                    ):
                        results = list_webhook_events(request=None)

                    actual_ids = {
                        event["paypal_event_id"]
                        for event in results
                    }

                    self.assertEqual(actual_ids, expected_ids)


if __name__ == "__main__":
    unittest.main()
