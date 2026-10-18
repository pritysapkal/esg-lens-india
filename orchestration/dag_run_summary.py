"""Print every task state of the latest esg_lens_pipeline run; exit 1 unless all succeeded."""

from __future__ import annotations

import sys

from airflow.models import DagRun, TaskInstance
from airflow.utils.session import create_session

with create_session() as session:
    run = (
        session.query(DagRun)
        .filter(DagRun.dag_id == "esg_lens_pipeline")
        .order_by(DagRun.id.desc())
        .first()
    )
    if run is None:
        sys.exit("no run of esg_lens_pipeline found")
    tasks = session.query(TaskInstance).filter(TaskInstance.run_id == run.run_id).all()
    for task in sorted(tasks, key=lambda t: (t.start_date is None, t.start_date)):
        took = (task.end_date - task.start_date).total_seconds() if task.end_date else 0
        print(f"{task.task_id:<32} {task.state!s:<10} {took:7.1f}s")
    failed = [t.task_id for t in tasks if t.state != "success"]
    print(f"run {run.run_id}: {run.state}; tasks not successful: {failed or 'none'}")
    sys.exit(0 if not failed and len(tasks) > 0 else 1)
