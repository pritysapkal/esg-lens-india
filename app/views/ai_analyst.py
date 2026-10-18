"""Ask the data: guided questions (always on, no language model) and, when switched on locally,
the AI analyst. Both answer through the same validated tools over the public tables."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import guided, labels, ui
from app.ai_analyst import agent

ui.require_data()
st.title("Ask the data")
st.markdown(
    "Pick a question and its details below. Every answer comes from a fixed, tested query on the "
    "public tables, and the query is shown under the answer so you can check it."
)


# ------------------------------------------------------------------ shared display


def show_notes(notes: list[str]) -> None:
    for note in notes:
        if "provisional" in note.lower():
            st.warning(note, icon=":material/schedule:")
        elif "withheld" in note.lower() or "n<5" in note:
            st.info(note, icon=":material/visibility_off:")
        else:
            st.caption(note)


def show_table(frame: pd.DataFrame) -> None:
    if frame is not None and not frame.empty:
        st.dataframe(labels.friendly(frame), hide_index=True, width="stretch")


# ------------------------------------------------------------------ guided questions

options = guided.choices()
st.subheader("Guided questions")
kind = st.radio(
    "Question",
    [q.key for q in guided.QUESTION_TYPES],
    format_func=lambda k: guided.BY_KEY[k].label,
    label_visibility="collapsed",
)
latest_final = options["years"][-2] if len(options["years"]) > 1 else options["years"][-1]
picks: dict = {}
c1, c2, c3, c4 = st.columns(4)
if kind == "group":
    picks["metric"] = c1.selectbox(
        "Figure", options["metrics"], format_func=lambda m: labels.GROUP_METRICS[m][0]
    )
    picks["group_type"] = c2.selectbox(
        "Group by", options["group_types"], index=1, format_func=labels.GROUP_TYPES.get
    )
    picks["group_value"] = c3.selectbox("Group", guided.group_values(picks["group_type"]))
    picks["year"] = c4.selectbox(
        "Financial year", [guided.ALL_YEARS, *options["years"]], index=len(options["years"]) - 1
    )
elif kind in ("card", "peers"):
    picks["company"] = c1.selectbox("Company", options["companies"])
    picks["year"] = c2.selectbox(
        "Financial year", options["years"], index=options["years"].index(latest_final)
    )
    if kind == "peers":
        picks["kpi"] = c3.selectbox(
            "KPI", [guided.ALL_KPIS, *options["kpis"]],
            format_func=lambda k: k if k == guided.ALL_KPIS else f"{labels.KPI_INFO[k][1]}: {labels.KPI_INFO[k][0]}",
        )  # fmt: skip
elif kind == "concentration":
    picks["year"] = c1.selectbox(
        "Financial year", options["years"], index=options["years"].index(latest_final)
    )
    picks["top_n"] = c2.slider("Largest emitters to list", 3, 20, 10)
elif kind == "movers":
    picks["direction"] = c1.selectbox(
        "Direction", ["improvement", "deterioration"],
        format_func={"improvement": "Largest improvements", "deterioration": "Largest deteriorations"}.get,
    )  # fmt: skip
    picks["ranking_group"] = c2.selectbox(
        "Ranking group", ["All ranking groups", *options["ranking_groups"]]
    )
    picks["limit"] = c3.slider("How many", 1, 10, 5)
elif kind == "restatements":
    picks["level"] = c1.selectbox(
        "Show", options["restatement_levels"], format_func=guided.GUIDED_RESTATEMENT_LEVELS.get
    )

answer = guided.ask(kind, picks)
with st.container(border=True):
    st.markdown(answer.sentence)
    show_table(answer.table)
    show_notes(answer.notes)
    st.caption(f"Query used: `{answer.call_text}` on the public table {answer.source}.")

# ------------------------------------------------------------------ the AI analyst (local only)

st.subheader("Ask in your own words")
if not agent.is_enabled():
    st.info(
        "Free-text questions with an AI model are not available on this public site. The guided "
        "questions above cover the same data, and a demonstration of the AI analyst is shown in "
        "the project video.",
        icon=":material/forum:",
    )
    ui.footer()
    st.stop()

limits = agent.LIMITS
if "analyst_history" not in st.session_state:
    st.session_state.analyst_history = []
asked = len(st.session_state.analyst_history)
st.caption(
    f"AI analyst on this computer: {agent.model_name()}. Question {min(asked + 1, limits.questions_per_session)} of "
    f"{limits.questions_per_session} this session; at most {limits.tool_calls_per_question} queries per question. "
    "Answers describe associations, not causes, and are not investment advice."
)


def show_calls(calls) -> None:
    if not calls:
        return
    with st.expander(f"Numbers used ({len(calls)} quer{'ies' if len(calls) != 1 else 'y'})"):
        for call in calls:
            st.markdown(
                f"`{call.name}({', '.join(f'{k}={v!r}' for k, v in call.arguments.items())})`"
            )
            if call.error:
                st.error(call.error)
                continue
            rows = next(
                (
                    call.result[k]
                    for k in ("rows", "movers", "largest_emitters")
                    if k in call.result
                ),
                None,
            )
            if rows:
                show_table(pd.DataFrame(rows))
            if "card" in call.result:
                show_table(
                    pd.DataFrame([call.result["card"]]).drop(
                        columns=["reasons_points_were_lost"], errors="ignore"
                    )
                )
            if "summary" in call.result:
                show_table(pd.DataFrame([call.result["summary"]]))
            for note in call.result.get("notes", []):
                st.caption(note)


def show_answer(reply) -> None:
    if reply.model_refused:
        st.warning(reply.text, icon=":material/block:")
    else:
        st.markdown(reply.text)
    show_calls(reply.calls)


for question, earlier in st.session_state.analyst_history:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        show_answer(earlier)

if asked >= limits.questions_per_session:
    st.info(
        f"This session has used its {limits.questions_per_session} questions. Reload the page to start a new session.",
        icon=":material/hourglass_empty:",
    )
    ui.footer()
    st.stop()

question = st.chat_input(
    "Ask about emissions, disclosure quality, restatements, peers ...",
    max_chars=limits.max_question_chars,
)
if question:
    try:
        question = agent.check_question(question, asked)
    except agent.QuestionRejected as error:
        st.warning(str(error))
        ui.footer()
        st.stop()
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Looking it up in the public tables ..."):
        try:
            reply = agent.ask(question)
        except Exception as error:  # an API, network or local-model error must not break the page
            st.error(
                f"The analyst could not answer ({type(error).__name__}). Please try again later."
            )
            st.stop()
        show_answer(reply)
    st.session_state.analyst_history.append((question, reply))
ui.footer()
