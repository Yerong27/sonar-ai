# Sonar AI Full-Stack Improvement Plan

## Summary

This plan upgrades Sonar from a local Dash monitoring dashboard into a portfolio-grade full-stack AI project.

Target positioning:

> Sonar AI is a local-first AI signal intelligence platform that monitors Hacker News, detects abnormal technology signal spikes, validates them with external news, and generates evidence-grounded AI incident briefs through a full-stack product interface.

The project should keep the existing Python collector, anomaly detection, SQLite storage, NewsAPI validation, Gemini summaries, and Dash dashboard. The upgrade adds a FastAPI backend, React/Vite product UI, evidence-grounded AI briefs, AI run audit trail, tests, and stronger documentation.

## Current Baseline

- `v0.0.0` tag represents the current baseline.
- GitHub repository: `https://github.com/Yerong27/sonar-ai`
- Current app entrypoint: `app.py`
- Current dashboard: Dash + Plotly in `sonar/dashboard/app.py`
- Current data pipeline: `sonar/ingestion/collector.py`
- Current database layer: `sonar/db.py`
- Current AI layer: `sonar/ai/gemini.py`

Current strengths:

- Hacker News ingestion through the official Firebase API.
- SQLite storage for stories, metrics, anomalies, news matches, explanations, and monitoring summaries.
- Rolling metric aggregation and z-score anomaly detection.
- Optional NewsAPI validation.
- Optional Gemini structured JSON explanations.
- Live Dash analyst dashboard.

Current gaps:

- No FastAPI backend.
- No React product interface.
- AI explanations are not yet strongly evidence-grounded.
- Prompt, raw response, model name, evidence IDs, and failure state are not fully audited.
- No API or AI evaluation test suite.
- README does not yet present the project as a full-stack AI system.

## Target Architecture

```text
Hacker News API / NewsAPI
        |
Shared Collection Cycle
        |
Python Collector Worker / API Manual Trigger
        |
SQLite
        |
AI Evidence Brief Generator
        |
+----------------------+----------------------+
| FastAPI Backend      | Dash Analyst UI      |
| REST API             | Deep monitoring      |
+----------+-----------+ Plotly diagnostics  |
           |
     React/Vite Product UI
```

Dash should not be removed or described as abandoned legacy. Its role is the internal analyst workbench for deep charts, operational monitoring, anomaly debugging, and exploratory analysis.

React should become the product-facing full-stack UI. It proves frontend capability through routing, API calls, loading/error/empty states, and a more polished user experience.

## Implementation Status

- [x] v0 baseline pushed to GitHub.
- [x] Full-stack improvement plan saved in repo.
- [x] FastAPI backend API foundation.
- [x] React/Vite product UI foundation.
- [x] AI evidence brief generator foundation.
- [x] AI run audit trail foundation.
- [x] API and AI tests.
- [ ] README, screenshots, and project presentation. README command docs updated; screenshots pending.
- [x] Optional local dev commands or Makefile.
- [x] Optional Docker Compose.
- [x] Shared collection cycle for API-triggered and worker-triggered runs.
- [x] Background worker entrypoint for scheduled collection.
- [ ] React polling and chart dashboard upgrade.
- [ ] React AI intelligence and investigation dashboard parity upgrade.
- [ ] Shared compact AI brief schema and normalization.

## Key Changes

### 1. FastAPI Backend

Add a FastAPI layer that reads from SQLite and triggers the existing collector.

Proposed endpoints:

```text
GET  /api/status
GET  /api/stories?feed=&limit=&since=
GET  /api/anomalies?limit=&news_aligned=
GET  /api/briefs?limit=
GET  /api/briefs/{brief_id}
POST /api/run-once
```

Endpoint behavior:

- `/api/status`: return collector status, Gemini status, last collection time, story count, anomaly count, brief count, and data freshness.
- `/api/stories`: return latest Hacker News story snapshots with feed, title, score, comments, permalink, source URL, and collected time.
- `/api/anomalies`: return anomaly timeline records with metric name, z-score, triggered metrics, news alignment, explanation status, and detected time.
- `/api/briefs`: return AI brief cards with headline, topic, sentiment, confidence, evidence count, and created time.
- `/api/briefs/{brief_id}`: return parsed brief JSON, raw response, model metadata, prompt metadata, and evidence links.
- `/api/run-once`: run one collector cycle for demo and local testing.

