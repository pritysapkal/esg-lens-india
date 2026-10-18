"""Ask the data: the AI analyst (Claude with a fixed set of tools over the public tables)."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from app import ui
from app.ai_analyst import agent

ui.require_data()
st.title("Ask the data")
st.markdown(
    'Ask a question about the public figures - for example *"How concentrated were emissions in '
    'FY2024-25?"* or *"Where does Asian Paints rank on GHG intensity?"*. The analyst can only '
    "call a fixed set of tested queries over the public tables; every number in its answer is "
    "shown below it with the query that produced it."
)

if not agent.is_enabled():
    st.info(
        "**The AI analyst is disabled** because no `ANTHROPIC_API_KEY` is set. The rest of the "
        "report card works without it. To enable it, set the key in the environment (or in "
        "Streamlit secrets) and restart the app.",
        icon=":material/key_off:",
    )
    ui.footer()
    st.stop()

st.caption(
    f"Model: {agent.model_name()}. Answers describe associations, not causes, and are not investment advice."
)

if "analyst_history" not in st.session_state:
    st.session_state.analyst_history = []


def show_calls(calls) -> None:
    if not calls:
        return
    with st.expander(f"Numbers used ({len(calls)} tool call{'s' if len(calls) != 1 else ''})"):
        for call in calls:
            st.markdown(f"**`{call.name}`** `{json.dumps(call.arguments)}`")
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
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            extra = {
                k: v
                for k, v in call.result.items()
                if k not in ("rows", "movers", "largest_emitters")
            }
            st.json(extra, expanded=False)


for question, answer in st.session_state.analyst_history:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        st.markdown(answer.text)
        show_calls(answer.calls)

question = st.chat_input("Ask about emissions, disclosure quality, restatements, peers ...")
if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Looking it up in the public tables ..."):
        try:
            answer = agent.ask(question)
        except Exception as error:  # an API or network error must not break the page
            st.error(
                f"The analyst could not answer: {type(error).__name__}. Please try again later."
            )
            st.stop()
        st.markdown(answer.text)
        show_calls(answer.calls)
    st.session_state.analyst_history.append((question, answer))
ui.footer()
