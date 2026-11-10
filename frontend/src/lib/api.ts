export type EventRecord = { id: number; title: string; description: string; event_date: string; venue: string; capacity: number };
export type Session = { id: number; event_id: number; title: string; speaker: string; room: string; start_time: string; end_time: string };
export type Room = { id: number; event_id: number; name: string; capacity: number };
export type Ticket = { id: number; name: string; price_usd: string; capacity: number; available: number };
export type Issue = { type: "ROOM_UNAVAILABLE" | "SPEAKER_DELAY" | "SESSION_CANCELLED"; room?: string; delay_minutes?: number };
export type Candidate = { room_id: number; room: string; start_time: string; end_time: string; time_shift_minutes: number; room_changed: boolean; disruption_score: number };
export type IncidentPreview = {
  status: string;
  mode: string;
  recovery_preview?: { candidates: Candidate[]; warnings?: string[]; status: string };
  impact_report?: { booking_summary?: { verified_paid_reservations: number; active_pending_reservations: number; recorded_capture_total_usd: string }; payment_recommendation: string; warnings?: string[]; message_draft?: string };
};
export type StoredProposal = { status: string; proposal_id: string; candidate: Candidate; expires_at: string; applied: boolean };
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const result = await fetch(`/api/bridge/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const json: unknown = await result.json().catch(() => ({}));
  if (!result.ok) {
    const detail = (json as {detail?: unknown})?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${result.status})`);
  }
  return json as T;
}
