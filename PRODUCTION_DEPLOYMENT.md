# ORVANTA Free-Tier Production Deployment

This runbook is for a 100% free-hosting setup.

## Free Stack

- Frontend: Vercel (Free)
- Backend API: Render Web Service (Free)
- Database + Auth: Supabase (Free)
- Redis: Upstash Redis (Free)

## Important Reality (No Paid Plan)

- Cold starts can happen on free services.
- Background workers are disabled in this free blueprint.
- Automatic scheduled ingest/live-sync is disabled.
- Manual sync from the Manage screen is the recommended mode.

This gives the best stability possible under free limits.

## 1) Create Free Infrastructure

### 1.1 Supabase

Create a project and collect:

- SUPABASE_URL
- SUPABASE_JWT_ISSUER
- Database URL (for app)

### 1.2 Upstash Redis

Create a Redis DB and copy:

- REDIS_URL

## 2) Deploy Backend (Render Free)

Use Render Blueprint from repo root. It reads [render.yaml](render.yaml).

Only one web service is created:

- orvanta-api

### Required Environment Variables

Set these in Render web service:

- APP_ENV=production
- APP_DEBUG=false
- SQL_ECHO=false
- API_V1_PREFIX=/api/v1
- DATABASE_URL=<supabase async url>
- DATABASE_URL_SYNC=<supabase sync url>
- REDIS_URL=<upstash redis url>
- JWT_SECRET_KEY=<strong random 64+ chars>
- JWT_ALGORITHM=HS256
- JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
- FRONTEND_URL=https://<your-vercel-domain>
- BACKEND_CORS_ORIGINS=["https://<your-vercel-domain>"]
- SUPABASE_URL=https://<project>.supabase.co
- SUPABASE_JWT_ISSUER=https://<project>.supabase.co/auth/v1
- SUPABASE_JWT_AUDIENCE=authenticated
- AUTO_INGEST_ENABLED=false
- LIVE_SYNC_AUTO_ENABLED=false

Optional keys:

- GROQ_API_KEY
- OPENROUTER_API_KEY
- NVIDIA_API_KEY
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

### Backend Health Check

- https://<render-api-domain>/api/v1/health

Expected:

- status ok

## 3) Deploy Frontend (Vercel Free)

Import repo on Vercel with root directory `frontend`.

Set frontend env vars:

- NEXT_PUBLIC_API_URL=https://<render-api-domain>/api/v1
- NEXT_PUBLIC_WS_URL=wss://<render-api-domain>/api/v1/ws
- NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
- NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<supabase publishable key>

Optional:

- NEXT_PUBLIC_GOOGLE_CLIENT_ID
- NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

Deploy production.

## 4) Final Validation Checklist

1. Open frontend URL and verify login page loads.
2. Sign in and open dashboard pages.
3. Verify events and alerts APIs load from backend.
4. Verify forgot password flow through Supabase.
5. Verify Manage page manual sync works.

## 5) What Is Disabled In Free Mode

- Celery worker service
- Celery beat scheduler
- Automatic periodic ingest/live sync

If you need always-on background processing and no cold starts, paid plan is required.

## 6) Troubleshooting

### API/CORS issue

- Ensure BACKEND_CORS_ORIGINS contains exact Vercel URL JSON array.
- Ensure NEXT_PUBLIC_API_URL points to Render API domain with `/api/v1`.

### Login works but dashboard fails

- Verify JWT_SECRET_KEY is set and non-empty.
- Verify Supabase issuer and audience values are correct.

### Forgot password email not delivered

- Check Supabase reset template and redirect URL.
- Configure custom SMTP in Supabase for better Gmail/Outlook delivery.
