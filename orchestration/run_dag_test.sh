#!/usr/bin/env bash
# Run the whole DAG once with `airflow dags test` (no scheduler, no web server) inside the
# container. Used with `docker run --network none`, so any task that tried to reach the
# network would fail. Called by `.\scripts\dev.ps1 airflow-test`.
set -euo pipefail
export AIRFLOW_HOME="${AIRFLOW_HOME:-/tmp/airflow_home}"
# no usage data (the DAG must not touch the network)
export AIRFLOW__COSMOS__ENABLE_TELEMETRY=False
export AIRFLOW__USAGE_DATA_COLLECTION__ENABLED=False
export SCARF_ANALYTICS=false
export DO_NOT_TRACK=1
export AIRFLOW__CORE__LOAD_EXAMPLES=False
mkdir -p "$AIRFLOW_HOME"
/opt/esg-lens-india/orchestration/prepare_work.sh
cd /opt/esg-lens-india
python -m pytest -q -p no:cacheprovider --noconftest tests/test_orchestration.py
airflow db migrate > /dev/null
airflow dags test esg_lens_pipeline
python /opt/esg-lens-india/orchestration/dag_run_summary.py
