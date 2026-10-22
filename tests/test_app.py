"""The Streamlit report card (Week 13): every page runs, the app reads only exports/public, withheld
and provisional figures are labelled, and the committed public files stay public."""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
PUBLIC = ROOT / "exports" / "public"
WAREHOUSE = ROOT / "data" / "warehouse" / "esg_lens.duckdb"
PAGES = ["views/overview.py", "views/company.py", "views/sectors.py", "views/concentration.py",
         "views/ai_analyst.py", "views/methodology.py"]  # fmt: skip

from app import data, labels  # noqa: E402

needs_public = pytest.mark.skipif(not data.available(), reason="run dev.ps1 bi-export first")

# ------------------------------------------------------------------ the data path

_OPENED: list[str] = []
_RECORDING = {"on": False}


def _audit(event, args):
    if _RECORDING["on"] and event == "open" and args and isinstance(args[0], str | Path):
        _OPENED.append(str(args[0]))


sys.addaudithook(_audit)


def test_app_code_names_no_other_data_source():
    """Static check of every Python file under app/: one door (app/data.py) to the data."""
    forbidden = re.compile(
        r"duckdb|exports[/\\\\]local|data[/\\\\]warehouse|data[/\\\\]processed|data[/\\\\]raw|"
        r"\bfct_|\bdim_|\bint_|\bstg_|semantic_manifest|\bmf\b|kpi_catalogue"
    )
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not forbidden.search(text), (
            f"{path.relative_to(ROOT)}: {forbidden.search(text).group(0)}"
        )
        if path.name != "data.py":
            assert "read_parquet" not in text and "open(" not in text, (
                f"{path.relative_to(ROOT)} reads files itself"
            )


def test_data_module_refuses_anything_but_the_public_tables():
    for name in (
        "fct_company_year",
        "rpt_restatement_summary",
        "../local/fct_company_year",
        "dim_company",
    ):
        with pytest.raises(data.NotPublic):
            data.table(name)
    assert set(data.PUBLIC_TABLES) == {
        p.stem for p in (ROOT / "dbt" / "models" / "marts").glob("rpt_public_*.sql")
    }


@needs_public
def test_every_page_runs_and_opens_only_public_files(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    data.table.cache_clear()
    _OPENED.clear()
    _RECORDING["on"] = True
    try:
        app = AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=60)
        app.run()
        assert not app.exception, app.exception
        for page in PAGES[1:]:
            app.switch_page(page).run()
            assert not app.exception, (page, app.exception)
    finally:
        _RECORDING["on"] = False
    opened = [Path(p).resolve() for p in _OPENED]
    data_files = [
        p
        for p in opened
        if p.suffix in (".parquet", ".duckdb", ".csv", ".xlsx", ".json")
        and ROOT in p.parents
        # installed libraries read their own package data (Plotly templates): not project data
        and (ROOT / ".venv") not in p.parents
        and "site-packages" not in p.parts
    ]
    assert data_files, "the audit hook saw no data file being opened"
    outside = [p for p in data_files if PUBLIC.resolve() not in p.parents]
    assert not outside, f"the app opened data outside exports/public: {outside}"
    assert {p.stem for p in data_files if p.suffix == ".parquet"} <= set(data.PUBLIC_TABLES)


