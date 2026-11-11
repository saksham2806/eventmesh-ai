
"use client";

import { BryntumScheduler } from "@bryntum/scheduler-react-community";
import type { Room, Session } from "@/lib/api";

import "@bryntum/scheduler-community/scheduler.css";
import "@bryntum/scheduler-community/svalbard-light.css";

type Props = {
  rooms: Room[];
  sessions: Session[];
  date: string;
};

export default function EventMeshBryntum({
  rooms,
  sessions,
  date,
}: Props) {
  const resourceRows = rooms.map((room) => ({
    id: room.id,
    name: `${room.name} (${room.capacity} seats)`,
  }));

  const eventRows = sessions.flatMap((session) => {
    const room = rooms.find(
      (item) =>
        item.name.trim().toLowerCase() ===
        session.room.trim().toLowerCase()
    );

    if (!room) return [];

    return [
      {
        id: session.id,
        resourceId: room.id,
        name: session.title,
        startDate: `${date}T${session.start_time}:00`,
        endDate: `${date}T${session.end_time}:00`,
      },
    ];
  });

  return (
    <div style={{ height: 560, width: "100%" }}>
      <BryntumScheduler
        startDate={new Date(`${date}T08:00:00`)}
        endDate={new Date(`${date}T20:00:00`)}
        viewPreset="hourAndDay"
        columns={[
          {
            text: "Room",
            field: "name",
            width: 190,
          },
        ]}
        resources={resourceRows}
        events={eventRows}
        readOnly={true}
      />
    </div>
  );
}
