"""The Airflow pipeline (Week 13). The plain-Python spec (orchestration/pipeline.py) is checked on
every machine; the DAG itself where Airflow is installed (the Docker image, the CI airflow job).
The full run with `airflow dags test` under `docker run --network none` is in
orchestration/run_dag_test.sh (`.\\scripts\\dev.ps1 airflow-test`)."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DAG_FILE = ROOT / "orchestration" / "dags" / "esg_lens_pipeline.py"

from orchestration import pipeline  # noqa: E402

EXPECTED_ORDER = [
    "check_inbox",
    "intake.discover",
    "intake.taxonomy",
    "intake.file_inbox",
    "parse",
    "load",
    "dbt_seed.seed",
    "dbt_run.run_staging",
    "dbt_run.run_warehouse",
    "dbt_run.run_elementary",
    "dbt_test.test_unit",
    "dbt_test.test_data",
    "semantic_validate",
    "analysis",
    "stats",
    "bi_export",
    "public_safety_checks",
]
NETWORK_MODULES = {
    "requests",
    "httpx",
    "aiohttp",
    "urllib.request",
    "urllib3",
    "http.client",
    "socket",
    "ftplib",
    "smtplib",
}
NETWORK_COMMANDS = re.compile(r"\b(curl|wget|pip|uv|git|dbt deps|deps)\b|https?://")


# ------------------------------------------------------------------ the spec (any machine)


def test_task_order_is_the_documented_pipeline():
    assert [step.node_id for step in pipeline.steps(pipeline.Settings())] == EXPECTED_ORDER


def test_dbt_runs_as_seed_run_and_test_groups_and_stops_at_the_first_failure():
    dbt = [s for s in pipeline.steps(pipeline.Settings()) if s.kind == "dbt"]
    assert {s.group for s in dbt} == {"dbt_seed", "dbt_run", "dbt_test"}
    assert [s.dbt_command for s in dbt] == ["seed"] + ["run"] * 3 + ["test"] * 2
    assert all("--fail-fast" in s.dbt_flags for s in dbt)
    # intermediate models read gold dimensions, rpt_public_group_metrics reads the semantic
    # views: those three folders reference each other and must be one dbt call
    warehouse = next(s for s in dbt if s.task_id == "run_warehouse")
    assert set(warehouse.select) == {
        "path:models/intermediate",
        "path:models/marts",
        "path:models/semantic",
    }


def test_no_task_command_reaches_the_network():
    for step in pipeline.steps(pipeline.Settings()):
        command = pipeline.shell_command(step, pipeline.Settings())
        assert not NETWORK_COMMANDS.search(command), f"{step.node_id}: {command}"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def test_no_code_the_tasks_run_imports_a_network_library():
    """Every Python file a task runs (ingestion, scripts, analysis/stats, orchestration)."""
    files = [
        *ROOT.glob("ingestion/*.py"),
        *ROOT.glob("analysis/stats/*.py"),
        *ROOT.glob("orchestration/*.py"),
        *(ROOT / "scripts" / name for name in (
            "run_analysis.py", "export_bi.py", "build_excel.py", "build_powerbi.py",
            "build_semantic_layer.py", "check_public.py",
        )),
    ]  # fmt: skip
    for path in files:
        bad = {
            m
            for m in _imports(path)
            if m in NETWORK_MODULES
            or m.split(".")[0] in {"requests", "httpx", "aiohttp", "urllib3"}
        }
        assert not bad, f"{path.relative_to(ROOT)} imports {sorted(bad)}"


def test_every_task_writes_only_under_the_work_folder():
    settings = pipeline.Settings(repo="/repo", work="/work")
    env = settings.env()
    assert env["DATA_DIR"] == env["ESG_DATA_DIR"] == "/work/data"
    assert env["DUCKDB_PATH"].startswith("/work/")
    for step in pipeline.steps(settings):
        for flag in ("--out", "--db"):
            for value in re.findall(rf"{flag} (\S+)", step.command):
                assert value.startswith("/work/"), f"{step.node_id}: {flag} {value}"


def test_telemetry_is_off_for_the_tasks_and_the_airflow_processes():
    """Cosmos and Airflow send usage data by default (found by the --network none run)."""
    env = pipeline.Settings().env()
    compose = (ROOT / "orchestration" / "docker-compose.yml").read_text(encoding="utf-8")
    script = (ROOT / "orchestration" / "run_dag_test.sh").read_text(encoding="utf-8")
    for key, value in pipeline.TELEMETRY_OFF.items():
        assert env[key] == value
        assert f'{key}: "{value}"' in compose, key
        assert f"{key}={value}" in script, key


def test_dag_file_sets_no_schedule_and_no_retries():
    tree = ast.parse(DAG_FILE.read_text(encoding="utf-8"))
    dag_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "DAG"
    ]
    assert len(dag_calls) == 1
    keywords = {k.arg: k.value for k in dag_calls[0].keywords}
    assert isinstance(keywords["schedule"], ast.Constant) and keywords["schedule"].value is None
    assert keywords["catchup"].value is False
    retries = next(
        v
        for k, v in zip(keywords["default_args"].keys, keywords["default_args"].values, strict=True)
        if k.value == "retries"
    )
    assert retries.value == 0


# ------------------------------------------------------------------ the DAG (needs Airflow)


@pytest.fixture(scope="module")
def dag():
    pytest.importorskip(
        "airflow", reason="Airflow runs in Docker: .\\scripts\\dev.ps1 airflow-test"
    )
    pytest.importorskip("cosmos")
    from airflow.models import DagBag

    os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "false")
    bag = DagBag(dag_folder=str(DAG_FILE.parent))
    assert not bag.import_errors, bag.import_errors
    return bag.dags[pipeline.DAG_ID]


def test_dag_imports_without_errors(dag):
    assert dag.dag_id == "esg_lens_pipeline"
    assert len(dag.tasks) == len(EXPECTED_ORDER)


def test_dag_is_manual_only(dag):
    assert dag.schedule is None or str(dag.timetable.summary).lower() in ("none", "null")
    assert dag.catchup is False and dag.max_active_runs == 1


def test_dag_task_order_matches_the_spec(dag):
    assert [t.task_id for t in dag.topological_sort()] == EXPECTED_ORDER
    for before, after in zip(EXPECTED_ORDER, EXPECTED_ORDER[1:], strict=False):
        assert dag.get_task(before).downstream_task_ids == {after}


def test_cosmos_telemetry_is_off_in_this_process(dag):
    from cosmos import settings

    assert settings.enable_telemetry is False


def test_dag_tasks_fail_fast(dag):
    for task in dag.tasks:
        assert task.retries == 0, task.task_id
        assert task.trigger_rule == "all_success", task.task_id


def test_dbt_tasks_are_cosmos_operators_that_never_install_packages(dag):
    from cosmos.operators.local import DbtLocalBaseOperator

    dbt_tasks = [t for t in dag.tasks if t.task_id.startswith("dbt_")]
    assert len(dbt_tasks) == 6
    for task in dbt_tasks:
        assert isinstance(task, DbtLocalBaseOperator), task.task_id
        assert task.install_deps is False, task.task_id
