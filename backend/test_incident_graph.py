
import unittest

from incident_graph import incident_graph


class IncidentGraphTests(unittest.TestCase):

    def setUp(self):
        self.state = {
            "event_id": 2,
            "session_id": 2,
            "session_title": "AI Keynote",
            "disruption_type": "ROOM_UNAVAILABLE",
            "description": "Hall D unavailable",
            "verified_suggestions": [
                {
                    "proposal_id": "p1",
                    "room": "Hall B",
                    "start_time": "10:30",
                    "end_time": "11:30",
                    "time_shift_minutes": 30
                },
                {
                    "proposal_id": "p2",
                    "room": "Hall A",
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "time_shift_minutes": 0
                }
            ],
            "reservations": [],
            "agents_executed": []
        }

    def test_combines_both_workflows(self):
        result = incident_graph.invoke(self.state)

        self.assertIn(
            "recovery_plan", result
        )

        self.assertIn(
            "impact_report", result
        )

        self.assertEqual(
            result["status"],
            "RECOVERY_AND_IMPACT_READY"
        )

    def test_selects_least_disruptive_option(self):
        result = incident_graph.invoke(self.state)

        self.assertEqual(
            result["recovery_plan"][
                "recommendation"
            ]["proposal_id"],
            "p2"
        )

    def test_financial_actions_not_executed(self):
        result = incident_graph.invoke(self.state)

        self.assertTrue(
            result["requires_approval"]
        )

        self.assertFalse(
            result["applied"]
        )

        self.assertFalse(
            result["paypal_called"]
        )

        self.assertFalse(
            result["message_sent"]
        )

    def test_without_recovery_options(self):
        self.state["verified_suggestions"] = []

        result = incident_graph.invoke(self.state)

        self.assertEqual(
            result["status"],
            "IMPACT_REVIEW_READY"
        )

        self.assertIsNone(
            result["recovery_plan"][
                "recommendation"
            ]
        )

    def test_cancellation_requires_manual_review(self):
        self.state["disruption_type"] = (
            "SESSION_CANCELLED"
        )

        result = incident_graph.invoke(self.state)

        self.assertEqual(
            result["status"],
            "IMPACT_REVIEW_READY"
        )


if __name__ == "__main__":
    unittest.main()
