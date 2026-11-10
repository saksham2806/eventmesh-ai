
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "@/lib/api";
import type { Candidate, EventRecord, IncidentPreview, Issue, Room, Session, StoredProposal, Ticket } from "@/lib/api";
import BryntumClient from "@/components/BryntumClient";
import dynamic from "next/dynamic";
import PayPalReturnNotice from "@/components/PayPalReturnNotice";
import OrganizerAuthGate from "@/components/OrganizerAuthGate";

const EventMeshAGStudio = dynamic(
  () => import("@/components/EventMeshAGStudio"),
  {
    ssr: false,
    loading: () => <p>Loading AG Studio analytics...</p>,
  }
);

type View = "overview" | "schedule" | "incidents" | "tickets" | "insights";
type Notice = { kind: "error" | "ok"; message: string } | null;

const views: { id: View; name: string; glyph: string }[] = [
  { id: "overview", name: "Overview", glyph: "◫" },
  { id: "schedule", name: "Event schedule", glyph: "▦" },
  { id: "incidents", name: "AI recovery", glyph: "✧" },
  { id: "tickets", name: "Tickets & payments", glyph: "▤" },
  { id: "insights", name: "Insights", glyph: "▥" },
];

const time = (x: string) => x?.slice(0, 5) || "—";

const niceDate = (s: string) => {
  try {
    return new Date(`${s}T12:00:00`).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return s;
  }
};