@needs_public
def test_visitors_get_guided_questions_and_a_friendly_note(monkeypatch):
    """The public deployment: the analyst is off (a key alone does not switch it on), the guided
    questions answer, and the note for visitors has no setup details in it."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("ESG_AI_ENABLED", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    app = AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=60)
    app.run()
    app.switch_page("views/ai_analyst.py").run()
    assert not app.exception
    assert app.radio and app.radio[0].value == "group"  # guided questions are the default
    assert any("Query used:" in c.value for c in app.caption)
    notes = [info.value for info in app.info]
    assert any("not switched on for this site" in n and "video" in n for n in notes)
    _no_setup_details(notes)
    assert not app.chat_input  # no way to send a free-text question while it is off


TECHNICAL = ("ESG_AI_ENABLED", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "ESG_AI_PROVIDER", "Ollama",
             "secrets", "environment", "429", "RESOURCE_EXHAUSTED", "ClientError")  # fmt: skip


def _no_setup_details(texts: list[str]) -> None:
    for technical in TECHNICAL:
        assert not any(technical in t for t in texts), technical


def _ai_page(monkeypatch, settings: dict[str, str], provider=None):
    """The Ask-the-data page with these settings in the environment (as dev.ps1 app sets them
    from the shell or .env); `provider` replaces agent.make_provider (a fake client, no network)."""
    from streamlit.testing.v1 import AppTest

    from app.ai_analyst import agent

    for name in ("ESG_AI_ENABLED", "ESG_AI_PROVIDER", "ESG_AI_MODEL", "GEMINI_API_KEY",
                 "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    if provider is not None:
        monkeypatch.setattr(agent, "make_provider", lambda *a, **k: provider)
    app = AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=60)
    app.run()
    app.switch_page("views/ai_analyst.py").run()
    assert not app.exception
    return app


def _gemini_provider(responses):
    sys.path.insert(0, str(ROOT / "tests"))
    from test_ai_providers import FakeGemini

    from app.ai_analyst import providers

    client = FakeGemini(responses)
    return providers.GeminiProvider(client=client), client


@needs_public
def test_free_text_box_appears_locally_when_switched_on_from_dot_env(monkeypatch, tmp_path):
    """The fix: settings in .env reach the app through scripts/run_local.py (dev.ps1 app), and
    with ESG_AI_ENABLED=true and the provider's key the input box is shown - not the note."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_local

    env_file = tmp_path / ".env"
    env_file.write_text("ESG_AI_ENABLED=true\nESG_AI_PROVIDER=gemini\nGEMINI_API_KEY=fake-key\n")
    settings = run_local.ai_settings(env_file, {})
    app = _ai_page(monkeypatch, settings)
    assert app.chat_input, "no input box although the analyst is switched on"
    assert not any("not switched on" in i.value for i in app.info)
    assert any("sent to Google's Gemini API" in i.value and "improve its products" in i.value
               for i in app.info)  # fmt: skip
    assert any("Google Gemini (gemini-3.5-flash-lite)" in c.value for c in app.caption)
    assert app.radio and app.radio[0].value == "group"  # guided questions stay the default


@needs_public
def test_local_model_box_appears_without_a_key_or_a_google_notice(monkeypatch):
    app = _ai_page(monkeypatch, {"ESG_AI_ENABLED": "true", "ESG_AI_PROVIDER": "ollama"})
    assert app.chat_input
    assert not any("Google" in i.value for i in app.info)


@needs_public
def test_switched_on_without_a_key_falls_back_to_guided_questions(monkeypatch):
    app = _ai_page(monkeypatch, {"ESG_AI_ENABLED": "true", "ESG_AI_PROVIDER": "gemini"})
    assert not app.chat_input
    notes = [i.value for i in app.info]
    assert any("not available right now" in n and "guided questions" in n for n in notes)
    _no_setup_details(notes)
    assert any("Query used:" in c.value for c in app.caption)  # guided mode answers


@needs_public
def test_used_up_quota_pauses_free_text_and_keeps_guided_questions(monkeypatch):
    from test_ai_providers import api_error

    provider, client = _gemini_provider([api_error(429, "RESOURCE_EXHAUSTED")])
    settings = {"ESG_AI_ENABLED": "true", "ESG_AI_PROVIDER": "gemini", "GEMINI_API_KEY": "k"}
    app = _ai_page(monkeypatch, settings, provider)
    app.chat_input[0].set_value("How concentrated are emissions?").run()
    assert not app.exception and len(client.requests) == 1
    warnings = [w.value for w in app.warning]
    assert any("quota is used up" in w and "guided questions" in w for w in warnings)
    _no_setup_details(warnings)
    app.run()  # the next interaction: free text stays paused for this session
    assert not app.exception and not app.chat_input
    assert any("quota is used up" in i.value for i in app.info)
    assert any("Query used:" in c.value for c in app.caption)
    assert app.session_state["analyst_history"] == []  # the failed question is not counted


