# Linux / macOS / CI task runner. On Windows use:  .\scripts\dev.ps1 <target>
.PHONY: help setup lint test intake todo parse load build dbt-build dbt-docs app

VENV   ?= .venv
PY     ?= $(VENV)/bin/python
DBT    ?= $(abspath $(VENV))/bin/dbt
DBTARGS = --profiles-dir .
# Absolute data path: dbt staging views read the files at query time (see dbt/models/staging).
export ESG_DATA_DIR ?= $(abspath data)

help:
	@echo "targets: setup lint test intake todo parse load dbt-build dbt-docs app"

setup:
	python3.12 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt
	$(PY) -m pre_commit install
	cd dbt && $(DBT) deps $(DBTARGS)

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	$(PY) -m sqlfluff lint dbt/models dbt/tests dbt/analyses dbt/macros

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

load:
	$(PY) -m ingestion.load_raw

build dbt-build:
	cd dbt && $(DBT) deps $(DBTARGS) && $(DBT) build $(DBTARGS)

dbt-docs:
	cd dbt && $(DBT) docs generate $(DBTARGS) && $(DBT) docs serve $(DBTARGS)

app:
	$(PY) -m streamlit run app/streamlit_app.py
