# ORVANTA Production Deployment Runbook

This guide deploys ORVANTA in production with a stable split architecture:

- Frontend: Vercel
- Backend API: Render (Docker web service)
- Background jobs: Render workers (Celery worker + Celery beat)
- Database: Supabase Postgres
- Redis: Upstash Redis

This setup avoids local bottlenecks, supports horizontal scaling, and keeps operational risk lower than all-in-one free-host deployments.

## 1) Create Managed Infrastructure

### 1.1 Supabase Postgres

Create a Supabase project and copy:

- Project URL
- Database connection string
- JWT issuer

Use pooler or direct connection URL as needed.

### 1.2 Upstash Redis

Create a Redis database and copy:

- REDIS_URL (rediss://...)

## 2) Deploy Backend on Render

### 2.1 Create Blueprint

In Render dashboard:

- New -> Blueprint
- Select repo: SHASHWAT-MISHRA-997/ORVANTA-AI
- Render will detect render.yaml

Services created:

- orvanta-api (web)
- orvanta-worker (worker)
- orvanta-beat (worker)

### 2.2 Set Required Environment Variables (all 3 services)

Set these values exactly:

- APP_ENV=production
- APP_DEBUG=false
- API_V1_PREFIX=/api/v1
- DATABASE_URL=<supabase async url>
- DATABASE_URL_SYNC=<supabase sync url>
- REDIS_URL=<upstash redis url>
- JWT_SECRET_KEY=<64+ random chars>
- BACKEND_CORS_ORIGINS=["https://<your-vercel-domain>"]
- FRONTEND_URL=https://<your-vercel-domain>
- SUPABASE_URL=https://<your-supabase-project>.supabase.co
- SUPABASE_JWT_ISSUER=https://<your-supabase-project>.supabase.co/auth/v1
- SUPABASE_JWT_AUDIENCE=authenticated

Optional AI and mail variables:

- GROQ_API_KEY, OPENROUTER_API_KEY, NVIDIA_API_KEY
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

### 2.3 Health Verification

After deployment succeeds:

- https://<render-api-domain>/api/v1/health -> should return status ok

## 3) Deploy Frontend on Vercel

### 3.1 Import Project

In Vercel dashboard:

- Add New Project
- Import repo: SHASHWAT-MISHRA-997/ORVANTA-AI
- Root Directory: frontend

### 3.2 Set Environment Variables

In Vercel project environment variables:

- NEXT_PUBLIC_API_URL=https://<render-api-domain>/api/v1
- NEXT_PUBLIC_WS_URL=wss://<render-api-domain>/api/v1/ws
- NEXT_PUBLIC_SUPABASE_URL=https://<your-supabase-project>.supabase.co
- NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<supabase publishable key>
- NEXT_PUBLIC_GOOGLE_CLIENT_ID=<optional>
- NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<optional>

Deploy to production.

## 4) Update Backend CORS After Frontend Domain Is Live

Set BACKEND_CORS_ORIGINS again to include all live frontend domains:

["https://<main-vercel-domain>","https://<custom-domain-if-any>"]

Redeploy backend service once.

## 5) Final Production Validation

Run this sequence:

1. Open frontend production URL.
2. Sign up / login works.
3. Forgot password sends email and reset link opens correctly.
4. Dashboard pages load under 2-3 seconds after warm start.
5. /api/v1/health returns ok.
6. Live sync works from Manage page.
7. Worker and beat services show healthy logs in Render.

## 6) Reliability Settings (Recommended)

- Render service plan: Starter or above for no sleep
- Enable auto-deploy only on main branch
- Add uptime monitor ping to /api/v1/health every 5 min
- Keep JWT secret, SMTP keys, AI keys rotated periodically

## 7) Common Failure Fixes

### 502 or CORS errors

- Check NEXT_PUBLIC_API_URL points to Render API domain
- Check BACKEND_CORS_ORIGINS JSON is valid and includes frontend domain

### Login works but dashboard API fails

- Check API_V1_PREFIX and frontend base URL both use /api/v1
- Verify JWT_SECRET_KEY is same for all backend services

### Celery tasks not running

- Check REDIS_URL for worker and beat
- Verify worker and beat services are both up in Render

### Forgot password not delivered

- Verify Supabase Email template and redirect URL
- Use custom SMTP in Supabase for reliable Gmail/Outlook delivery

## 8) Rollback Plan

- Keep previous Render deploy active until new one is healthy
- In Vercel, promote previous deployment if critical issue appears
- Roll back by redeploying previous known-good commit