@needs_public
def test_an_api_error_gives_a_plain_message_and_the_box_stays(monkeypatch):
    from dataclasses import replace

    from test_ai_providers import api_error

    from app.ai_analyst import agent

    monkeypatch.setattr(agent, "LIMITS", replace(agent.LIMITS, retry_backoff_seconds=0))
    # a 503 is retried once; a second one gives the plain message
    provider, client = _gemini_provider([api_error(503, "UNAVAILABLE")] * 2)
    settings = {"ESG_AI_ENABLED": "true", "ESG_AI_PROVIDER": "gemini", "GEMINI_API_KEY": "k"}
    app = _ai_page(monkeypatch, settings, provider)
    app.chat_input[0].set_value("How concentrated are emissions?").run()
    assert not app.exception and len(client.requests) == 2
    warnings = [w.value for w in app.warning]
    assert any("could not answer just now" in w for w in warnings)
    _no_setup_details(warnings)
    app.run()
    assert app.chat_input  # a passing error does not pause free text


@needs_public
def test_a_gemini_refusal_is_shown_as_a_refusal(monkeypatch):
    from test_ai_providers import _gemini

    provider, client = _gemini_provider([_gemini(finish="SAFETY")])
    settings = {"ESG_AI_ENABLED": "true", "ESG_AI_PROVIDER": "gemini", "GEMINI_API_KEY": "k"}
    app = _ai_page(monkeypatch, settings, provider)
    app.chat_input[0].set_value("something it declines").run()
    assert not app.exception and len(client.requests) == 1  # no second model, no retry
    assert any("declined to answer" in w.value for w in app.warning)
    ((question, reply),) = app.session_state["analyst_history"]
    assert reply.model_refused and reply.provider == "gemini"


@needs_public
def test_a_gemini_answer_shows_its_tool_calls(monkeypatch):
    from test_ai_providers import _gemini

    provider, _ = _gemini_provider([
        _gemini(calls=[("concentration", {"year": "FY2024-25", "top_n": 5})]),
        _gemini("The five largest emitters held 85.5%."),
    ])  # fmt: skip
    settings = {"ESG_AI_ENABLED": "true", "ESG_AI_PROVIDER": "gemini", "GEMINI_API_KEY": "k"}
    app = _ai_page(monkeypatch, settings, provider)
    app.chat_input[0].set_value("How concentrated are emissions?").run()
    assert not app.exception
    assert any("85.5%" in m.value for m in app.markdown)
    assert any("Numbers used (1 query)" in e.label for e in app.expander)


@needs_public
def test_no_page_shows_a_raw_column_name(monkeypatch):
    """Every table on every page - and every guided question type - has reader-facing headers."""
    from streamlit.testing.v1 import AppTest

    from app import guided

    monkeypatch.delenv("ESG_AI_ENABLED", raising=False)
    app = AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=60)
    app.run()
    seen = 0

    def check(where: str) -> None:
        nonlocal seen
        assert not app.exception, (where, app.exception)
        for frame in app.dataframe:
            value = frame.value
            names = [*map(str, value.columns), *[str(n) for n in value.index.names if n]]
            raw = [n for n in names if "_" in n]
            assert not raw, f"{where}: raw column names {raw}"
            seen += 1

    check("overview")
    for page in PAGES[1:]:
        app.switch_page(page).run()
        check(page)
    app.switch_page("views/ai_analyst.py").run()
    for question in guided.QUESTION_TYPES:
        app.radio[0].set_value(question.key).run()
        check(f"guided {question.key}")
    assert seen >= 10


# ------------------------------------------------------------------ labels


def _catalogue() -> dict[str, dict[str, str]]:
    with (ROOT / "dbt" / "seeds" / "kpi_catalogue.csv").open(encoding="utf-8", newline="") as fh:
        return {row["kpi_name"]: row for row in csv.DictReader(fh)}


def test_group_metric_labels_follow_the_catalogue():
    catalogue = _catalogue()
    for metric, (_label, _unit, gate, restatement) in labels.GROUP_METRICS.items():
        row = catalogue[metric]
        assert row["public_safe"] == "true", metric
        assert (row["companies_metric"] or None) == gate, metric
        assert restatement == (row["source_model"] == "fct_restatement"), metric


