"""Airflow 3 DAG `esg_lens_pipeline`: the whole ESG Lens India pipeline, triggered by hand.

Built from orchestration/pipeline.py, which lists every task, its group, its command and its
order. dbt runs through Astronomer Cosmos operators (seed, run and test in their own task
groups). Rules:

- manual trigger only (schedule=None): new filings arrive when a person saves them;
- nothing downloads: the pipeline reads the inbox, it never fetches (ADR 0002);
- fail fast: retries 0, every task needs the one before it to succeed, and dbt stops at the
  first failing model or test (--fail-fast).

Run it: docs/orchestration.md (Docker, `.\\scripts\\dev.ps1 airflow`).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, TaskGroup
from cosmos import ProfileConfig
from cosmos.operators.local import (
    DbtRunLocalOperator,
    DbtSeedLocalOperator,
    DbtTestLocalOperator,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the repository root

from orchestration.pipeline import DAG_ID, Settings, Step, steps  # noqa: E402

SETTINGS = Settings.from_env()
PROFILE = ProfileConfig(
    profile_name="esg_lens",
    target_name="dev",
    profiles_yml_filepath=Path(SETTINGS.repo) / "dbt" / "profiles.yml",
)
DBT_OPERATORS = {
    "seed": DbtSeedLocalOperator,
    "run": DbtRunLocalOperator,
    "test": DbtTestLocalOperator,
}


def _operator(step: Step):
    env = SETTINGS.env()
    if step.kind == "dbt":
        return DBT_OPERATORS[step.dbt_command](
            task_id=step.task_id,
            doc_md=step.description,
            project_dir=str(Path(SETTINGS.repo) / "dbt"),
            profile_config=PROFILE,
            dbt_executable_path=SETTINGS.dbt,
            install_deps=False,  # dbt_packages/ is in the repository: no download
            select=list(step.select),
            dbt_cmd_flags=list(step.dbt_flags),
            emit_datasets=False,  # no OpenLineage events
            env=env,
            append_env=True,
        )
    return BashOperator(
        task_id=step.task_id,
        doc_md=step.description,
        bash_command=step.command,
        env=env,
        append_env=True,
    )


with DAG(
    dag_id=DAG_ID,
    description="ESG Lens India: inbox -> warehouse -> analysis -> public exports (manual only)",
    schedule=None,
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    fail_fast=True,
    default_args={"retries": 0, "owner": "esg-lens-india"},
    tags=["esg-lens-india", "manual"],
    doc_md=__doc__,
) as dag:
    groups: dict[str, TaskGroup] = {}
    previous = None
    for step in steps(SETTINGS):
        if step.group and step.group not in groups:
            groups[step.group] = TaskGroup(group_id=step.group)
        if step.group:
            with groups[step.group]:
                task = _operator(step)
        else:
            task = _operator(step)
        if previous is not None:
            previous >> task
        previous = task


if __name__ == "__main__":
    dag.test()
