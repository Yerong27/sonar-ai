# Sonar AI

Sonar AI is a technology-signal monitoring and evidence-analysis system. It collects Hacker News activity, tracks engagement over time, detects unusual changes, validates relevant events against external news, and produces evidence-linked AI summaries.

The repository covers the complete operating path: collection, PostgreSQL persistence, anomaly detection, model audit records, a read-only FastAPI service, an interactive React dashboard, containerized workloads, and GCP infrastructure managed with Terraform.

## Current Status

Phase 4 of the migration is deployed and verified in GCP. The API, database, scheduled collector, migrations, secrets, container registry, and Terraform state are running in the Sydney region. Phase 5 workflow configuration and runbooks are implemented in the repository; their first GitHub execution, rollback exercise, and the public frontend cutover still require manual acceptance.

| Surface or service | Status | Location |
| --- | --- | --- |
| Public dashboard | Deployed with a curated snapshot | [Open Sonar AI Radar](https://sonar-ai-radar.liyerongvv.chatgpt.site) |
| FastAPI | Deployed and reading Cloud SQL | [Open API status](https://sonar-api-4akcp3ehqa-ts.a.run.app/api/status) |
| PostgreSQL | Cloud SQL for PostgreSQL 16 | `australia-southeast1` |
| Collector | Cloud Run Job, scheduled every six hours | Cloud Scheduler, UTC |
| Schema migrations | Alembic through a dedicated Cloud Run Job | Run before application revisions |
| Application image | Artifact Registry, pinned by digest | Shared by API, collector, and migration jobs |
| Infrastructure state | Versioned GCS remote state | Separate bootstrap and application roots |

The public dashboard still uses its built-in snapshot because `NEXT_PUBLIC_SONAR_API_BASE` has not yet been applied to the Sites deployment. Local frontend builds can connect directly to FastAPI, and the cloud API already exposes live Cloud SQL data.

## What Sonar Does

- collects `topstories` and `newstories` through the official Hacker News Firebase API
- records time-based story snapshots instead of overwriting prior observations
- aggregates volume, score, comment, engagement, and growth metrics
- detects statistically unusual activity and persists the supporting data
- optionally validates events with NewsAPI
- optionally generates structured Gemini summaries from stored evidence
- preserves prompts, provider/model metadata, raw output, parsed output, status, and errors for auditability
- exposes low-cost, read-only API endpoints to the React dashboard
- links story titles and interactive visual elements to the corresponding Hacker News discussion

Sonar continues to collect and analyze Hacker News data when NewsAPI or Gemini credentials are absent. Only the corresponding enrichment step is skipped.

## Architecture

```text
                         Cloud Scheduler (every 6 hours)
                                      |
                                      v
Hacker News API -----> Cloud Run collector Job <----- NewsAPI / Gemini
                                      |
                                      v
                           Cloud SQL PostgreSQL
                                      |
                                      v
React dashboard <----- Cloud Run FastAPI Service

Deployment support:
GitHub WIF identities -> Artifact Registry / Cloud Run / Terraform
Terraform bootstrap   -> GCS remote state + deployer identity + WIF
Terraform application -> SQL, secrets, runtime identities, API, jobs, scheduler
```

The API, collector, and migration job use separate service accounts. Runtime secrets are stored in Secret Manager rather than Terraform variables or container images. Cloud Run connects to Cloud SQL through its managed Unix socket.

## Reliability and Security

- PostgreSQL uniqueness constraints prevent duplicate logical snapshots and metrics.
- `pipeline_runs` records stage, status, attempt count, counts, and failure details for each collection run.
- A repeated successful `run_id` returns its stored result instead of duplicating writes.
- A PostgreSQL advisory lock prevents overlapping collectors.
- Alembic owns schema changes; application startup does not create or mutate tables.
- The public API contains read-only endpoints, and `/api/run-once` is not exposed.
- FastAPI CORS is restricted to the deployed frontend origin and local development origins.
- Cloud Run scaling is capped to reduce cost and database connection pressure.
- GitHub-to-GCP access uses Workload Identity Federation rather than a service-account JSON key.
- Terraform precisely ignores the workload image, API revision name, and deployment-client metadata owned by CD without hiding runtime-configuration or infrastructure drift.

## AI Evidence Records

Gemini is an optional analysis stage rather than a chatbot interface. For each generated brief, Sonar can retain:

- `documents`: Hacker News and external-news evidence
- `brief_evidence`: evidence attached to a model run
- `ai_runs`: provider, model, prompt, raw response, parsed JSON, status, and error
- `explanations`: normalized brief content consumed by the UI

This keeps generated conclusions traceable to both the source material and the exact model execution.

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

Create the Python environment and local configuration:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `DATABASE_URL` and `TEST_DATABASE_URL` in `.env`, then load them and apply the schema:

```bash
set -a
source .env
set +a
alembic upgrade head
```

Run one collection cycle and start the API:

```bash
python -m sonar.worker --once
uvicorn sonar.api.main:app --host 127.0.0.1 --port 8060
```

In another terminal, start the frontend:

```bash
cd frontend
npm install
NEXT_PUBLIC_SONAR_API_BASE=http://127.0.0.1:8060 npm run dev
```

Open `http://127.0.0.1:5173`. If no API base is configured, the frontend intentionally falls back to its curated snapshot.

### Docker Compose

The same components can run as containers:

```bash
docker compose up -d --wait postgres
docker compose run --rm migrate
docker compose up --build api frontend
docker compose run --rm worker
```

Local ports:

- API: `http://127.0.0.1:8060`
- frontend: `http://127.0.0.1:5173`
- PostgreSQL: `127.0.0.1:5432`

## API

```text
GET /health/live
GET /health/ready
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

## Tests and Validation

Run backend tests against the dedicated PostgreSQL test database:

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check sonar tests alembic
python -m pytest -q
```

Build the frontend:

```bash
cd frontend
npm run build
```

Validate both Terraform roots:

```bash
terraform -chdir=terraform/bootstrap fmt -check
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/application fmt -check
terraform -chdir=terraform/application validate
```

## GCP Deployment

Infrastructure is split deliberately:

- [`terraform/bootstrap`](terraform/bootstrap/README.md) creates the remote-state bucket, Workload Identity Federation provider, and Terraform deployer identity needed before remote state can be used.
- [`terraform/application`](terraform/application/README.md) creates application APIs, Artifact Registry, Cloud SQL, Secret Manager containers, least-privilege service accounts, Cloud Run workloads, and Cloud Scheduler.
- [`docs/gcp-phase4-runbook.md`](docs/gcp-phase4-runbook.md) documents initialization, secret provisioning, image deployment, migrations, verification, and cleanup.
- [`docs/phase5-github-actions.md`](docs/phase5-github-actions.md) documents CI/CD ownership, WIF, workflow sequencing, GitHub Environment setup, and Sites cutover.
- [`docs/application-rollback.md`](docs/application-rollback.md) records the tested application rollback boundary and commands.
- [`docs/cost-and-cleanup.md`](docs/cost-and-cleanup.md) explains normal cost controls, pausing collection, and destructive-cleanup safeguards.

Real secret values, local `terraform.tfvars`, state files, and saved plans are excluded from Git. The monthly GCP budget alert is managed manually in the Cloud Console; it is not a hard spending cap.

## Phase 5 Acceptance Status

The repository now contains:

1. PR and `main` CI for Ruff, PostgreSQL tests, Alembic validation, frontend build, container build, and Terraform validation.
2. A post-CI deployment workflow that authenticates through WIF, builds one immutable image, runs migrations, updates the collector, deploys the API, verifies readiness, and records rollback inputs.
3. A separate manually triggered Terraform workflow using the Terraform deployer identity and GCS remote state.
4. GitHub setup, application rollback, Sites cutover, and cost/cleanup runbooks.

Manual acceptance remains: configure the `production` and `infrastructure` GitHub Environments, exercise the workflows from GitHub, diagnose one real workflow failure, verify a rollback and redeploy, set the Sites production API variable, and publish the live-data frontend. Phase 5 is complete only after those checks pass.

## Project Layout

```text
Sonar/
  alembic/                 # versioned PostgreSQL migrations
  docs/                    # cloud deployment and operations runbooks
  frontend/                # React/Next.js dashboard
  sonar/
    ai/                    # Gemini integration and evidence briefs
    api/                   # read-only FastAPI service
    ingestion/             # Hacker News and NewsAPI clients
    processing/            # metrics and anomaly detection
    services/               # collection and pipeline orchestration
    db.py                   # SQLAlchemy PostgreSQL adapter
    worker.py               # collector entrypoint
  terraform/
    bootstrap/             # remote state and deployment identity
    application/           # GCP application infrastructure
  tests/                   # API, database, AI, and pipeline tests
  docker-compose.yml       # local PostgreSQL and application services
  Dockerfile.api           # shared production image
```

## Current Limitations

- The public Sites build still displays snapshot data until the Phase 5 frontend cutover.
- Phase 5 workflows are not accepted until their first real GitHub runs and rollback exercise succeed.
- The deployment is single-region, zonal, and intentionally sized for a low-traffic system.
- The API has no end-user authentication or rate-limiting layer; only read-only routes are public.
- NewsAPI and Gemini behavior depends on provider availability, quota, and configured credentials.
- Budget alerts notify; they do not automatically stop GCP resources or spending.
