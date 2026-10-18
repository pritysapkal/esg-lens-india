# Orchestration: the Airflow pipeline

Week 13. The whole pipeline - from the files a person saved to the public exports - as one
Airflow DAG. Code in [`orchestration/`](../orchestration/).

## Setup used

- **Airflow 3.3.2** (official image `apache/airflow:3.3.2-python3.12`, run as `airflow standalone`)
  with **Astronomer Cosmos 1.15.1** for the dbt tasks, in **Docker Desktop** (WSL 2). Airflow does
  not run natively on Windows, so Docker is the only supported way here; the Astro CLI is not
  needed.
- **Two Python environments in one image.** Airflow's own (Airflow, Cosmos, pytest), and
  `/opt/esg-venv` with the project's pinned `requirements.txt`, which every task runs with.
  Airflow's dependency pins never touch the project's.
- **The repository is mounted read-only.** The pipeline writes only to a Docker volume
  (`esg_work`): its own copy of `data/raw` (made by `prepare_work.sh` from the host folder, never
  overwriting), its own warehouse, its own exports. A run in Docker cannot change the repository,
  the host's data or the warehouse that `dev.ps1` builds.

## The DAG `esg_lens_pipeline`

- **Manual trigger only** (`schedule=None`, no catch-up, one run at a time). New filings arrive
  when a person saves them (NSE terms - [ADR 0002](adr/0002-manual-intake-nse-terms.md)).
- **Nothing downloads.** `check_inbox` only counts the files in `data/raw/xbrl_inbox`; intake
  files them. dbt packages come from the repository (`install_deps=False`, never `dbt deps`).
  Airflow's and Cosmos's usage statistics are switched off, for the Airflow processes and every
  task.
- **Fail fast.** Retries 0 on every task, each task needs the one before to succeed, the DAG
  stops all remaining tasks when one fails (`fail_fast=True`), and every dbt call stops at the
  first failing model or test (`--fail-fast`).

| # | Task | Group | What it does |
|---|---|---|---|
| 1 | `check_inbox` | - | Count the files a person saved into data/raw/xbrl_inbox. Never downloads. |
| 2 | `discover` | intake | Read the hand-saved NSE listing CSVs into one table. |
| 3 | `taxonomy` | intake | Scan the SEBI taxonomy packages on disk. |
| 4 | `file_inbox` | intake | Hash, match and file the inbox XBRL files (never overwrites). |
| 5 | `parse` | - | Parse every filed XBRL instance to Parquet. |
| 6 | `load` | - | Load the Parquet tables into the DuckDB warehouse. |
| 7 | `seed` | dbt_seed | dbt seed: the rule tables. |
| 8 | `run_staging` | dbt_run | dbt run: staging models. |
| 9 | `run_warehouse` | dbt_run | dbt run: intermediate, gold, public and semantic-layer models. |
| 10 | `run_elementary` | dbt_run | dbt run: elementary monitoring models. |
| 11 | `test_unit` | dbt_test | dbt test: unit tests. |
| 12 | `test_data` | dbt_test | dbt test: all data tests (public safety included); stops at the first failure. |
| 13 | `semantic_validate` | - | Semantic layer in sync with the catalogue; dbt parse; mf validate-configs. |
| 14 | `analysis` | - | The 12 business questions (Week 10). |
| 15 | `stats` | - | The five statistics studies (Week 11). |
| 16 | `bi_export` | - | Parquet exports and workbooks; the committed Power BI projects must still match. |
| 17 | `public_safety_checks` | - | Only rpt_public_* files in exports/public, no raw-value column, no statistic below 5. |

The list lives in [`orchestration/pipeline.py`](../orchestration/pipeline.py) as plain Python
(no Airflow import); the DAG file only turns it into Airflow and Cosmos operators. So the order
and commands are tested on any machine, and the documented pipeline and the one Airflow runs
cannot drift apart.

**Why dbt is three task groups of whole-folder calls, not one task per model.** Cosmos can render
every dbt model as its own Airflow task. Here each dbt call parses the project first (about 20
seconds, because partial parsing is off - [semantic_layer.md](semantic_layer.md)), so ~85 model
tasks would spend half an hour parsing. And the folders reference each other: intermediate models
read gold dimensions, `rpt_public_group_metrics` reads the semantic views. So intermediate, gold
and semantic models run in one call (`run_warehouse`), where dbt orders them itself. The first
full run caught exactly this: a split by folder failed in `run_intermediate`.

