# ESG Lens India - Airflow 3 with Astronomer Cosmos (Week 12-13). Build from the repository root:
#   docker compose -f orchestration/docker-compose.yml build
# Two Python environments, kept apart on purpose:
#   - Airflow's own (Airflow, Cosmos, pytest): schedules and renders the tasks;
#   - /opt/esg-venv: the project's pinned requirements.txt (dbt, DuckDB, pandas, scipy, ...),
#     which every task runs with. Airflow's dependencies never touch the project pins.
FROM apache/airflow:3.3.2-python3.12

USER root
# esg_work exists in the image, owned by airflow, so a new named volume inherits that owner
RUN python -m venv /opt/esg-venv && mkdir -p /opt/airflow/esg_work \
    && chown -R airflow: /opt/esg-venv /opt/airflow/esg_work
USER airflow

COPY requirements.txt /tmp/esg-requirements.txt
RUN /opt/esg-venv/bin/pip install --no-cache-dir -r /tmp/esg-requirements.txt

RUN pip install --no-cache-dir \
    "apache-airflow==3.3.2" \
    "astronomer-cosmos==1.15.1" \
    "pytest==9.1.1"
