
import unittest

from event_architect import architect_graph


class EventArchitectTests(unittest.TestCase):

    def setUp(self):
        self.state = {
            "prompt": (
                "Organize an AI hackathon for 30 participants "
                "with a keynote, two technical workshops, "
                "lunch break and final judging."
            ),
            "expected_attendees": 30,
            "event_capacity": 50,
            "rooms": [
                {
                    "id": 1,
                    "name": "Hall A",
                    "capacity": 100
                },
                {
                    "id": 2,
                    "name": "Hall B",
                    "capacity": 40
                }
            ],
            "existing_sessions": [],
            "trace": []
        }

    def test_generates_agenda(self):
        result = architect_graph.invoke(self.state)

        self.assertEqual(
            result["status"],
            "DRAFT_READY"
        )

        self.assertEqual(
            len(result["schedule"]),
            5
        )

        self.assertFalse(
            result["persisted"]
        )

    def test_capacity_violation(self):
        self.state["expected_attendees"] = 120

        result = architect_graph.invoke(self.state)

        self.assertEqual(
            result["status"],
            "NEEDS_REVIEW"
        )

        self.assertEqual(
            result["schedule"],
            []
        )

    def test_avoids_existing_room_booking(self):
        self.state["existing_sessions"] = [{
            "room": "Hall B",
            "start_time": "09:00",
            "end_time": "10:00"
        }]

        result = architect_graph.invoke(self.state)

        keynote = next(
            s for s in result["schedule"]
            if s["title"] == "Keynote"
        )

        self.assertNotEqual(
            keynote["room"],
            "Hall B"
        )


if __name__ == "__main__":
    unittest.main()
