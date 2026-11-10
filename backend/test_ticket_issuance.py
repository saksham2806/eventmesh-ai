
import sqlite3
import unittest

from ticket_fulfillment import apply_verified_capture


class TicketIssuanceTests(unittest.TestCase):

    def setUp(self):
        # Isolated database, never events.db
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row

        self.db.executescript("""
            CREATE TABLE events (
                id INTEGER,
                capacity INTEGER
            );

            CREATE TABLE ticket_types (
                id INTEGER,
                event_id INTEGER,
                price_cents INTEGER,
                capacity INTEGER
            );

            CREATE TABLE reservations (
                id TEXT,
                event_id INTEGER,
                ticket_type_id INTEGER,
                quantity INTEGER,
                status TEXT,
                expires_at TEXT
            );

            CREATE TABLE checkout_orders (
                reservation_id TEXT,
                paypal_order_id TEXT,
                status TEXT
            );

            CREATE TABLE verified_payments (
                reservation_id TEXT PRIMARY KEY,
                paypal_order_id TEXT UNIQUE,
                paypal_capture_id TEXT UNIQUE,
                amount_cents INTEGER,
                currency TEXT,
                verified_at TEXT
            );

            CREATE TABLE issued_tickets (
                id TEXT PRIMARY KEY,
                reservation_id TEXT,
                seat_number INTEGER,
                status TEXT,
                UNIQUE(reservation_id, seat_number)
            );

            INSERT INTO events VALUES (2, 3);

            INSERT INTO ticket_types
            VALUES (1, 2, 1000, 3);

            INSERT INTO reservations VALUES (
                'r1', 2, 1, 2,
                'PENDING_PAYMENT',
                '2100-01-01T00:00:00+00:00'
            );

            INSERT INTO checkout_orders
            VALUES ('r1', 'O1', 'CREATED');
        """)

        # Synthetic test fixture only
        self.order = {
            "id": "O1",
            "status": "COMPLETED",
            "purchase_units": [{
                "custom_id": "r1",
                "payments": {
                    "captures": [{
                        "id": "C1",
                        "status": "COMPLETED",
                        "amount": {
                            "currency_code": "USD",
                            "value": "20.00"
                        }
                    }]
                }
            }]
        }

    def tearDown(self):
        self.db.close()

    def test_issues_exactly_once(self):
        first = apply_verified_capture(
            "r1", self.order, self.db
        )

        second = apply_verified_capture(
            "r1", self.order, self.db
        )

        self.assertEqual(
            first["status"], "TICKETS_ISSUED"
        )

        self.assertEqual(
            second["status"], "ALREADY_ISSUED"
        )

        count = self.db.execute(
            "SELECT COUNT(*) FROM issued_tickets"
        ).fetchone()[0]

        self.assertEqual(count, 2)

    def test_wrong_amount_rejected(self):
        capture = self.order[
            "purchase_units"
        ][0]["payments"]["captures"][0]

        capture["amount"]["value"] = "19.00"

        with self.assertRaises(ValueError):
            apply_verified_capture(
                "r1", self.order, self.db
            )

        count = self.db.execute(
            "SELECT COUNT(*) FROM verified_payments"
        ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_oversold_requires_review(self):
        self.db.execute("""
            INSERT INTO reservations VALUES (
                'r2', 2, 1, 2,
                'PAID',
                '2100-01-01T00:00:00+00:00'
            )
        """)
        self.db.commit()

        result = apply_verified_capture(
            "r1", self.order, self.db
        )

        self.assertEqual(
            result["status"], "REVIEW_REQUIRED"
        )

        count = self.db.execute(
            "SELECT COUNT(*) FROM issued_tickets"
        ).fetchone()[0]

        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