The frontend must call the API only. It should not read SQLite directly.

Manual API runs and scheduled worker runs must use the same service function:

```text
sonar.services.collection.run_collection_cycle()
```

This prevents drift between "Run once" behavior and background collection behavior.

### 2. React/Vite Product UI

Add a React/Vite frontend as the main product demo.

Required pages:

- Overview: system health, last collection time, story count, anomaly count, AI brief count, Gemini status.
- Stories: story table with feed filter, score/comments display, and external links.
- Anomalies: anomaly timeline/list with z-score, triggered metrics, news alignment, and explanation status.
- AI Briefs: incident brief cards with headline, topic, confidence, sentiment, evidence links, and raw JSON toggle.
- System: local service links, configuration notes, data freshness, API status, and Dash analyst workbench link.

Frontend requirements:

- Loading states for every page.
- Empty states for no data.
- Error states for API failure.
- Responsive dashboard layout.
- Product UI should be clean and operational, not a marketing landing page.

Polling and chart upgrade plan:

1. Keep the worker and API as separate backend roles sharing SQLite.
2. Add lightweight frontend polling instead of SSE/WebSockets for this stage.
   - Poll `/api/status` every 60 seconds.
   - Compare `last_collection_time`, `latest_story_time`, `latest_anomaly_time`, and `latest_brief_time`.
   - Trigger page data refresh only when those freshness markers change.
   - Keep a manual refresh button for demos and debugging.
3. Add chart-friendly API endpoints so React does not need to reverse-engineer SQL concepts.
   - `GET /api/dashboard/overview`: status, counts, recent top stories, latest brief, feed summary, and latest anomalies.
   - `GET /api/metrics/timeline`: time-series rows from `aggregated_metrics` for story volume, score, comments, engagement, and growth.
4. Upgrade React from list-first pages to a product-facing command center.
   - KPI cards for story volume, HN score, comments, anomalies, and AI brief count.
   - Line charts for story volume and engagement over time.
   - Scatter chart for anomaly timing and z-score.
   - Horizontal bar chart for top current stories by score.
   - AI briefing panel with evidence and model status.
   - Story explorer remains as a table, but becomes secondary.
5. Keep Dash as the analyst workbench.
   - Dash can remain deeper and more diagnostic.
   - React should prove full-stack product UI capability through FastAPI APIs, polling, loading/error/empty states, and chart presentation.

Chosen approach:

- Use frontend polling first because Sonar collects every few minutes and does not require second-level event streaming.
- Defer SSE/WebSocket and Redis/pub-sub until the project needs lower-latency event delivery or multi-instance deployment.

Dash parity upgrade plan:

The original Dash dashboard is strongest because it supports an end-to-end analyst workflow:

```text
Command Center -> KPI/charts -> Top Movers -> AI Insight Briefing
-> Keyword Explorer -> Event Briefs -> Story Explorer
```

The React full-stack UI should inherit those strengths instead of becoming a list-only rewrite.

Implementation scope:

1. Add a chart-friendly AI intelligence endpoint.
   - `GET /api/ai/intelligence`
   - Return latest brief summary, ranked themes, heading visibility, sentiment distribution, keyword bubble data, and notable stories.
   - Derive first version from `explanations.response_json`, `documents`, `brief_evidence`, and recent `hn_story_snapshots`.
2. Add investigation-friendly event brief data.
   - Extend existing brief list/detail UI into an accordion-style investigation panel.
   - Show event type, confidence, news alignment, triggered metrics, why it matters, supporting evidence, and raw JSON toggle.
3. Add Top Movers to the product overview.
   - First version ranks current latest stories by score and comments because true per-story score delta is not always available from all historical snapshots.
   - Later version can compute score gain between adjacent snapshots.
4. Add Keyword Explorer without a heavy dependency.
   - Use a deterministic SVG bubble layout.
   - Use keyword visibility counts/scores from story titles and AI brief themes.
   - Keep layout stable across refreshes.
5. Keep Dash as the deeper analyst workbench.
   - React becomes the product-facing full-stack command center.
   - Dash remains useful for dense diagnostics and exploratory Plotly views.

Shared compact AI brief plan:

