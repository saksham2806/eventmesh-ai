from room_utils import normalize_room

OPEN_MINUTE = 9 * 60
CLOSE_MINUTE = 18 * 60


def to_minutes(text: str) -> int:
    hours, minutes = map(int, text.split(':'))
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError('Invalid HH:MM session time')
    return hours * 60 + minutes


def to_clock(total: int) -> str:
    return f'{total // 60:02d}:{total % 60:02d}'


def slot_is_free(session: dict, other_sessions: list[dict], room: str,
                 start: int, end: int) -> bool:
    target_speaker = str(session.get('speaker') or '').strip().casefold()
    for other in other_sessions:
        other_start = to_minutes(other['start_time'])
        other_end = to_minutes(other['end_time'])
        if not (start < other_end and end > other_start):
            continue
        room_collision = normalize_room(other['room']) == normalize_room(room)
        speaker_collision = bool(target_speaker) and (
            target_speaker == str(other.get('speaker') or '').strip().casefold()
        )
        if room_collision or speaker_collision:
            return False
    return True


def plan_multi_disruption(session: dict, rooms: list[dict],
                          other_sessions: list[dict], issues: list[dict],
                          required_capacity: int) -> dict:
    registered = {normalize_room(room['name']) for room in rooms}
    blocked = set()
    delays = []
    cancelled = False

    for issue in issues:
        kind = issue['type']
        if kind == 'ROOM_UNAVAILABLE':
            room_key = normalize_room(issue['room'])
            if room_key not in registered:
                raise ValueError(f"Unregistered unavailable room: {issue['room']}")
            blocked.add(room_key)
        elif kind == 'SPEAKER_DELAY':
            delays.append(int(issue['delay_minutes']))
        elif kind == 'SESSION_CANCELLED':
            cancelled = True
        else:
            raise ValueError('Unsupported disruption type')

    warnings = [
        'Preview only: no proposal ID has been stored or approved.',
        'Room equipment, attendee availability and room outages outside this report are not checked.'
    ]

    if cancelled:
        return {
            'status': 'CANCELLATION_REVIEW',
            'candidates': [],
            'warnings': warnings + [
                'Cancellation overrides rescheduling suggestions; organizer must review refunds and notices.'
            ],
            'can_approve_now': False,
        }

    original_start = to_minutes(session['start_time'])
    original_end = to_minutes(session['end_time'])
    duration = original_end - original_start
    if duration <= 0 or duration > CLOSE_MINUTE - OPEN_MINUTE:
        raise ValueError('Invalid session duration')

    current_room_blocked = normalize_room(session['room']) in blocked
    delay = max(delays, default=0)
    if delays:
        warnings.append(
            'Speaker delay is treated as the minimum shift from the original start; confirm actual availability.'
        )
    if len(delays) > 1:
        warnings.append('Multiple speaker delays were combined using the maximum, not their sum.')

    if not current_room_blocked and delay == 0:
        return {
            'status': 'NO_SCHEDULE_CHANGE_REQUIRED',
            'candidates': [],
            'warnings': warnings,
            'can_approve_now': False,
        }

    earliest = original_start + delay
    candidate_starts = set(range(OPEN_MINUTE, CLOSE_MINUTE - duration + 1, 30))
    candidate_starts.add(earliest)
    starts = sorted(
        (s for s in candidate_starts
         if s >= earliest and OPEN_MINUTE <= s and s + duration <= CLOSE_MINUTE)
    )

    usable_rooms = [
        room for room in rooms
        if normalize_room(room['name']) not in blocked
        and room['capacity'] >= required_capacity
    ]
    usable_rooms.sort(key=lambda room: (
        normalize_room(room['name']) != normalize_room(session['room']),
        room['capacity'], room['name'].casefold()
    ))

    options = []
    for start in starts:
        end = start + duration
        for room in usable_rooms:
            if not slot_is_free(session, other_sessions, room['name'], start, end):
                continue
            shift = start - original_start
            changed_room = normalize_room(room['name']) != normalize_room(session['room'])
            options.append({
                'room_id': room['id'],
                'room': room['name'],
                'start_time': to_clock(start),
                'end_time': to_clock(end),
                'time_shift_minutes': shift,
                'room_changed': changed_room,
                'disruption_score': shift + (5 if changed_room else 0),
            })
        if len(options) >= 12:
            break

    options.sort(key=lambda o: (o['disruption_score'], o['room'].casefold(), o['start_time']))
    if not options:
        warnings.append('No option satisfies the reported disruptions and basic scheduling constraints.')
    return {
        'status': 'CANDIDATES_PREVIEW' if options else 'MANUAL_REVIEW_REQUIRED',
        'candidates': options[:3],
        'warnings': warnings,
        'can_approve_now': False,
    }
