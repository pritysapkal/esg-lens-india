# Linux / macOS / CI task runner. On Windows use:  .\scripts\dev.ps1 <target>
.PHONY: help setup lint test intake todo parse build app

VENV   ?= .venv
PY     ?= $(VENV)/bin/python
DBT    ?= $(abspath $(VENV))/bin/dbt
DBTARGS = --profiles-dir .

help:
	@echo "targets: setup lint test intake todo parse build app"

setup:
	python3.12 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt
	$(PY) -m pre_commit install
	cd dbt && $(DBT) deps $(DBTARGS)

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(PY) -m sqlfluff lint dbt/models

test:
	$(PY) -m pytest -q

# Files are downloaded from NSE by hand (docs/how_to_add_filings.md); nothing here fetches data.
intake:
	$(PY) -m ingestion.discover
	$(PY) -m ingestion.taxonomy
	$(PY) -m ingestion.intake

todo:
	$(PY) -m ingestion.todo

parse:
	$(PY) -m ingestion.parse_xbrl

build:
	cd dbt && $(DBT) deps $(DBTARGS) && $(DBT) build $(DBTARGS)

app:
	$(PY) -m streamlit run app/streamlit_app.py
