"use client";
// Requires: npm install @bryntum/scheduler@npm:@bryntum/scheduler-trial@7.3.7 @bryntum/scheduler-react@7.3.7
// Next.js usage: dynamically import this client component with ssr:false.
import { BryntumScheduler } from "@bryntum/scheduler-react";
import type { Room, Session } from "@/lib/api";
import "@bryntum/scheduler/scheduler.css";
import "@bryntum/scheduler/svalbard-light.css";

export default function EventMeshBryntum({ rooms, sessions, date }: { rooms: Room[]; sessions: Session[]; date: string }) {
  const resourceRows = rooms.map((r) => ({ id: r.id, name: `${r.name} (${r.capacity} seats)` }));
  const eventRows = sessions.flatMap((s) => {
    const room = rooms.find((r) => r.name.trim().toLowerCase() === s.room.trim().toLowerCase());
    return room ? [{ id: s.id, resourceId: room.id, name: s.title, startDate: `${date}T${s.start_time}:00`, endDate: `${date}T${s.end_time}:00` }] : [];
  });
  return <div style={{ height: 560, width: "100%" }}><BryntumScheduler
    startDate={new Date(`${date}T08:00:00`)} endDate={new Date(`${date}T20:00:00`)}
    viewPreset="hourAndDay" columns={[{ text: "Room", field: "name", width: 190 }]}
    resources={resourceRows} events={eventRows}
    // Read-only until drag/drop has transaction-based backend checks and approval.
    readOnly={true}
  /></div>;
}
