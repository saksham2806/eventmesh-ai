# backend/multi_incident_api.py
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, Header, HTTPException,Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ticketing_api import check_organizer, connect_db
from impact_api import ImpactRequest, analyze_event_impact
from multi_incident_planner import plan_multi_disruption
from event_ownership import require_event_session_owner

router = APIRouter(tags=['AI Multi-Incident'])


class IncidentIssue(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: Literal['ROOM_UNAVAILABLE', 'SPEAKER_DELAY', 'SESSION_CANCELLED']
    room: str | None = Field(default=None, max_length=100)
    delay_minutes: int | None = Field(default=None, ge=1, le=480)

    @model_validator(mode='after')
    def validate_issue(self):
        if self.type == 'ROOM_UNAVAILABLE':
            if not self.room or len(self.room.strip()) < 2:
                raise ValueError('ROOM_UNAVAILABLE requires a room')
            if self.delay_minutes is not None:
                raise ValueError('Room outage cannot have delay_minutes')
        elif self.type == 'SPEAKER_DELAY':
            if self.delay_minutes is None:
                raise ValueError('SPEAKER_DELAY requires delay_minutes')
            if self.room is not None:
                raise ValueError('Speaker delay cannot have a room')
        else:
            if self.room is not None or self.delay_minutes is not None:
                raise ValueError('Cancellation takes no room or delay')
        return self


class MultiIncidentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    description: str = Field(min_length=10, max_length=1000)
    issues: list[IncidentIssue] = Field(min_length=1, max_length=5)
    expected_attendees: int | None = Field(default=None, ge=1)


@router.post('/ai/events/{event_id}/sessions/{session_id}/multi-incident-preview',
             dependencies=[Depends(require_event_session_owner)])
def multi_incident_preview(
    event_id: int,
    session_id: int,
    request: MultiIncidentRequest,
    x_organizer_key: str | None = Header(default=None),
):
    # This is a local development authorization gate.
    check_organizer(x_organizer_key)

    with closing(connect_db()) as db:
        event = db.execute(
            'SELECT id, capacity FROM events WHERE id = ?',
            (event_id,)
        ).fetchone()
        if event is None:
            raise HTTPException(status_code=404, detail='Event not found')

        session = db.execute(
            'SELECT id, title, speaker, room, start_time, end_time '
            'FROM sessions WHERE event_id = ? AND id = ?',
            (event_id, session_id)
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail='Session not found')

        rooms = db.execute(
            'SELECT id, name, capacity FROM rooms WHERE event_id = ?',
            (event_id,)
        ).fetchall()
        other_sessions = db.execute(
            'SELECT id, speaker, room, start_time, end_time '
            'FROM sessions WHERE event_id = ? AND id != ?',
            (event_id, session_id)
        ).fetchall()

        event_capacity = event['capacity']
        session_data = dict(session)
        rooms_data = [dict(row) for row in rooms]
        booked_data = [dict(row) for row in other_sessions]

    required_capacity = request.expected_attendees or event_capacity
    if required_capacity > event_capacity:
        raise HTTPException(
            status_code=422,
            detail='Expected attendees exceed event capacity'
        )

    try:
        recovery = plan_multi_disruption(
            session=session_data,
            rooms=rooms_data,
            other_sessions=booked_data,
            issues=[issue.model_dump() for issue in request.issues],
            required_capacity=required_capacity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    kinds = {issue.type for issue in request.issues}
    if 'SESSION_CANCELLED' in kinds:
        impact_type = 'SESSION_CANCELLED'
    elif 'ROOM_UNAVAILABLE' in kinds:
        impact_type = 'ROOM_UNAVAILABLE'
    else:
        impact_type = 'SESSION_DELAYED'

    # Reuse the already-tested read-only EventMesh impact endpoint.
    impact = analyze_event_impact(
        event_id=event_id,
        session_id=session_id,
        request=ImpactRequest(
            disruption_type=impact_type,
            description=request.description,
        ),
        x_organizer_key=x_organizer_key,
    )

    return {
        'status': recovery['status'],
        'mode': 'RULE_BASED_MULTI_ISSUE',
        'event_id': event_id,
        'session_id': session_id,
        'session_title': session_data['title'],
        'disruptions': [issue.model_dump() for issue in request.issues],
        'recovery_preview': recovery,
        'impact_report': {
            'booking_summary': impact['booking_summary'],
            'payment_recommendation': impact['payment_recommendation'],
            'warnings': impact['warnings'],
            'message_draft': impact['message_draft'],
        },
        'capacity_check': {
            'minimum_room_capacity': required_capacity,
            'basis': (
                'EXPECTED_ATTENDEES'
                if request.expected_attendees is not None
                else 'EVENT_CAPACITY_CONSERVATIVE'
            ),
        },
        'requires_approval': True,
        'can_approve_now': False,
        'persisted': False,
        'applied': False,
        'paypal_called': False,
        'message_sent': False,
    }
