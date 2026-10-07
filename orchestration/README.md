# Orchestration (placeholder - week 13)

Planned: **Apache Airflow 3** with **Astronomer Cosmos** (renders the dbt project as an Airflow
task group, one task per model/test), run locally with the **Astro CLI**.

Prerequisites (not installed yet):

- Docker Desktop (WSL 2 backend) - required by the Astro CLI
- Astro CLI - `winget install -e --id Astronomer.Astro`

Planned DAG: `discover -> download -> parse_xbrl -> dbt (Cosmos: seed, snapshot, run, test) -> elementary report`.

Nothing in this folder runs yet.
