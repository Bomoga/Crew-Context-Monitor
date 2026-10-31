# Crew Context Monitor dev tasks. On Windows, run with GNU Make from
# C:\msys64\usr\bin on PATH (Git Bash).
SHELL := bash
PYTHON ?= python
VENV := .venv
VBIN := $(shell if [ -d $(VENV)/Scripts ]; then echo $(VENV)/Scripts; else echo $(VENV)/bin; fi)

DASH := dashboard
SCENARIO ?= scrubber_failure
SPEED ?= 60

.PHONY: setup lint test contracts types dashboard-check check sim-eval build serve-mock dashboard-dev e2e check-all clean

setup:
	$(PYTHON) -m venv $(VENV)
	$$(if [ -d $(VENV)/Scripts ]; then echo $(VENV)/Scripts; else echo $(VENV)/bin; fi)/python -m pip install -q --upgrade pip
	$$(if [ -d $(VENV)/Scripts ]; then echo $(VENV)/Scripts; else echo $(VENV)/bin; fi)/python -m pip install -q -e "sim[dev]"
	@if [ -f $(DASH)/package.json ]; then cd $(DASH) && npm ci; fi

lint:
	cd sim && ../$(VBIN)/ruff check src tests && ../$(VBIN)/ruff format --check src tests
	cd sim && ../$(VBIN)/mypy

test:
	cd sim && ../$(VBIN)/python -m pytest -q

contracts:
	$(VBIN)/python -m ccm_sim.contracts

types:
	cd $(DASH) && npm run gen:types

dashboard-check:
	@if [ -f $(DASH)/package.json ]; then cd $(DASH) && npm run lint && npm run typecheck && npm test && npm run check:types-fresh; fi

check: contracts lint test dashboard-check

sim-eval:
	$(VBIN)/ccm-sim scenarios check
	cd sim && ../$(VBIN)/python -m pytest -q -m '' tests/test_scenario_*.py tests/test_sim_eval.py tests/test_quiet_week.py tests/test_mockapi.py tests/test_mockapi_copy.py

build:
	cd $(DASH) && npm run build

serve-mock: build
	$(VBIN)/ccm-sim serve-mock --scenario $(SCENARIO) --speed $(SPEED) --port 8000

dashboard-dev:
	cd $(DASH) && npm run dev

check-all: check sim-eval build e2e

e2e:
	cd $(DASH) && npm run build && npx playwright test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache sim/.pytest_cache sim/.mypy_cache sim/.ruff_cache
