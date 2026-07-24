PYTHON ?= python3
VENV := .venv
WEB_DIR := apps/web
WORKER_DIR := apps/worker

.PHONY: install web-install worker-install dev-web fetch-once check-inventory poll-once run-worker rebuild-manifests serve-files lint format format-check typecheck test build check clean

install: web-install worker-install

web-install:
	npm --prefix $(WEB_DIR) ci

worker-install: $(VENV)/bin/python
	$(VENV)/bin/python -m pip install --requirement $(WORKER_DIR)/requirements-dev.lock
	$(VENV)/bin/python -m pip install --force-reinstall --no-deps --no-build-isolation $(WORKER_DIR)

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)

dev-web:
	npm --prefix $(WEB_DIR) run dev

fetch-once:
	$(VENV)/bin/aemet-radar fetch-once

check-inventory:
	$(VENV)/bin/aemet-radar check-inventory

poll-once:
	$(VENV)/bin/aemet-radar run --cycles 1

run-worker:
	$(VENV)/bin/aemet-radar run

rebuild-manifests:
	$(VENV)/bin/aemet-radar rebuild-manifests

serve-files:
	$(VENV)/bin/aemet-radar serve-files

lint:
	npm --prefix $(WEB_DIR) run lint
	$(VENV)/bin/ruff check .

format:
	npm --prefix $(WEB_DIR) run format
	$(VENV)/bin/ruff format .

format-check:
	npm --prefix $(WEB_DIR) run format:check
	$(VENV)/bin/ruff format --check .

typecheck:
	npm --prefix $(WEB_DIR) run typecheck
	$(VENV)/bin/mypy $(WORKER_DIR)/src $(WORKER_DIR)/tests

test:
	npm --prefix $(WEB_DIR) test
	$(VENV)/bin/pytest

build:
	npm --prefix $(WEB_DIR) run build

check: lint format-check typecheck test build

clean:
	npm --prefix $(WEB_DIR) run clean