The first Dash version already solved a key UX problem: Gemini output must be concise enough for monitoring cards. The full-stack evidence brief layer should reuse that lesson instead of letting the new React UI carry all trimming responsibility.

Implementation scope:

1. Add shared AI brief normalization helpers.
   - Normalize list fields.
   - Strip essay-style headline openings.
   - Clamp `headline_summary` to a monitoring-title length.
   - Clamp `topic` to a short label.
   - Clamp `bullet_insights` to a maximum of 3 items.
   - Clamp each insight to a short dashboard-safe sentence.
   - Clamp `summary` to a short paragraph.
2. Update `EvidenceBriefGenerator` prompt.
   - Require `headline_summary` max 16 words.
   - Require `topic` 2-4 words.
   - Require exactly/at most 3 `bullet_insights`.
   - Require each bullet to be one sentence and max 18 words.
   - Require `summary` to be 2 short sentences and max 45 words.
3. Keep the newer evidence/audit design.
   - Preserve `documents`, `ai_runs`, and `brief_evidence`.
   - Store raw model output even when normalization trims the displayed brief.
4. Keep frontend truncation only as a defensive fallback.
   - The API should return compact normalized briefs by default.

### 3. AI Evidence Brief Generator

Strengthen AI so it is not just an explanation label after anomaly detection.

Add evidence-grounded brief flow:

1. Detect anomaly from metrics.
2. Select related Hacker News stories.
3. Select related NewsAPI articles if available.
4. Select prior historical briefs if relevant.
5. Build an evidence packet.
6. Ask LLM for structured JSON brief.
7. Store prompt, model, raw response, parsed JSON, status, error, and evidence IDs.
8. Display the brief and evidence links in Dash and React.

Minimum data concepts:

```text
documents
document_terms or document_embeddings
ai_runs
brief_evidence
```

First version should use SQLite text scoring or simple term matching for retrieval. Chroma, LanceDB, and full vector search can be added later.

Required AI brief JSON shape:

```json
{
  "headline_summary": "string",
  "topic": "string",
  "event_type": "engagement_spike | controversy | product_launch | security_incident | research_breakthrough | other",
  "sentiment_label": "positive | negative | neutral | mixed",
  "confidence": 0.0,
  "is_news_aligned": true,
  "evidence": [
    {
      "source": "hacker_news | newsapi | historical_brief",
      "id": "string",
      "title": "string",
      "url": "string",
      "reason_used": "string"
    }
  ],
  "bullet_insights": ["string"],
  "summary": "string"
}
```

Rules:

- Every generated brief must include evidence.
- If evidence is weak or missing, confidence must be low.
- The model must not invent unsupported claims.
- Raw model output must be stored even if parsing fails.
- Failures should update status instead of crashing the collector.

### 4. AI Provider Boundary

Add a lightweight AI provider interface without overbuilding a full model platform.

First version:

- `AIProvider` interface.
- `GeminiProvider` implementation.
- `FakeProvider` for tests.

Provider responsibilities:

- Generate JSON from a prompt.
- Return model name.
- Normalize markdown-fenced JSON and trailing commas.
- Return structured errors.
- Allow tests to run without real API keys.

OpenAI, fallback routing, and vector-provider abstractions are later enhancements.

### 5. Dash Analyst Workbench

Keep the Dash dashboard and make its role explicit.

Dash should continue to support:

- Deep Plotly charts.
- Story exploration.
- Anomaly debugging.
- Gemini monitoring summaries.
- AI event brief inspection.

Enhancement if feasible:

- Show new evidence links in event brief panels.
- Show AI run status and raw response diagnostics.
- Keep Dash as the richer analyst/debugging interface while React remains the product interface.

### 6. Local Developer Experience

Add simple local commands after the main backend/frontend structure exists.

Preferred commands:

```text
make install
make worker
make api
make frontend
make dash
make test
```

Docker Compose is useful but should not block the first full-stack version.

## Test Plan

### Backend/API

- `GET /api/status` works with an empty database.
- `GET /api/status` works after data exists.
- `GET /api/stories` supports `limit` and optional feed filter.
- `GET /api/anomalies` returns stable fields for timeline rendering.
- `GET /api/briefs` returns an empty list when no briefs exist.
- `GET /api/briefs/{brief_id}` returns 404 for unknown IDs.
- `POST /api/run-once` returns run status and does not crash without API keys.

