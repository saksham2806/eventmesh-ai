"""Isolated tests: no network requests or real refunds."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import refund_api
import refund_reconciliation


class RefundReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_db = refund_api.DB_PATH
        self.original_key = os.environ.get('EVENTMESH_ORGANIZER_KEY')
        self.original_client_id = os.environ.get('PAYPAL_CLIENT_ID')
        self.original_client_secret = os.environ.get('PAYPAL_CLIENT_SECRET')
        refund_api.DB_PATH = Path(self.directory.name) / '11c_test.db'
        os.environ['EVENTMESH_ORGANIZER_KEY'] = 'test-organizer-key'
        os.environ.pop('PAYPAL_CLIENT_ID', None)
        os.environ.pop('PAYPAL_CLIENT_SECRET', None)
        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            db.executescript('''
                CREATE TABLE reservations(id TEXT PRIMARY KEY, event_id INTEGER, status TEXT, quantity INTEGER);
                CREATE TABLE verified_payments(reservation_id TEXT PRIMARY KEY, paypal_capture_id TEXT, currency TEXT, amount_cents INTEGER);
                CREATE TABLE checkout_orders(reservation_id TEXT PRIMARY KEY, status TEXT);
                CREATE TABLE issued_tickets(id TEXT PRIMARY KEY, reservation_id TEXT);
                INSERT INTO reservations VALUES ('r1',2,'PAID',2);
                INSERT INTO verified_payments VALUES ('r1','capture_demo','USD',2000);
                INSERT INTO checkout_orders VALUES ('r1','CAPTURED');
                INSERT INTO issued_tickets VALUES ('t1','r1'),('t2','r1');
            ''')
            db.commit()
        refund_api.initialize_refunds()
        refund_reconciliation.initialize_refund_reconciliation()
        app = FastAPI()
        app.include_router(refund_api.router)
        app.include_router(refund_reconciliation.router)
        # Test-only authorization overrides.
# Never use these in the production application.
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
        self.headers = {'x-organizer-key': 'test-organizer-key'}
        proposal = self.client.post('/refunds/proposals',headers=self.headers,json={
            'reservation_id':'r1', 'reason':'Session cancelled', 'amount_usd':'7.50'
        })
        assert proposal.status_code == 201, proposal.text
        self.proposal_id = proposal.json()['proposal_id']

    def tearDown(self):
        self.client.close()
        refund_api.DB_PATH = self.original_db
        for k, old in [
            ('EVENTMESH_ORGANIZER_KEY', self.original_key),
            ('PAYPAL_CLIENT_ID', self.original_client_id),
            ('PAYPAL_CLIENT_SECRET', self.original_client_secret),
        ]:
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        self.directory.cleanup()

    def test_unapproved_proposal_not_ready(self):
        response = self.client.get(
            f'/refunds/proposals/{self.proposal_id}/execution-preview', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['local_checks_passed'])
        self.assertFalse(response.json()['execution_enabled'])

    def test_approval_is_preview_only(self):
        approval = self.client.post(
            f'/refunds/proposals/{self.proposal_id}/approve', headers=self.headers)
        self.assertEqual(approval.status_code, 200)
        result = self.client.get(
            f'/refunds/proposals/{self.proposal_id}/execution-preview', headers=self.headers).json()
        self.assertTrue(result['local_checks_passed'])
        self.assertFalse(result['execution_enabled'])
        self.assertFalse(result['paypal_called'])

    def test_no_refund_submitted(self):
        result = self.client.post(
            f'/refunds/proposals/{self.proposal_id}/reconcile', headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['refund_status'], 'NOT_SUBMITTED')
        self.assertFalse(result.json()['paypal_called'])

    def test_tracking_is_not_submitted(self):
        result = self.client.get(
            f'/refunds/proposals/{self.proposal_id}/tracking', headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['refund_status'], 'NOT_SUBMITTED')

    def test_organizer_authentication_required(self):
        result = self.client.get(f'/refunds/proposals/{self.proposal_id}/tracking')
        self.assertEqual(result.status_code, 403)

    def test_mismatched_refund_amount_rejected(self):
        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            db.execute('UPDATE refund_proposals SET paypal_refund_id=? WHERE id=?',
                       ('refund_demo', self.proposal_id))
            db.commit()
        fake = {'id':'refund_demo','status':'COMPLETED',
                'amount':{'currency_code':'USD', 'value':'8.00'}}
        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM refund_proposals WHERE id=?', (self.proposal_id,)).fetchone()
            with self.assertRaises(ValueError):
                refund_reconciliation.validate_remote_refund(fake, row)

    def test_mocked_paypal_status_updates_one_row(self):
        # Only a fabricated server response, from a mocked HTTP client.
        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            db.execute('UPDATE refund_proposals SET paypal_refund_id=? WHERE id=?',
                       ('refund_demo', self.proposal_id))
            db.commit()
        os.environ['PAYPAL_CLIENT_ID'] = 'unused-test-id'
        os.environ['PAYPAL_CLIENT_SECRET'] = 'unused-test-secret'
        fake = {'id':'refund_demo','status':'COMPLETED',
                'amount':{'currency_code':'USD', 'value':'7.50'}}
        with patch('refund_reconciliation.get_paypal_token', new_callable=AsyncMock) as auth:
            auth.return_value = 'mock-token'
            with patch('refund_reconciliation.httpx.AsyncClient') as klass:
                client = klass.return_value.__aenter__.return_value
                client.get = AsyncMock(return_value=SimpleNamespace(status_code=200,json=lambda: fake))
                for _ in range(2):
                    response = self.client.post(
                        f'/refunds/proposals/{self.proposal_id}/reconcile', headers=self.headers)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()['refund_status'], 'COMPLETED')
        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            count = db.execute('SELECT COUNT(*) FROM refund_reconciliation').fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == '__main__':
    unittest.main()