@needs_public
def test_withheld_and_not_yet_observable_cells_say_why():
    automobiles = data.group_row("ranking_group", "Automobiles", "FY2023-24")
    assert labels.group_cell(automobiles, "ghg_intensity_median") == "n<5 (withheld)"
    latest = data.group_row("all", "All companies", data.latest_year())
    assert labels.group_cell(latest, "material_restatement_share") == "not yet observable"
    assert isinstance(labels.group_cell(latest, "ghg_intensity_agg"), float)
    assert data.is_provisional(data.latest_year()) and data.provisional_note(data.latest_year())
    assert not data.provisional_note(data.latest_final_year())


def test_ranking_status_and_reason_code_labels():
    assert (
        labels.ranking_status(False, "not_material") == "not ranked for this group (not material)"
    )
    assert labels.ranking_status(True, None) == "ranked"
    assert labels.reason_codes("assurance_core_only|waste_balance_gap") == [
        "Only the mandatory BRSR Core was assured",
        "Waste figures do not add up",
    ]


# ------------------------------------------------------------------ the committed public files


@needs_public
def test_public_folder_passes_the_safety_checks():
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_public

    assert check_public.problems(PUBLIC) == []


def test_only_public_parquet_files_are_tracked_under_exports():
    """exports/public/*.parquet is committed for Streamlit Community Cloud; nothing else."""
    result = subprocess.run(
        ["git", "ls-files", "exports"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    tracked = [Path(line) for line in result.stdout.splitlines() if line]
    allowed = {f"{name}.parquet" for name in data.PUBLIC_TABLES} | {".gitkeep"}
    for path in tracked:
        assert path.parts[:2] == ("exports", "public") and path.name in allowed, f"tracked: {path}"


# ------------------------------------------------------------------ rpt_public_ghg_yoy = Week 10 Q3


@pytest.mark.skipif(not WAREHOUSE.exists(), reason="needs the real warehouse")
def test_public_yoy_model_equals_the_week_10_result():
    sys.path.insert(0, str(ROOT / "tests"))
    from test_analysis import QUERIES, RUNNER

    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        if con.sql("select count(distinct isin) from fct_company_year").fetchone()[0] < 40:
            pytest.skip("not the real warehouse")
        q3 = RUNNER.run_queries(
            con,
            [
                q
                for q in QUERIES
                if q.result_id == "q03_ghg_leaders_laggards__yoy_changes_with_confidence"
            ],
        )
        model = con.sql("select * from rpt_public_ghg_yoy").df()
    finally:
        con.close()
    q3 = q3["q03_ghg_leaders_laggards__yoy_changes_with_confidence"]
    key = ["display_name", "to_year"]
    merged = q3.merge(model, on=key, suffixes=("_q3", "_model"))
    assert len(merged) == len(q3) == len(model)
    for column in (
        "change_pct",
        "confidence",
        "is_ranked",
        "improvement_rank_in_group",
        "intensity_to",
    ):
        left, right = merged[f"{column}_q3"], merged[f"{column}_model"]
        assert ((left == right) | (left.isna() & right.isna())).all(), column
    assert pd.api.types.is_bool_dtype(model["is_ranked"])


@needs_public
def test_ai_page_stops_after_the_session_limit(monkeypatch):
    """With the analyst switched on and 10 questions already asked, the page offers no input (so
    no request can be sent) and says why. No API call is made in this test."""
    from streamlit.testing.v1 import AppTest

    from app.ai_analyst import agent

    monkeypatch.setenv("ESG_AI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    app = AppTest.from_file(str(APP / "streamlit_app.py"), default_timeout=60)
    app.run()
    asked = [("q", agent.Answer(text="a"))] * agent.LIMITS.questions_per_session
    app.session_state["analyst_history"] = asked
    app.switch_page("views/ai_analyst.py").run()
    assert not app.exception
    assert any("used its 10 questions" in info.value for info in app.info)
    assert not app.chat_input
