"""How an answer is shown on the Ask the data page: notes, tables and the tool calls behind an AI
answer. Kept out of the page script so tests/test_answer_view.py can run them on every tool's
output without starting the page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import labels

# Per guided question: (how to read it, how it is calculated). Presentation text only.
GUIDED_HELP: dict[str, tuple[str, str]] = {
    "group": (
        "Whole group and typical company can differ a lot: a few large companies move the first.",
        "Whole group = ratio of sums (all the group's emissions, energy, water or waste divided by "
        "all its turnover). Typical company = the median of the companies' own ratios. A figure is "
        "shown only when 5 or more companies stand behind it.",
    ),
    "card": (
        "The score says how completely and consistently a company discloses, not how good its "
        "performance is. It is not an ESG rating.",
        "Disclosure Quality Score (0-100) from completeness, consistency over time and assurance. "
        "Rank and percentile are within the ranking group and year, with 5 or more gradable companies.",
    ),
    "peers": (
        "A position is where the company stands in its group; it is associated with the group's "
        "make-up and size, not with effort alone.",
        "Percentile in the ranking group and year (100 = best). Only KPIs that are material for "
        "the group, in groups of 5 or more companies, with a trusted value, are ranked.",
    ),
    "concentration": (
        "A handful of companies account for most of the emissions covered, so a group trend is "
        "largely the trend of those few.",
        "Each company's share of the Scope 1+2 emissions of all companies covered in the year; "
        "the running total is the cumulative share. Shares only, never tonnes.",
    ),
    "movers": (
        "Only changes a later report confirms are ranked; large moves are often data issues.",
        "Year-on-year change in GHG intensity, confirmed-only: both years must be repeated in the "
        "next report. Provisional, unit-inferred, restated and one-year-reversal moves are excluded.",
    ),
    "restatements": (
        "Restated figures are common; the data show no tilt in the companies' favour.",
        "Figures first filed for a year, compared with the same figures in the next report "
        "('Material' = the change is large enough to matter, as defined in the restatement method). "
        "The latest year is not yet observable.",
    ),
}


def show_guided_help(key: str) -> None:
    reading, how = GUIDED_HELP[key]
    st.markdown(f"**Takeaway:** {reading}")
    with st.expander("How this is calculated"):
        st.markdown(how)


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
