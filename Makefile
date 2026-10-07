# Linux / macOS / CI task runner. On Windows use:  .\scripts\dev.ps1 <target>
.PHONY: help setup lint test download parse build app

VENV   ?= .venv
PY     ?= $(VENV)/bin/python
DBT    ?= $(abspath $(VENV))/bin/dbt
DBTARGS = --profiles-dir .

help:
	@echo "targets: setup lint test download parse build app"

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

download:
	$(PY) -m ingestion.discover
	$(PY) -m ingestion.download

parse:
	$(PY) -m ingestion.parse_xbrl

build:
	cd dbt && $(DBT) deps $(DBTARGS) && $(DBT) build $(DBTARGS)

app:
	$(PY) -m streamlit run app/streamlit_app.py
