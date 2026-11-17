# Phase 2: admin dashboard (v1)

Build a single-page dashboard served by the existing FastAPI app. No npm, no build step, no frameworks: plain HTML, CSS and JS only.

## Setup
- Put the files in app/static/ (index.html, dashboard.js, style.css) and serve them at /dashboard with StaticFiles in app/main.py. Make "/" redirect to /dashboard.
- Same origin as the API, so no CORS changes.
- Read the real response shapes from app/api/endpoints.py. Do not rely on docs/plan.md for field names.

## Auth
- On load, show a small box asking for the admin key. Keep it in sessionStorage only, send it as the X-API-Key header on every fetch, and add a "Sign out" button that clears it.
- Never hardcode a key, never log it, never write it to any file. A 401/403 response sends the user back to the key box with a clear message.

## Views (one page, three panels)
1. System stats from GET /api/system-stats. Show the computed numbers in one panel and the "benchmark" object in a separate panel labeled "Test-bench results (not live data)". Refresh every 300s.
2. Tickets table from GET /api/tickets, with status and category filters, pagination, and a Refresh every 60s. Each row has a "Resolve" button that opens a confirm dialog, then calls POST /api/resolve-ticket with {ticketId, resolvedBy}. The resolvedBy value comes from a text box in the page header, and the button is disabled while it is empty. After success, reload the table. Clicking a row's chat id opens the conversation panel.
3. Conversation viewer from GET /api/conversations/{chat_id}: last messages in order (user vs assistant), the escalation state, and the ticket status. Refresh every 30s while a chat is open. Also include a text box to look up any chat id.

## Rules
- Every fetch failure shows a visible, specific message in the panel (status code and detail). No silent failures, no blank panels, and empty data shows "No data yet".
- Escape all text from the API before inserting it into the page (use textContent, never innerHTML with API data).
- Keep it clean and readable: a simple card layout, light/dark friendly, and usable on a laptop screen. No decoration beyond that.
- Out of scope: brain-status, workflow-progress, websockets, user accounts, charts libraries, anything new in the backend beyond serving the static files.

## Workflow
- Work panel by panel: auth box first, then stats, then tickets, then conversation. After each one, start the server on port 8001, check it, and report what you verified and what you could not.
- Do not touch workflows/RELAY.json or sql/schema.sql. Never print .env values.
- If a command fails twice, stop and show me the error.
