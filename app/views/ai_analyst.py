"""Ask the data: guided questions (always on, no language model) and, when switched on, the AI
analyst. Both answer through the same validated tools over the public tables. When the analyst's
provider cannot answer (Gemini quota used up, key missing, API error) the page says so in plain
words and the guided questions carry on."""

from __future__ import annotations

import logging

import streamlit as st

from app import guided, labels, layout, ui
from app.ai_analyst import agent
from app.answer_view import show_calls, show_guided_help, show_notes, show_table

ui.require_data()
layout.page_header(
    "Ask the data",
    "**Can I get a checked answer to a specific question?** Pick a question and its details below. "
    "Every answer comes from a fixed, tested query on the public tables, and the query is shown "
    "under the answer so you can check it.",
)


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
    show_guided_help(kind)
    st.caption(f"Query used: `{answer.call_text}` on the public table {answer.source}.")

# ------------------------------------------------------------------ the AI analyst (when switched on)

GUIDED_STILL_WORKS = "The guided questions above answer the same data and always work."
UNAVAILABLE = {  # what a reader is told when the provider cannot answer; no setup details
    "quota": "Free-text questions are paused: the free AI quota is used up for now. "
    + GUIDED_STILL_WORKS,
    "auth": "Free-text questions are not available right now. " + GUIDED_STILL_WORKS,
    "error": "The AI analyst could not answer just now (the AI service did not respond). "
    "Please try again in a minute. " + GUIDED_STILL_WORKS,
}
GOOGLE_NOTICE = (
    "Questions are sent to Google's Gemini API; on the free tier Google may use them to improve "
    "its products. Please do not type personal information."
)

st.subheader("Ask in your own words")
st.markdown(":orange-badge[:material/science: Experimental]")
st.caption(
    "It can look up figures in the public tables through fixed, validated queries and describe "
    "associations. It cannot browse the web, see filed values, give investment advice or claim "
    "that one thing causes another; guided questions above remain the reference."
)
if not agent.switched_on():
    # the default, and the public site unless Gemini is switched on there
    st.info(
        "Free-text questions with an AI model are not switched on for this site. The guided "
        "questions above cover the same data; how the AI analyst works and how it scored on a "
        "fixed question set is in the project's GitHub repository (docs/ai_analyst_eval.md).",
        icon=":material/forum:",
    )
    ui.footer()
    st.stop()

paused = st.session_state.get("analyst_unavailable")
if paused or not agent.is_enabled():
    # switched on, but the provider cannot answer: missing key, or quota / key failure earlier in
    # this session. The reason goes to the terminal / app log, never to the page.
    if not paused:
        logging.getLogger(__name__).warning("AI analyst unavailable: %s", agent.disabled_reason())
    st.info(UNAVAILABLE[paused or "auth"], icon=":material/forum:")
    ui.footer()
    st.stop()

limits = agent.LIMITS
if "analyst_history" not in st.session_state:
    st.session_state.analyst_history = []
asked = len(st.session_state.analyst_history)
where = {
    "gemini": f"Google Gemini ({agent.model_name()})",
    "anthropic": f"Claude ({agent.model_name()})",
}.get(agent.provider_name(), f"a model on this computer ({agent.model_name()})")
if agent.sends_questions_to_google():
    st.info(GOOGLE_NOTICE, icon=":material/info:")
st.caption(
    f"AI analyst: {where}. Question {min(asked + 1, limits.questions_per_session)} of "
    f"{limits.questions_per_session} this session; at most {limits.tool_calls_per_question} queries per question. "
    "Answers describe associations, not causes, and are not investment advice."
)


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
        except agent.ProviderUnavailable as error:
            logging.getLogger(__name__).warning("AI analyst unavailable: %s", error)
            if error.reason in ("quota", "auth"):
                # retrying cannot help in this session: pause free text, keep the guided questions
                st.session_state.analyst_unavailable = error.reason
            st.warning(UNAVAILABLE.get(error.reason, UNAVAILABLE["error"]))
            ui.footer()
            st.stop()
        except Exception as error:  # an API, network or local-model error must not break the page
            logging.getLogger(__name__).warning("AI analyst error: %r", error)
            st.warning(UNAVAILABLE["error"])
            ui.footer()
            st.stop()
        show_answer(reply)
    st.session_state.analyst_history.append((question, reply))
ui.footer()
