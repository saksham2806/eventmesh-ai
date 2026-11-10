import type { Metadata } from "next";
import "./globals.css";
import "@bryntum/scheduler/fontawesome/css/fontawesome.css";
import "@bryntum/scheduler/fontawesome/css/solid.css";

export const metadata: Metadata = {
  title: "EventMesh AI | Operations Console",
  description: "Self-healing event operations. Real scheduling, ticketing, and organizer-approved incident recovery.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
