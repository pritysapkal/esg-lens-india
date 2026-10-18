"""The ESG Lens India pipeline as plain data: every task, its group, its command and its order.

This module does not import Airflow. The DAG (orchestration/dags/esg_lens_pipeline.py) is built
from it, and tests/test_orchestration.py checks it on any machine (Windows included). One
definition, so the documented pipeline and the one Airflow runs cannot drift apart.

The pipeline never downloads anything. Filings are saved into the inbox by a person
(docs/adr/0002-manual-intake-nse-terms.md); `check_inbox` only looks at what is there.

    check_inbox
      -> intake.discover -> intake.taxonomy -> intake.file_inbox
      -> parse -> load
      -> dbt_seed.seed
      -> dbt_run.run_staging -> dbt_run.run_warehouse -> dbt_run.run_elementary
      -> dbt_test.test_unit -> dbt_test.test_data
      -> semantic_validate -> analysis -> stats -> bi_export -> public_safety_checks
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

DAG_ID = "esg_lens_pipeline"

# Airflow and Cosmos both send anonymous usage data by default; the pipeline must not touch the
# network, so it is switched off for the Airflow processes (docker-compose.yml) and every task.
TELEMETRY_OFF = {
    "AIRFLOW__COSMOS__ENABLE_TELEMETRY": "False",
    "AIRFLOW__USAGE_DATA_COLLECTION__ENABLED": "False",
    "SCARF_ANALYTICS": "false",
}


@dataclass(frozen=True)
class Settings:
    """Where things are. Defaults are the paths inside the Docker image (orchestration/)."""

    repo: str = "/opt/esg-lens-india"  # the repository, mounted read-only
    work: str = "/opt/airflow/esg_work"  # everything the pipeline writes
    python: str = "/opt/esg-venv/bin/python"  # the project's own environment (requirements.txt)
    dbt: str = "/opt/esg-venv/bin/dbt"
    mf: str = "/opt/esg-venv/bin/mf"

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            repo=os.getenv("ESG_REPO", defaults.repo),
            work=os.getenv("ESG_WORK", defaults.work),
            python=os.getenv("ESG_PYTHON", defaults.python),
            dbt=os.getenv("ESG_DBT", defaults.dbt),
            mf=os.getenv("ESG_MF", defaults.mf),
        )

    @property
    def data(self) -> str:
        return f"{self.work}/data"

    @property
    def duckdb(self) -> str:
        return f"{self.data}/warehouse/esg_lens.duckdb"

    def env(self) -> dict[str, str]:
        """Environment of every task: the data folder and the warehouse live under `work`."""
        return {
            "DATA_DIR": self.data,  # ingestion (ingestion/config.py)
            "ESG_DATA_DIR": self.data,  # dbt staging views
            "DUCKDB_PATH": self.duckdb,  # dbt profile and every script
            "PYTHONPATH": self.repo,
            "PYTHONDONTWRITEBYTECODE": "1",  # the repository is read-only
            "PYTHONUTF8": "1",  # mf prints symbols some consoles cannot encode
            "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
            "DO_NOT_TRACK": "1",
            **TELEMETRY_OFF,
        }


@dataclass(frozen=True)
class Step:
    task_id: str
    description: str
    group: str = ""  # Airflow task group; empty = top level
    command: str = ""  # shell command (kind == "bash")
    kind: str = "bash"  # bash | dbt
    dbt_command: str = ""  # seed | run | test (kind == "dbt")
    select: tuple[str, ...] = ()
    dbt_flags: tuple[str, ...] = field(default=("--fail-fast",))

    @property
    def node_id(self) -> str:
        """The task's id in Airflow: group.task for a task in a group."""
        return f"{self.group}.{self.task_id}" if self.group else self.task_id


def _py(settings: Settings, *args: str) -> str:
    return f"cd {settings.repo} && {settings.python} " + " ".join(args)


