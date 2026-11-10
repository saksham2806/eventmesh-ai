
"use client";

import dynamic from "next/dynamic";
import type { Room, Session } from "@/lib/api";

const EventMeshBryntum = dynamic(
  () => import("./EventMeshBryntum"),
  {
    ssr: false,
    loading: () => (
      <p>Loading Bryntum Scheduler...</p>
    ),
  }
);

type Props = {
  rooms: Room[];
  sessions: Session[];
  date: string;
};

export default function BryntumClient(props: Props) {
  return <EventMeshBryntum {...props} />;
}
