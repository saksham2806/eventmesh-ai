
import os
import sqlite3
import tempfile
from contextlib import contextmanager, closing
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import refund_api
import refund_execution


def fake_response(status_code, body):
    return SimpleNamespace(
        status_code=status_code,
        json=lambda: body
    )


class RefundExecutionTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_db = refund_api.DB_PATH

        refund_api.DB_PATH = (
            Path(self.directory.name) / "refund_execution_test.db"
        )

        self.env = patch.dict(os.environ, {
            "EVENTMESH_ORGANIZER_KEY": "offline-test-key",
            "EVENTMESH_SANDBOX_REFUNDS_ENABLED": "true",
        })
        self.env.start()

        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            db.executescript("""
                CREATE TABLE reservations (
                    id TEXT PRIMARY KEY,
                    event_id INTEGER,
                    status TEXT,
                    quantity INTEGER
                );

                CREATE TABLE verified_payments (
                    reservation_id TEXT PRIMARY KEY,
                    paypal_capture_id TEXT,
                    currency TEXT,
                    amount_cents INTEGER
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
                VALUES ('r_demo', 1, 'PAID', 1);

                INSERT INTO verified_payments
                VALUES ('r_demo', 'CAPTURE_TEST_01', 'USD', 1000);

                INSERT INTO checkout_orders
                VALUES ('r_demo', 'CAPTURED');

                INSERT INTO issued_tickets
                VALUES ('ticket_demo', 'r_demo');
            """)

        refund_api.initialize_refunds()
        refund_execution.initialize_execution()

        app = FastAPI()
        app.include_router(refund_api.router)
        app.include_router(refund_execution.router)

