# Sonar AI

Sonar AI is a Hacker News signal-monitoring and evidence-analysis system. It collects story activity over time, measures changes in engagement, detects unusual behavior, and uses Gemini to turn the current technology landscape into structured, traceable intelligence.

The project includes a live dashboard, a read-only FastAPI service, a scheduled collection pipeline, PostgreSQL persistence, AI audit records, containerized workloads, and reproducible GCP infrastructure.

## Live Application

| Surface | URL |
| --- | --- |
| Dashboard | [Sonar AI Radar](https://sonar-ai-radar.liyerongvv.chatgpt.site) |
| API status | [FastAPI status](https://sonar-api-4akcp3ehqa-ts.a.run.app/api/status) |
| GCP runtime verification | [Live Cloud Run record](https://sonar-api-4akcp3ehqa-ts.a.run.app/api/runtime) |

The public dashboard reads live data from the production API. If the API is unavailable, the frontend can fall back to a curated demonstration snapshot rather than rendering a broken page.

### Verify the GCP deployment

Open **Live infrastructure verification** at the bottom of the dashboard, then select **Open live runtime record**. The record exposes only non-sensitive values that Cloud Run injects into the running container: `K_SERVICE`, `K_REVISION`, and `K_CONFIGURATION`. A genuine production response reports the active `sonar-api` service and its current immutable revision, together with the live PostgreSQL connectivity check.

The linked API uses Google's assigned `run.app` domain. Its HTTP response also includes Google-managed headers such as `server: Google Frontend` and `x-cloud-trace-context`; these can be inspected in the browser Network panel or with:

```bash
curl -sS -D - -o /dev/null \
  https://sonar-api-4akcp3ehqa-ts.a.run.app/api/runtime
```

No Secret Manager values, database credentials, connection addresses, or private infrastructure identifiers are returned by this endpoint.

## What Sonar Does

- collects Hacker News `topstories` and `newstories`
- stores time-based snapshots instead of overwriting previous observations
- calculates story volume, score, comment, engagement, and growth metrics
- detects statistically unusual changes against recent feed history
- produces a Gemini landscape summary from the strongest current stories
- generates evidence-backed event briefs when an anomaly is detected
- optionally checks external NewsAPI coverage for supporting context
- preserves prompts, model metadata, raw responses, parsed output, and errors
- connects charts, themes, keywords, and story lists to individual Hacker News discussions

## AI Analysis

Sonar uses two complementary forms of AI analysis.

### Landscape monitoring

After a collection cycle, Gemini summarizes a ranked sample of current stories. The result powers the dashboard's current landscape, ranked themes, sentiment distribution, keyword explorer, notable stories, and concise monitoring insights.

### Evidence-backed event briefs

When a metric crosses the anomaly threshold, Sonar selects the strongest event per feed, gathers Hacker News and optional external-news evidence, and requests a structured brief. Each result remains linked to the anomaly, source documents, model execution, and exact evidence used.

Gemini and NewsAPI are optional enrichments. Collection, storage, metrics, anomaly detection, and the read-only API continue to operate when either provider is unavailable.

## Architecture

```text
Cloud Scheduler (every 6 hours)
              |
              v
     Cloud Run collector Job <------ Hacker News / NewsAPI / Gemini
              |
              v
     Cloud SQL for PostgreSQL
              |
              v
       Cloud Run FastAPI <---------- Sites React dashboard

Delivery and infrastructure:
GitHub Actions + Workload Identity Federation
Artifact Registry + Cloud Run
Terraform + versioned GCS remote state
Secret Manager for runtime credentials
```

Production resources run in the GCP Sydney region (`australia-southeast1`). The API, collector, and migration job use separate service accounts and connect to Cloud SQL through the managed Unix socket.

## Main Components

| Component | Responsibility |
| --- | --- |
| `sonar/ingestion` | Hacker News and NewsAPI clients |
| `sonar/processing` | Metrics and anomaly detection |
| `sonar/ai` | Gemini monitoring summaries and evidence briefs |
| `sonar/services` | Retry-safe collection pipeline orchestration |
| `sonar/api` | Public read-only FastAPI endpoints |
| `frontend` | Interactive React dashboard |
| `alembic` | Versioned PostgreSQL schema migrations |
| `terraform` | GCP identity, state, database, jobs, API, and scheduler |
| `.github/workflows` | CI, application deployment, and infrastructure planning |

## Reliability and Security

- PostgreSQL constraints prevent duplicate logical snapshots and metrics.
- Stable `run_id` values make collection retries idempotent.
- `pipeline_runs` records stage, status, attempt count, result counts, and failures.
- A PostgreSQL advisory lock prevents overlapping collectors.
- Alembic owns schema changes; application startup does not mutate tables.
- The public API is read-only and does not expose a collection trigger.
- CORS is restricted to the deployed dashboard and local development origins.
- Secrets are stored in Secret Manager rather than source code or container images.
- GitHub authenticates to GCP through Workload Identity Federation without a service-account key file.
- Application images are pinned by digest and shared by the API, collector, and migration job.
- Cloud Run scaling is capped to limit cost and database connection pressure.

## Run Locally

Requirements:

- Python 3.11 or newer
- Node.js 22.13 or newer
- Docker with Compose

Start PostgreSQL and create the test database the first time:

```bash
docker compose up -d --wait postgres
docker compose exec postgres createdb -U sonar sonar_test
```

Create the Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Set `POSTGRES_PASSWORD`, `DATABASE_URL`, and `TEST_DATABASE_URL` in the untracked `.env` file. Add `GEMINI_API_KEY` and `NEWSAPI_KEY` only when those enrichments are required.

Load the environment and apply the database schema:

```bash
set -a
source .env
set +a
alembic upgrade head
```

Run one collection cycle and start FastAPI:

```bash
python -m sonar.worker --once
uvicorn sonar.api.main:app --host 127.0.0.1 --port 8060
```

In another terminal, start the dashboard:

```bash
cd frontend
npm install
NEXT_PUBLIC_SONAR_API_BASE=http://127.0.0.1:8060 npm run dev
```

Open `http://127.0.0.1:5173`.

### Docker Compose

The local stack can also run as containers:

```bash
docker compose up -d --wait postgres
docker compose run --rm migrate
docker compose up --build api frontend
docker compose run --rm worker
```

Local services:

- API: `http://127.0.0.1:8060`
- dashboard: `http://127.0.0.1:5173`
- PostgreSQL: `127.0.0.1:5432`

## API

```text
GET /health/live
GET /health/ready
GET /api/runtime
GET /api/status
GET /api/stories
GET /api/anomalies
GET /api/metrics/timeline
GET /api/dashboard/overview
GET /api/ai/intelligence
GET /api/briefs
GET /api/briefs/{brief_id}
```

Example:

```bash
curl -fsS https://sonar-api-4akcp3ehqa-ts.a.run.app/api/status
```

## Tests

Backend validation uses a dedicated PostgreSQL database:

```bash
python -m ruff check sonar tests alembic
python -m pytest -q
```

Build the production frontend:

```bash
cd frontend
npm run build
```

Validate the infrastructure definitions:

```bash
terraform -chdir=terraform/bootstrap fmt -check
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/application fmt -check
terraform -chdir=terraform/application validate
```

## Deployment

The infrastructure is divided into two Terraform roots:

- [`terraform/bootstrap`](terraform/bootstrap/README.md) creates remote state, the Terraform deployer identity, and GitHub Workload Identity Federation.
- [`terraform/application`](terraform/application/README.md) manages Cloud SQL, Secret Manager containers, Artifact Registry, service accounts, Cloud Run workloads, and Cloud Scheduler.

Pull requests run Python linting and PostgreSQL tests, Alembic validation, the frontend production build, a production container build, and Terraform validation. After successful checks are merged into `main`, the deployment workflow builds one immutable image, runs migrations, updates the collector, deploys a new API revision, routes production traffic to it, and verifies readiness.

Operational references:

- [`docs/application-rollback.md`](docs/application-rollback.md)
- [`docs/cost-and-cleanup.md`](docs/cost-and-cleanup.md)

Sensitive values, local environment files, Terraform variable files, state files, and saved plans are excluded from Git.

## Current Scope

- The deployment is single-region and intentionally sized for a low-traffic public project.
- The API has no end-user authentication or dedicated rate-limiting layer; only read-only routes are public.
- AI and external-news enrichment depend on provider availability and quota.
- The GCP budget alert sends notifications but is not a hard spending cap.
