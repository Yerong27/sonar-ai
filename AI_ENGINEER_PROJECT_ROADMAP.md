# Sonar AI Engineer Project Roadmap

## Goal

Upgrade Sonar from a local monitoring dashboard into an AI engineering portfolio project:

> An AI-powered trend intelligence system that monitors Hacker News, detects abnormal technology signal spikes, validates them against external news, and generates grounded incident briefs using LLMs and retrieval-augmented evidence.

The goal is not to add AI branding. The goal is to show practical AI engineering skills: data pipelines, model integration, retrieval, structured outputs, evaluation, observability, and product delivery.

## Current Strengths

- Local-first Python project with a working Dash dashboard.
- Hacker News ingestion through the official Firebase API.
- SQLite storage for stories, metrics, anomalies, news matches, explanations, and monitoring summaries.
- Statistical anomaly detection with z-score and rolling baselines.
- Optional NewsAPI validation for detected anomalies.
- Optional Gemini explanations with structured JSON output.
- Clear end-to-end data flow from ingestion to dashboard display.

## Current Gaps For AI Engineer Applications

- AI is currently mostly an explanation layer after anomaly detection.
- No retrieval-augmented generation over historical stories, news, or prior anomaly briefs.
- No AI chat or analyst query interface.
- Limited evaluation of model outputs.
- No stored prompt/model/raw-response audit trail.
- No provider abstraction for switching between Gemini, OpenAI, or other models.
- UI is a Python Dash dashboard, not a modern full-stack web app.
- Deployment story is local-only and not yet containerized.

## Target Project Name

**Sonar AI: Tech Signal Intelligence Agent**

## Core Upgrade: AI Evidence Brief Generator

Build a feature that turns each anomaly into a grounded AI brief.

Pipeline:

1. Detect an anomaly from Hacker News metrics.
2. Collect related Hacker News stories.
3. Collect related external news articles.
4. Generate embeddings for stories, news headlines, and historical anomaly summaries.
5. Retrieve the most relevant evidence.
6. Ask an LLM to generate a structured JSON brief.
7. Save the prompt input, raw response, parsed JSON, model name, evidence IDs, confidence, and failure state.
8. Display the AI brief and evidence links in the dashboard.

Expected JSON output:

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
  "bullet_insights": [
    "What changed.",
    "Why it likely changed.",
    "Why it matters."
  ],
  "summary": "string"
}
```

## Recommended Enhancements

### 1. Add RAG

Add a retrieval layer over:

- Hacker News story titles and metadata.
- NewsAPI headlines and snippets.
- Historical anomalies.
- Previous Gemini/OpenAI briefs.

Suggested options:

- Lightweight: SQLite table with embedding vectors serialized as JSON.
- Better portfolio signal: LanceDB or Chroma.

Recommended schema additions:

- `documents`
- `document_embeddings`
- `ai_runs`
- `brief_evidence`

This shows that the system grounds model output in retrieved evidence instead of asking the model to guess.

### 2. Add AI Provider Abstraction

Create a small provider interface:

```python
class AIProvider:
    def generate_json(self, prompt: str, schema_name: str) -> dict:
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...
```

Implement:

- `GeminiProvider`
- `OpenAIProvider`

Add:

- timeout handling
- retry policy
- JSON repair
- fallback provider support
- model name stored with every AI run

This demonstrates model integration rather than one-off API usage.

### 3. Add AI Analyst Chat

Add a chat interface that answers questions using the local Sonar database and retrieval layer.

Example questions:

- "What AI-related trends are spiking today?"
- "Which anomalies are supported by external news?"
- "Summarize the top 5 technology events in the last 24 hours."
- "Why did this Hacker News story spike?"
- "Compare today's AI trends against yesterday."

The chat should:

- retrieve evidence first
- cite story IDs and article links
- refuse to answer when evidence is weak
- store conversation history locally

### 4. Add Evaluation

Create a small evaluation set under:

```text
tests/fixtures/
```

Test cases should cover:

- normal monitoring snapshot
- real anomaly with external news alignment
- anomaly with no external confirmation
- misleading high-score story
- multiple competing topics
- malformed model output

Automated checks:

- returned JSON is valid
- required keys are present
- confidence is within 0.0 to 1.0
- evidence list is not empty when a grounded brief is produced
- unsupported claims are not made when no evidence exists
- fallback behavior works when the model fails

This is one of the strongest signals for AI Engineer applications.

### 5. Add FastAPI Backend

Keep the current collector and database logic, but expose APIs:

```text
GET  /api/stories
GET  /api/anomalies
GET  /api/briefs
POST /api/chat
POST /api/run-once
GET  /api/status
```

This separates data/AI logic from the UI and makes the project look more like a production service.

### 6. Add React/Vite Frontend

Dash is fine for internal dashboards, but a React frontend will look stronger for a portfolio.

Suggested pages:

- Overview dashboard
- Story explorer
- Anomaly timeline
- AI briefs
- Analyst chat
- System status

The current Dash dashboard can remain as a legacy/internal interface while React becomes the main demo UI.

### 7. Add Docker Compose

Add a local deployment story:

```text
docker-compose.yml
services:
  api
  frontend
  worker
```

Optional later:

- Postgres instead of SQLite
- Redis queue for background collection

For a portfolio project, Docker Compose is enough to show deployability.

### 8. Improve README And Presentation

Add:

- architecture diagram
- screenshots
- demo GIF
- AI brief example
- setup instructions
- `.env.example`
- limitations section
- evaluation section
- roadmap section

Suggested README positioning:

> Sonar AI is a local-first AI trend intelligence system. It monitors Hacker News, detects unusual technology signal spikes, validates them against external news, and generates evidence-grounded incident briefs using LLMs and retrieval.

## Suggested Milestones

### Milestone 1: Portfolio Cleanup

- Add `.env.example`.
- Add GitHub-friendly README.
- Add screenshots.
- Add architecture diagram.
- Ensure no real API keys are committed.

### Milestone 2: AI Evidence Briefs

- Add evidence retrieval.
- Store evidence IDs with each brief.
- Store prompt, model, raw response, and parsed response.
- Show evidence in dashboard.

### Milestone 3: AI Evaluation

- Add fixtures.
- Add pytest tests for JSON validity and evidence grounding.
- Add model failure tests.

### Milestone 4: Full-Stack Upgrade

- Add FastAPI backend.
- Add React/Vite frontend.
- Keep the collector as a background service.

### Milestone 5: Deployment

- Add Docker Compose.
- Add setup docs.
- Optional: deploy frontend/backend to a public URL.

## What This Demonstrates To Recruiters

- LLM integration with structured outputs.
- RAG and evidence grounding.
- Data ingestion and processing.
- Anomaly detection.
- Prompt and response observability.
- Model failure handling.
- API design.
- Frontend productization.
- Testing and evaluation.
- Local deployment and environment management.

## What To Avoid

- Do not add "AI" features that are only UI labels.
- Do not expose API keys in frontend code.
- Do not let the model generate claims without evidence.
- Do not make the project depend on a paid API for every test.
- Do not replace the existing data pipeline with a generic chatbot.

## Best Short-Term Next Step

Build the **AI Evidence Brief Generator** first.

It extends the existing Sonar architecture naturally, makes the AI connection stronger, and gives the project a clear AI Engineer story without throwing away the current work.
