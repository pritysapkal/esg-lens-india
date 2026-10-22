"""How an answer is shown on the Ask the data page: notes, tables and the tool calls behind an AI
answer. Kept out of the page script so tests/test_answer_view.py can run them on every tool's
output without starting the page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import labels


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


def call_tables(result: dict) -> list[pd.DataFrame]:
    """The tables of one tool result, as shown under "Numbers used"."""
    tables = []
    rows = next(
        (result[k] for k in ("rows", "movers", "largest_emitters") if k in result),
        None,
    )
    if rows:
        tables.append(pd.DataFrame(rows))
    if "card" in result:
        tables.append(
            pd.DataFrame([result["card"]]).drop(
                columns=["reasons_points_were_lost"], errors="ignore"
            )
        )
    if "summary" in result:
        tables.append(pd.DataFrame([result["summary"]]))
    return tables


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
            for table in call_tables(call.result):
                show_table(table)
            for note in call.result.get("notes", []):
                st.caption(note)
