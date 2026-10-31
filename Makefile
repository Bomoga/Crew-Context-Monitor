# Crew Context Monitor dev tasks. On Windows, run with GNU Make from
# C:\msys64\usr\bin on PATH (Git Bash).
SHELL := bash
PYTHON ?= python
VENV := .venv
VBIN := $(shell if [ -d $(VENV)/Scripts ]; then echo $(VENV)/Scripts; else echo $(VENV)/bin; fi)

.PHONY: setup lint test contracts check sim-eval clean

setup:
	$(PYTHON) -m venv $(VENV)
	$$(if [ -d $(VENV)/Scripts ]; then echo $(VENV)/Scripts; else echo $(VENV)/bin; fi)/python -m pip install -q --upgrade pip
	$$(if [ -d $(VENV)/Scripts ]; then echo $(VENV)/Scripts; else echo $(VENV)/bin; fi)/python -m pip install -q -e "sim[dev]"

lint:
	cd sim && ../$(VBIN)/ruff check src tests && ../$(VBIN)/ruff format --check src tests
	cd sim && ../$(VBIN)/mypy

test:
	cd sim && ../$(VBIN)/python -m pytest -q

contracts:
	$(VBIN)/python -m ccm_sim.contracts

check: contracts lint test

sim-eval:
	$(VBIN)/ccm-sim scenarios check
	cd sim && ../$(VBIN)/python -m pytest -q -m '' tests/test_scenario_*.py tests/test_sim_eval.py tests/test_quiet_week.py tests/test_mockapi.py tests/test_mockapi_copy.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache sim/.pytest_cache sim/.mypy_cache sim/.ruff_cache
