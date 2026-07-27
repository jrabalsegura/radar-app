PYTHON ?= python3
VENV := .venv
WEB_DIR := apps/web
WORKER_DIR := apps/worker
LIVE_PREVIEW_DIR := tmp/live-preview
LIVE_PREVIEW_PORT ?= 4173

.PHONY: install web-install worker-install dev-web prepare-live-preview preview-live fetch-once check-inventory poll-once run-worker rebuild-manifests serve-files analyze-reflectivity validate-radar validate-national georeference-murcia build-reflectivity-mask build-radar-masks lint format format-check typecheck test test-e2e build check clean

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

prepare-live-preview: build
	@test -f $(WEB_DIR)/dist/index.html || (echo "El build no contiene dist/index.html" && exit 2)
	@test -f data/radar/index.json || (echo "Falta data/radar/index.json; ejecuta make poll-once primero" && exit 2)
	@test -f data/status/health.json || (echo "Falta data/status/health.json; ejecuta make poll-once primero" && exit 2)
	mkdir -p $(LIVE_PREVIEW_DIR)
	rsync -a --delete $(WEB_DIR)/dist/ $(LIVE_PREVIEW_DIR)/
	rm -rf $(LIVE_PREVIEW_DIR)/radar $(LIVE_PREVIEW_DIR)/status
	ln -s ../../data/radar $(LIVE_PREVIEW_DIR)/radar
	ln -s ../../data/status $(LIVE_PREVIEW_DIR)/status
	@test -f $(LIVE_PREVIEW_DIR)/index.html
	@test -f $(LIVE_PREVIEW_DIR)/radar/index.json
	@test -f $(LIVE_PREVIEW_DIR)/status/health.json

preview-live: prepare-live-preview
	$(PYTHON) -m http.server $(LIVE_PREVIEW_PORT) --bind 127.0.0.1 --directory $(LIVE_PREVIEW_DIR)

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

analyze-reflectivity:
	@test -n "$(SAMPLE)" || (echo "Uso: make analyze-reflectivity SAMPLE=ruta/al/original.gif" && exit 2)
	$(VENV)/bin/aemet-radar analyze-reflectivity "$(SAMPLE)"

validate-radar:
	@test -n "$(PRODUCT)" || (echo "Uso: make validate-radar PRODUCT=regional-am SAMPLE=ruta/al/original.gif" && exit 2)
	@test -n "$(SAMPLE)" || (echo "Uso: make validate-radar PRODUCT=regional-am SAMPLE=ruta/al/original.gif" && exit 2)
	$(VENV)/bin/aemet-radar validate-radar --product "$(PRODUCT)" "$(SAMPLE)"

validate-national:
	@test -n "$(SAMPLE)" || (echo "Uso: make validate-national SAMPLE=ruta/al/original.png" && exit 2)
	$(VENV)/bin/aemet-radar validate-national "$(SAMPLE)"

georeference-murcia:
	@test -n "$(OVERLAY)" || (echo "Uso: make georeference-murcia OVERLAY=ruta/al/overlay.png" && exit 2)
	$(VENV)/bin/aemet-radar georeference-murcia "$(OVERLAY)"

build-reflectivity-mask:
	@test -n "$(SAMPLES)" || (echo "Uso: make build-reflectivity-mask SAMPLES='muestra1.gif muestra2.gif muestra3.gif'" && exit 2)
	$(VENV)/bin/aemet-radar build-reflectivity-mask $(SAMPLES)

build-radar-masks:
	$(VENV)/bin/aemet-radar build-radar-masks \
		--sample-root data/phase6-samples \
		--sample-root data/mask-samples \
		--sample-root data/manual-phase2

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

test-e2e:
	npm --prefix $(WEB_DIR) run test:e2e

build:
	npm --prefix $(WEB_DIR) run build

check: lint format-check typecheck test build

clean:
	npm --prefix $(WEB_DIR) run clean
