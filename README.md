# Sonar AI

Sonar AI is a local-first tech signal intelligence system that monitors Hacker News, detects abnormal technology attention spikes, validates events against external news, and generates evidence-grounded AI briefs.

The project is designed as an AI/FDE portfolio system: it combines data ingestion, anomaly detection, LLM structured outputs, model audit trails, REST APIs, a React product UI, and an analyst dashboard.

## Live Site And Deployment Status

**Hosted frontend:** [sonar-ai-radar.liyerongvv.chatgpt.site](https://sonar-ai-radar.liyerongvv.chatgpt.site)

The current public-facing deployment is the React product UI hosted on OpenAI Sites. It is intentionally a portfolio demonstration rather than a full production stack.

| Component | Current deployment | Data source |
| --- | --- | --- |
| React product UI | Deployed on OpenAI Sites | Curated demonstration snapshot |
| FastAPI backend | Runs locally or through Docker Compose | Local SQLite |
| Scheduled collector | Runs locally or through Docker Compose | Hacker News API, optional NewsAPI and Gemini |
| Dash analyst workbench | Runs locally or through Docker Compose | Local SQLite |

The hosted frontend does not currently connect to a production FastAPI service. When no `NEXT_PUBLIC_SONAR_API_BASE` is configured, it loads the built-in demonstration dataset. The Sites project has no D1 or R2 binding, so Sites is not storing the monitoring database.

## Data Storage

Sonar currently uses SQLite:

- local development stores data in `sonar/data/sonar.db`
- Docker Compose stores the same database in the shared `sonar-data` volume used by the API, worker, and Dash services
- the database contains story snapshots, aggregated metrics, anomalies, news matches, evidence documents, AI runs, and generated briefs
- database files, local locks, `.env`, and API keys are excluded from Git

The frontend never reads SQLite directly. In live mode it calls FastAPI; in the hosted portfolio mode it uses the curated frontend snapshot.

## Why It Exists

Hacker News can surface early signals around developer tools, AI infrastructure, security incidents, product launches, and research breakthroughs. Raw rankings show what is popular, but they do not explain whether a spike is unusual, whether external news supports it, or what evidence an analyst should trust.

Sonar turns that stream into an operational workflow:

- collect live Hacker News stories
- aggregate engagement metrics over time
- detect abnormal spikes with statistical thresholds
- cross-check anomalies against external news
- generate concise AI briefs from stored evidence
- expose the workflow through FastAPI, React, and Dash

## Architecture

```text
Hacker News API          NewsAPI
       |                   |
       v                   v
Python collector ---> SQLite local database
       |                   |
       v                   v
Metric aggregation    News validation
       |                   |
       v                   |
Anomaly detection ---------+
       |
       v
Evidence brief generator
       |
       +--> documents
       +--> brief_evidence
       +--> ai_runs
       +--> explanations
       |
       +--> FastAPI REST API
       |        |
       |        v
       |   React product UI
       |
       +--> Dash analyst workbench
```

## Current Product Surfaces

### React Product UI

The React/Vite frontend is the product-facing interface. It consumes the FastAPI API and provides:

- signal overview with KPI cards and charts
- story explorer
- anomaly triage
- AI intelligence panels
- keyword exploration
- system status and manual run controls

Screenshot placeholder:

```text
docs/screenshots/react-dashboard.png
```

### AI Evidence Briefs

The AI layer is not a generic chatbot. It produces structured incident-style briefs from evidence selected by the monitoring pipeline.

Each brief can be traced through:

- `documents`: stored Hacker News or external news evidence
- `brief_evidence`: which evidence rows were attached to an AI run
- `ai_runs`: provider, model, prompt, raw response, parsed JSON, status, and error
- `explanations`: normalized brief shown to the UI

Screenshot placeholder:

```text
docs/screenshots/ai-brief-evidence.png
```

### Dash Analyst Workbench

Dash remains available as an analyst workbench for deeper Plotly diagnostics, dense monitoring views, and exploratory analysis. React is the product UI; Dash is the diagnostic surface.

## What The AI Does

Sonar uses Gemini optionally. If `GEMINI_API_KEY` is not configured, the ingestion, metrics, anomaly detection, API, React UI, and Dash dashboard can still run.

When Gemini is enabled, Sonar:

1. selects anomalies from the monitoring pipeline
2. collects related Hacker News stories and external news context
3. stores evidence records in SQLite
4. asks the model for strict JSON only
5. normalizes verbose model output into dashboard-safe fields
6. stores raw model output, parsed JSON, prompt, model name, status, and errors
7. links the generated brief back to the evidence used

This makes the AI layer auditable rather than a one-off LLM call.

## Features

- Hacker News ingestion through the official Firebase API
- SQLite storage for story snapshots, metrics, anomalies, news matches, evidence, AI runs, and briefs
- metric aggregation for story volume, score, comments, engagement, and growth
- z-score based anomaly detection
- optional NewsAPI validation
- optional Gemini structured JSON brief generation
- FastAPI backend for product UI and local automation
- React/Vite frontend for product-facing exploration
- Dash/Plotly analyst workbench
- shared collection cycle for API-triggered and scheduled worker runs
- Docker Compose for local multi-service execution

## Run Locally

Create a virtual environment and install Python dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create local environment variables:

```bash
cp .env.example .env
```

API keys are optional:

```text
NEWSAPI_KEY=
GEMINI_API_KEY=
```

Run one collection cycle:

```bash
make worker-once
```

Start the FastAPI server:

```bash
make api
```

Open:

```text
http://127.0.0.1:8060/api/status
```

Start the React product UI:

```bash
make frontend
```

Open:

```text
http://127.0.0.1:5173
```

Start the Dash analyst workbench:

```bash
make dash
```

Open:

```text
http://127.0.0.1:8050
```

## Docker Compose

Optional local multi-service run:

```bash
docker compose up --build
```

Services:

- FastAPI API: `http://127.0.0.1:8060`
- React product UI: `http://127.0.0.1:5173`
- Dash analyst workbench: `http://127.0.0.1:8050`
- background worker sharing the same SQLite volume

The Compose setup intentionally does not load `.env` by default, so private API keys are not exposed through `docker compose config`.

## API Endpoints

```text
GET  /api/status
GET  /api/stories
GET  /api/anomalies
GET  /api/metrics/timeline
GET  /api/dashboard/overview
GET  /api/ai/intelligence
GET  /api/briefs
GET  /api/briefs/{brief_id}
POST /api/run-once
```

The frontend consumes the API only. It does not read SQLite directly.

## What Works Without API Keys

Without `NEWSAPI_KEY`:

- Hacker News ingestion still works
- metrics and anomaly detection still work
- news validation is skipped

Without `GEMINI_API_KEY`:

- collection, metrics, anomalies, FastAPI, React, and Dash still work
- AI brief generation is skipped
- Gemini status is recorded as disabled/provider unavailable

This keeps the project usable as a local monitoring system even when external AI services are not configured.

## Developer Commands

```bash
make api         # FastAPI server on 8060
make worker      # scheduled collector worker
make worker-once # one collection cycle
make dash        # Dash analyst workbench on 8050
make frontend    # React product UI on 5173
make test        # Python tests
```

Frontend commands:

```bash
cd frontend
npm install
npm run dev
npm run build
```

## Project Layout

```text
Sonar/
  app.py                    # Dash entrypoint
  sonar/
    api/                    # FastAPI backend
    ai/                     # Gemini provider, brief schema, evidence briefs
    dashboard/              # Dash analyst workbench
    ingestion/              # Hacker News and NewsAPI clients
    processing/             # metrics and anomaly detection
    services/               # shared collection cycle
    worker.py               # scheduled worker entrypoint
    db.py                   # SQLite schema and persistence helpers
  frontend/                 # React/Vite product UI
  tests/                    # API and AI brief tests
  docker-compose.yml
```

## Limitations

- Sonar is local-first and uses SQLite; it is not designed as a multi-user hosted SaaS.
- The hosted Sites deployment currently contains the frontend only and uses demonstration data.
- The first retrieval layer uses stored evidence and simple selection logic, not a production vector database.
- Gemini is optional and depends on API quota and model availability.
- The current UI is a portfolio-grade product interface, not a fully deployed commercial application.
- External news validation depends on NewsAPI availability and query quality.

## Production Roadmap

The shortest path from the current portfolio deployment to a more formal product is:

1. **Deploy the backend and worker**
   - run FastAPI as a persistent service
   - run collection as a separate scheduled worker
   - configure the hosted frontend with `NEXT_PUBLIC_SONAR_API_BASE`
   - allow only the production frontend origin through CORS

2. **Move operational data to a managed database**
   - migrate SQLite tables to PostgreSQL or another managed relational database
   - introduce versioned schema migrations
   - configure automated backups, retention, and restore testing

3. **Make ingestion reliable**
   - add idempotent collection jobs and database-level deduplication
   - add retry and backoff policies for Hacker News, NewsAPI, and Gemini
   - track freshness, failed runs, queue depth, and provider quota usage

4. **Add production controls**
   - store secrets in the deployment platform rather than local files
   - add authentication before exposing manual collection or analyst actions
   - add rate limiting, request validation, structured logs, error tracking, and health checks

5. **Add delivery discipline**
   - run backend tests and frontend builds in CI for every pull request
   - add API contract tests and browser tests for the main investigation workflow
   - maintain staging and production environments with separate data and secrets

6. **Polish the product boundary**
   - replace the demo banner with live freshness and coverage indicators
   - add a custom domain and operational status page
   - document data retention, third-party API usage, and AI-generated content behavior

For a portfolio-quality next milestone, prioritize steps 1–3. Authentication and multi-user features should follow after the live data pipeline is reliable.

## Resume Positioning

Built Sonar AI, a full-stack tech signal intelligence system using Python, FastAPI, React, SQLite, Hacker News API, NewsAPI, and Gemini. The system collects live technology signals, detects statistical anomalies, validates events against external news, and generates structured AI briefs with stored evidence and model audit trails.

Skills demonstrated:

- Python
- FastAPI
- React
- REST APIs
- SQLite
- data pipelines
- anomaly detection
- LLM APIs
- structured JSON outputs
- evidence-grounded AI workflows
- Docker Compose
- full-stack development

## Next Improvements

Follow the production roadmap above before adding more dashboard surface area or speculative backend features.