## Run it

```powershell
.\scripts\dev.ps1 airflow
```

Builds the image (first time: several minutes) and starts Airflow on http://localhost:8080 (user
`admin`; the password is printed by the command the task shows). The DAG starts paused: unpause
it and press *Trigger*. Stop with `docker compose -f orchestration\docker-compose.yml down`.
If port 8080 is taken, set `$env:AIRFLOW_PORT = '8085'` first (checked on this laptop, where
8080 was in use: Airflow 3.3.2 answered on 8085 with the DAG listed, paused, no schedule).

```powershell
.\scripts\dev.ps1 airflow-test
```

Runs, in a container with **the network switched off** (`docker run --network none`): the
orchestration tests with Airflow installed, then the whole DAG once with `airflow dags test`, then
a summary that fails unless every task succeeded. Any task that tried to reach the network would
fail here.

## How it is tested

| Where | What |
|---|---|
| `tests/test_orchestration.py`, any machine (Windows, CI) | the task order; dbt as seed / run / test groups with `--fail-fast`; no command contains curl, wget, pip, git, `dbt deps` or a URL; no Python file a task runs imports a network library; every task writes only under the work folder; the DAG file sets no schedule, no catch-up and retries 0; telemetry switched off for tasks, compose and the test script |
| the same file, where Airflow is installed (Docker image, CI job `airflow-dag`) | the DAG imports without errors; it is manual only; its task order and dependencies equal the spec; every task has retries 0 and `all_success`; the dbt tasks are Cosmos operators that never install packages; Cosmos telemetry is off |
| `.\scripts\dev.ps1 airflow-test` | one full run of all 17 tasks with the network off |

### The full run with the network off (2026-10-18)

`docker run --network none`, on a copy of the 196 real filings. 13 orchestration tests passed
inside the container, then all 17 tasks succeeded in 18 minutes; no usage-statistics call was
attempted. dbt: 0 warnings, 0 errors in every call.

| Task | Result | Time |
|---|---|---|
| `check_inbox`, `intake.*` (3) | success | 22 s |
| `parse` (196 filings, 0 failed) | success | 91 s |
| `load` | success | 8 s |
| `dbt_seed.seed` (20 seeds) | success | 66 s |
| `dbt_run.run_staging` (10 models) | success | 68 s |
| `dbt_run.run_warehouse` (47 models) | success | 89 s |
| `dbt_run.run_elementary` (32 models) | success | 116 s |
| `dbt_test.test_unit` (15 unit tests) | success | 94 s |
| `dbt_test.test_data` (448 data tests) | success | 227 s |
| `semantic_validate` | success | 203 s |
| `analysis` (24 results) | success | 4 s |
| `stats` | success | 46 s |
| `bi_export` (+ Power BI files still match) | success | 23 s |
| `public_safety_checks` | success | 4 s |

Slower than `dev.ps1` on Windows (about 3 minutes for the dbt build there) because every dbt call
parses the project again and the repository is read through a Docker bind mount.

The first runs were worth it: they found a work folder Docker created as root, the folder split
of the dbt models (see above), and that **Cosmos sends usage statistics by default** - with the
network off the call failed silently, but "no task touches the network" has to be true, not just
blocked. Telemetry is now switched off and tested.

## Limitations

- **Docker only**, and on its own copy of the data. The DAG shows that the pipeline runs end to
  end from the inbox; daily work on the laptop still uses `dev.ps1`. To make Airflow the main
  runner, mount `data/` read-write and point `ESG_WORK` at it (the warehouse built inside the
  container would then hold Linux paths in its staging views; rebuild with `dev.ps1 dbt-build`
  before using it on Windows).
- **No sensor.** A sensor that waits for new files would only make sense on a schedule; the DAG
  is manual on purpose. `check_inbox` reports what is new.
- **Standalone mode** (one container, SQLite metadata database) is for one person on a laptop,
  not a shared server.
- The CI job installs Airflow and checks the DAG; the full run needs the real filings and runs
  locally.
