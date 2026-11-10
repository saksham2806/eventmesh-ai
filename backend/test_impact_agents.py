
import unittest
from datetime import datetime, timedelta, timezone

from impact_agents import impact_graph


class ImpactAgentTests(unittest.TestCase):

    def setUp(self):
        future = (
            datetime.now(timezone.utc)
            + timedelta(minutes=10)
        ).isoformat()

        self.state = {
            "event_id": 2,
            "session_id": 2,
            "session_title": "AI Keynote",
            "disruption_type": "SESSION_CANCELLED",
            "description": "Speaker unavailable",
            "reservations": [
                {
                    "id": "r1",
                    "status": "PAID",
                    "quantity": 2,
                    "verified_capture": 1,
                    "amount_cents": 2000,
                    "expires_at": future,
                    "active_ticket_count": 2
                },
                {
                    "id": "r2",
                    "status": "PENDING_PAYMENT",
                    "quantity": 1,
                    "verified_capture": 0,
                    "amount_cents": None,
                    "expires_at": future,
                    "active_ticket_count": 0
                }
            ],
            "trace": []
        }

    def test_counts_bookings(self):
        result = impact_graph.invoke(self.state)
        summary = result["booking_summary"]

        self.assertEqual(
            summary["verified_paid_seats"], 2
        )

        self.assertEqual(
            summary["active_pending_seats"], 1
        )

        self.assertEqual(
            summary["recorded_capture_total_usd"],
            "20.00"
        )

    def test_no_paypal_operation(self):
        result = impact_graph.invoke(self.state)

        self.assertFalse(result["paypal_called"])
        self.assertFalse(result["applied"])
        self.assertFalse(result["message_sent"])
        self.assertTrue(result["requires_approval"])

    def test_no_verified_payments(self):
        self.state["reservations"] = []

        result = impact_graph.invoke(self.state)

        self.assertEqual(
            result["booking_summary"][
                "verified_paid_reservations"
            ], 0
        )

        self.assertIn(
            "NO_VERIFIED_PAID_BOOKINGS",
            result["payment_recommendation"]
        )

    def test_inconsistent_payment_detected(self):
        self.state["reservations"][0][
            "verified_capture"
        ] = 0

        result = impact_graph.invoke(self.state)

        self.assertEqual(
            result["booking_summary"][
                "paid_without_verified_capture"
            ], 1
        )


if __name__ == "__main__":
    unittest.main()
