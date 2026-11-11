
"use client";

import type { CSSProperties } from "react";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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

const panel: CSSProperties = {
  background: "#ffffff",
  border: "1px solid #dce7f4",
  borderRadius: 18,
  padding: 22,
  boxShadow: "0 4px 18px rgba(16, 48, 92, 0.04)",
  minWidth: 0,
};

const heading: CSSProperties = {
  color: "#142d50",
  fontSize: 16,
  fontWeight: 800,
  marginBottom: 8,
};

const th: CSSProperties = {
  padding: "12px 14px",
  textAlign: "left",
  color: "#536d8e",
  background: "#f2f7fd",
  fontSize: 12,
  whiteSpace: "nowrap",
};

const td: CSSProperties = {
  padding: "13px 14px",
  borderBottom: "1px solid #edf2f8",
  fontSize: 13,
  color: "#243f62",
};

export default function EventMeshInsights({
  eventId,
  events,
  rooms,
  sessions,
  tickets,
}: Props) {
  const selectedEvent = events.find(
    (event) => Number(event.id) === Number(eventId)
  );

  const roomData = rooms.map((room) => ({
    name: room.name,
    sessions: sessions.filter(
      (session) =>
        session.room.trim().toLowerCase() ===
        room.name.trim().toLowerCase()
    ).length,
  }));

  const ticketData = tickets.map((ticket) => {
    const capacity = Math.max(
      0,
      Number(ticket.capacity) || 0
    );

    const available = Math.max(
      0,
      Math.min(capacity, Number(ticket.available) || 0)
    );

    return {
      id: ticket.id,
      name: ticket.name,
      capacity,
      available,
      allocated: capacity - available,
      price: Number(ticket.price_usd) || 0,
    };
  });

  const totalCapacity = ticketData.reduce(
    (sum, ticket) => sum + ticket.capacity,
    0
  );

  const totalAllocated = ticketData.reduce(
    (sum, ticket) => sum + ticket.allocated,
    0
  );

  const sortedSessions = [...sessions].sort((a, b) =>
    String(a.start_time).localeCompare(String(b.start_time))
  );

  const stats = [
    { label: "Registered rooms", value: rooms.length },
    { label: "Scheduled sessions", value: sessions.length },
    { label: "Ticket categories", value: tickets.length },
    { label: "Seats allocated", value: totalAllocated },
  ];

  return (
    <div
      style={{
        display: "grid",
        gap: 20,
        width: "100%",
      }}
    >
      <div
        style={{
          ...panel,
          background: "linear-gradient(125deg, #082e63, #076bd0)",
          color: "#ffffff",
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 800,
            letterSpacing: 2,
            color: "#b8dcff",
            marginBottom: 8,
          }}
        >
          EVENT INTELLIGENCE
        </div>

        <h3
          style={{
            fontSize: 25,
            fontWeight: 800,
            margin: "0 0 8px",
            color: "#ffffff",
          }}
        >
          Analytics Overview
        </h3>

        <p
          style={{
            color: "#dcecff",
            margin: 0,
            fontSize: 13,
          }}
        >
          {selectedEvent
            ? `Live operational insights for ${selectedEvent.title}`
            : "Live insights for your selected event"}
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit, minmax(160px, 1fr))",
          gap: 14,
        }}
      >
        {stats.map((stat) => (
          <div key={stat.label} style={panel}>
            <div
              style={{
                color: "#6c82a0",
                fontSize: 12,
                fontWeight: 700,
                marginBottom: 12,
              }}
            >
              {stat.label}
            </div>

            <div
              style={{
                color: "#0969d2",
                fontSize: 32,
                fontWeight: 900,
                lineHeight: 1,
              }}
            >
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit, minmax(min(100%, 350px), 1fr))",
          gap: 18,
        }}
      >
        <section style={panel}>
          <h3 style={heading}>Sessions by Room</h3>

          <p
            style={{
              color: "#7890ac",
              fontSize: 12,
              marginBottom: 22,
            }}
          >
            Session distribution across registered rooms.
          </p>

          {roomData.length > 0 ? (
            <div style={{ height: 270, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={roomData}
                  margin={{
                    top: 10,
                    right: 12,
                    left: -24,
                    bottom: 12,
                  }}
                >
                  <CartesianGrid
                    stroke="#e9eff7"
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: "#657e9c" }}
                    interval={0}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: "#657e9c" }}
                  />
                  <Tooltip />
                  <Bar
                    dataKey="sessions"
                    name="Sessions"
                    fill="#0875de"
                    radius={[6, 6, 0, 0]}
                    maxBarSize={55}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p>No rooms have been added yet.</p>
          )}
        </section>

        <section style={panel}>
          <h3 style={heading}>Ticket Inventory</h3>

          <p
            style={{
              color: "#7890ac",
              fontSize: 12,
              marginBottom: 22,
            }}
          >
            Available and allocated seats by category.
          </p>

          {ticketData.length > 0 ? (
            <div style={{ height: 270, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={ticketData}
                  margin={{
                    top: 10,
                    right: 12,
                    left: -24,
                    bottom: 12,
                  }}
                >
                  <CartesianGrid
                    stroke="#e9eff7"
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: "#657e9c" }}
                    interval={0}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: "#657e9c" }}
                  />
                  <Tooltip />
                  <Legend />
                  <Bar
                    dataKey="allocated"
                    name="Allocated"
                    stackId="seats"
                    fill="#0875de"
                    maxBarSize={55}
                  />
                  <Bar
                    dataKey="available"
                    name="Available"
                    stackId="seats"
                    fill="#9dcbfa"
                    maxBarSize={55}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p>No ticket categories have been added yet.</p>
          )}
        </section>
      </div>

      <section style={panel}>
        <h3 style={heading}>Ticket Category Details</h3>

        <p
          style={{
            color: "#7890ac",
            fontSize: 12,
            marginBottom: 16,
          }}
        >
          Total capacity: {totalCapacity} seats
        </p>

        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
            }}
          >
            <thead>
              <tr>
                <th style={th}>Category</th>
                <th style={th}>Price</th>
                <th style={th}>Capacity</th>
                <th style={th}>Allocated</th>
                <th style={th}>Available</th>
              </tr>
            </thead>

            <tbody>
              {ticketData.map((ticket) => (
                <tr key={ticket.id}>
                  <td style={td}>{ticket.name}</td>
                  <td style={td}>
                    ${ticket.price.toFixed(2)}
                  </td>
                  <td style={td}>{ticket.capacity}</td>
                  <td style={td}>{ticket.allocated}</td>
                  <td style={td}>{ticket.available}</td>
                </tr>
              ))}

              {ticketData.length === 0 && (
                <tr>
                  <td style={td} colSpan={5}>
                    No ticket data available.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section style={panel}>
        <h3 style={heading}>Session Schedule</h3>

        <p
          style={{
            color: "#7890ac",
            fontSize: 12,
            marginBottom: 16,
          }}
        >
          Live sessions for the selected event.
        </p>

        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
            }}
          >
            <thead>
              <tr>
                <th style={th}>Session</th>
                <th style={th}>Room</th>
                <th style={th}>Speaker</th>
                <th style={th}>Start</th>
                <th style={th}>End</th>
              </tr>
            </thead>

            <tbody>
              {sortedSessions.map((session) => (
                <tr key={session.id}>
                  <td style={td}>{session.title}</td>
                  <td style={td}>{session.room}</td>
                  <td style={td}>{session.speaker}</td>
                  <td style={td}>{session.start_time}</td>
                  <td style={td}>{session.end_time}</td>
                </tr>
              ))}

              {sortedSessions.length === 0 && (
                <tr>
                  <td style={td} colSpan={5}>
                    No sessions scheduled yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <p
        style={{
          fontSize: 12,
          color: "#7c90a8",
          margin: 0,
        }}
      >
        Data is read from EventMesh AI. Allocated seats are
        calculated from ticket capacity minus availability;
        they do not necessarily represent verified payments.
      </p>
    </div>
  );
}
