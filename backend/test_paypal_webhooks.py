from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from paypal_webhooks import (
    initialize_webhook_table,
    save_verified_event,
    router,
)


# Synthetic test event, NOT a real payment.
TEST_EVENT = {
    "id": "WH-TEST-001",
    "event_type": "PAYMENT.CAPTURE.COMPLETED",
    "resource": {
        "id": "CAPTURE-DEMO-001"
    }
}


class PayPalWebhookTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

        self.test_db = (
            Path(self.temp_dir.name) / "test_webhooks.db"
        )

        initialize_webhook_table(self.test_db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_verified_event_is_recorded(self):

        result = save_verified_event(
            TEST_EVENT, self.test_db
        )

        self.assertEqual(
            result["status"],
            "RECORDED"
        )

        self.assertEqual(
            result["processing_state"],
            "AWAITING_RECONCILIATION"
        )

    def test_duplicate_event_is_not_added_twice(self):

        save_verified_event(
            TEST_EVENT, self.test_db
        )

        duplicate = save_verified_event(
            TEST_EVENT, self.test_db
        )

        self.assertEqual(
            duplicate["status"],
            "DUPLICATE"
        )

        with closing(sqlite3.connect(self.test_db)) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM paypal_webhook_events"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_event_does_not_create_paid_tickets(self):

        save_verified_event(
            TEST_EVENT, self.test_db
        )

        with closing(sqlite3.connect(self.test_db)) as db:
            tables = {
                row[0]
                for row in db.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

        self.assertEqual(
            tables,
            {"paypal_webhook_events"}
        )

    def test_unsigned_webhook_is_rejected(self):

        app = FastAPI()
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/webhooks/paypal",
                json=TEST_EVENT
            )

        self.assertEqual(
            response.status_code,
            400
        )

        self.assertEqual(
            response.json()["detail"],
            "Missing PayPal signature headers"
        )

    def test_valid_mocked_signature_is_accepted(self):
        app = FastAPI()
        app.include_router(router)

        headers = {
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-cert-url": "https://example.test/cert",
            "paypal-transmission-id": "offline-transmission",
            "paypal-transmission-sig": "offline-signature",
            "paypal-transmission-time": "2026-11-04T10:00:00Z",
        }

        with patch(
            "paypal_webhooks.verify_signature_with_paypal",
            new_callable=AsyncMock
        ) as verify, patch(
            "paypal_webhooks.save_verified_event",
            side_effect=lambda event: save_verified_event(
                event, self.test_db
            )
        ):
            verify.return_value = True

            with TestClient(app) as client:
                first = client.post(
                    "/webhooks/paypal",
                    json=TEST_EVENT,
                    headers=headers
                )
                second = client.post(
                    "/webhooks/paypal",
                    json=TEST_EVENT,
                    headers=headers
                )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "RECORDED")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "DUPLICATE")

        with closing(sqlite3.connect(self.test_db)) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM paypal_webhook_events"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_invalid_mocked_signature_is_rejected(self):
        app = FastAPI()
        app.include_router(router)

        headers = {
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-cert-url": "https://example.test/cert",
            "paypal-transmission-id": "offline-transmission",
            "paypal-transmission-sig": "invalid-signature",
            "paypal-transmission-time": "2026-11-04T10:00:00Z",
        }

        with patch(
            "paypal_webhooks.verify_signature_with_paypal",
            new_callable=AsyncMock
        ) as verify, patch(
            "paypal_webhooks.save_verified_event"
        ) as save:
            verify.return_value = False

            with TestClient(app) as client:
                response = client.post(
                    "/webhooks/paypal",
                    json=TEST_EVENT,
                    headers=headers
                )

            self.assertEqual(response.status_code, 401)
            save.assert_not_called()

    def test_verification_service_unavailable(self):
        app = FastAPI()
        app.include_router(router)

        headers = {
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-cert-url": "https://example.test/cert",
            "paypal-transmission-id": "offline-transmission",
            "paypal-transmission-sig": "offline-signature",
            "paypal-transmission-time": "2026-11-04T10:00:00Z",
        }

        with patch(
            "paypal_webhooks.verify_signature_with_paypal",
            new_callable=AsyncMock
        ) as verify, patch(
            "paypal_webhooks.save_verified_event"
        ) as save:
            verify.side_effect = HTTPException(
                status_code=503,
                detail="Verification service unavailable"
            )

            with TestClient(app) as client:
                response = client.post(
                    "/webhooks/paypal",
                    json=TEST_EVENT,
                    headers=headers
                )

            self.assertEqual(response.status_code, 503)
            save.assert_not_called()



if __name__ == "__main__":
    unittest.main()
