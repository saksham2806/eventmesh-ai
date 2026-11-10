# backend/auto_incident_api.py
from contextlib import closing

from fastapi import APIRouter, Header, HTTPException,Depends
from pydantic import BaseModel, ConfigDict, Field

from ticketing_api import check_organizer, connect_db
from multi_incident_api import (
    IncidentIssue, MultiIncidentRequest, multi_incident_preview,
)
from issue_extractor import (
    extract_rules, extract_with_llm, ground_extraction,
)
from event_ownership import require_event_session_owner
router = APIRouter(tags=['AI Natural Language Incidents'])


class AutoIncidentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    description: str = Field(min_length=10, max_length=1000)
    expected_attendees: int | None = Field(default=None, ge=1)
    use_llm: bool = False


@router.post('/ai/events/{event_id}/sessions/{session_id}/auto-incident-preview',
             dependencies=[Depends(require_event_session_owner)])
async def auto_incident_preview(
    event_id: int,
    session_id: int,
    request: AutoIncidentRequest,
    x_organizer_key: str | None = Header(default=None),
):
    check_organizer(x_organizer_key)

    with closing(connect_db()) as db:
        event = db.execute('SELECT capacity FROM events WHERE id = ?', (event_id,)).fetchone()
        if event is None:
            raise HTTPException(status_code=404, detail='Event not found')
        session = db.execute(
            'SELECT room FROM sessions WHERE id = ? AND event_id = ?',
            (session_id, event_id),
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail='Session not found')
        rooms = [dict(r) for r in db.execute(
            'SELECT name, capacity FROM rooms WHERE event_id = ?', (event_id,)
        ).fetchall()]
        capacity = event['capacity']
        current_room = session['room']

    rule_draft, rule_warnings = extract_rules(request.description, current_room, rooms)

    if request.use_llm:
        draft = await extract_with_llm(request.description, current_room, rooms)
        # If an explicitly detected problem disappears from LLM output, block auto-planning.
        rule_types = {i.type for i in rule_draft.issues}
        llm_types = {i.type for i in draft.issues}
        if not rule_types.issubset(llm_types):
            rule_warnings.append('LLM omitted an explicitly detected disruption; review required.')
        if (rule_draft.expected_attendees is not None
                and draft.expected_attendees != rule_draft.expected_attendees):
            rule_warnings.append('LLM attendee count conflicts with the report; review required.')
    else:
        draft = rule_draft

    extracted = ground_extraction(
        draft, request.description, current_room, rooms, capacity, rule_warnings
    )

    # Explicit request field takes precedence, but never ignore conflicting attendee counts.
    attendees = request.expected_attendees or extracted['expected_attendees']
    if (
        request.expected_attendees is not None
        and extracted['expected_attendees'] is not None
        and request.expected_attendees != extracted['expected_attendees']
    ):
        extracted['warnings'].append('Attendee count in request differs from report; review required.')
        extracted['needs_review'] = True
    if attendees is not None and attendees > capacity:
        extracted['warnings'].append('Requested attendees exceed event capacity.')
        extracted['needs_review'] = True
    extracted['expected_attendees'] = attendees

    if extracted['needs_review'] or not extracted['issues']:
        extracted['status'] = 'NEEDS_REVIEW'
        return {
            'status': 'NEEDS_REVIEW',
            'mode': 'LLM_ASSISTED' if request.use_llm else 'RULE_BASED',
            'extraction': extracted,
            'preview': None,
            'requires_approval': True,
            'can_approve_now': False,
            'persisted': False,
            'applied': False,
            'paypal_called': False,
            'message_sent': False,
        }

    # Delegate all scheduling and payment impact checks to the existing 12D.3 endpoint.
    preview = multi_incident_preview(
        event_id=event_id,
        session_id=session_id,
        request=MultiIncidentRequest(
            description=request.description,
            issues=[IncidentIssue.model_validate(i) for i in extracted['issues']],
            expected_attendees=attendees,
        ),
        x_organizer_key=x_organizer_key,
    )

    return {
        'status': preview['status'],
        'mode': 'LLM_ASSISTED' if request.use_llm else 'RULE_BASED',
        'extraction': extracted,
        'preview': preview,
        'requires_approval': True,
        'can_approve_now': False,
        'persisted': False,
        'applied': False,
        'paypal_called': False,
        'message_sent': False,
    }