def steps(settings: Settings | None = None) -> list[Step]:
    """All tasks, in the order they run (each one depends on the one before)."""
    s = settings or Settings.from_env()
    exports = f"{s.work}/exports"
    semantic_dir = f"{s.work}/dbt_semantic"
    return [
        Step(
            "check_inbox",
            "Count the files a person saved into data/raw/xbrl_inbox. Never downloads.",
            command=_py(s, "-m", "orchestration.check_inbox"),
        ),
        Step(
            "discover",
            "Read the hand-saved NSE listing CSVs into one table.",
            group="intake",
            command=_py(s, "-m", "ingestion.discover"),
        ),
        Step(
            "taxonomy",
            "Scan the SEBI taxonomy packages on disk.",
            group="intake",
            command=_py(s, "-m", "ingestion.taxonomy"),
        ),
        Step(
            "file_inbox",
            "Hash, match and file the inbox XBRL files (never overwrites).",
            group="intake",
            command=_py(s, "-m", "ingestion.intake"),
        ),
        Step(
            "parse",
            "Parse every filed XBRL instance to Parquet.",
            command=_py(s, "-m", "ingestion.parse_xbrl"),
        ),
        Step(
            "load",
            "Load the Parquet tables into the DuckDB warehouse.",
            command=_py(s, "-m", "ingestion.load_raw"),
        ),
        Step(
            "seed", "dbt seed: the rule tables.", group="dbt_seed", kind="dbt", dbt_command="seed"
        ),
        Step(
            "run_staging",
            "dbt run: staging models.",
            group="dbt_run",
            kind="dbt",
            dbt_command="run",
            select=("path:models/staging",),
        ),
        Step(
            "run_warehouse",
            "dbt run: intermediate, gold, public and semantic-layer models.",
            group="dbt_run",
            kind="dbt",
            dbt_command="run",
            # one call: intermediate models read gold dimensions and rpt_public_group_metrics
            # reads the semantic views, so the folders cannot run one after another
            select=("path:models/intermediate", "path:models/marts", "path:models/semantic"),
        ),
        Step(
            "run_elementary",
            "dbt run: elementary monitoring models.",
            group="dbt_run",
            kind="dbt",
            dbt_command="run",
            select=("package:elementary",),
        ),
        Step(
            "test_unit",
            "dbt test: unit tests.",
            group="dbt_test",
            kind="dbt",
            dbt_command="test",
            select=("test_type:unit",),
        ),
        Step(
            "test_data",
            "dbt test: all data tests (public safety included); stops at the first failure.",
            group="dbt_test",
            kind="dbt",
            dbt_command="test",
            select=("test_type:data",),
        ),
        Step(
            "semantic_validate",
            "Semantic layer in sync with the catalogue; dbt parse; mf validate-configs.",
            command=(
                f"cd {s.repo} && {s.python} scripts/build_semantic_layer.py --check"
                f" && rm -rf {semantic_dir} && cp -r {s.repo}/dbt {semantic_dir}"
                f" && rm -rf {semantic_dir}/target {semantic_dir}/logs"
                f" && cd {semantic_dir} && {s.dbt} parse --profiles-dir ."
                f" && {s.mf} validate-configs"
            ),
        ),
        Step(
            "analysis",
            "The 12 business questions (Week 10).",
            command=_py(
                s, "scripts/run_analysis.py", "--db", s.duckdb, "--out", f"{s.work}/analysis"
            ),
        ),
        Step(
            "stats",
            "The five statistics studies (Week 11).",
            command=_py(
                s, "-m", "analysis.stats.run", "--db", s.duckdb, "--out", f"{s.work}/stats"
            ),
        ),
        Step(
            "bi_export",
            "Parquet exports and workbooks; the committed Power BI projects must still match.",
            command=(
                _py(s, "scripts/export_bi.py", "--db", s.duckdb, "--out", exports)
                + f" && {s.python} scripts/build_powerbi.py --db {s.duckdb} --check"
            ),
        ),
        Step(
            "public_safety_checks",
            "Only rpt_public_* files in exports/public, no raw-value column, no statistic below 5.",
            command=_py(s, "scripts/check_public.py", f"{exports}/public"),
        ),
    ]


def shell_command(step: Step, settings: Settings | None = None) -> str:
    """What the task runs, as one shell line (for dbt steps: the dbt call Cosmos makes)."""
    if step.kind == "bash":
        return step.command
    s = settings or Settings.from_env()
    parts = [s.dbt, step.dbt_command, "--profiles-dir", "."]
    if step.select:
        parts += ["--select", *step.select]
    parts += list(step.dbt_flags)
    return f"cd {s.repo}/dbt && " + " ".join(shlex.quote(p) for p in parts)


def describe() -> str:
    """The task list as Markdown (used by docs/orchestration.md)."""
    lines = ["| # | Task | Group | What it does |", "|---|---|---|---|"]
    for number, step in enumerate(steps(Settings()), start=1):
        lines.append(f"| {number} | `{step.task_id}` | {step.group or '-'} | {step.description} |")
    return "\n".join(lines)


def check_paths(settings: Settings) -> list[str]:
    """Problems that would stop the pipeline before it starts."""
    problems = []
    if not Path(settings.repo, "dbt", "dbt_project.yml").exists():
        problems.append(f"repository not found at {settings.repo}")
    if not Path(settings.data, "raw").exists():
        problems.append(f"no data/raw under {settings.work}")
    return problems
