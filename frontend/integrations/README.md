# Optional official sponsor integrations (not installed / not yet runtime-verified)

The main dashboard works without the commercial/trial packages. The two adapters in this directory are **starter integration code**, not proof that the sponsor products are installed. No sponsor SDK is bundled with the ZIP.

## Bryntum Scheduler React
1. In `frontend/`, run `npm install @bryntum/scheduler@npm:@bryntum/scheduler-trial@7.3.7 @bryntum/scheduler-react@7.3.7`.
2. Copy `integrations/BryntumScheduler.tsx.example` to `src/components/BryntumScheduler.tsx`.
3. Load it in a React client component using `next/dynamic` with `{ ssr:false }`, then pass live `rooms`, `sessions`, and `selectedEvent.event_date` from the dashboard.
4. Check the installed version docs for changed props. This is **read-only on purpose**: drag-and-drop mutations require server-side conflict verification and organizer approval before saving.

Official docs: https://www.bryntum.com/products/scheduler/docs/guide/Scheduler/quick-start/nextjs

## AG Studio React
1. In `frontend/`, run `npm install ag-studio-react`.
2. Copy `integrations/AGStudioPanel.tsx.example` to `src/components/AGStudioPanel.tsx`.
3. Render the component using live `events`, `rooms`, `sessions`, and `tickets` from your dashboard (e.g., on the Insights tab).
4. In Studio `mode="edit"`, arrange grids/charts from the supplied data sources and optionally persist report state.

Official docs: https://www.ag-grid.com/studio/react/installation/

**Verification:** Once npm dependencies can install, run `npm run build`, open both panels, and verify the real vendor components and console warnings. The ZIP builder's environment could not access the npm registry, so these sponsor adapters have not been runtime-tested.
