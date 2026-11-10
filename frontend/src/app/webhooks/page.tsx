"use client";

import OrganizerAuthGate from "@/components/OrganizerAuthGate";
import PayPalWebhookMonitor from "@/components/PayPalWebhookMonitor";

export default function WebhooksPage() {
  return (
    <OrganizerAuthGate>
      <PayPalWebhookMonitor />
    </OrganizerAuthGate>
  );
}
