import hmac
import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import APIRouter,Depends, Header, HTTPException,Request
from pydantic import BaseModel, Field
from event_ownership import require_reservation_owner,require_refund_proposal_owner

load_dotenv(Path(__file__).parent / '.env')
router = APIRouter(tags=['Refund Proposals'])
from db_config import DB_PATH
class RefundProposalCreate(BaseModel):
    reservation_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=5, max_length=250)
    amount_usd: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)


def require_refund_create_owner(
    request: Request,
    payload: RefundProposalCreate,
) -> str:
    return require_reservation_owner(
        request,
        payload.reservation_id,
    )


def connection():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db

def initialize_refunds():
    db = connection()
    try:
        db.execute('''
            CREATE TABLE IF NOT EXISTS refund_proposals (
                id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL UNIQUE REFERENCES reservations(id),
                capture_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                currency TEXT NOT NULL DEFAULT 'USD',
                reason TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PENDING_APPROVAL', 'APPROVED_PENDING_PAYPAL')),
                paypal_request_id TEXT NOT NULL UNIQUE,
                paypal_refund_id TEXT UNIQUE,
                created_at TEXT NOT NULL,
                approved_at TEXT
            )
        ''')
        db.commit()
    finally:
        db.close()

initialize_refunds()

def organizer_required(value):
    expected = os.getenv('EVENTMESH_ORGANIZER_KEY')
    if not expected:
        raise HTTPException(503, 'Organizer key not configured')
    if not value or not hmac.compare_digest(value, expected):
        raise HTTPException(403, 'Organizer authorization required')

def usd(cents):
    return f'{cents // 100}.{cents % 100:02d}'

def payment_record(db, reservation_id):
    return db.execute('''
        SELECT r.id, r.event_id, r.status AS reservation_status, r.quantity,
               p.paypal_capture_id, p.currency, p.amount_cents,
               c.status AS checkout_status,
               (SELECT COUNT(*) FROM issued_tickets t WHERE t.reservation_id = r.id) AS issued_count
        FROM reservations r
        LEFT JOIN verified_payments p ON p.reservation_id = r.id
        LEFT JOIN checkout_orders c ON c.reservation_id = r.id
        WHERE r.id = ?
    ''', (reservation_id,)).fetchone()

def payment_eligibility_reason(row):
    if row['reservation_status'] != 'PAID':
        return 'Reservation has not been marked paid'
    if not row['paypal_capture_id'] or row['amount_cents'] is None:
        return 'No verified PayPal capture on record'
    if row['currency'] != 'USD' or row['amount_cents'] <= 0:
        return 'Unsupported or invalid payment amount'
    if row['checkout_status'] != 'CAPTURED':
        return 'Checkout has not been recorded as captured'
    if row['issued_count'] != row['quantity']:
        return 'Tickets and reservation are inconsistent'
    return None


@router.get(
    '/refunds/eligibility/{reservation_id}',
    dependencies=[Depends(require_reservation_owner)],
)

def refund_eligibility(reservation_id: str, x_organizer_key: str | None = Header(default=None)):
    organizer_required(x_organizer_key)
    db = connection()
    try:
        row = payment_record(db, reservation_id)
        if row is None:
            raise HTTPException(404, 'Reservation not found')
        reason = payment_eligibility_reason(row)
        existing = db.execute('SELECT id, status FROM refund_proposals WHERE reservation_id = ?', (reservation_id,)).fetchone()
        if existing:
            reason = 'A refund proposal already exists for this reservation'
        return {
            'reservation_id': reservation_id,
            'eligible': reason is None,
            'reason': reason,
            'captured_amount_usd': usd(row['amount_cents']) if row['amount_cents'] is not None else None,
            'existing_proposal_id': existing['id'] if existing else None,
        }
    finally:
        db.close()

