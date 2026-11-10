# Tests do not contact an LLM, PayPal or events.db.
import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from issue_extractor import (
    Extraction, extract_rules, extract_with_llm, ground_extraction
)

ROOMS = [{'name': 'Hall A'}, {'name': 'Hall D'}]


class MultiIssueExtractorTests(unittest.TestCase):
    def parse(self, text):
        draft, warnings = extract_rules(text, 'Hall D', ROOMS)
        return ground_extraction(draft, text, 'Hall D', ROOMS, 50, warnings)

    def test_two_issues_and_attendees(self):
        result = self.parse('Hall D is unavailable and the keynote speaker is 45 minutes late for 30 attendees.')
        self.assertEqual(result['status'], 'EXTRACTION_READY')
        self.assertEqual([x['type'] for x in result['issues']], ['ROOM_UNAVAILABLE', 'SPEAKER_DELAY'])
        self.assertEqual(result['expected_attendees'], 30)
        self.assertEqual(result['issues'][1]['delay_minutes'], 45)

    def test_current_room_shorthand(self):
        result = self.parse('Our current room is unavailable and the keynote speaker is delayed by 30 minutes.')
        self.assertEqual(result['issues'][0]['room'], 'Hall D')
        self.assertFalse(result['needs_review'])

    def test_unknown_room_does_not_approve(self):
        result = self.parse('Hall Z is unavailable and our keynote speaker is 45 minutes late.')
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['status'], 'NEEDS_REVIEW')

    def test_missing_delay_requires_review(self):
        result = self.parse('Hall D is unavailable and our keynote speaker will be late.')
        self.assertTrue(result['needs_review'])

    def test_cancellation(self):
        result = self.parse('The keynote session is cancelled; please review the impact.')
        self.assertEqual(result['issues'][0]['type'], 'SESSION_CANCELLED')

    def test_unstated_room_from_llm_rejected(self):
        draft = Extraction.model_validate({
            'issues': [{'type': 'ROOM_UNAVAILABLE', 'room': 'Hall A', 'delay_minutes': None}],
            'expected_attendees': None,
            'needs_review': False,
            'summary': 'A room outage',
        })
        result = ground_extraction(draft, 'Hall D is unavailable.', 'Hall D', ROOMS, 50)
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['issues'], [])

    def test_invalid_llm_shape_rejected(self):
        with self.assertRaises(ValidationError):
            Extraction.model_validate({
                'issues': [{'type': 'SPEAKER_DELAY', 'room': None, 'delay_minutes': 900}],
                'needs_review': False,
                'summary': 'Speaker delayed',
            })

    def test_llm_missing_credentials(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': '', 'OPENROUTER_MODEL': ''}):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(extract_with_llm('Hall D is unavailable.', 'Hall D', ROOMS))
        self.assertEqual(error.exception.status_code, 503)


if __name__ == '__main__':
    unittest.main()
