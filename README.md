# Sonar

Sonar is a local-first Python project that monitors Hacker News activity, detects unusual tech signal spikes, cross-checks events with NewsAPI, and displays live results in a Plotly Dash dashboard.

## Features

- Hacker News ingestion through the official Firebase API
- SQLite storage for raw story snapshots, metrics, anomalies, news matches, and AI explanations
- Rolling metric aggregation for story volume, Hacker News points, comments, engagement, and growth
- Basic anomaly detection using z-score and rolling thresholds
- Optional NewsAPI validation for anomalies
- Optional Gemini structured JSON explanations for anomalies
- Optional low-frequency Gemini monitoring summaries even when no anomaly is detected
- Shared collection cycle used by API-triggered runs and the scheduled worker
- Live-updating Dash dashboard

## Project layout

```text
Sonar/
  app.py
  requirements.txt
  README.md
  sonar/
    config.py
    db.py
    ingestion/
    processing/
    ai/
    services/
    dashboard/
    worker.py
    utils/
    data/
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Fill in the values in [`.env`](/Users/Djoker/Python/Sonar/.env).

4. Run the app:

```bash
python3 app.py
```

The dashboard starts on `http://127.0.0.1:8050`.

## API Server

Sonar also includes an initial FastAPI layer for the full-stack upgrade.

Run the API locally:

```bash
uvicorn sonar.api.main:app --host 127.0.0.1 --port 8060
```

Useful endpoints:

- `GET /api/status`
- `GET /api/stories`
- `GET /api/anomalies`
- `GET /api/metrics/timeline`
- `GET /api/dashboard/overview`
- `GET /api/ai/intelligence`
- `GET /api/briefs`
- `GET /api/briefs/{brief_id}`
- `POST /api/run-once`

The API reads from the same local SQLite database as the Dash dashboard.

## Background Worker

The API and scheduled worker share one collection entrypoint:

```text
sonar.services.collection.run_collection_cycle()
```

This keeps manual and scheduled runs on the same code path. `POST /api/run-once`,
`make worker-once`, and the long-running worker all execute the same ingestion,
metric, anomaly, NewsAPI validation, AI brief, and status update flow.

Run one cycle and exit:

```bash
make worker-once
```

Run scheduled collection continuously:

```bash
make worker
```

The interval defaults to `SONAR_POLL_INTERVAL_SECONDS`, currently 300 seconds.

## React Product UI

The React/Vite frontend is in `frontend/`. It consumes the FastAPI API and provides product-facing views for:

- Overview command center with KPI cards, charts, AI briefing, ranked themes, sentiment, and clickable keyword explorer
- Stories
- Anomalies
- System status

The frontend polls `/api/status` every 60 seconds by default. Override it with
`VITE_SONAR_POLL_INTERVAL_MS` if needed. When freshness markers change,
it refreshes the active page data, so data written by `make worker` appears in
the UI without a browser reload.

Run locally:

```bash
cd frontend
npm install
npm run dev
```

The frontend starts on `http://127.0.0.1:5173` and expects the API at `http://127.0.0.1:8060`.

## Developer Commands

After creating `.venv` and installing dependencies:

```bash
make api       # FastAPI server on 8060
make worker    # scheduled collector worker
make worker-once
make dash      # Dash analyst workbench on 8050
make frontend  # React product UI on 5173
make test
```

## Docker Compose

Optional local deployment:

```bash
docker compose up --build
```

Services:

- FastAPI API: `http://127.0.0.1:8060`
- Background worker: scheduled collector service
- Dash analyst workbench: `http://127.0.0.1:8050`
- React product UI: `http://127.0.0.1:5173`

The Compose setup intentionally does not read `.env` by default, so API keys are not exposed through `docker compose config`. Run without keys for the local pipeline, or pass keys explicitly from your shell when needed.

## Test

```bash
PYTHONPATH=. .venv/bin/pytest
```

## Notes

- Sonar runs locally and stores data in `sonar/data/sonar.db`.
- If `NEWSAPI_KEY` is not set, news validation is skipped.
- If `GEMINI_API_KEY` is not set, explanation generation is skipped.
- The default Gemini model is `gemini-2.5-flash`, and it can be overridden with `GEMINI_MODEL`.
- The collector polls selected Hacker News feeds every 3 minutes by default.
- Gemini anomaly mode runs on detected spikes only.
- Gemini monitoring mode runs at a lower frequency and summarizes the current topic landscape.

## Phase status

- Phase 1: Implemented
- Phase 2: Implemented with simple statistical anomaly detection
- Phase 3: Implemented as optional modules for NewsAPI and Gemini
