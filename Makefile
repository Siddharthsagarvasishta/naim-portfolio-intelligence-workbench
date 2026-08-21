PYTHON ?= $(firstword $(wildcard .venv/bin/python) $(shell command -v python3.12 2>/dev/null) $(shell command -v python3 2>/dev/null))
PYTHONPATH := src
PROFILE ?= default
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
FRONTEND_HOST ?= localhost
FRONTEND_PORT ?= 3000
NO_OPEN ?= 0
LOG_LINES ?= 80
AUTH_USER ?= portfolio.analyst
AUTH_ROLE ?= Portfolio Analyst

.PHONY: check-python doctor setup generate-data validate-data build-marts train-models test \
        test-backend test-frontend lint run run-api run-web export-excel \
        export-powerbi export-all demo benchmark clean-generated brand-check db-upgrade \
        db-status db-repair auth-setup-demo start stop restart status open logs \
        naim-start naim-stop naim-restart run-docker self-test typecheck demo-60 \
        export-powerpoint export-tableau export-sas export-linkedin release-check

check-python:
	@test -n "$(PYTHON)" || (echo "Python 3.12+ was not found. Install it, then rerun make doctor." >&2; exit 1)
	@$(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else "Python 3.12+ is required; selected: " + sys.version.split()[0])'

doctor: check-python
	$(PYTHON) scripts/check_environment.py

setup: doctor
	@test -x .venv/bin/python || $(PYTHON) -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[analytics,dev]"
	npm ci --ignore-scripts --no-audit --no-fund

generate-data:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m naim_risk.cli pipeline --profile $(PROFILE)

validate-data:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m naim_risk.cli pipeline --profile $(PROFILE)

build-marts:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m naim_risk.cli pipeline --profile $(PROFILE)

train-models:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/validate_model_registry.py

test: test-backend test-frontend

test-backend:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest

test-frontend:
	npm test

lint:
	$(PYTHON) scripts/check_public_brand.py
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m ruff check src apps tests scripts
	npm run lint
	npm run typecheck

run: start

run-docker:
	docker compose up --build

run-api:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m naim_risk.cli api --profile $(PROFILE) --data-root ./data --host $(API_HOST) --port $(API_PORT)

db-upgrade:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m naim_risk.cli db upgrade

db-status:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m naim_risk.cli db status

db-repair:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m naim_risk.cli db repair

start:
	PYTHONPATH=$(PYTHONPATH) PROFILE=$(PROFILE) API_HOST=$(API_HOST) API_PORT=$(API_PORT) FRONTEND_HOST=$(FRONTEND_HOST) FRONTEND_PORT=$(FRONTEND_PORT) NAIM_NO_OPEN=$(NO_OPEN) $(PYTHON) scripts/local_lifecycle.py start

stop:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/local_lifecycle.py stop

restart:
	PYTHONPATH=$(PYTHONPATH) PROFILE=$(PROFILE) API_HOST=$(API_HOST) API_PORT=$(API_PORT) FRONTEND_HOST=$(FRONTEND_HOST) FRONTEND_PORT=$(FRONTEND_PORT) NAIM_NO_OPEN=$(NO_OPEN) $(PYTHON) scripts/local_lifecycle.py restart

status:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/local_lifecycle.py status

open:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/local_lifecycle.py open

logs:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/local_lifecycle.py logs --lines $(LOG_LINES)

naim-start: start

naim-stop: stop

naim-restart: restart

auth-setup-demo:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m naim_risk.cli auth setup-demo --username "$(AUTH_USER)" --role "$(AUTH_ROLE)"

run-web:
	npm run dev

typecheck:
	npm run typecheck

self-test: check-python db-status
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/unit/test_database_migrations.py tests/unit/test_cli_auth_db.py tests/unit/test_local_lifecycle.py tests/integration/test_workflow_persistence.py
	npm run contracts:check

export-excel:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/export_demo.py --format excel

export-powerbi:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/export_demo.py --format powerbi

export-all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/export_demo.py --format all

demo:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_demo.py --profile $(PROFILE)

demo-60:
	@test -f scripts/run_60_second_demo.py || (echo "The governed 60-second demo runner is not implemented yet; refusing to substitute a different demo." >&2; exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/run_60_second_demo.py --profile $(PROFILE)

export-powerpoint:
	@test -f scripts/export_presentation.py || (echo "The standalone PowerPoint exporter is not implemented yet; use the live Presentations workflow." >&2; exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/export_presentation.py --profile $(PROFILE)

export-tableau:
	@test -f exports/validation/interop_evidence_snapshot.json || (echo "Canonical interop evidence is missing; run the governed interop export first." >&2; exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/interop_flatten_exports.py

export-sas:
	@test -f exports/validation/interop_evidence_snapshot.json || (echo "Canonical interop evidence is missing; run the governed interop export first." >&2; exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/interop_flatten_exports.py

export-linkedin:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/build_share_site.py

release-check: self-test typecheck brand-check
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/reconcile_release_artifacts.py

benchmark:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/benchmark_backend.py --profile $(PROFILE)

clean-generated:
	$(PYTHON) scripts/clean_generated.py

brand-check:
	$(PYTHON) scripts/check_public_brand.py
