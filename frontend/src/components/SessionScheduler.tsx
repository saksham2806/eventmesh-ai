
"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

const API = "http://127.0.0.1:8000";

type EventOption = {
  id: number;
  title: string;
};

type Session = {
  id: number;
  event_id: number;
  title: string;
  speaker: string;
  room: string;
  start_time: string;
  end_time: string;
};

const initialForm = {
  title: "",
  speaker: "",
  room: "",
  start_time: "10:00",
  end_time: "11:00",
};

function toMinutes(time: string): number {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function formatTime(minutes: number): string {
  const h = String(Math.floor(minutes / 60)).padStart(2, "0");
  const m = String(minutes % 60).padStart(2, "0");
  return `${h}:${m}`;
}

export default function SessionScheduler({
  events,
}: {
  events: EventOption[];
}) {
  const [selectedId, setSelectedId] = useState<number | null>(
    null
  );

  const [schedule, setSchedule] = useState<{
    eventId: number;
    items: Session[];
  } | null>(null);

  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const eventId =
    events.some((event) => event.id === selectedId)
      ? selectedId
      : (events[0]?.id ?? null);

  const sessions =
    schedule?.eventId === eventId ? schedule.items : [];

  // Fetch the sessions whenever the selected event changes.
  useEffect(() => {
    if (eventId === null) return;

    let active = true;

    async function load() {
      try {
        const response = await fetch(
          `${API}/events/${eventId}/sessions`,
          { cache: "no-store" }
        );

        if (!response.ok) {
          throw new Error("Could not load sessions.");
        }

        const data: Session[] = await response.json();

        if (active && eventId !== null) {
          setSchedule({ eventId, items: data });
        }
      } catch {
        if (active) {
          setError("Failed to load the selected schedule.");
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [eventId]);

  async function addSession(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (eventId === null) return;

    setError("");
    setSuccess("");

    if (form.start_time >= form.end_time) {
      setError("End time must be after start time.");
      return;
    }

    setSaving(true);

    try {
      const response = await fetch(
        `${API}/events/${eventId}/sessions`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(form),
        }
      );

      if (!response.ok) {
        const result = await response.json();

        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Invalid session details."
        );
      }

      setForm(initialForm);
      setSuccess("Session added successfully!");

      // Refresh from the actual database.
      const listResponse = await fetch(
        `${API}/events/${eventId}/sessions`,
        { cache: "no-store" }
      );

      if (!listResponse.ok) {
        throw new Error("Session saved, but refresh failed.");
      }

      const updated: Session[] = await listResponse.json();
      setSchedule({ eventId, items: updated });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong."
      );
    } finally {
      setSaving(false);
    }
  }

  // Build a timeline based on actual session times.
  const starts = sessions.map((s) => toMinutes(s.start_time));
  const ends = sessions.map((s) => toMinutes(s.end_time));

  const timelineStart = sessions.length
    ? Math.max(0, Math.floor((Math.min(...starts) - 30) / 60) * 60)
    : 540;

  const timelineEnd = sessions.length
    ? Math.min(
        1440,
        Math.ceil((Math.max(...ends) + 30) / 60) * 60
      )
    : 1020;

  const duration = Math.max(60, timelineEnd - timelineStart);

  const rooms = [
    ...new Set(sessions.map((s) => s.room.toLowerCase())),
  ];

  const inputStyle =
    "w-full rounded-lg border border-slate-700 " +
    "bg-slate-800 px-3 py-3 text-white " +
    "outline-none focus:border-blue-500";

  return (
    <section className="mt-12 rounded-xl border border-slate-800 bg-slate-900 p-6">
      <h2 className="text-2xl font-bold">
        Event Scheduling
      </h2>

      <p className="mt-2 text-sm text-slate-400">
        Create sessions and automatically detect scheduling conflicts.
      </p>

      {events.length === 0 ? (
        <p className="mt-6 text-slate-400">
          Create an event first to start scheduling.
        </p>
      ) : (
        <>
          {/* EVENT SELECTOR */}
          <div className="mt-6">
            <label htmlFor="schedule-event" className="mb-2 block">
              Select Event
            </label>

            <select
              id="schedule-event"
              className={inputStyle}
              value={eventId ?? ""}
              onChange={(e) => {
                setSelectedId(Number(e.target.value));
                setError("");
                setSuccess("");
              }}
            >
              {events.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.title}
                </option>
              ))}
            </select>
          </div>

          {/* CREATE SESSION FORM */}
          <form
            onSubmit={addSession}
            className="mt-8 space-y-4"
          >
            <h3 className="text-lg font-semibold">
              Add New Session
            </h3>

            <input
              className={inputStyle}
              placeholder="Session title"
              required
              minLength={3}
              value={form.title}
              onChange={(e) =>
                setForm({ ...form, title: e.target.value })
              }
            />

            <div className="grid gap-4 md:grid-cols-2">
              <input
                className={inputStyle}
                placeholder="Speaker name"
                required
                minLength={2}
                value={form.speaker}
                onChange={(e) =>
                  setForm({ ...form, speaker: e.target.value })
                }
              />

              <input
                className={inputStyle}
                placeholder="Room / Hall"
                required
                minLength={2}
                value={form.room}
                onChange={(e) =>
                  setForm({ ...form, room: e.target.value })
                }
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <label>
                <span className="mb-2 block text-sm text-slate-300">
                  Start Time
                </span>
                <input
                  type="time"
                  required
                  className={inputStyle}
                  value={form.start_time}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      start_time: e.target.value,
                    })
                  }
                />
              </label>

              <label>
                <span className="mb-2 block text-sm text-slate-300">
                  End Time
                </span>
                <input
                  type="time"
                  required
                  className={inputStyle}
                  value={form.end_time}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      end_time: e.target.value,
                    })
                  }
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-blue-600 px-6 py-3 font-semibold hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? "Adding..." : "Add Session"}
            </button>
          </form>

          {error && (
            <p role="alert" className="mt-5 text-red-400">
              {error}
            </p>
          )}

          {success && (
            <p role="status" className="mt-5 text-green-400">
              {success}
            </p>
          )}

          {/* VISUAL TIMELINE */}
          <div className="mt-10">
            <h3 className="text-xl font-semibold">
              Visual Schedule
            </h3>

            <p className="mt-1 text-sm text-slate-400">
              {sessions.length} scheduled sessions
            </p>

            {sessions.length === 0 ? (
              <p className="mt-5 text-slate-400">
                No sessions scheduled for this event.
              </p>
            ) : (
              <div className="mt-6 space-y-5">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>{formatTime(timelineStart)}</span>
                  <span>
                    {formatTime(
                      timelineStart + Math.floor(duration / 2)
                    )}
                  </span>
                  <span>{formatTime(timelineEnd)}</span>
                </div>

                {rooms.map((room) => (
                  <div key={room}>
                    <p className="mb-2 font-medium capitalize">
                      {room}
                    </p>

                    <div className="relative h-20 rounded-lg bg-slate-800">
                      {sessions
                        .filter(
                          (s) => s.room.toLowerCase() === room
                        )
                        .map((session) => {
                          const left =
                            ((toMinutes(session.start_time) -
                              timelineStart) /
                              duration) *
                            100;

                          const width =
                            ((toMinutes(session.end_time) -
                              toMinutes(session.start_time)) /
                              duration) *
                            100;

                          return (
                            <div
                              key={session.id}
                              title={`${session.title} - ${session.speaker}`}
                              style={{
                                left: `${left}%`,
                                width: `${width}%`,
                              }}
                              className="absolute bottom-2 top-2 overflow-hidden rounded-md bg-blue-600 px-2 py-2"
                            >
                              <p className="truncate text-xs font-semibold">
                                {session.title}
                              </p>

                              <p className="truncate text-xs">
                                {session.start_time}–
                                {session.end_time}
                              </p>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
