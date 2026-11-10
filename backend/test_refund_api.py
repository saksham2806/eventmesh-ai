import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import refund_api
from event_ownership import require_reservation_owner
from event_ownership import require_refund_proposal_owner
from refund_api import require_refund_create_owner

class RefundProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = refund_api.DB_PATH
        refund_api.DB_PATH = Path(self.temp_dir.name) / 'refunds_test.db'
        self.original_key = os.environ.get('EVENTMESH_ORGANIZER_KEY')
        os.environ['EVENTMESH_ORGANIZER_KEY'] = 'test-local-key'
        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            db.executescript('''
                CREATE TABLE reservations(id TEXT PRIMARY KEY, event_id INTEGER, status TEXT, quantity INTEGER);
                CREATE TABLE verified_payments(reservation_id TEXT PRIMARY KEY, paypal_capture_id TEXT, currency TEXT, amount_cents INTEGER);
                CREATE TABLE checkout_orders(reservation_id TEXT PRIMARY KEY, status TEXT);
                CREATE TABLE issued_tickets(id TEXT PRIMARY KEY, reservation_id TEXT);
                INSERT INTO reservations VALUES ('r1', 2, 'PAID', 2);
                INSERT INTO verified_payments VALUES ('r1', 'CAPTURE_TEST_01', 'USD', 2000);
                INSERT INTO checkout_orders VALUES ('r1','CAPTURED');
                INSERT INTO issued_tickets VALUES ('t1','r1'), ('t2','r1');
                INSERT INTO reservations VALUES ('r2', 2, 'PENDING_PAYMENT', 1);
            ''')
            db.commit()
        refund_api.initialize_refunds()
        app = FastAPI()
        app.include_router(refund_api.router)
        app.dependency_overrides[require_reservation_owner] = (
            lambda: "isolated-test-organizer"
        )

        app.dependency_overrides[require_refund_create_owner] = (
            lambda: "isolated-test-organizer"
        )

        app.dependency_overrides[require_refund_proposal_owner] = (
            lambda: "isolated-test-organizer"
        )

        self.client = TestClient(app)
        self.headers = {'x-organizer-key':'test-local-key'}
    def tearDown(self):
        self.client.close()
        refund_api.DB_PATH = self.original_path
        if self.original_key is None:
            os.environ.pop('EVENTMESH_ORGANIZER_KEY',None)
        else:
            os.environ['EVENTMESH_ORGANIZER_KEY'] = self.original_key
        self.temp_dir.cleanup()
    def test_not_paid_is_ineligible(self):
        res=self.client.get('/refunds/eligibility/r2', headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()['eligible'])
        create=self.client.post('/refunds/proposals', headers=self.headers, json={'reservation_id':'r2','reason':'Session cancelled'})
        self.assertEqual(create.status_code,409)
    def test_approval_does_not_call_paypal(self):
        eligibility=self.client.get('/refunds/eligibility/r1',headers=self.headers)
        self.assertTrue(eligibility.json()['eligible'])
        res=self.client.post('/refunds/proposals',headers=self.headers,json={'reservation_id':'r1','reason':'Session cancelled'})
        self.assertEqual(res.status_code,201)
        pid=res.json()['proposal_id']
        self.assertEqual(res.json()['amount_usd'],'20.00')
        approval=self.client.post(f'/refunds/proposals/{pid}/approve',headers=self.headers)
        self.assertEqual(approval.status_code,200)
        self.assertEqual(approval.json()['status'],'APPROVED_PENDING_PAYPAL')
        self.assertFalse(approval.json()['paypal_called'])
        again=self.client.post(f'/refunds/proposals/{pid}/approve',headers=self.headers)
        self.assertEqual(again.status_code,200)
        with closing(sqlite3.connect(refund_api.DB_PATH)) as db:
            count=db.execute('SELECT COUNT(*) FROM refund_proposals').fetchone()[0]
        self.assertEqual(count,1)
    def test_over_amount_rejected(self):
        res=self.client.post('/refunds/proposals',headers=self.headers,json={'reservation_id':'r1','reason':'Session cancelled','amount_usd':'21.00'})
        self.assertEqual(res.status_code,422)
    def test_duplicate_proposal_rejected(self):
        payload={'reservation_id':'r1','reason':'Session cancelled'}
        self.assertEqual(self.client.post('/refunds/proposals',headers=self.headers,json=payload).status_code,201)
        self.assertEqual(self.client.post('/refunds/proposals',headers=self.headers,json=payload).status_code,409)
    def test_unauthorized_blocked(self):
        self.assertEqual(self.client.get('/refunds/eligibility/r1').status_code,403)
    def test_partial_approval(self):
        res=self.client.post('/refunds/proposals', headers=self.headers,json={'reservation_id':'r1','reason':'Partial event cancellation','amount_usd':'7.50'})
        self.assertEqual(res.status_code,201)
        self.assertEqual(res.json()['amount_usd'],'7.50')

if __name__=='__main__': unittest.main()
