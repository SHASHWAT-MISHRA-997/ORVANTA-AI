# ORVANTA — Geopolitical Risk Intelligence Platform

> ORVANTA = Operational Risk Visibility, Analysis, Notification, Triage, and Automation.

> AI-powered Agentic-as-a-Service (AaaS) platform for real-time geopolitical risk monitoring, supply chain intelligence, and automated threat response.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Next.js    │────▶│    Nginx     │────▶│   FastAPI    │
│  Frontend    │     │  Rev Proxy   │     │   Backend    │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                │
                    ┌───────────────────────────┤
                    │                           │
              ┌─────▼─────┐            ┌────────▼────────┐
              │  Celery    │            │   PostgreSQL    │
              │  Workers   │            │   + ChromaDB    │
              └─────┬──────┘            └─────────────────┘
                    │
         ┌──────────┼──────────┐
         │          │          │
    ┌────▼───┐ ┌────▼───┐ ┌───▼────┐
    │ GDELT  │ │ ACLED  │ │  RSS   │
    │ API    │ │ API    │ │ Feeds  │
    └────────┘ └────────┘ └────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, TypeScript, Recharts, Leaflet |
| Backend | FastAPI, Python 3.12, SQLAlchemy (async), Pydantic v2 |
| Agent Layer | CrewAI (5 specialized agents) |
| Database | PostgreSQL 16 |
| Queue | Redis + Celery (with Beat scheduler) |
| Vector DB | ChromaDB |
| LLM | Ollama (Mistral) |
| Infra | Docker Compose, Nginx |

## Quick Start

### 1. Clone & Configure

```bash
cp .env.example .env
# Edit .env with your settings (JWT_SECRET_KEY is critical for production)
```

### 2. Run with Docker Compose

```bash
docker compose up -d
```

By default, automatic periodic ingestion is disabled for clean client onboarding:

```dotenv
AUTO_INGEST_ENABLED=false
```

Set it to `true` only when you intentionally want scheduled background feed ingestion.

For always-on 24x7 official live updates (recommended), keep the live sync scheduler enabled:

```dotenv
LIVE_SYNC_AUTO_ENABLED=true
LIVE_SYNC_AUTO_INTERVAL_SECONDS=300
```

This runs a background sync for every active organization every 5 minutes, even when no dashboard page is open.

### 3. Access the Platform

- **Frontend**: http://localhost:3000
- **API Docs**: http://localhost:8000/api/v1/docs
- **Via Nginx**: http://localhost:8080

### 4. Register & Login

Navigate to http://localhost:3000/register to create your account and organization.

### 5. Enable Google Sign-In (Free)

Google Sign-In in this project uses Google Identity Services (free).

1. Create a Web OAuth Client in Google Cloud Console.
2. Add Authorized JavaScript origins:
      - `http://localhost:3000`
      - `http://localhost:8080`
3. Copy your Google client ID into `.env`:
      - `GOOGLE_CLIENT_ID=...`
      - `NEXT_PUBLIC_GOOGLE_CLIENT_ID=...`
4. Restart backend and frontend containers:

```bash
docker compose restart backend frontend
```

After this, users can click Google Sign-In on Login/Register and get redirected directly to Dashboard without manual registration.

### 6. Enable Clerk Sign-In (Recommended)

You can use Clerk as the auth provider (including Google social login) and still keep existing backend APIs.

1. Create a Clerk application.
2. In Clerk Dashboard, enable Google as a social provider.
3. Copy and set these env variables in `.env`:
      - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=...`
      - `CLERK_SECRET_KEY=...`
      - `CLERK_ISSUER=...` (your Clerk issuer URL, for JWT verification)
4. Restart services:

```bash
docker compose restart backend frontend
```

Flow:
- User clicks Clerk sign-in on Login/Register.
- Clerk authenticates (Google or other enabled provider).
- App exchanges Clerk session token at `/api/v1/auth/clerk`.
- App issues internal JWT and redirects directly to Dashboard.

## Client Onboarding SOP

A ready-to-share onboarding checklist is available at:

- `CLIENT_ONBOARDING_SOP.md`

It includes fresh-login steps, admin-only controls, and what to do if a client sees old data.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register user + org |
| POST | `/api/v1/auth/login` | Login, get JWT |
| POST | `/api/v1/auth/google` | Google Sign-In, get JWT |
| POST | `/api/v1/auth/forgot-password` | Request password reset |
| POST | `/api/v1/auth/reset-password` | Reset password with token |
| GET | `/api/v1/auth/me` | Get current user |
| GET | `/api/v1/dashboard` | Dashboard stats |
| GET | `/api/v1/events` | List events (filtered) |
| POST | `/api/v1/events` | Create event |
| GET | `/api/v1/risk-score` | List risk scores |
| POST | `/api/v1/risk-score/compute` | Compute risk scores |
| GET | `/api/v1/risk-score/trends` | Get risk trends |
| GET | `/api/v1/alerts` | List alerts |
| POST | `/api/v1/alerts/{id}/ack` | Acknowledge alert |
| POST | `/api/v1/agents/run` | Trigger agent pipeline |
| GET | `/api/v1/agents/runs` | List agent runs |
| GET | `/api/v1/agents/runs/{id}` | Run detail + logs |
| GET | `/api/v1/agents/status` | Agent statuses |
| WS | `/api/v1/ws/{org_id}` | Real-time alerts |

## Agent Pipeline

The platform uses 5 specialized AI agents:

1. **Data Agent** — Collects events from GDELT, ACLED, RSS feeds
2. **Verification Agent** — Validates source credibility, deduplicates
3. **Risk Agent** — Computes risk scores (severity × confidence × proximity × time decay × supply chain weight)
4. **Prediction Agent** — Trend analysis and threat forecasting
5. **Action Agent** — Generates alerts and recommendations

## Risk Scoring Algorithm

```
Score = (Severity × Confidence × Proximity) × Supply Chain Weight × Time Decay × Region Weight

Where:
- Severity: Combines event-inherent severity with event type base severity (1-10)
- Confidence: Source reliability factor (0-1)
- Proximity: Distance to 8 major supply chain chokepoints
- Supply Chain Weight: Amplified for events near critical trade routes
- Time Decay: Exponential decay with 7-day half-life
- Region Weight: Geopolitical significance multiplier
```

## Project Structure

```
ADvanced SAAS/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   ├── agents/        # CrewAI agent definitions
│   │   ├── core/          # Config, security, deps, logging
│   │   ├── db/            # Database engine, session
│   │   ├── ingestion/     # GDELT, ACLED, RSS pipelines
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic services
│   │   ├── tasks/         # Celery tasks
│   │   ├── websocket/     # WebSocket manager
│   │   └── main.py        # FastAPI app entry
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/           # Next.js pages (App Router)
│   │   ├── components/    # Reusable components
│   │   └── lib/           # API client
│   ├── Dockerfile
│   └── package.json
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── .env.example
└── README.md
```

## License

MIT
