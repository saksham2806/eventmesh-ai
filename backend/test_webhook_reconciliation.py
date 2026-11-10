
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import paypal_webhooks
import webhook_reconciliation


class WebhookReconciliationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "webhook_test.db"

        self.env_patch = patch.dict(os.environ, {
            "EVENTMESH_ORGANIZER_KEY": "offline-test-key"
        })
        self.env_patch.start()

        self.path_patch = patch.object(
            paypal_webhooks, "DB_PATH", self.db_path
        )
        self.path_patch.start()

        self.sandbox_patch = patch.object(
            webhook_reconciliation,
            "PAYPAL_BASE",
            "https://api-m.sandbox.paypal.com"
        )
        self.sandbox_patch.start()

        paypal_webhooks.initialize_webhook_table(self.db_path)

        with closing(sqlite3.connect(self.db_path)) as db:
            db.executescript("""
                CREATE TABLE reservations (
                    id TEXT PRIMARY KEY,
                    status TEXT,
                    quantity INTEGER
                );

                CREATE TABLE verified_payments (
                    reservation_id TEXT PRIMARY KEY,
                    paypal_capture_id TEXT,
                    amount_cents INTEGER,
                    currency TEXT
                );

                CREATE TABLE checkout_orders (
                    reservation_id TEXT PRIMARY KEY,
                    status TEXT
                );

                CREATE TABLE issued_tickets (
                    id TEXT PRIMARY KEY,
                    reservation_id TEXT
                );

                INSERT INTO reservations
                VALUES ('r1', 'PAID', 1);

                INSERT INTO verified_payments
                VALUES ('r1', 'CAPTURE_01', 1000, 'USD');

                INSERT INTO checkout_orders
                VALUES ('r1', 'CAPTURED');

                INSERT INTO issued_tickets
                VALUES ('ticket_01', 'r1');
            """)
            db.commit()

        app = FastAPI()
        app.include_router(webhook_reconciliation.router)
        self.client = TestClient(app)

        self.headers = {
            "x-organizer-key": "offline-test-key"
        }

    def tearDown(self):
        self.client.close()
        self.sandbox_patch.stop()
        self.path_patch.stop()
        self.env_patch.stop()
        self.temp.cleanup()

    def create_event(
        self,
        event_id="WH_TEST_01",
        event_type="PAYMENT.CAPTURE.COMPLETED",
        capture_id="CAPTURE_01"
    ):
        paypal_webhooks.save_verified_event({
            "id": event_id,
            "event_type": event_type,
            "resource": {"id": capture_id}
        }, self.db_path)

        return event_id

    def remote_capture(
        self,
        capture_id="CAPTURE_01",
        amount="10.00",
        status="COMPLETED"
    ):
        return {
            "id": capture_id,
            "status": status,
            "amount": {
                "currency_code": "USD",
                "value": amount
            }
        }

    def reconcile(self, event_id, headers=None):
        return self.client.post(
            f"/paypal/webhooks/events/{event_id}/reconcile",
            headers=self.headers if headers is None else headers
        )

    def event_state(self, event_id):
        with closing(sqlite3.connect(self.db_path)) as db:
            return db.execute("""
                SELECT processing_state
                FROM paypal_webhook_events
                WHERE paypal_event_id = ?
            """, (event_id,)).fetchone()[0]

    def test_completed_capture_reconciles(self):
        event_id = self.create_event()

        with patch(
            "webhook_reconciliation.fetch_capture",
            new_callable=AsyncMock
        ) as fetch:
            fetch.return_value = self.remote_capture()

            response = self.reconcile(event_id)

            self.assertEqual(
                response.status_code, 200, response.text
            )
            self.assertEqual(
                response.json()["status"], "RECONCILED"
            )
            self.assertEqual(
                response.json()["tickets_already_issued"], 1
            )
            fetch.assert_awaited_once()

        self.assertEqual(
            self.event_state(event_id), "RECONCILED"
        )

    def test_duplicate_reconciliation_is_safe(self):
        event_id = self.create_event()

        with patch(
            "webhook_reconciliation.fetch_capture",
            new_callable=AsyncMock
        ) as fetch:
            fetch.return_value = self.remote_capture()

            first = self.reconcile(event_id)
            second = self.reconcile(event_id)

            self.assertEqual(
                first.json()["status"], "RECONCILED"
            )
            self.assertEqual(
                second.json()["status"], "ALREADY_RECONCILED"
            )

            # No unnecessary second PayPal lookup.
            fetch.assert_awaited_once()

    def test_wrong_amount_is_rejected(self):
        event_id = self.create_event()

        with patch(
            "webhook_reconciliation.fetch_capture",
            new_callable=AsyncMock
        ) as fetch:
            fetch.return_value = self.remote_capture(
                amount="11.00"
            )
            response = self.reconcile(event_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self.event_state(event_id),
            "AWAITING_RECONCILIATION"
        )

    def test_unlinked_payment_waits(self):
        event_id = self.create_event(
            capture_id="CAPTURE_UNKNOWN"
        )

        with patch(
            "webhook_reconciliation.fetch_capture",
            new_callable=AsyncMock
        ) as fetch:
            fetch.return_value = self.remote_capture(
                capture_id="CAPTURE_UNKNOWN"
            )
            response = self.reconcile(event_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "WAITING_FOR_LOCAL_PAYMENT"
        )
        self.assertEqual(
            self.event_state(event_id),
            "AWAITING_RECONCILIATION"
        )

    def test_missing_ticket_is_not_reconciled(self):
        event_id = self.create_event()

        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute(
                "DELETE FROM issued_tickets WHERE reservation_id = ?",
                ("r1",)
            )
            db.commit()

        with patch(
            "webhook_reconciliation.fetch_capture",
            new_callable=AsyncMock
        ) as fetch:
            fetch.return_value = self.remote_capture()
            response = self.reconcile(event_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "WAITING_FOR_LOCAL_FINALIZATION"
        )
        self.assertEqual(
            self.event_state(event_id),
            "AWAITING_RECONCILIATION"
        )

    def test_other_event_type_needs_review(self):
        event_id = self.create_event(
            event_type="PAYMENT.CAPTURE.REFUNDED"
        )

        with patch(
            "webhook_reconciliation.fetch_capture",
            new_callable=AsyncMock
        ) as fetch:
            response = self.reconcile(event_id)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["status"],
                "NEEDS_MANUAL_REVIEW"
            )

            fetch.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
