
"use client";

import { useMemo, useRef } from "react";
import { AgStudio, AgStudioProvider } from "ag-studio-react";

import type {
  EventRecord,
  Room,
  Session,
  Ticket,
} from "@/lib/api";

type Props = {
  eventId: number;
  events: EventRecord[];
  rooms: Room[];
  sessions: Session[];
  tickets: Ticket[];
};

export default function EventMeshAGStudio({
  eventId,
  events,
  rooms,
  sessions,
  tickets,
}: Props) {
  const initialized = useRef(false);

  // Each event gets its own saved dashboard.
  const storageKey = `eventmesh-agstudio-v1-${eventId}`;

  // Keep data stable between React renders.
  const data = useMemo(
    () => ({
      sources: [
        {
          id: "events",
          data: events.map((e) => ({
            id: e.id,
            title: e.title,
            eventDate: e.event_date,
            venue: e.venue,
            capacity: e.capacity,
          })),
        },
        {
          id: "rooms",
          data: rooms.map((r) => ({
            id: r.id,
            name: r.name,
            capacity: r.capacity,
          })),
        },
        {
          id: "sessions",
          data: sessions.map((s) => ({
            id: s.id,
            title: s.title,
            room: s.room,
            speaker: s.speaker,
            startTime: s.start_time,
            endTime: s.end_time,
          })),
        },
        {
          id: "tickets",
          data: tickets.map((t) => ({
            id: t.id,
            name: t.name,
            capacity: t.capacity,
            available: t.available,
            priceUSD: Number(t.price_usd),
          })),
        },
      ],
    }),
    [events, rooms, sessions, tickets]
  );

  return (
  <div style={{ height: 620, width: "100%" }}>
    <AgStudioProvider
      licenseKey={
        process.env.NEXT_PUBLIC_AG_STUDIO_LICENSE_KEY || ""
      }
    >
      <AgStudio
        data={data}
        mode="edit"
        onApiReady={({ api }) => {
          initialized.current = false;

          try {
            const saved = localStorage.getItem(storageKey);

            if (saved) {
              api.setState(JSON.parse(saved));
            }
          } catch (error) {
            console.error("Restore failed:", error);
          }

          initialized.current = true;
        }}
        onStateUpdated={({ state }) => {
          if (!initialized.current) return;

          try {
            localStorage.setItem(
              storageKey,
              JSON.stringify(state)
            );
          } catch (error) {
            console.error("Save failed:", error);
          }
        }}
      />
    </AgStudioProvider>
  </div>
  );
}
