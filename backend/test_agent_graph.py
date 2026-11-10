
import unittest

from agent_graph import recovery_graph


class AgentGraphTests(unittest.TestCase):

    def test_prefers_no_time_change(self):
        result = recovery_graph.invoke({
            "session_id": 2,
            "suggestions": [
                {
                    "proposal_id": "p1",
                    "room": "Hall B",
                    "start_time": "10:30",
                    "end_time": "11:30",
                    "time_shift_minutes": 30
                },
                {
                    "proposal_id": "p2",
                    "room": "Hall C",
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "time_shift_minutes": 0
                }
            ],
            "trace": []
        })

        self.assertEqual(
            result["recommendation"]["proposal_id"],
            "p2"
        )

    def test_no_solution(self):
        result = recovery_graph.invoke({
            "session_id": 2,
            "suggestions": [],
            "trace": []
        })

        self.assertIsNone(
            result["recommendation"]
        )

        self.assertFalse(
            result["requires_approval"]
        )

    def test_requires_approval(self):
        result = recovery_graph.invoke({
            "session_id": 2,
            "suggestions": [
                {
                    "proposal_id": "p3",
                    "room": "Hall D",
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "time_shift_minutes": 0
                }
            ],
            "trace": []
        })

        self.assertTrue(
            result["requires_approval"]
        )

        self.assertFalse(
            result["applied"]
        )

        self.assertIn(
            "not sent",
            result["message_draft"]
        )


if __name__ == "__main__":
    unittest.main()
