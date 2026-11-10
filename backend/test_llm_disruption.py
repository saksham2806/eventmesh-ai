
import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from llm_disruption import (
    DisruptionIntent,
    interpret_with_llm,
    review_intent
)


class LLMDisruptionTests(unittest.TestCase):

    def setUp(self):
        self.rooms = [
            {"id": 1, "name": "Hall A"},
            {"id": 2, "name": "Hall D"}
        ]

    def test_room_normalization(self):
        intent = DisruptionIntent(
            disruption_type="ROOM_UNAVAILABLE",
            summary="Hall A unavailable",
            reported_room="hall-A",
            delay_minutes=None,
            needs_review=False
        )

        result = review_intent(intent, self.rooms)

        self.assertEqual(
            result["reported_room"], "Hall A"
        )

        self.assertFalse(result["needs_review"])

    def test_unknown_room_requires_review(self):
        intent = DisruptionIntent(
            disruption_type="ROOM_UNAVAILABLE",
            summary="Unknown room unavailable",
            reported_room="Hall Z",
            delay_minutes=None,
            needs_review=False
        )

        result = review_intent(intent, self.rooms)

        self.assertTrue(result["needs_review"])
        self.assertTrue(result["warnings"])

    def test_missing_delay_requires_review(self):
        intent = DisruptionIntent(
            disruption_type="SPEAKER_DELAY",
            summary="Speaker delayed",
            reported_room=None,
            delay_minutes=None,
            needs_review=False
        )

        result = review_intent(intent, self.rooms)

        self.assertTrue(result["needs_review"])

    def test_invalid_output_rejected(self):
        with self.assertRaises(ValidationError):
            DisruptionIntent.model_validate({
                "disruption_type": "UNKNOWN_ACTION",
                "summary": "Invalid",
                "reported_room": None,
                "delay_minutes": None,
                "needs_review": False
            })

    def test_missing_provider_configuration(self):
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "",
                "OPENROUTER_MODEL": ""
            }
        ):
            with self.assertRaises(
                HTTPException
            ) as error:
                asyncio.run(
                    interpret_with_llm(
                        "Hall A is unavailable",
                        "AI Keynote",
                        "Hall A",
                        self.rooms
                    )
                )

            self.assertEqual(
                error.exception.status_code, 503
            )


if __name__ == "__main__":
    unittest.main()