@router.post('/refunds/proposals', status_code=201,dependencies=[Depends(require_refund_create_owner)],)
def create_refund_proposal(payload: RefundProposalCreate, x_organizer_key: str | None = Header(default=None)):
    organizer_required(x_organizer_key)
    db = connection()
    try:
        db.execute('BEGIN IMMEDIATE')
        row = payment_record(db, payload.reservation_id)
        if row is None:
            raise HTTPException(404, 'Reservation not found')
        reason = payment_eligibility_reason(row)
        if reason:
            raise HTTPException(409, reason)
        existing = db.execute('SELECT id FROM refund_proposals WHERE reservation_id = ?', (payload.reservation_id,)).fetchone()
        if existing:
            raise HTTPException(409, 'Refund proposal already exists')
        amount = row['amount_cents'] if payload.amount_usd is None else int(payload.amount_usd * 100)
        if amount <= 0 or amount > row['amount_cents']:
            raise HTTPException(422, 'Refund amount must be within captured amount')
        proposal_id = uuid4().hex
        request_id = uuid4().hex[:24]
        reason_text = payload.reason.strip()
        if len(reason_text) < 5:
            raise HTTPException(422, 'Reason must contain at least five characters')
        db.execute('''
            INSERT INTO refund_proposals
            (id, reservation_id, capture_id, amount_cents, currency, reason,
             status, paypal_request_id, created_at)
            VALUES (?, ?, ?, ?, 'USD', ?, 'PENDING_APPROVAL', ?, ?)
        ''', (proposal_id, payload.reservation_id, row['paypal_capture_id'], amount,
              reason_text, request_id, datetime.now(timezone.utc).isoformat(timespec='seconds')))
        db.commit()
        return {'proposal_id': proposal_id, 'reservation_id': payload.reservation_id,
                'amount_usd': usd(amount), 'status': 'PENDING_APPROVAL', 'paypal_called': False}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@router.post('/refunds/proposals/{proposal_id}/approve', dependencies=[Depends(require_refund_proposal_owner)],)
def approve_refund_proposal(proposal_id: str, x_organizer_key: str | None = Header(default=None)):
    organizer_required(x_organizer_key)
    db = connection()
    try:
        db.execute('BEGIN IMMEDIATE')
        proposal = db.execute('SELECT * FROM refund_proposals WHERE id = ?', (proposal_id,)).fetchone()
        if proposal is None:
            raise HTTPException(404, 'Refund proposal not found')
        if proposal['status'] == 'APPROVED_PENDING_PAYPAL':
            db.commit()
            return {'proposal_id': proposal_id, 'status': 'APPROVED_PENDING_PAYPAL',
                    'amount_usd': usd(proposal['amount_cents']), 'paypal_called': False}
        if proposal['status'] != 'PENDING_APPROVAL':
            raise HTTPException(409, 'Refund proposal is not pending')
        row = payment_record(db, proposal['reservation_id'])
        reason = payment_eligibility_reason(row) if row else 'Reservation not found'
        if reason or row['paypal_capture_id'] != proposal['capture_id'] or proposal['amount_cents'] > row['amount_cents']:
            raise HTTPException(409, 'Payment eligibility changed; approval blocked')
        db.execute('''
            UPDATE refund_proposals
            SET status = 'APPROVED_PENDING_PAYPAL', approved_at = ?
            WHERE id = ? AND status = 'PENDING_APPROVAL'
        ''', (datetime.now(timezone.utc).isoformat(timespec='seconds'), proposal_id))
        db.commit()
        return {'proposal_id': proposal_id, 'status': 'APPROVED_PENDING_PAYPAL',
                'amount_usd': usd(proposal['amount_cents']), 'paypal_called': False}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@router.get('/refunds/proposals/{proposal_id}' ,dependencies=[Depends(require_refund_proposal_owner)],)
def get_refund_proposal(proposal_id: str, x_organizer_key: str | None = Header(default=None)):
    organizer_required(x_organizer_key)
    db = connection()
    try:
        row = db.execute('''
            SELECT id, reservation_id, amount_cents, currency, reason, status, created_at, approved_at
            FROM refund_proposals WHERE id = ?
        ''', (proposal_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Refund proposal not found')
        return {'proposal_id': row['id'], 'reservation_id': row['reservation_id'],
                'amount_usd': usd(row['amount_cents']), 'currency': row['currency'],
                'reason': row['reason'], 'status': row['status'],
                'created_at': row['created_at'], 'approved_at': row['approved_at'],
                'paypal_called': False}
    finally:
        db.close()