### AI/Evidence

- Fake provider valid JSON creates an `ai_runs` record.
- Fake provider malformed JSON stores raw response and failed status.
- Briefs with evidence create `brief_evidence` rows.
- Brief schema validation catches missing required keys.
- Confidence must stay within `0.0` and `1.0`.
- No-evidence cases must not produce high-confidence briefs.

### Pipeline

- Existing z-score anomaly detection behavior remains covered.
- Collector can run without `NEWSAPI_KEY`.
- Collector can run without `GEMINI_API_KEY`.
- Existing monitoring summaries are not broken.

### Frontend

- Overview shows loading, empty, error, and populated states.
- Stories page renders API data and external links.
- Anomalies page shows z-score and explanation status.
- AI Briefs page shows confidence, evidence links, and raw JSON toggle.
- API failure does not produce a blank screen.

## Suggested Milestones

### Milestone 1: API Foundation

- Add FastAPI app.
- Add database query helpers.
- Add `/api/status`, `/api/stories`, `/api/anomalies`, `/api/briefs`.
- Add basic API tests.

### Milestone 2: React Product UI

- Add React/Vite app.
- Add Overview, Stories, Anomalies, AI Briefs, and System pages.
- Connect to FastAPI.
- Add loading, empty, and error states.

### Milestone 3: Evidence-Grounded AI Briefs

- Add evidence document storage.
- Add `ai_runs` and `brief_evidence`.
- Add Gemini provider boundary and fake test provider.
- Store prompt, raw response, parsed JSON, model, status, and evidence IDs.
- Show evidence in React and Dash.

### Milestone 4: Testing And Documentation

- Add API tests.
- Add AI provider and brief parsing tests.
- Add pipeline regression tests.
- Update README with architecture, setup, screenshots, API examples, and limitations.

### Milestone 5: Developer Experience

- Add Makefile or equivalent scripts.
- Add optional Docker Compose if time permits.
- Add final demo checklist.

## Assumptions And Defaults

- Target depth: portfolio-grade full-stack project.
- AI focus: evidence-grounded incident briefs.
- Dash remains an analyst workbench, not dead code.
- React is the product-facing frontend.
- SQLite remains the local data store.
- Retrieval starts with SQLite/text scoring, not Chroma or LanceDB.
- AI chat is deferred until evidence briefs are strong.
- Docker Compose is useful but optional for the first full-stack version.
- `.env`, runtime SQLite DBs, API keys, logs, and caches must never be committed.

## 2026-05-30 Frontend Parity Revision

The first Dash version is the visual and interaction reference for the React rewrite. The React app should not reduce the product to plain API lists; it should preserve the dashboard's signal intelligence shape while still proving a clean frontend/backend boundary.

### Goals

- Keep the essential navigation split small: Overview for the live dashboard, Stories for explorer/table workflows, Anomalies for triage workflows.
- Move the AI intelligence experience closer to the first Dash layout: brief headline and bullets, heading visibility, ranked themes, sentiment, keyword cloud, and contextual story panel.
- Restore the original keyword cloud behavior: clicking a keyword highlights it and swaps the right-side story panel to related stories; clicking it again resets to notable stories.
- Stop hard-cutting the AI briefing paragraph in the Overview. Prefer compact headline, metadata, and up to three bullets; put longer text in a controlled details area only when needed.
- Keep story/anomaly tables paginated and bounded so the page stays readable.
- Verify the final UI with browser screenshots at local desktop size.

### Implementation Steps

1. Extend `/api/ai/intelligence` so keyword bubbles include related-story counts and story drilldown data, using the first Dash keyword matching and engagement weighting logic.
2. Rework the React AI section into the two-column Dash-inspired layout instead of isolated full-width panels.
3. Make `KeywordBubbleCloud` interactive, larger, deterministic, and visually balanced.
4. Make `NotableStories` double as the selected keyword drilldown panel.
5. Reuse the same AI section in Overview so the main dashboard carries the AI argument, while keeping the dedicated AI page only if it still adds value.
6. Run unit tests, build the frontend, visually inspect the local app, audit ignored secrets/runtime files, then commit and push.