function Home() {
  const [view, setView] = useState<View>("overview");
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [chosenEvent, setChosenEvent] = useState<number | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [healthy, setHealthy] = useState(false);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState<Notice>(null);

  const [eventForm, setEventForm] = useState({
    title: "",
    description: "",
    event_date: "",
    venue: "",
    capacity: 60,
  });

  const [roomForm, setRoomForm] = useState({
    name: "",
    capacity: 50,
  });

  const [sessionForm, setSessionForm] = useState({
    title: "",
    speaker: "",
    room: "",
    start_time: "09:00",
    end_time: "10:00",
  });

  const [ticketForm, setTicketForm] = useState({
    name: "General admission",
    price_usd: "10.00",
    capacity: 30,
  });

  const [booking, setBooking] = useState({
    ticket_type_id: 0,
    quantity: 1,
  });

  const [checkout, setCheckout] = useState<{
    reservation_id: string;
    payment_status: string;
    total: string;
    currency: string;
    checkout_available: boolean;
  } | null>(null);

  const [sandboxOrder, setSandboxOrder] = useState<string | null>(null);
  const [sandboxApprovalUrl, setSandboxApprovalUrl] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [incidentDescription, setIncidentDescription] = useState("");
  const [outage, setOutage] = useState(true);
  const [delay, setDelay] = useState(45);
  const [headcount, setHeadcount] = useState(30);
  const [preview, setPreview] = useState<IncidentPreview | null>(null);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [proposal, setProposal] = useState<StoredProposal | null>(null);
  const [confirmations, setConfirmations] = useState([false, false, false]);

  const selectedEvent = events.find((e) => e.id === chosenEvent) ?? null;
  const selectedSession = sessions.find((s) => s.id === sessionId) ?? null;
  const totalCapacity = events.reduce((a, e) => a + e.capacity, 0);

  const capacityUtilization = useMemo(
    () => tickets.reduce((a, t) => a + t.capacity - t.available, 0),
    [tickets]
  );

  const allCandidates = preview?.recovery_preview?.candidates ?? [];

  const loadEvents = useCallback(async () => {
    try {
      const [health, list] = await Promise.all([
        api<{ status: string }>("health"),
        api<EventRecord[]>("events"),
      ]);

      setHealthy(health.status === "healthy");
      setEvents(list);
      setChosenEvent((current) =>
        current !== null && list.some((x) => x.id === current)
          ? current
          : list[0]?.id ?? null
      );
      setNotice(null);
    } catch (e) {
      setHealthy(false);
      setNotice({ kind: "error", message: (e as Error).message });
    }
  }, []);

  const loadDetails = useCallback(async (id: number) => {
    try {
      const [ss, rr, tt] = await Promise.all([
        api<Session[]>(`events/${id}/sessions`),
        api<Room[]>(`events/${id}/rooms`),
        api<Ticket[]>(`events/${id}/ticket-types`),
      ]);

      setSessions(ss);
      setRooms(rr);
      setTickets(tt);

      setSessionId((current) =>
        current !== null && ss.some((x) => x.id === current)
          ? current
          : ss[0]?.id ?? null
      );

      setBooking((current) => ({
        ...current,
        ticket_type_id: tt.some((t) => t.id === current.ticket_type_id)
          ? current.ticket_type_id
          : tt[0]?.id ?? 0,
      }));
    } catch (e) {
      setNotice({ kind: "error", message: (e as Error).message });
    }
  }, []);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  useEffect(() => {
    if (chosenEvent === null) {
      setSessions([]);
      setRooms([]);
      setTickets([]);
      return;
    }

    void loadDetails(chosenEvent);
    setPreview(null);
    setCandidate(null);
    setProposal(null);
    setCheckout(null);
    setSandboxOrder(null);
    setSandboxApprovalUrl(null);
  }, [chosenEvent, loadDetails]);

  useEffect(() => {
    setPreview(null);
    setCandidate(null);
    setProposal(null);
    setConfirmations([false, false, false]);
  }, [sessionId]);

  useEffect(() => {
    if (selectedSession) {
      setIncidentDescription(
        `${selectedSession.room} is unavailable and the speaker is delayed by 45 minutes.`
      );
    }
  }, [selectedSession?.id, selectedSession?.room]); // eslint-disable-line react-hooks/exhaustive-deps

  async function action(fn: () => Promise<void>, label: string) {
    setBusy(label);
    setNotice(null);

    try {
      await fn();
    } catch (e) {
      setNotice({ kind: "error", message: (e as Error).message });
    } finally {
      setBusy("");
    }
  }

  function done(message: string) {
    setNotice({ kind: "ok", message });
  }

  const createEvent = (e: FormEvent) => {
    e.preventDefault();

    void action(async () => {
      const made = await api<EventRecord>("events", eventForm);
      await loadEvents();
      setChosenEvent(made.id);

      setEventForm({
        title: "",
        description: "",
        event_date: "",
        venue: "",
        capacity: 60,
      });

      done("Event created. Add rooms and sessions to get started.");
    }, "event");
  };

  const createRoom = (e: FormEvent) => {
    e.preventDefault();
    if (!chosenEvent) return;

    void action(async () => {
      await api(`events/${chosenEvent}/rooms`, roomForm);
      await loadDetails(chosenEvent);
      setRoomForm({ name: "", capacity: 50 });
      done("Room added to the registry.");
    }, "room");
  };

  const createSession = (e: FormEvent) => {
    e.preventDefault();
    if (!chosenEvent) return;

    void action(async () => {
      if (sessionForm.start_time >= sessionForm.end_time) {
        throw Error("End time must be after start time.");
      }

      const room = sessionForm.room || rooms[0]?.name;
      if (!room) throw Error("Create a room first.");

      await api(`events/${chosenEvent}/sessions`, {
        ...sessionForm,
        room,
      });

      await loadDetails(chosenEvent);

      setSessionForm({
        title: "",
        speaker: "",
        room,
        start_time: "09:00",
        end_time: "10:00",
      });

      done("Session added. Scheduling conflicts are checked by FastAPI.");
    }, "session");
  };

  const createTicket = (e: FormEvent) => {
    e.preventDefault();
    if (!chosenEvent) return;

    void action(async () => {
      await api(`events/${chosenEvent}/ticket-types`, ticketForm);
      await loadDetails(chosenEvent);
      done("Ticket type created.");
    }, "ticket");
  };

  function buildIssues(): Issue[] {
    if (!selectedSession) throw Error("Select a session first.");

    const result: Issue[] = [];

    if (outage) {
      result.push({
        type: "ROOM_UNAVAILABLE",
        room: selectedSession.room,
      });
    }

    if (delay > 0) {
      result.push({
        type: "SPEAKER_DELAY",
        delay_minutes: delay,
      });
    }

    if (!result.length) throw Error("Choose at least one disruption.");
    return result;
  }

  function buildPayload() {
    return {
      description: incidentDescription.trim(),
      issues: buildIssues(),
      expected_attendees: headcount,
    };
  }

  async function makePreview() {
    if (!chosenEvent || !sessionId) {
      throw Error("Choose an event and session first.");
    }

    const data = await api<IncidentPreview>(
      `ai/events/${chosenEvent}/sessions/${sessionId}/multi-incident-preview`,
      buildPayload()
    );

    setPreview(data);
    setCandidate(null);
    setProposal(null);

    done(
      `Analysis ready. ${data.recovery_preview?.candidates?.length ?? 0} recovery candidates found.`
    );
  }

  async function storeProposal() {
    if (!chosenEvent || !sessionId || !candidate) {
      throw Error("Choose a recovery candidate first.");
    }

    const data = await api<StoredProposal>(
      `ai/events/${chosenEvent}/sessions/${sessionId}/multi-recovery-proposals`,
      {
        ...buildPayload(),
        selected_candidate: {
          room_id: candidate.room_id,
          start_time: candidate.start_time,
          end_time: candidate.end_time,
        },
      }
    );

    setProposal(data);
    done(
      `Recovery proposal ${data.status.toLowerCase()}. Organizer approval is still required.`
    );
  }

  async function approve() {
    if (!proposal || !chosenEvent) throw Error("Create a proposal first.");

    if (!confirmations.every(Boolean)) {
      throw Error("All three organizer confirmations are required.");
    }

    const answer = await api<{ status: string; applied: boolean }>(
      `ai/multi-recovery-proposals/${proposal.proposal_id}/approve`,
      {
        confirm_room_suitability: confirmations[0],
        confirm_speaker_availability: confirmations[1],
        confirm_attendee_impact_reviewed: confirmations[2],
      }
    );

    await loadDetails(chosenEvent);

    setProposal({
      ...proposal,
      status: answer.status,
      applied: answer.applied,
    });

    setPreview(null);
    setCandidate(null);

    done(
      answer.applied
        ? "Recovery approved and schedule updated in SQLite."
        : "Approval recorded without a schedule change."
    );
  }

  async function reserve() {
    setSandboxOrder(null);
    setSandboxApprovalUrl(null);
    window.localStorage.removeItem("eventmesh_pending_paypal");

    if (!chosenEvent || !booking.ticket_type_id) {
      throw Error("Select a ticket category first.");
    }

    const result = await api<{ reservation_id?: string; id?: string }>(
      `events/${chosenEvent}/reservations`,
      booking
    );

    const id = result.reservation_id || result.id;

    if (!id) {
      throw Error("Reservation created but did not return an ID.");
    }

    const receipt = await api<{
      reservation_id: string;
      payment_status: string;
      total: string;
      currency: string;
      checkout_available: boolean;
    }>(`checkout/reservations/${id}/preview`);

    setCheckout(receipt);
    await loadDetails(chosenEvent);

    done("Reservation held. No money was collected; this is a checkout preview.");
  }

  async function createSandboxOrder() {
    if (!checkout?.reservation_id) {
      throw Error("Reserve a ticket first.");
    }

    if (!checkout.checkout_available) {
      throw Error("PayPal Sandbox is not configured.");
    }

    const result = await api<{
      id?: string;
      order_id?: string;
      paypal_order_id?: string;
      approval_url?: string | null;
    }>(
      `checkout/reservations/${encodeURIComponent(
        checkout.reservation_id
      )}/paypal-order`,
      {}
    );

    const orderId =
      result.paypal_order_id ||
      result.order_id ||
      result.id;

    if (!orderId) {
      throw Error("PayPal did not return an order ID.");
    }

    setSandboxOrder(orderId);
    setSandboxApprovalUrl(null);

    if (result.approval_url) {
      const url = new URL(result.approval_url);

      if (
        url.protocol !== "https:" ||
        url.hostname !== "www.sandbox.paypal.com"
      ) {
        throw Error("Unexpected PayPal approval URL.");
      }

      setSandboxApprovalUrl(url.toString());
    }

    window.localStorage.setItem(
      "eventmesh_pending_paypal",
      JSON.stringify({
        reservationId: checkout.reservation_id,
        orderId: orderId,
      })
    );

    done(
      "Sandbox order created. Awaiting buyer approval. No payment captured."
    );
  }

  const navigate = (next: View) => {
    setView(next);
    setNotice(null);
  };

  const currentView =
    views.find((item) => item.id === view)?.name ?? "Overview";

  const sessionsByStart = [...sessions].sort((a, b) =>
    a.start_time.localeCompare(b.start_time)
  );

  const bestCandidateScore = allCandidates.length
    ? Math.min(...allCandidates.map((item) => item.disruption_score))
    : null;

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-symbol" aria-hidden="true">
            E<span>✳</span>
          </span>
          <div>
            <strong>
              EventMesh<span className="brand-accent">.</span>
            </strong>
            <small>AI OPERATIONS</small>
          </div>
        </div>

        <div className="sidebar-group-title">WORKSPACE</div>

        <nav className="side-nav" aria-label="Dashboard sections">
          {views.map((item) => (
            <button
              type="button"
              className={`nav-item ${view === item.id ? "active" : ""}`}
              key={item.id}
              onClick={() => navigate(item.id)}
              aria-current={view === item.id ? "page" : undefined}
            >
              <NavGlyph type={item.id} />
              <span className="nav-text">{item.name}</span>
              {view === item.id && (
                <span className="nav-arrow" aria-hidden="true">›</span>
              )}
            </button>
          ))}

          <a className="nav-item" href="/webhooks">
            <NavGlyph type="webhooks" />
            <span className="nav-text">PayPal Webhooks</span>
          </a>
        </nav>

        <div className="sidebar-bottom">
          <div className="agent-panel">
            <span className="agent-led" />
            <div>
              <b>Recovery engine</b>
              <small>Rule-based · Human approved</small>
            </div>
            <span className="agent-panel-icon">✳</span>
          </div>
          <div className="side-foot">
            <span>EVENT OPERATIONS</span>
            <span>v1.3</span>
          </div>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div className="crumb">
            <span>WORKSPACE</span>
            <span className="crumb-divider">/</span>
            <strong>{currentView}</strong>
          </div>

          <div className="top-actions">
            <span className={`connection ${healthy ? "up" : "down"}`}>
              <span className="connection-dot" />
              {healthy ? "API online" : "Backend unavailable"}
            </span>

            <button
              type="button"
              className="refresh"
              onClick={() =>
                void action(async () => {
                  await loadEvents();
                  if (chosenEvent) await loadDetails(chosenEvent);
                  done("Workspace synced with FastAPI.");
                }, "refresh")
              }
              disabled={!!busy}
            >
              <span aria-hidden="true">↻</span>
              <span>{busy === "refresh" ? "Syncing" : "Refresh"}</span>
            </button>

            <span className="avatar" aria-label="EventMesh organizer">
              EM
            </span>
          </div>
        </header>

        <div className="workspace">
          <div className="page-head">
            <div className="page-intro">
              <div className="eyebrow">
                <span className="pulse" />
                EVENT INTELLIGENCE / OPERATIONS
              </div>

              <h1>
                {view === "overview" ? "Mission control" : currentView}
                <span className="title-dot">.</span>
              </h1>

              <p>
                {view === "overview"
                  ? "A clearer view of every event, decision and next move."
                  : view === "schedule"
                  ? "Coordinate rooms, speakers and sessions with conflict checks."
                  : view === "incidents"
                  ? "Turn disruptions into explainable, organizer-approved recovery plans."
                  : view === "tickets"
                  ? "Track inventory, reservations and Sandbox checkout safely."
                  : "Make sense of real event operations data."}
              </p>
            </div>

            <div className="event-switch">
              <label htmlFor="event-select">CURRENT EVENT</label>
              <select
                id="event-select"
                value={chosenEvent ?? ""}
                onChange={(e) =>
                  setChosenEvent(
                    e.target.value ? Number(e.target.value) : null
                  )
                }
              >
                <option value="" disabled>Select an event</option>
                {events.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.title}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {notice &&
            (notice.kind === "error" ||
              view === "incidents" ||
              !notice.message.startsWith("Analysis ready.")) && (
              <div
                role={notice.kind === "error" ? "alert" : "status"}
                className={`notice ${notice.kind}`}
              >
                <span className="notice-symbol" aria-hidden="true">
                  {notice.kind === "ok" ? "✓" : "!"}
                </span>
                <span>{notice.message}</span>
                <button
                  type="button"
                  onClick={() => setNotice(null)}
                  aria-label="Dismiss notification"
                >
                  ×
                </button>
              </div>
            )}

          {!events.length && healthy && view !== "overview" && (
            <div className="empty-banner">
              Create an event in Overview to unlock the rest of your workspace.
            </div>
          )}

          <PayPalReturnNotice />

          {view === "overview" && (
            <>
              <div className="stats-grid">
                <Stat label="TOTAL EVENTS" value={String(events.length).padStart(2, "0")} foot="Across your workspace" icon="◈" />
                <Stat label="SCHEDULED SESSIONS" value={String(sessions.length).padStart(2, "0")} foot="For the selected event" icon="▦" />
                <Stat label="REGISTERED ROOMS" value={String(rooms.length).padStart(2, "0")} foot="For the selected event" icon="▣" />
                <Stat label="EVENT CAPACITY" value={totalCapacity.toLocaleString()} foot="Across all your events" icon="◎" />
              </div>

              <div className="overview-columns">
                <section className="panel feature-panel">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">CONTROL CENTER / 01</span>
                      <h2>Operational intelligence</h2>
                    </div>
                    <span className="subtle-pill">HUMAN IN CONTROL</span>
                  </div>

                  <div className="feature-content">
                    <div className="feature-text">
                      <span className="feature-tag">
                        <span className="feature-tag-dot" />
                        SMARTER EVENT OPERATIONS
                      </span>
                      <h3>Keep every event<br /><em>one step ahead.</em></h3>
                      <p>
                        Analyze disruptions, compare conflict-checked
                        options, and take action only after organizer
                        approval.
                      </p>
                      <button
                        type="button"
                        className="btn primary"
                        onClick={() => navigate("incidents")}
                      >
                        Explore AI recovery
                        <span aria-hidden="true">↗</span>
                      </button>
                    </div>

                    <div className="ambient-orbit" aria-hidden="true">
                      <span className="orbit ring-1" />
                      <span className="orbit ring-2" />
                      <span className="orbit ring-3" />
                      <span className="core">✳</span>
                      <span className="orb-dot d1" />
                      <span className="orb-dot d2" />
                      <span className="orb-dot d3" />
                    </div>
                  </div>

                  <div className="three-foot">
                    <span><i className="dot-emerald" /> Conflict validation</span>
                    <span><i className="dot-emerald" /> Human approval</span>
                    <span><i className="dot-amber" /> Sandbox payments</span>
                  </div>
                </section>

                <section className="panel events-panel">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">YOUR WORKSPACE / 02</span>
                      <h2>Managed events</h2>
                    </div>
                    <span className="count-pill">{events.length}</span>
                  </div>

                  <div className="events-stack">
                    {events.length ? (
                      events.slice(0, 6).map((event, index) => (
                        <button
                          type="button"
                          className={`event-row ${event.id === chosenEvent ? "chosen" : ""}`}
                          key={event.id}
                          onClick={() => setChosenEvent(event.id)}
                        >
                          <span className="event-index">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <span className="event-description">
                            <b>{event.title}</b>
                            <small>
                              {niceDate(event.event_date)} · {event.venue}
                            </small>
                          </span>
                          <span className="event-arr" aria-hidden="true">↗</span>
                        </button>
                      ))
                    ) : (
                      <div className="empty-content">
                        No events yet. Create your first event below.
                      </div>
                    )}
                  </div>

                  <div className="events-panel-foot">
                    <span className="agent-led" />
                    {selectedEvent
                      ? `Currently managing: ${selectedEvent.title}`
                      : "Select an event to begin"}
                  </div>
                </section>
              </div>

              <div className="overview-columns overview-detail-columns">
                <section className="panel schedule-snapshot">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">SELECTED EVENT / 03</span>
                      <h2>Session overview</h2>
                    </div>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => navigate("schedule")}
                    >
                      Full schedule ↗
                    </button>
                  </div>

                  <div className="snapshot-list">
                    {sessionsByStart.length ? (
                      sessionsByStart.slice(0, 4).map((session) => (
                        <div className="snapshot-row" key={session.id}>
                          <div className="snapshot-time">
                            {time(session.start_time)}
                          </div>
                          <div className="snapshot-marker" aria-hidden="true" />
                          <div className="snapshot-details">
                            <b>{session.title}</b>
                            <small>
                              {session.room} · {session.speaker}
                            </small>
                          </div>
                          <span className="snapshot-end">
                            {time(session.end_time)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="empty-content">
                        No sessions scheduled for this event yet.
                      </div>
                    )}
                  </div>
                </section>

                <section className="panel readiness-panel">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">EVENT SNAPSHOT / 04</span>
                      <h2>Workspace overview</h2>
                    </div>
                    <span className="subtle-pill">LIVE DATA</span>
                  </div>

                  <div className="readiness-list">
                    <div>
                      <span>Selected event</span>
                      <strong>{selectedEvent?.title ?? "None"}</strong>
                    </div>
                    <div>
                      <span>Registered rooms</span>
                      <strong>{rooms.length}</strong>
                    </div>
                    <div>
                      <span>Ticket categories</span>
                      <strong>{tickets.length}</strong>
                    </div>
                    <div>
                      <span>Seats held / sold</span>
                      <strong>{capacityUtilization}</strong>
                    </div>
                  </div>

                  <button
                    type="button"
                    className="btn secondary wide"
                    onClick={() => navigate("tickets")}
                  >
                    View ticketing <span aria-hidden="true">↗</span>
                  </button>
                </section>
              </div>

              <section className="panel form-panel">
                <div className="panel-top">
                  <div>
                    <span className="section-kicker">NEW EVENT / 05</span>
                    <h2>Create an event</h2>
                  </div>
                  <span className="subtle-pill">ORGANIZER TOOL</span>
                </div>

                <form className="form-grid" onSubmit={createEvent}>
                  <label className="field span-two">
                    Event title
                    <input
                      required
                      minLength={3}
                      maxLength={100}
                      value={eventForm.title}
                      onChange={(e) =>
                        setEventForm({ ...eventForm, title: e.target.value })
                      }
                      placeholder="e.g. AI Innovation Summit"
                    />
                  </label>

                  <label className="field">
                    Event date
                    <input
                      type="date"
                      required
                      value={eventForm.event_date}
                      onChange={(e) =>
                        setEventForm({
                          ...eventForm,
                          event_date: e.target.value,
                        })
                      }
                    />
                  </label>

                  <label className="field">
                    Venue
                    <input
                      required
                      minLength={2}
                      value={eventForm.venue}
                      onChange={(e) =>
                        setEventForm({ ...eventForm, venue: e.target.value })
                      }
                      placeholder="Grand Convention Center"
                    />
                  </label>

                  <label className="field">
                    Capacity
                    <input
                      type="number"
                      min={1}
                      max={1000000}
                      required
                      value={eventForm.capacity}
                      onChange={(e) =>
                        setEventForm({
                          ...eventForm,
                          capacity: Number(e.target.value),
                        })
                      }
                    />
                  </label>

                  <label className="field span-two">
                    Description
                    <input
                      value={eventForm.description}
                      onChange={(e) =>
                        setEventForm({
                          ...eventForm,
                          description: e.target.value,
                        })
                      }
                      placeholder="A short description of your event"
                    />
                  </label>

                  <button
                    className="btn primary form-submit"
                    type="submit"
                    disabled={!!busy}
                  >
                    {busy === "event" ? "Creating…" : "Create event"}
                    <span aria-hidden="true">↗</span>
                  </button>
                </form>
              </section>
            </>
          )}

          {view === "schedule" && (
            <>
              <div className="split-columns">
                <section className="panel">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">RESOURCES / 01</span>
                      <h2>Room registry</h2>
                    </div>
                    <span className="count-pill">{rooms.length}</span>
                  </div>

                  <div className="room-list">
                    {rooms.map((room) => (
                      <div className="room-item" key={room.id}>
                        <span className="room-icon">▦</span>
                        <div>
                          <b>{room.name}</b>
                          <small>{room.capacity} seats</small>
                        </div>
                        <span className="room-status">REGISTERED</span>
                      </div>
                    ))}
                    {!rooms.length && (
                      <div className="empty-content">
                        No rooms registered for this event.
                      </div>
                    )}
                  </div>

                  <form className="inline-form" onSubmit={createRoom}>
                    <h3>Add a room</h3>
                    <label className="field">
                      Room name
                      <input
                        required
                        minLength={2}
                        placeholder="Hall A"
                        value={roomForm.name}
                        onChange={(e) =>
                          setRoomForm({ ...roomForm, name: e.target.value })
                        }
                      />
                    </label>

                    <label className="field">
                      Capacity
                      <input
                        type="number"
                        min={1}
                        required
                        value={roomForm.capacity}
                        onChange={(e) =>
                          setRoomForm({
                            ...roomForm,
                            capacity: Number(e.target.value),
                          })
                        }
                      />
                    </label>

                    <button
                      className="btn primary"
                      disabled={!chosenEvent || !!busy}
                      type="submit"
                    >
                      Add room <span aria-hidden="true">↗</span>
                    </button>
                  </form>
                </section>

                <section className="panel">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">SCHEDULING / 02</span>
                      <h2>Create a session</h2>
                    </div>
                    <span className="subtle-pill">CONFLICT CHECKED</span>
                  </div>

                  <form className="inline-form" onSubmit={createSession}>
                    <label className="field">
                      Session title
                      <input
                        required
                        minLength={3}
                        value={sessionForm.title}
                        onChange={(e) =>
                          setSessionForm({
                            ...sessionForm,
                            title: e.target.value,
                          })
                        }
                        placeholder="Opening keynote"
                      />
                    </label>

                    <label className="field">
                      Speaker
                      <input
                        required
                        minLength={2}
                        value={sessionForm.speaker}
                        onChange={(e) =>
                          setSessionForm({
                            ...sessionForm,
                            speaker: e.target.value,
                          })
                        }
                        placeholder="Guest speaker"
                      />
                    </label>

                    <label className="field">
                      Room
                      <select
                        required
                        value={sessionForm.room || rooms[0]?.name || ""}
                        onChange={(e) =>
                          setSessionForm({
                            ...sessionForm,
                            room: e.target.value,
                          })
                        }
                      >
                        <option value="" disabled>Choose a room</option>
                        {rooms.map((room) => (
                          <option key={room.id} value={room.name}>
                            {room.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="field-pair">
                      <label className="field">
                        Start time
                        <input
                          type="time"
                          required
                          value={sessionForm.start_time}
                          onChange={(e) =>
                            setSessionForm({
                              ...sessionForm,
                              start_time: e.target.value,
                            })
                          }
                        />
                      </label>

                      <label className="field">
                        End time
                        <input
                          type="time"
                          required
                          value={sessionForm.end_time}
                          onChange={(e) =>
                            setSessionForm({
                              ...sessionForm,
                              end_time: e.target.value,
                            })
                          }
                        />
                      </label>
                    </div>

                    <button
                      className="btn primary"
                      type="submit"
                      disabled={!chosenEvent || !rooms.length || !!busy}
                    >
                      Save session <span aria-hidden="true">↗</span>
                    </button>
                  </form>
                </section>
              </div>

              <section className="panel schedule-panel">
                <div className="panel-top">
                  <div>
                    <span className="section-kicker">LIVE RESOURCE VIEW / 03</span>
                    <h2>Room timeline</h2>
                  </div>
                  <span className="subtle-pill">BRYNTUM TRIAL · READ ONLY</span>
                </div>

                {selectedEvent ? (
                  <BryntumClient
                    key={`${selectedEvent.id}-${JSON.stringify(sessions)}`}
                    rooms={rooms}
                    sessions={sessions}
                    date={selectedEvent.event_date}
                  />
                ) : (
                  <div className="empty-content">
                    Select an event to view the schedule.
                  </div>
                )}

                <div className="panel-note">
                  Scheduling data comes from FastAPI. Editing the schedule
                  requires backend conflict validation.
                </div>
              </section>
            </>
          )}

          {view === "incidents" && (
            <>
              <section className="incident-intro">
                <div>
                  <span className="section-kicker">
                    RECOVERY COMMAND / HUMAN-IN-THE-LOOP
                  </span>
                  <h2>Plan the best<br />next move<span>.</span></h2>
                  <p>
                    Report a disruption, compare explainable recovery
                    options and decide what changes—without automatic
                    payments or schedule updates.
                  </p>
                </div>

                <div
                  className="agent-pipeline"
                  aria-label="Three-stage recovery workflow"
                >
                  <span><small>01</small><b>DETECT</b></span>
                  <i>→</i>
                  <span><small>02</small><b>PLAN</b></span>
                  <i>→</i>
                  <span><small>03</small><b>APPROVE</b></span>
                </div>
              </section>

              <div className="split-columns incident-grid">
                <section className="panel">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">STEP 01 / REPORT</span>
                      <h2>Describe disruption</h2>
                    </div>
                    <span className="count-pill">01</span>
                  </div>

                  <div className="inline-form">
                    <label className="field">
                      Affected session
                      <select
                        value={sessionId ?? ""}
                        onChange={(e) =>
                          setSessionId(Number(e.target.value))
                        }
                      >
                        {!sessions.length && <option value="">No sessions</option>}
                        {sessions.map((session) => (
                          <option key={session.id} value={session.id}>
                            {session.title} · {session.room}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="field">
                      What happened?
                      <textarea
                        rows={4}
                        minLength={10}
                        value={incidentDescription}
                        onChange={(e) =>
                          setIncidentDescription(e.target.value)
                        }
                        placeholder="Describe the disruption…"
                      />
                    </label>

                    <div className="field-pair checkbox-pair">
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={outage}
                          onChange={(e) => setOutage(e.target.checked)}
                        />
                        Room unavailable
                      </label>

                      <label className="field">
                        Speaker delay (minutes)
                        <input
                          type="number"
                          min={0}
                          max={480}
                          value={delay}
                          onChange={(e) =>
                            setDelay(Number(e.target.value))
                          }
                        />
                      </label>
                    </div>

                    <label className="field">
                      Expected attendees
                      <input
                        type="number"
                        min={1}
                        max={selectedEvent?.capacity || 10000}
                        value={headcount}
                        onChange={(e) =>
                          setHeadcount(Number(e.target.value))
                        }
                      />
                    </label>

                    <div className="hint">
                      <strong>How it works</strong>
                      <span>
                        Rule-based scheduling analysis uses the selected
                        disruption details. No live LLM is required for
                        this preview.
                      </span>
                    </div>

                    <button
                      type="button"
                      className="btn primary wide"
                      disabled={!chosenEvent || !sessionId || !!busy}
                      onClick={() => void action(makePreview, "analyze")}
                    >
                      {busy === "analyze"
                        ? "Analyzing…"
                        : "Generate recovery analysis"}
                      <span aria-hidden="true">✳</span>
                    </button>
                  </div>
                </section>

                <section className="panel">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">STEP 02 / EVALUATE</span>
                      <h2>Recommended options</h2>
                    </div>
                    <span className="count-pill">{allCandidates.length}</span>
                  </div>

                  {!preview ? (
                    <div className="empty-analysis">
                      <div className="analysis-glyph" aria-hidden="true">✳</div>
                      <b>Your recovery plan starts here</b>
                      <p>
                        Choose a session, describe the issue and generate
                        alternatives.
                      </p>
                    </div>
                  ) : (
                    <div className="candidates">
                      {allCandidates.length === 0 ? (
                        <div className="empty-content">
                          No valid candidates found. Check available
                          rooms, capacity and schedule conflicts.
                        </div>
                      ) : (
                        allCandidates.map((item, i) => (
                          <button
                            type="button"
                            key={`${item.room_id}-${item.start_time}`}
                            className={`candidate ${
                              candidate?.room_id === item.room_id &&
                              candidate?.start_time === item.start_time
                                ? "selected"
                                : ""
                            }`}
                            onClick={() => {
                              setCandidate(item);
                              setProposal(null);
                            }}
                          >
                            <div className="candidate-top">
                              <span>
                                OPTION {String(i + 1).padStart(2, "0")}
                                {item.disruption_score === bestCandidateScore
                                  ? " · LOWEST SCORE"
                                  : ""}
                              </span>
                              <b>
                                {candidate?.room_id === item.room_id &&
                                candidate?.start_time === item.start_time
                                  ? "✓ SELECTED"
                                  : "SELECT ↗"}
                              </b>
                            </div>
                            <strong>{item.room}</strong>
                            <p>
                              {time(item.start_time)} – {time(item.end_time)}
                              <span>
                                {" "}· Shift +{item.time_shift_minutes} min
                              </span>
                            </p>
                            <div className="score-track">
                              <i
                                style={{
                                  width: `${Math.min(
                                    100,
                                    Math.max(5, item.disruption_score)
                                  )}%`,
                                }}
                              />
                            </div>
                            <small>
                              Disruption score {item.disruption_score}
                              {" "}· lower is better
                            </small>
                          </button>
                        ))
                      )}

                      {preview.impact_report && (
                        <div className="impact-box">
                          <div className="section-kicker">
                            PAYMENT IMPACT REVIEW
                          </div>
                          <p>
                            {preview.impact_report.payment_recommendation}
                          </p>
                          <div>
                            <span>Verified paid reservations</span>
                            <b>
                              {preview.impact_report.booking_summary
                                ?.verified_paid_reservations ?? 0}
                            </b>
                          </div>
                          <div>
                            <span>Pending reservations</span>
                            <b>
                              {preview.impact_report.booking_summary
                                ?.active_pending_reservations ?? 0}
                            </b>
                          </div>
                        </div>
                      )}

                      {candidate && !proposal && (
                        <button
                          type="button"
                          className="btn primary wide"
                          disabled={!!busy}
                          onClick={() =>
                            void action(storeProposal, "proposal")
                          }
                        >
                          Save selected recovery
                          <span aria-hidden="true">↗</span>
                        </button>
                      )}
                    </div>
                  )}
                </section>
              </div>

              {proposal && (
                <section className="panel approve-panel">
                  <div className="panel-top">
                    <div>
                      <span className="section-kicker">
                        STEP 03 / HUMAN APPROVAL
                      </span>
                      <h2>Review before applying</h2>
                    </div>
                    <span
                      className={`state-tag ${
                        proposal.applied ? "approved" : "pending"
                      }`}
                    >
                      {proposal.status}
                    </span>
                  </div>

                  <div className="approve-layout">
                    <div>
                      <div className="proposal-label">PROPOSAL ID</div>
                      <code className="proposal-id">
                        {proposal.proposal_id}
                      </code>
                      <p className="muted">
                        Proposed change: <b>{proposal.candidate.room}</b>
                        {" "}· {proposal.candidate.start_time}–
                        {proposal.candidate.end_time}
                      </p>
                      <p className="muted">
                        Expires: {new Date(
                          proposal.expires_at
                        ).toLocaleString()}
                      </p>
                    </div>

                    <div className="confirm-list">
                      {[
                        "I confirmed the room is suitable and available.",
                        "I confirmed the speaker's availability.",
                        "I reviewed attendee and payment impact.",
                      ].map((text, i) => (
                        <label className="check" key={text}>
                          <input
                            type="checkbox"
                            checked={confirmations[i]}
                            disabled={proposal.applied}
                            onChange={(e) =>
                              setConfirmations((old) =>
                                old.map((value, j) =>
                                  j === i ? e.target.checked : value
                                )
                              )
                            }
                          />
                          {text}
                        </label>
                      ))}

                      <button
                        type="button"
                        className="btn primary wide"
                        disabled={
                          proposal.applied ||
                          !confirmations.every(Boolean) ||
                          !!busy
                        }
                        onClick={() => void action(approve, "approve")}
                      >
                        {proposal.applied
                          ? "✓ Schedule updated"
                          : "Approve & apply change ↗"}
                      </button>
                    </div>
                  </div>
                </section>
              )}
            </>
          )}

          {view === "tickets" && (
            <div className="split-columns">
              <section className="panel">
                <div className="panel-top">
                  <div>
                    <span className="section-kicker">INVENTORY / 01</span>
                    <h2>Ticket categories</h2>
                  </div>
                  <span className="count-pill">{tickets.length}</span>
                </div>

                <div className="ticket-list">
                  {tickets.length ? (
                    tickets.map((ticket) => (
                      <div className="ticket-row" key={ticket.id}>
                        <div>
                          <b>{ticket.name}</b>
                          <small>
                            {ticket.available} of {ticket.capacity} available
                          </small>
                          <div className="ticket-inventory">
                            <i
                              style={{
                                width: `${
                                  ticket.capacity
                                    ? (ticket.available / ticket.capacity) * 100
                                    : 0
                                }%`,
                              }}
                            />
                          </div>
                        </div>
                        <strong>${ticket.price_usd}</strong>
                      </div>
                    ))
                  ) : (
                    <div className="empty-content">
                      No ticket categories for this event.
                    </div>
                  )}
                </div>

                <form onSubmit={createTicket} className="inline-form">
                  <h3>Create ticket category</h3>

                  <label className="field">
                    Name
                    <input
                      required
                      value={ticketForm.name}
                      onChange={(e) =>
                        setTicketForm({
                          ...ticketForm,
                          name: e.target.value,
                        })
                      }
                    />
                  </label>

                  <div className="field-pair">
                    <label className="field">
                      Price (USD)
                      <input
                        type="number"
                        step="0.01"
                        min="0.01"
                        required
                        value={ticketForm.price_usd}
                        onChange={(e) =>
                          setTicketForm({
                            ...ticketForm,
                            price_usd: e.target.value,
                          })
                        }
                      />
                    </label>

                    <label className="field">
                      Capacity
                      <input
                        type="number"
                        min={1}
                        required
                        value={ticketForm.capacity}
                        onChange={(e) =>
                          setTicketForm({
                            ...ticketForm,
                            capacity: Number(e.target.value),
                          })
                        }
                      />
                    </label>
                  </div>

                  <button
                    className="btn primary"
                    type="submit"
                    disabled={!chosenEvent || !!busy}
                  >
                    Create category <span aria-hidden="true">↗</span>
                  </button>
                </form>
              </section>

              <section className="panel">
                <div className="panel-top">
                  <div>
                    <span className="section-kicker">PAYPAL SANDBOX / 02</span>
                    <h2>Reservation & checkout</h2>
                  </div>
                  <span className="subtle-pill">PREVIEW · NO CHARGE</span>
                </div>

                <div className="inline-form">
                  <div className="hint">
                    <strong>Safe checkout preview</strong>
                    <span>
                      Holding a reservation doesn't charge a payment
                      method or mark a ticket paid. Sandbox order creation
                      is a separate action.
                    </span>
                  </div>

                  <label className="field">
                    Ticket category
                    <select
                      value={booking.ticket_type_id || ""}
                      onChange={(e) =>
                        setBooking({
                          ...booking,
                          ticket_type_id: Number(e.target.value),
                        })
                      }
                    >
                      <option value="" disabled>Choose a ticket</option>
                      {tickets.map((ticket) => (
                        <option key={ticket.id} value={ticket.id}>
                          {ticket.name} · ${ticket.price_usd}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="field">
                    Quantity (maximum 5)
                    <input
                      type="number"
                      min={1}
                      max={5}
                      value={booking.quantity}
                      onChange={(e) =>
                        setBooking({
                          ...booking,
                          quantity: Number(e.target.value),
                        })
                      }
                    />
                  </label>

                  <button
                    type="button"
                    className="btn primary"
                    disabled={!chosenEvent || !tickets.length || !!busy}
                    onClick={() => void action(reserve, "reserve")}
                  >
                    Reserve & preview checkout
                    <span aria-hidden="true">↗</span>
                  </button>

                  {checkout && (
                    <div className="checkout-receipt">
                      <div className="section-kicker">CHECKOUT PREVIEW</div>
                      <div>
                        <span>Total</span>
                        <strong>
                          {checkout.currency} {checkout.total}
                        </strong>
                      </div>
                      <div>
                        <span>Status</span>
                        <strong>{checkout.payment_status}</strong>
                      </div>
                      <div>
                        <span>Sandbox configured</span>
                        <strong>
                          {checkout.checkout_available ? "Yes" : "No"}
                        </strong>
                      </div>
                      <small>Reservation: {checkout.reservation_id}</small>
                    </div>
                  )}

                  {checkout && (
                    <div className="sandbox-order-actions">
                      <button
                        type="button"
                        className="btn secondary wide"
                        disabled={
                          !checkout.checkout_available ||
                          !!busy ||
                          !!sandboxOrder
                        }
                        onClick={() =>
                          void action(createSandboxOrder, "paypal-order")
                        }
                      >
                        {sandboxOrder
                          ? "Sandbox order created ✓"
                          : "Create PayPal Sandbox order ↗"}
                      </button>

                      {sandboxOrder && (
                        <div className="checkout-receipt">
                          <div className="section-kicker">
                            PAYPAL SANDBOX ORDER
                          </div>
                          <div>
                            <span>Order ID</span>
                            <strong>{sandboxOrder}</strong>
                          </div>
                          <small>
                            Payment has not been captured through
                            this action.
                          </small>

                          {sandboxApprovalUrl ? (
                            <a
                              href={sandboxApprovalUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="btn primary wide"
                            >
                              Approve in PayPal Sandbox ↗
                            </a>
                          ) : (
                            <p className="hint">
                              Approval link unavailable. Check the backend
                              response before creating another order.
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </section>
            </div>
          )}

          {view === "insights" && (
            <>
              <div className="stats-grid">
                <Stat label="EVENTS" value={String(events.length)} foot="Across your workspace" icon="◈" />
                <Stat label="ROOMS" value={String(rooms.length)} foot="Selected event" icon="▣" />
                <Stat label="SESSIONS" value={String(sessions.length)} foot="Selected event" icon="▦" />
                <Stat label="SEATS HELD / SOLD" value={String(capacityUtilization)} foot="Based on ticket inventory" icon="◎" />
              </div>

              <section className="panel insights-note">
                <div className="panel-top">
                  <div>
                    <span className="section-kicker">OPERATIONS REPORT / 01</span>
                    <h2>Sessions by room</h2>
                  </div>
                  <span className="subtle-pill">LIVE SQLITE DATA</span>
                </div>

                <div className="insights-bars">
                  {rooms.map((room) => {
                    const count = sessions.filter(
                      (session) =>
                        session.room.toLowerCase() === room.name.toLowerCase()
                    ).length;

                    return (
                      <div className="insight-bar" key={room.id}>
                        <span>{room.name}</span>
                        <div>
                          <i
                            style={{
                              width: `${
                                sessions.length
                                  ? (count / sessions.length) * 100
                                  : 0
                              }%`,
                            }}
                          />
                        </div>
                        <b>{count}</b>
                      </div>
                    );
                  })}

                  {!rooms.length && (
                    <div className="empty-content">
                      Register rooms and create sessions to see utilization.
                    </div>
                  )}
                </div>
              </section>

              <section className="panel">
                <div className="panel-top">
                  <div>
                    <span className="section-kicker">AG STUDIO / 02</span>
                    <h2>Interactive Analytics Studio</h2>
                  </div>
                  <span className="subtle-pill">EVENT DATA</span>
                </div>

                <EventMeshAGStudio
                  key={selectedEvent?.id ?? 0}
                  eventId={selectedEvent?.id ?? 0}
                  events={events}
                  rooms={rooms}
                  sessions={sessions}
                  tickets={tickets}
                />
              </section>
            </>
          )}

          <footer className="footer">
            <span>
              EVENTMESH AI <i>◆</i> INTELLIGENT EVENT OPERATIONS
            </span>
            <span>LOCAL DEMO · PAYPAL SANDBOX ONLY</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default function Page() {
  return (
    <OrganizerAuthGate>
      <Home />
    </OrganizerAuthGate>
  );
}

function Stat({
  label,
  value,
  foot,
  icon,
}: {
  label: string;
  value: string;
  foot: string;
  icon: string;
}) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        <i aria-hidden="true">{icon}</i>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-foot">
        <span className="stat-indicator" />
        {foot}
      </div>
    </div>
  );
}

function NavGlyph({
  type,
}: {
  type: View | "webhooks";
}) {
  return (
    <svg
      className="nav-glyph"
      aria-hidden="true"
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {type === "overview" && (
        <>
          <rect x="3" y="3" width="8" height="8" rx="1.5" />
          <rect x="13" y="3" width="8" height="5" rx="1.5" />
          <rect x="13" y="10" width="8" height="11" rx="1.5" />
          <rect x="3" y="13" width="8" height="8" rx="1.5" />
        </>
      )}

      {type === "schedule" && (
        <>
          <rect x="3" y="4" width="18" height="17" rx="2" />
          <path d="M7 2v4M17 2v4M3 10h18M8 14h3M13 14h3M8 18h3" />
        </>
      )}

      {type === "incidents" && (
        <>
          <path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5L12 2Z" />
          <path d="M19 2v4M17 4h4" />
        </>
      )}

      {type === "tickets" && (
        <>
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M3 9h18M8 13h8M8 17h5" />
        </>
      )}

      {type === "insights" && (
        <>
          <path d="M4 20V10M10 20V4M16 20v-7M22 20V8" />
          <path d="M2 20h22" />
        </>
      )}

      {type === "webhooks" && (
        <>
          <path d="M12 3a5 5 0 0 1 5 5c0 2-1 3-2 4M21 12a5 5 0 0 1-5 5c-2 0-3 1-4 2M12 21a5 5 0 0 1-5-5c0-2 1-3 2-4M3 12a5 5 0 0 1 5-5c2 0 3 1 4 2" />
          <circle cx="12" cy="12" r="2" />
        </>
      )}
    </svg>
  );
}
