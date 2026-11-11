# EventMesh AI

**Explainable event recovery, organizer-controlled decisions, and PayPal Sandbox payments in one event-operations workspace.**

> **PayPal AI Hackathon 2026 submission project**  
> Status: **Working local demo** · **PayPal Sandbox only** · **Render hosted demo is opt-in and must be validated end-to-end**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Next.js](https://img.shields.io/badge/Frontend-Next.js%2016-black)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)
![PayPal](https://img.shields.io/badge/Payments-PayPal%20Sandbox-003087)

**Project repository:** <https://github.com/saksham2806/eventmesh-ai>  
**Hackathon:** <https://paypalaihackathon.devpost.com/>  
**Demo video:** **[ADD PUBLIC YOUTUBE VIDEO LINK BEFORE SUBMISSION]**  
**Hosted demo (test deployment):** <https://eventmesh-frontend-a1c5.onrender.com> — not verified for complete checkout or durable data; use the local instructions if unavailable.

## The problem

Live events are difficult to coordinate. A room can become unavailable, a session can conflict with another booking, or ticket capacity can change while payments are in progress. Organizers often have to switch between scheduling tools, payment systems, and spreadsheets to resolve one incident.

**EventMesh AI** brings these activities into a single workflow: inspect the schedule, consider ranked recovery options, have an organizer approve a change, manage ticket inventory, and reconcile PayPal Sandbox transactions without treating a payment as successful before the provider confirms it.

## What it does

| Capability | Experience |
| --- | --- |
| **Event operations** | Create and view organizer-owned events, rooms, sessions, and ticket types. |
| **Visual schedule** | Explore the event schedule using Bryntum Scheduler Community. |
| **Explainable recovery** | Evaluate candidate recovery options for unavailable rooms and scheduling disruptions, with constraint-aware suggestions and explanations. |
| **Human-in-the-loop decisions** | Preview recovery proposals and explicitly approve changes rather than silently modifying the schedule. |
| **EventMesh Insights** | Inspect room/session activity, ticket inventory, and operational summaries through Recharts visualizations. |
| **PayPal Sandbox checkout** | Create PayPal orders, check approval, capture payment, and confirm payment/ticket state through server-side API calls. |
| **Refund workflow** | Review refund eligibility, create proposals, approve sandbox execution, and inspect reconciliation/tracking. |
| **Webhook monitoring** | Verify incoming PayPal webhook signatures before recording events, and isolate event history by organizer. |
| **Organizer accounts** | Login sessions and event-level ownership checks across organizer-facing routes. |

### Example scenario

1. An organizer creates an event with rooms, sessions, and ticket inventory.
2. A scheduled room becomes unavailable.
3. EventMesh AI evaluates alternative room/session arrangements and presents explainable recovery suggestions.
4. The organizer reviews and approves a proposed change.
5. A Sandbox reservation is paid using PayPal; the backend checks the provider's order/capture response before issuing tickets.
6. The organizer can inspect payment status, webhook events, and refund proposals from the application.

**What is different:** scheduling recovery is linked to the realities of event operations and payment reconciliation, with a deliberate **human-approval step** rather than autonomous, irreversible changes.

## How AI is used

The implemented recovery workflow uses **constraint-aware candidate evaluation and explainable ranking** to support operational decisions. It examines scheduling context, such as unavailable rooms, existing sessions, and proposed alternatives, and returns options for an organizer to review. These recommendations are **decision support**, not automatically executed actions.

The backend example configuration also contains `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` settings for optional model-based integration. **An API-key setting alone does not establish that an LLM is used in the running demo.** If an external model is demonstrated, document its exact provider, model name, code path, input, and output here before submitting.

**AI-model disclosure for the final submission:** **[CONFIRM AND ENTER THE EXACT AI TOOL/MODEL ACTUALLY USED IN THE DEMO]**.

> Hackathon note: The PayPal AI Hackathon requires a meaningful integration of both the PayPal developer platform **and an AI tool, model, or platform**. Verify and demonstrate the AI integration you actually use; a feature named “AI” or deterministic rules by themselves should not be presented as an unverified LLM integration.

## How PayPal is used

The integration is **PayPal REST APIs in Sandbox mode**. It is central to the ticketing/payment workflow, rather than a decorative payment button.

- **Orders:** Create a PayPal Sandbox order linked to an EventMesh reservation.
- **Capture:** Confirm approval, submit capture using a `PayPal-Request-Id`, and handle uncertain outcomes conservatively.
- **Verification:** Compare the returned order ID, reservation reference, capture status, USD amount, and ticket total before fulfilling the reservation.
- **Idempotency and tickets:** Reconcile previously completed captures and avoid issuing duplicate tickets.
- **Refunds:** Use a proposal, approval, execution, tracking, and reconciliation flow for Sandbox refunds.
- **Webhooks:** Verify signed event notifications with PayPal before recording them; organizer-facing history is filtered using payment/reservation ownership.

**No live payment credentials or real-money transactions are required for the local demonstration.** Use a PayPal **Sandbox business application** and a **Sandbox personal buyer** account.

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16, React, TypeScript |
| Scheduling interface | `@bryntum/scheduler-community`, `@bryntum/scheduler-react-community` |
| Analytics | Recharts |
| Backend | Python, FastAPI, Uvicorn, HTTPX |
| Persistence | SQLite (`backend/events.db` locally; not committed) |
| Payments | PayPal Sandbox REST APIs and webhook signature verification |
| Decision support | Constraint-aware, explainable recovery proposals; optional external AI configuration where implemented |
| Authentication | Organizer sessions with per-event/reservation authorization |

### Architecture

```text
Organizer browser
    |
    v
Next.js dashboard and server-side API routes
    |  login session + approved API bridge
    v
FastAPI backend  ------------------------>  PayPal Sandbox REST API
    |                                            |
    v                                            | signed notifications
SQLite (events, sessions, reservations,           v
payments, tickets, refund proposals)        FastAPI webhook receiver
    |
    v
Recovery suggestions, approval, insights, and payment reconciliation
```

The browser does not need the PayPal client secret. API credentials and the shared backend integration key belong **only** in ignored server-side environment files.

## Run the working demo locally

The following setup is designed for judges and reviewers using a development computer. The application is currently intended to be run **locally**, not as an unattended production service.

### Prerequisites

- **Git**
- **Node.js 20.9+** and npm (Next.js 16 requirement)
- **Python 3.11+** and `pip` (the local test environment has also used Python 3.14)
- A free **PayPal Developer Sandbox** business app and Sandbox buyer account to exercise the complete checkout flow
- A terminal and browser

### 1. Get the source

```powershell
git clone https://github.com/saksham2806/eventmesh-ai.git
cd eventmesh-ai
```

### 2. Set up FastAPI (Windows PowerShell)

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit **`backend/.env`** and configure the appropriate development values:

```dotenv
EVENTMESH_ORGANIZER_KEY=REPLACE_WITH_A_LONG_RANDOM_LOCAL_SECRET
PAYPAL_CLIENT_ID=YOUR_SANDBOX_CLIENT_ID
PAYPAL_CLIENT_SECRET=YOUR_SANDBOX_CLIENT_SECRET
PAYPAL_WEBHOOK_ID=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
EVENTMESH_ENABLE_REGISTRATION=true
```

- Generate a strong random organizer secret; use the **same value** in the frontend server environment file below.
- The PayPal client ID and secret come from a **Sandbox** app at <https://developer.paypal.com/dashboard/applications/sandbox>.
- Set `PAYPAL_WEBHOOK_ID` only if you have configured a real Sandbox webhook subscription. A webhook needs a reachable HTTPS listener; it is not required for the basic local order/capture walkthrough.
- Leave optional model-related keys empty unless you have verified the corresponding integration.
- `EVENTMESH_ENABLE_REGISTRATION=true` is for creating **local demo accounts only**. Keep public registration disabled in production.
- **Never commit `.env`, session cookies, client secrets, buyer credentials, or the SQLite database.**

Start FastAPI in **Terminal 1**, from the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The API health endpoint should be available at <http://127.0.0.1:8000/health>; interactive API documentation is normally available at <http://127.0.0.1:8000/docs>.

**macOS/Linux equivalent:** use `python3 -m venv .venv`, `source .venv/bin/activate`, `python -m pip install -r requirements.txt`, and `python -m uvicorn main:app --host 127.0.0.1 --port 8000`.

### 3. Set up Next.js

In **Terminal 2**, from the repository root:

```powershell
cd frontend
npm ci
Copy-Item .env.local.example .env.local
```

Edit **`frontend/.env.local`**:

```dotenv
EVENTMESH_BACKEND_URL=http://127.0.0.1:8000
EVENTMESH_ORGANIZER_KEY=REPLACE_WITH_THE_SAME_LOCAL_SECRET_AS_BACKEND
```

Run the frontend:

```powershell
npm run dev -- --webpack
```

Open <http://localhost:3000>. The frontend's server-side routes communicate with the local FastAPI instance; the backend and frontend should both be running.

### Fresh-database and legacy ownership notes

New clones using this version create `events.organizer_id` automatically, so event creation does not require a manual migration on a new database. **For an older SQLite database containing events without owners**, back it up and use `python migrate_event_ownership.py` only after creating the first organizer. That script deliberately requires **exactly one** account and assigns older unowned events to it. Do not run it to infer ownership in a multi-organizer database. Stop FastAPI before executing it.

### 4. Create a local organizer and explore

1. Visit <http://localhost:3000/register> and create a demo organizer account (local registration must be enabled as above).
2. Sign in at <http://localhost:3000/login>.
3. Create an event; add rooms, sessions, and ticket types.
4. Inspect the Bryntum Community schedule and EventMesh Insights charts.
5. Try a recovery preview for a room disruption, review the ranked alternatives, and approve a suitable proposal.
6. Create a ticket reservation and Sandbox PayPal order. Approve the payment using a **Sandbox buyer**, then check the capture, payment status, and ticket fulfillment results.
7. Inspect webhook monitoring and refund proposals where corresponding Sandbox records exist.

Actual menu labels and available actions depend on the current UI and seeded data. Use **fake attendee details** while demonstrating the workflow.

### 5. Verify the project

From the **backend** directory:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
```

From the **frontend** directory:

```powershell
npx tsc --noEmit
```

**Most recent local validation during preparation:** 94 backend unit tests passed, the frontend TypeScript check passed, and organizer login/dashboard worked locally. These results are a development checkpoint, not a claim of a completed production security audit or external PayPal integration certification.

## Demo and judging access

**Current demo method:** reproduce the working app with the instructions above. **A publicly hosted deployment is not required by the hackathon rules** when a working build can be installed and run from the repository.

To test the end-to-end PayPal flow, reviewers need their own free PayPal Sandbox app credentials and Sandbox buyer (or separately arranged judge-only test access). **Do not publish real credentials or session tokens in this README.** If private demo access is arranged, provide the instructions and credentials through an appropriate private channel in the submission process.

### Suggested video walkthrough (under 3 minutes)

| Time | What to show |
| --- | --- |
| 0:00–0:20 | The problem: an unavailable event room disrupts an active schedule. |
| 0:20–0:55 | Event dashboard, rooms/sessions, Bryntum Community schedule, and Insights. |
| 0:55–1:40 | Recovery suggestions, explanations, and organizer approval. |
| 1:40–2:30 | PayPal Sandbox order approval, capture verification, and ticket status. |
| 2:30–2:50 | Refund/reconciliation view, security/ownership, and project impact. |

Record an actual **running application**, use only media you have permission to use, upload the video as **public on YouTube**, and insert its URL near the top of this README and in Devpost.

## Render hosted demo — opt-in deployment

This setup is a **restricted Sandbox demonstration**, not a production-grade, durable service. Both services connect to the public GitHub repository's `main` branch. Preserve the earlier local demo, and verify new code before putting a link in Devpost.

### Backend: `eventmesh-backend`

- **Render Web Service** from repository `saksham2806/eventmesh-ai`, root directory `backend`, Python 3.13.3.
- Build: `pip install -r requirements.txt`
- Start: `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`
- Keep `EVENTMESH_ORGANIZER_KEY` as a private random secret, matching the frontend's server secret.
- Set `EVENTMESH_BOOTSTRAP_ORGANIZER_EMAIL` to a test-account email and `EVENTMESH_BOOTSTRAP_ORGANIZER_PASSWORD` to a unique strong password (12–128 characters). These are **private** Render environment variables. They create an organizer only when the database has no organizer accounts. **Never post the password publicly.**
- Set `EVENTMESH_ENABLE_REGISTRATION=false` (or omit it). **Do not** enable public production registration; the frontend rejects production signups by design.
- Set `EVENTMESH_PUBLIC_FRONTEND_URL=https://eventmesh-frontend-a1c5.onrender.com` for PayPal Sandbox redirect URLs. Set PayPal **Sandbox** `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` if payments will be tested. Never use Live keys.
- **Render Free:** Leave `EVENTMESH_DB_PATH` unset. This uses temporary `backend/events.db`, which is erased on restarts/spin-downs/redeploys. The initial organizer can be recreated from the private bootstrap variables, but event/ticket/payment history **will not persist**.
- **If upgrading to a paid persistent disk later:** Mount a disk at `/var/data`, set `EVENTMESH_DB_PATH=/var/data/events.db`, and redeploy. Every SQLite-using backend module now shares this setting. Confirm read/write access and backups before accepting payments.

### Frontend: `eventmesh-frontend`

- **Render Web Service** from the same repo, root directory `frontend`, Node 22.
- Build: `npm install --no-audit --no-fund && npm run build` (temporary workaround for a cross-platform npm lockfile issue; fix the lockfile and return to `npm ci` when verified).
- Start: `npm run start -- --hostname 0.0.0.0 --port $PORT`.
- Private environment variables:

```dotenv
EVENTMESH_BACKEND_URL=https://eventmesh-backend.onrender.com
EVENTMESH_ORGANIZER_KEY=THE_EXACT_SAME_SECRET_AS_RENDER_BACKEND
EVENTMESH_ENABLE_PRODUCTION_BRIDGE=true
EVENTMESH_PUBLIC_FRONTEND_URL=https://eventmesh-frontend-a1c5.onrender.com
```

`EVENTMESH_ENABLE_PRODUCTION_BRIDGE=true` must be set **only** on a deployment you control, after checking server-side session validation, allowlisted API routes and the `EVENTMESH_BACKEND_URL` HTTPS origin. The backend and frontend keys may differ from local `.env` values, but the **two Render keys must match**.

### Enable hosted PayPal Sandbox only after testing core organizer functions

For an end-to-end PayPal Sandbox test, set `EVENTMESH_ENABLE_PRODUCTION_SANDBOX_CHECKOUT=true` on the **frontend** after verifying login, event creation, scheduling, and recovery. The backend uses `EVENTMESH_PUBLIC_FRONTEND_URL` for PayPal's fixed return/cancel URLs. The completion route requires an authenticated organizer session, matching signed checkout cookie and same-origin HTTPS request, and the backend re-verifies capture before issuing tickets.

**Do not treat an approval redirect as successful payment.** Confirm `PAID`, `payment_verified=true`, and ticket count matching the reservation. If the capture result is uncertain, reconcile instead of retrying. Never expose real PayPal credentials or post demo-buyer passwords publicly. This integration has **not yet been validated end-to-end on Render**.

### Hosted smoke-test sequence

1. Check backend `https://eventmesh-backend.onrender.com/health` returns a healthy response.
2. Open frontend `https://eventmesh-frontend-a1c5.onrender.com`; verify it reaches the login page. A `401 Authentication required` at `/api/auth/organizer/me` before login is expected.
3. Sign in with the privately configured initial organizer credentials. Production public registration is intentionally unavailable.
4. Create an event, two rooms and two sessions; check the Bryntum timeline and Insights. Confirm event creation does **not** fail with `no column named organizer_id`.
5. Trigger room-unavailable recovery, review the ranked options, approve one and check the updated schedule.
6. If PayPal Sandbox is configured, create a fresh reservation, pay with a Sandbox buyer, verify capture and ticket issuance. A simulator or direct URL open does **not** prove live webhook delivery.
7. Because Render Free loses SQLite records, test a fresh start and confirm the demo organizer can log in again—but **do not claim that event/payment data survives**.

**Judge access:** Arrange private credentials or a controlled demo account via the submission's appropriate private contact method. Do not paste any credentials into GitHub, YouTube, screenshots, or public Devpost text. If no private distribution is available, rely on the runnable local instructions and demo video for full reproduction.

## Development safeguards and current limitations

- **Sandbox only:** This is a hackathon prototype; no live PayPal processing is supported or claimed.
- **Organizer authorization:** Backend routes use organizer-session and ownership checks. The frontend API bridge also validates sessions and restricts forwarded routes.
- **Webhooks:** The receiver checks required signature headers and posts the event to PayPal for verification before storing it. Real Sandbox events, not PayPal simulator mock events, are required for that postback verification method.
- **Duplicate/failure handling:** Capture preparation uses a database transaction and a PayPal idempotency request ID; uncertain outcomes require reconciliation. This reduces risk but is not a blanket guarantee against all network/concurrency failures.
- **Production bridge:** The production API bridge is **disabled by default** and must be opted into only after verifying the exact backend origin, matching server-side organizer key, restricted routes, authenticated sessions, and HTTPS.
- **Sandbox completion route:** Hosted Sandbox checkout requires an additional explicit opt-in and a fixed HTTPS return origin. No live-money checkout is supported.
- **Signup:** Public production registration remains disabled until suitable rate limiting and account-verification controls exist. Render demo setup uses a private server-seeded organizer account instead.
- **Persistence:** The local SQLite file is ignored by Git. Render Free loses SQLite data on spin-down/restart/redeploy; this patch can recreate only the initial demo organizer at restart, **not** preserve events, reservations or payments. A paid persistent disk or a database migration is required for durable judging data.
- **Production hardening still required:** HTTPS, trusted-proxy cookie behavior, secret rotation, end-to-end access tests, monitoring, and deployment validation.

## Repository layout

```text
eventmesh-ai/
├── backend/                    # FastAPI endpoints, SQLite models, auth, tests
│   ├── main.py
│   ├── organizer_auth.py
│   ├── event_ownership.py
│   ├── paypal_webhooks.py
│   ├── paypal_capture.py
│   ├── ticket_fulfillment.py
│   └── .env.example
├── frontend/                   # Next.js organizer dashboard
│   ├── src/app/
│   ├── src/components/
│   │   ├── EventMeshBryntum.tsx
│   │   └── EventMeshInsights.tsx
│   └── .env.local.example
├── docs/
│   └── THIRD_PARTY_LICENSE_INVENTORY.md
├── LICENSE
└── README.md
```

## Open source and third-party software

EventMesh AI's own contributed code is distributed under the **[MIT License](LICENSE)**, subject to the rights of its respective contributors. The project uses third-party libraries with their **own** license terms.

- **Bryntum Scheduler Community** packages, not the commercial/trial Scheduler packages.
- **Recharts** for analytics, not the commercial AG Studio/AG Grid Enterprise stack.
- A dependency-license inventory is available at **[docs/THIRD_PARTY_LICENSE_INVENTORY.md](docs/THIRD_PARTY_LICENSE_INVENTORY.md)**. Verify any additional attribution/notice obligations for redistributed assets and dependencies.

PayPal and other third-party product names are the property of their respective owners. This project is an independent hackathon prototype and does not claim official endorsement.
