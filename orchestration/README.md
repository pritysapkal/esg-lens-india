# Orchestration (Week 13)

Airflow 3.3.2 with Astronomer Cosmos 1.15, in Docker. One DAG, `esg_lens_pipeline`, triggered by
hand only; it never downloads anything. Full description: [docs/orchestration.md](../docs/orchestration.md).

| File | What it is |
|---|---|
| `pipeline.py` | every task, its group, command and order - plain Python, no Airflow import |
| `dags/esg_lens_pipeline.py` | the DAG, built from `pipeline.py` (Cosmos operators for dbt) |
| `check_inbox.py` | first task: counts what a person saved into the inbox |
| `Dockerfile`, `docker-compose.yml` | Airflow standalone + the project's own environment |
| `prepare_work.sh` | copies the host's `data/raw` (read-only) into the container's work volume |
| `run_dag_test.sh`, `dag_run_summary.py` | one full run with `airflow dags test` (used with `--network none`) |

```powershell
.\scripts\dev.ps1 airflow        # UI on http://localhost:8080
.\scripts\dev.ps1 airflow-test   # tests + one full run, network switched off
```
