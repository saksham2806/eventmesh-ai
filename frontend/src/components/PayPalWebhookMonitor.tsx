
"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

type WebhookEvent = {
  paypal_event_id: string;
  event_type: string;
  resource_id: string;
  processing_state: string;
  received_at: string;
};

function isWebhookEvent(value: unknown): value is WebhookEvent {
  if (!value || typeof value !== "object") return false;

  const event = value as Record<string, unknown>;

  return (
    typeof event.paypal_event_id === "string" &&
    typeof event.event_type === "string" &&
    typeof event.resource_id === "string" &&
    typeof event.processing_state === "string" &&
    typeof event.received_at === "string"
  );
}

function formatDate(value: string): string {
  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString();
}

export default function PayPalWebhookMonitor() {
  const [events, setEvents] = useState<WebhookEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const controllerRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    controllerRef.current?.abort();

    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        "/api/bridge/paypal/webhooks/events",
        {
          method: "GET",
          cache: "no-store",
          credentials: "same-origin",
          signal: controller.signal,
        }
      );

      if (!response.ok) {
        throw new Error(
          `Webhook API returned HTTP ${response.status}`
        );
      }

      const result: unknown = await response.json();

      if (
        !Array.isArray(result) ||
        !result.every(isWebhookEvent)
      ) {
        throw new Error("Unexpected webhook API response");
      }

      if (controllerRef.current !== controller) return;

      setEvents(result);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      if (controller.signal.aborted) return;

      setError(
        err instanceof Error
          ? err.message
          : "Unable to retrieve webhook events."
      );
    } finally {
      if (controllerRef.current === controller) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();

    const timer = setInterval(() => {
      void refresh();
    }, 30000);

    return () => {
      clearInterval(timer);
      controllerRef.current?.abort();
    };
  }, [refresh]);

  const awaitingReconciliation = events.filter(
    (event) =>
      event.processing_state === "AWAITING_RECONCILIATION"
  ).length;

  return (
    <main className="wh-page">
      <header className="wh-topbar">
        <div className="wh-brand">
          <div className="wh-brand-icon">
            E<span>✳</span>
          </div>

          <div>
            <strong>
              EventMesh<span className="wh-brand-dot">.</span>
            </strong>
            <small>PAYMENT OPERATIONS</small>
          </div>
        </div>

        <div className="top-actions wh-header-actions">
          <a href="/" className="wh-back">
            ← Dashboard
          </a>
        </div>
      </header>

      <div className="wh-content">
        <div className="wh-breadcrumb">
          WORKSPACE <span>/</span> PAYMENT OPERATIONS
          <span>/</span> WEBHOOKS
        </div>

        <section className="wh-heading">
          <div>
            <div className="wh-eyebrow">
              <span className="wh-live-dot" />
              PAYPAL SANDBOX / MONITORING
            </div>

            <h1>
              Webhook Monitor<span>.</span>
            </h1>

            <p>
              Track authenticated PayPal webhook notifications,
              monitor processing states and review reconciliation
              activity in one place.
            </p>
          </div>

          <button
            type="button"
            className="wh-refresh-button"
            onClick={() => void refresh()}
            disabled={loading}
          >
            <span aria-hidden="true">↻</span>
            {loading ? "Refreshing..." : "Refresh Events"}
          </button>
        </section>

        <div className="wh-hero">
          <div>
            <div className="wh-hero-label">
              PAYMENT EVENT INTELLIGENCE
            </div>

            <h2>Every notification. One clear view.</h2>

            <p>
              Keep track of incoming Sandbox notifications
              and their processing status without initiating
              payments, captures or refunds.
            </p>

            <div className="wh-hero-badges">
              <span>✓ Authenticated events</span>
              <span>↻ 30-second auto-refresh</span>
            </div>
          </div>

          <div className="wh-hero-symbol" aria-hidden="true">
            <span>↔</span>
          </div>
        </div>

        <section className="wh-stats">
          <div className="wh-stat-card">
            <div className="wh-stat-top">
              <span>RECENT VERIFIED EVENTS</span>
              <div className="wh-stat-icon">✓</div>
            </div>

            <strong>{events.length}</strong>

            <p>
              <span className="wh-small-dot" />
              Returned by the webhook API
            </p>
          </div>

          <div className="wh-stat-card">
            <div className="wh-stat-top">
              <span>AWAITING RECONCILIATION</span>
              <div className="wh-stat-icon">↻</div>
            </div>

            <strong>{awaitingReconciliation}</strong>

            <p>
              <span className="wh-small-dot wh-dot-amber" />
              Events requiring reconciliation
            </p>
          </div>

          <div className="wh-stat-card">
            <div className="wh-stat-top">
              <span>REFRESH INTERVAL</span>
              <div className="wh-stat-icon">◷</div>
            </div>

            <strong>
              30<span className="wh-stat-unit">sec</span>
            </strong>

            <p>
              <span className="wh-small-dot" />
              Automatic monitoring interval
            </p>
          </div>
        </section>

        <section className="wh-activity-panel">
          <div className="wh-panel-header">
            <div>
              <span className="wh-section-kicker">
                ACTIVITY / 01
              </span>

              <h2>Webhook Activity</h2>

              <p>
                Recent events received and reported
                by the FastAPI backend.
              </p>
            </div>

            <span className="wh-event-count">
              {events.length} EVENTS
            </span>
          </div>

          {error && (
            <div className="wh-error" role="alert">
              <span className="wh-error-icon">!</span>
              <div>
                <strong>Unable to refresh webhook events</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {loading && events.length === 0 && (
            <div
              className="wh-empty"
              role="status"
            >
              <div className="wh-empty-icon">↻</div>
              <h3>Loading webhook events...</h3>
              <p>
                Connecting to the EventMesh webhook API.
              </p>
            </div>
          )}

          {!loading && !error && events.length === 0 && (
            <div className="wh-empty">
              <div className="wh-empty-icon">
                <svg
                  width="34"
                  height="34"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <rect x="3" y="5" width="18" height="14" rx="3" />
                  <path d="m3 8 9 6 9-6" />
                </svg>
              </div>

              <h3>No verified webhook events yet</h3>

              <p>
                Authenticated PayPal Sandbox events will
                appear here when they are received and
                returned by your backend.
              </p>

              <span className="wh-empty-badge">
                MONITORING ACTIVE
              </span>
            </div>
          )}

          {events.length > 0 && (
            <div className="wh-table-wrapper">
              <table className="wh-table">
                <thead>
                  <tr>
                    <th>RECEIVED AT</th>
                    <th>EVENT TYPE</th>
                    <th>EVENT ID</th>
                    <th>RESOURCE ID</th>
                    <th>PROCESSING STATE</th>
                  </tr>
                </thead>

                <tbody>
                  {events.map((event) => {
                    const pending =
                      event.processing_state ===
                      "AWAITING_RECONCILIATION";

                    return (
                      <tr key={event.paypal_event_id}>
                        <td>{formatDate(event.received_at)}</td>

                        <td>
                          <span className="wh-event-type">
                            {event.event_type}
                          </span>
                        </td>

                        <td>
                          <code>{event.paypal_event_id}</code>
                        </td>

                        <td>
                          <code>
                            {event.resource_id || "—"}
                          </code>
                        </td>

                        <td>
                          <span
                            className={`wh-status ${
                              pending
                                ? "wh-status-pending"
                                : "wh-status-neutral"
                            }`}
                          >
                            <span />
                            {event.processing_state}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="wh-bottom-info">
          <div className="wh-sync-info">
            <span className="wh-sync-dot" />

            {lastUpdated
              ? `Last successful refresh: ${lastUpdated}`
              : "No successful refresh yet"}
          </div>

          <span>Auto-refresh every 30 seconds</span>
        </div>

        <div className="wh-security-note">
          <div className="wh-security-icon">i</div>

          <p>
            <strong>Payment verification notice:</strong>{" "}
            Webhook receipt alone does not confirm
            payment completion. Payment capture verification
            and reconciliation are handled separately by
            the backend.
          </p>
        </div>

        <footer className="wh-footer">
          <span>EVENTMESH AI · PAYMENT MONITORING</span>
          <span>LOCAL DEMO · PAYPAL SANDBOX ONLY</span>
        </footer>
      </div>

      <style>{`
        .wh-page {
          min-height: 100vh;
          background: #f5f9ff;
          color: #102a50;
          font-family: Inter, ui-sans-serif, system-ui,
            -apple-system, "Segoe UI", Arial, sans-serif;
        }

        .wh-page * {
          box-sizing: border-box;
        }

        .wh-topbar {
          min-height: 76px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 20px;
          padding: 15px clamp(20px, 5vw, 72px);
          background: #ffffff;
          border-bottom: 1px solid #e0e9f6;
        }

        .wh-brand {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .wh-brand-icon {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 43px;
          height: 43px;
          border-radius: 12px;
          background: #003087;
          color: white;
          font-size: 29px;
          font-weight: 900;
        }

        .wh-brand-icon span {
          position: absolute;
          top: 0;
          right: 2px;
          font-size: 15px;
        }

        .wh-brand strong {
          display: block;
          color: #092b65;
          font-size: 20px;
          letter-spacing: -0.7px;
          font-weight: 850;
        }

        .wh-brand-dot {
          color: #0070e0;
        }

        .wh-brand small {
          display: block;
          margin-top: 2px;
          color: #7795bb;
          font-size: 9px;
          font-weight: 850;
          letter-spacing: 1.5px;
        }

        .wh-header-actions {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .wh-back {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: 39px;
          padding: 10px 14px;
          border: 1px solid #d2e5fa;
          border-radius: 9px;
          background: #edf6ff;
          color: #0054a9;
          font-size: 12px;
          font-weight: 800;
          text-decoration: none;
        }

        .wh-back:hover {
          background: #ddecff;
        }

        .wh-content {
          max-width: 1500px;
          margin: 0 auto;
          padding: 38px clamp(20px, 5vw, 72px) 24px;
        }

        .wh-breadcrumb {
          color: #899eb8;
          font-size: 10px;
          font-weight: 850;
          letter-spacing: 1.4px;
        }

        .wh-breadcrumb span {
          padding: 0 10px;
          color: #c3d0e1;
        }

        .wh-heading {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 22px;
          margin: 25px 0 27px;
        }

        .wh-eyebrow {
          display: flex;
          align-items: center;
          gap: 10px;
          color: #0063bc;
          font-size: 10px;
          font-weight: 850;
          letter-spacing: 1.55px;
        }

        .wh-live-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #168bfa;
        }

        .wh-heading h1 {
          margin: 13px 0 10px;
          font-size: clamp(32px, 3.5vw, 48px);
          font-weight: 850;
          letter-spacing: -1.8px;
          line-height: 1.15;
        }

        .wh-heading h1 span {
          color: #0070e0;
        }

        .wh-heading p {
          max-width: 650px;
          margin: 0;
          color: #7589a4;
          font-size: 13px;
          line-height: 1.7;
        }

        .wh-refresh-button {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          min-height: 43px;
          padding: 12px 18px;
          border: 0;
          border-radius: 9px;
          background: #0070e0;
          color: white;
          font-size: 12px;
          font-weight: 850;
          white-space: nowrap;
          cursor: pointer;
        }

        .wh-refresh-button:hover:not(:disabled) {
          background: #0058b8;
        }

        .wh-refresh-button:disabled {
          opacity: 0.65;
          cursor: wait;
        }

        .wh-refresh-button > span {
          font-size: 20px;
          line-height: 0.8;
        }

        .wh-hero {
          position: relative;
          display: flex;
          justify-content: space-between;
          gap: 20px;
          min-height: 190px;
          padding: 28px 32px;
          margin-bottom: 22px;
          border-radius: 16px;
          overflow: hidden;
          background: linear-gradient(
            115deg,
            #071e49,
            #003c94 65%,
            #0768cb
          );
          color: white;
        }

        .wh-hero > div:first-child {
          position: relative;
          z-index: 2;
          max-width: 610px;
        }

        .wh-hero-label {
          color: #9bd6ff;
          font-size: 10px;
          letter-spacing: 1.4px;
          font-weight: 850;
        }

        .wh-hero h2 {
          margin: 14px 0 10px;
          font-size: clamp(20px, 2.2vw, 29px);
          letter-spacing: -0.6px;
        }

        .wh-hero p {
          max-width: 570px;
          margin: 0;
          color: #c4dcfa;
          font-size: 12px;
          line-height: 1.75;
        }

        .wh-hero-badges {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 22px;
        }

        .wh-hero-badges span {
          padding: 8px 10px;
          border: 1px solid rgba(192,221,255,0.25);
          border-radius: 7px;
          background: rgba(255,255,255,0.09);
          color: #d1e8ff;
          font-size: 10px;
          font-weight: 750;
        }

        .wh-hero-symbol {
          display: grid;
          place-items: center;
          flex: 0 0 160px;
          width: 160px;
          height: 160px;
          align-self: center;
          border-radius: 45px;
          border: 1px solid rgba(194,225,255,0.25);
          box-shadow:
            0 0 0 35px rgba(138,201,255,0.06),
            0 0 0 70px rgba(138,201,255,0.035);
          background: rgba(64,154,244,0.18);
          color: #a6dfff;
          font-size: 85px;
          font-weight: 300;
        }

        .wh-stats {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 17px;
          margin-bottom: 22px;
        }

        .wh-stat-card,
        .wh-activity-panel {
          border: 1px solid #dfe9f5;
          border-radius: 15px;
          background: #ffffff;
          box-shadow: 0 5px 20px rgba(0,48,135,0.035);
        }

        .wh-stat-card {
          min-height: 153px;
          padding: 23px;
        }

        .wh-stat-top {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }

        .wh-stat-top > span {
          color: #788da8;
          font-size: 10px;
          font-weight: 850;
          letter-spacing: 1px;
          line-height: 1.55;
        }

        .wh-stat-icon {
          display: grid;
          place-items: center;
          flex: 0 0 33px;
          width: 33px;
          height: 33px;
          border-radius: 10px;
          background: #e8f3ff;
          color: #006bcf;
          font-size: 19px;
        }

        .wh-stat-card > strong {
          display: block;
          margin: 9px 0 10px;
          color: #082f69;
          font-size: 39px;
          font-weight: 850;
          line-height: 1.1;
          font-variant-numeric: tabular-nums;
        }

        .wh-stat-unit {
          margin-left: 5px;
          color: #7592b3;
          font-size: 16px;
        }

        .wh-stat-card p {
          margin: 0;
          color: #8698ae;
          font-size: 11px;
        }

        .wh-small-dot {
          display: inline-block;
          width: 6px;
          height: 6px;
          margin-right: 7px;
          border-radius: 50%;
          background: #258cdf;
          vertical-align: middle;
        }

        .wh-dot-amber {
          background: #dba34b;
        }

        .wh-activity-panel {
          overflow: hidden;
        }

        .wh-panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 18px;
          padding: 25px 26px;
          border-bottom: 1px solid #e7eef7;
        }

        .wh-section-kicker {
          color: #0068cc;
          font-size: 10px;
          font-weight: 850;
          letter-spacing: 1.4px;
        }

        .wh-panel-header h2 {
          margin: 8px 0;
          font-size: 21px;
          letter-spacing: -0.5px;
        }

        .wh-panel-header p {
          margin: 0;
          color: #879ab3;
          font-size: 11px;
          line-height: 1.6;
        }

        .wh-event-count {
          padding: 9px 12px;
          border: 1px solid #d5e6fb;
          border-radius: 8px;
          background: #eff7ff;
          color: #0059b5;
          font-size: 10px;
          font-weight: 850;
          white-space: nowrap;
        }

        .wh-empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 300px;
          padding: 45px 24px;
          text-align: center;
        }

        .wh-empty-icon {
          display: grid;
          place-items: center;
          width: 83px;
          height: 83px;
          margin-bottom: 20px;
          border-radius: 25px;
          background: #eaf4ff;
          color: #1679d2;
          font-size: 45px;
        }

        .wh-empty h3 {
          margin: 0 0 10px;
          color: #1d3d72;
          font-size: 17px;
        }

        .wh-empty p {
          max-width: 380px;
          margin: 0;
          color: #879ab3;
          font-size: 12px;
          line-height: 1.8;
        }

        .wh-empty-badge {
          margin-top: 22px;
          padding: 9px 12px;
          border-radius: 8px;
          background: #eaf5ff;
          color: #0069c9;
          font-size: 10px;
          font-weight: 850;
          letter-spacing: 0.8px;
        }

        .wh-error {
          display: flex;
          align-items: flex-start;
          gap: 13px;
          margin: 20px 25px;
          padding: 15px;
          border: 1px solid #f0c6c6;
          border-radius: 10px;
          background: #fff2f2;
          color: #a13f3f;
        }

        .wh-error-icon {
          display: grid;
          place-items: center;
          width: 22px;
          height: 22px;
          flex: 0 0 22px;
          border-radius: 50%;
          background: #d95353;
          color: white;
          font-weight: 850;
        }

        .wh-error strong {
          display: block;
          font-size: 12px;
        }

        .wh-error p {
          margin: 4px 0 0;
          font-size: 11px;
          line-height: 1.6;
        }

        .wh-table-wrapper {
          overflow-x: auto;
        }

        .wh-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
          font-size: 12px;
        }

        .wh-table th {
          padding: 17px 19px;
          background: #f7faff;
          color: #718ba8;
          font-size: 10px;
          letter-spacing: 0.8px;
          font-weight: 850;
          white-space: nowrap;
        }

        .wh-table td {
          padding: 18px 19px;
          border-top: 1px solid #ebf0f7;
          color: #38557b;
          vertical-align: middle;
          overflow-wrap: anywhere;
        }

        .wh-table tbody tr:hover {
          background: #f7fbff;
        }

        .wh-table code {
          color: #537499;
          font-size: 11px;
          overflow-wrap: anywhere;
        }

        .wh-event-type {
          color: #005cba;
          font-weight: 800;
        }

        .wh-status {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          padding: 7px 10px;
          border-radius: 7px;
          font-size: 10px;
          font-weight: 800;
          white-space: nowrap;
        }

        .wh-status > span {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }

        .wh-status-pending {
          background: #fff4df;
          color: #94631f;
        }

        .wh-status-pending > span {
          background: #d49a3e;
        }

        .wh-status-neutral {
          background: #e9f4ff;
          color: #005eae;
        }

        .wh-status-neutral > span {
          background: #1689e5;
        }

        .wh-bottom-info {
          display: flex;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 20px;
          color: #8195b0;
          font-size: 11px;
        }

        .wh-sync-info {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .wh-sync-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #1e88e5;
        }

        .wh-security-note {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          margin-top: 22px;
          padding: 17px;
          border: 1px solid #d9e8fa;
          border-radius: 11px;
          background: #ecf5ff;
        }

        .wh-security-icon {
          display: grid;
          place-items: center;
          flex: 0 0 22px;
          width: 22px;
          height: 22px;
          border: 1px solid #b8d8f7;
          border-radius: 50%;
          color: #0067c7;
          font-size: 13px;
          font-weight: 850;
        }

        .wh-security-note p {
          margin: 0;
          color: #6683a2;
          font-size: 11px;
          line-height: 1.75;
        }

        .wh-security-note strong {
          color: #235e9b;
        }

        .wh-footer {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
          margin-top: 35px;
          padding: 17px 0;
          border-top: 1px solid #dfebf8;
          color: #9aadc2;
          font-size: 9px;
          font-weight: 850;
          letter-spacing: 1px;
        }

        .wh-page button:focus-visible,
        .wh-page a:focus-visible {
          outline: 3px solid #288bec;
          outline-offset: 3px;
        }

        @media (max-width: 900px) {
          .wh-stats {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .wh-hero-symbol {
            flex-basis: 100px;
            width: 100px;
            height: 100px;
            font-size: 60px;
          }
        }

        @media (max-width: 650px) {
          .wh-topbar {
            padding: 14px 16px;
          }

          .wh-content {
            padding: 26px 16px 20px;
          }

          .wh-heading {
            display: block;
          }

          .wh-heading h1 {
            font-size: 34px;
          }

          .wh-refresh-button {
            width: 100%;
            margin-top: 20px;
          }

          .wh-hero {
            padding: 24px 20px;
          }

          .wh-hero-symbol {
            display: none;
          }

          .wh-stats {
            grid-template-columns: 1fr;
            gap: 12px;
          }

          .wh-stat-card {
            min-height: 140px;
          }

          .wh-panel-header {
            padding: 20px;
            align-items: flex-start;
          }

          .wh-event-count {
            font-size: 9px;
          }

          .wh-table {
            min-width: 850px;
          }

          .wh-footer {
            font-size: 8px;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .wh-page *,
          .wh-page *::before,
          .wh-page *::after {
            animation: none !important;
            transition: none !important;
          }
        }
      `}</style>
    </main>
  );
}