# Test-only ownership overrides.
# Never add these to the production application.
        app.dependency_overrides[
            refund_api.require_reservation_owner
        ] = lambda: "isolated-test-organizer"

        app.dependency_overrides[
            refund_api.require_refund_create_owner
        ] = lambda: "isolated-test-organizer"

        app.dependency_overrides[
            refund_api.require_refund_proposal_owner
        ] = lambda: "isolated-test-organizer"


        self.client = TestClient(app)

        self.headers = {
            "x-organizer-key": "offline-test-key",
            "x-confirm-sandbox-refund": "CONFIRM_SANDBOX_REFUND",
        }

    def tearDown(self):
        self.client.close()
        self.env.stop()
        refund_api.DB_PATH = self.original_db
        self.directory.cleanup()

    def approved_proposal(self, amount=None):
        payload = {
            "reservation_id": "r_demo",
            "reason": "Offline Sandbox refund test",
        }

        if amount is not None:
            payload["amount_usd"] = amount

        created = self.client.post(
            "/refunds/proposals",
            headers=self.headers,
            json=payload
        )
        self.assertEqual(created.status_code, 201, created.text)

        proposal_id = created.json()["proposal_id"]

        approved = self.client.post(
            f"/refunds/proposals/{proposal_id}/approve",
            headers=self.headers
        )
        self.assertEqual(approved.status_code, 200, approved.text)

        return proposal_id

    @contextmanager
    def mock_paypal(self, refund_amount="10.00"):
        capture = {
            "id": "CAPTURE_TEST_01",
            "status": "COMPLETED",
            "amount": {
                "currency_code": "USD",
                "value": "10.00",
            },
        }

        refund = {
            "id": "REFUND_TEST_01",
            "status": "COMPLETED",
            "amount": {
                "currency_code": "USD",
                "value": refund_amount,
            },
        }

        with patch(
            "refund_execution.get_paypal_token",
            new_callable=AsyncMock
        ) as auth, patch(
            "refund_execution.httpx.AsyncClient"
        ) as factory:

            auth.return_value = "fake-offline-token"

            remote = factory.return_value.__aenter__.return_value

            remote.get = AsyncMock(
                return_value=fake_response(200, capture)
            )
            remote.post = AsyncMock(
                return_value=fake_response(201, refund)
            )

            yield remote

    def test_unauthorized_execution_blocked(self):
        pid = self.approved_proposal()

        with self.mock_paypal() as remote:
            result = self.client.post(
                f"/refunds/proposals/{pid}/execute-sandbox"
            )

            self.assertEqual(result.status_code, 403)
            remote.post.assert_not_awaited()

    def test_explicit_confirmation_required(self):
        pid = self.approved_proposal()

        with self.mock_paypal() as remote:
            result = self.client.post(
                f"/refunds/proposals/{pid}/execute-sandbox",
                headers={
                    "x-organizer-key": "offline-test-key"
                }
            )

            self.assertEqual(result.status_code, 400)
            remote.post.assert_not_awaited()

    def test_disabled_refunds_blocked(self):
        pid = self.approved_proposal()

        with patch.dict(os.environ, {
            "EVENTMESH_SANDBOX_REFUNDS_ENABLED": "false"
        }):
            with self.mock_paypal() as remote:
                result = self.client.post(
                    f"/refunds/proposals/{pid}/execute-sandbox",
                    headers=self.headers
                )

                self.assertEqual(result.status_code, 503)
                remote.post.assert_not_awaited()

    def test_full_refund_and_duplicate_protection(self):
        pid = self.approved_proposal()

        with self.mock_paypal() as remote:
            first = self.client.post(
                f"/refunds/proposals/{pid}/execute-sandbox",
                headers=self.headers
            )

            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(
                first.json()["refund_status"], "COMPLETED"
            )
            self.assertEqual(
                first.json()["paypal_refund_id"], "REFUND_TEST_01"
            )

            second = self.client.post(
                f"/refunds/proposals/{pid}/execute-sandbox",
                headers=self.headers
            )

            self.assertEqual(second.status_code, 409)
            remote.post.assert_awaited_once()

            self.assertEqual(
                remote.post.await_args.kwargs["json"], {}
            )

        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            state = db.execute("""
                SELECT state
                FROM refund_execution_attempts
                WHERE proposal_id = ?
            """, (pid,)).fetchone()[0]

            saved_id = db.execute("""
                SELECT paypal_refund_id
                FROM refund_proposals
                WHERE id = ?
            """, (pid,)).fetchone()[0]

        self.assertEqual(state, "SUBMITTED")
        self.assertEqual(saved_id, "REFUND_TEST_01")

    def test_partial_refund_amount(self):
        pid = self.approved_proposal("7.50")

        with self.mock_paypal(refund_amount="7.50") as remote:
            result = self.client.post(
                f"/refunds/proposals/{pid}/execute-sandbox",
                headers=self.headers
            )

            self.assertEqual(result.status_code, 200, result.text)

            body = remote.post.await_args.kwargs["json"]

            self.assertEqual(
                body["amount"]["value"], "7.50"
            )
            self.assertEqual(
                body["amount"]["currency_code"], "USD"
            )

    def test_timeout_does_not_trigger_second_refund(self):
        pid = self.approved_proposal()

        with self.mock_paypal() as remote:
            remote.post.side_effect = httpx.ReadTimeout(
                "Simulated timeout: no real network"
            )

            first = self.client.post(
                f"/refunds/proposals/{pid}/execute-sandbox",
                headers=self.headers
            )

            self.assertEqual(first.status_code, 502)

            second = self.client.post(
                f"/refunds/proposals/{pid}/execute-sandbox",
                headers=self.headers
            )

            self.assertEqual(second.status_code, 409)
            remote.post.assert_awaited_once()

        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            state = db.execute("""
                SELECT state
                FROM refund_execution_attempts
                WHERE proposal_id = ?
            """, (pid,)).fetchone()[0]

        self.assertEqual(state, "UNKNOWN")

    def test_mismatched_capture_blocked(self):
        pid = self.approved_proposal()

        with self.mock_paypal() as remote:
            remote.get.return_value = fake_response(
                200,
                {
                    "id": "WRONG_CAPTURE",
                    "status": "COMPLETED",
                    "amount": {
                        "currency_code": "USD",
                        "value": "10.00"
                    }
                }
            )

            result = self.client.post(
                f"/refunds/proposals/{pid}/execute-sandbox",
                headers=self.headers
            )

            self.assertEqual(result.status_code, 409)
            remote.post.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
