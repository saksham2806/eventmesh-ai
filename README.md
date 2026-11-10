
# EventMesh AI

### AI-Powered Multi-Agent Event Management Platform

EventMesh AI is a full-stack event operations platform built for the PayPal AI Hackathon.

It helps event organizers manage events, schedules, tickets, payments, and unexpected disruptions from a unified dashboard.

## The Problem

Managing a large event involves coordinating rooms, speakers, attendees, schedules, and payments.

Unexpected problems such as room unavailability, speaker delays, and scheduling conflicts can disrupt multiple activities.

Traditional event management tools often require organizers to resolve these problems manually.

## Our Solution

EventMesh AI combines event management with intelligent disruption analysis and human-controlled recovery workflows.

When an incident occurs, organizers can:

1. Report the disruption.
2. Generate AI-assisted recovery recommendations.
3. Compare alternative rooms and time slots.
4. Review disruption scores and potential payment impact.
5. Select a proposed recovery plan.
6. Approve changes through a controlled workflow.

## Key Features

### 1. Event Management

- Organizer authentication
- Event creation and management
- Room registration
- Session scheduling
- Schedule conflict detection
- Event-level ownership controls

### 2. AI Recovery Engine

- Multi-incident analysis
- Room unavailability handling
- Speaker delay analysis
- Alternative scheduling recommendations
- Disruption scoring
- Recovery proposal persistence
- Human approval workflow
- Conflict and impact assessment

### 3. Ticketing and Reservations

- Ticket category creation
- Ticket inventory tracking
- Reservation management
- Checkout previews
- Payment status tracking
- Ticket issuance after verified payment

### 4. PayPal Sandbox Integration

- PayPal Sandbox checkout
- Payment capture verification
- Webhook signature verification
- Payment reconciliation
- Refund eligibility checks
- Human-controlled refund proposals
- Gated Sandbox refund execution

Payment integrations are tested in PayPal Sandbox.
This project does not claim live production payment processing.

### 5. Security

- Organizer login sessions
- Password hashing
- Organizer-specific event access
- Cross-organizer isolation for tested endpoints
- Server-side API credentials
- Protected payment and refund operations
- Local-only development proxy

### 6. Monitoring and Analytics

- Event statistics
- Room and session timelines
- Ticket inventory monitoring
- Payment webhook monitoring
- Reconciliation status
- AG Studio analytics integration
- Bryntum scheduling integration

The Bryntum trial integration may operate in read-only mode.

## Technology Stack

### Frontend
- Next.js
- React
- TypeScript
- Tailwind CSS
- AG Studio
- Bryntum Scheduler

### Backend
- Python
- FastAPI
- SQLite
- PayPal Sandbox APIs

### Development Tools
- Git and GitHub
- VS Code
- Python unittest
- PowerShell

## System Architecture

Organizer
    |
    v
Next.js Frontend
    |
    v
Authenticated API Routes
    |
    v
FastAPI Backend
    |
    +-- Organizer Authentication
    +-- Event Management
    +-- Scheduling and Conflict Detection
    +-- AI Recovery and Proposal Management
    +-- Ticketing and Reservations
    +-- Payment and Refund Services
    +-- Webhook Verification and Reconciliation
    |
    v
SQLite Database

External Integration:
PayPal Sandbox APIs and Webhooks

## Running Locally

### Backend

Open PowerShell:

```powershell
cd D:\eventmesh-ai\backend

.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Backend API documentation:

http://127.0.0.1:8000/docs

### Frontend

Open another PowerShell terminal:

```powershell
cd D:\eventmesh-ai\frontend

npm run dev -- --webpack
```

Frontend:

http://localhost:3000

Install dependencies from the respective requirements and package files when setting up a new environment. Configure local credentials using the provided example environment files.

Never commit real API keys, credentials, or local database files.

## Testing

The backend regression suite was executed successfully:

93 tests passed.

The following workflows have also been verified during local development:

- Organizer login and logout
- Cross-organizer isolation for tested routes
- Event and room loading
- Session scheduling display
- AI recovery preview generation
- PayPal Sandbox payment persistence
- Verified payment records
- Issued ticket records
- Frontend TypeScript checking

A previously tested Sandbox reservation was stored with PAID status, one linked verified payment, and one issued ticket.

## Current Limitations

- The project is currently designed for local demonstration.
- Public production deployment has not been security-audited.
- Production frontend build verification remains incomplete because the development laptop encountered an out-of-memory crash.
- Real PayPal live payments are not enabled.
- Refund execution must remain explicitly authorized and restricted to its configured Sandbox workflow.
- AI suggestions require organizer review and approval.
- Third-party scheduling components may have trial-license limitations.

## Demo Walkthrough

1. Sign in as an organizer.
2. View the main dashboard.
3. Select an existing event.
4. View its rooms and session timeline.
5. Open AI Recovery.
6. Report room unavailability and speaker delay.
7. Generate recovery recommendations.
8. Compare disruption scores and impact analysis.
9. Demonstrate the approval safeguards without executing unnecessary changes.
10. Open Tickets & Payments.
11. Show reservation and payment status.
12. Open PayPal Webhook Monitoring.
13. Explain verified Sandbox payment reconciliation and ticket issuance.

## Project Status

Functional local demonstration with tested backend workflows.

Production deployment and complete release verification remain future work.

## Hackathon

Developed for the PayPal AI Hackathon.

EventMesh AI demonstrates how AI-assisted operational planning can work alongside secure payment workflows and human decision-making.
