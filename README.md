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
    dashboard/
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
