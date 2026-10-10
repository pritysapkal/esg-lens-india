# Orchestration (placeholder - week 13)

Planned: **Apache Airflow 3** with **Astronomer Cosmos** (renders the dbt project as an Airflow
task group, one task per model/test), run locally with the **Astro CLI**.

Prerequisites (not installed yet):

- Docker Desktop (WSL 2 backend) - required by the Astro CLI
- Astro CLI - `winget install -e --id Astronomer.Astro`

Planned DAG: a sensor watches `data/raw/xbrl_inbox/` (files are downloaded by hand, never by
Airflow - see `docs/adr/0002-manual-intake-nse-terms.md`), then
`discover -> intake -> todo -> parse_xbrl -> dbt (Cosmos: seed, run, test) -> elementary report`.

Nothing in this folder runs yet.
