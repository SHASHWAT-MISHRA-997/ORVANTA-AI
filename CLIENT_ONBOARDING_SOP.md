# Client Onboarding SOP (Google Sign-In, Fresh Workspace)

## Purpose

Ensure every new client gets a fresh workspace with no inherited live/demo data.

## Preconditions (one-time platform setup)

1. Google OAuth client ID is configured in `.env`:
   - `GOOGLE_CLIENT_ID`
   - `NEXT_PUBLIC_GOOGLE_CLIENT_ID`
2. Auto-ingest is disabled:
   - `AUTO_INGEST_ENABLED=false`
3. Services are running:
   - `docker compose up -d --build backend frontend celery-worker celery-beat`

## Admin Rules

1. Only org admins can run live sync (`/events/live-sync`).
2. Full workspace wipe is available in Settings:
   - `Clear All Workspace Data`

## New Client Flow

1. Ask client to open app in an incognito/private window.
2. Client clicks `Continue with Google` on login/register.
3. Client selects their Google account.
4. System creates a fresh user and organization on first login.
5. Confirm dashboard is empty (events/analytics/alerts/agents).

## If Client Sees Old Data

1. In browser storage, remove:
   - `warops_token`
   - `warops_user`
2. Hard refresh and re-login via Google.
3. If data still appears, admin opens Settings and clicks `Clear All Workspace Data`.

## Optional Manual Data Start (Admin only)

1. Admin can trigger live sync intentionally from dashboard pages.
2. Non-admin users cannot trigger sync.
