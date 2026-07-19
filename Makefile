PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
UVICORN ?= .venv/bin/uvicorn
PYTEST ?= .venv/bin/pytest

.PHONY: install api worker worker-once dash frontend test docker-up docker-down

install:
	python3 -m venv .venv
	$(PIP) install -r requirements.txt

api:
	$(UVICORN) sonar.api.main:app --host 127.0.0.1 --port 8060

worker:
	$(PYTHON) -m sonar.worker

worker-once:
	$(PYTHON) -m sonar.worker --once

dash:
	$(PYTHON) app.py

frontend:
	cd frontend && npm run dev

test:
	PYTHONPATH=. $(PYTEST)

docker-up:
	docker compose up --build

docker-down:
	docker compose down
