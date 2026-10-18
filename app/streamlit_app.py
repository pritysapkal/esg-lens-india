"""ESG Lens India - public report card (Streamlit).

    .\\scripts\\dev.ps1 app        # or: streamlit run app/streamlit_app.py

Reads only the public tables in exports/public (app/data.py). Pages live in app/views/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `import app...` works

st.set_page_config(page_title="ESG Lens India", page_icon=":material/eco:", layout="wide")

pages = [
    st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/company.py", title="Company report card", icon=":material/badge:"),
    st.Page("views/sectors.py", title="Sectors", icon=":material/category:"),
    st.Page("views/concentration.py", title="Concentration", icon=":material/stacked_bar_chart:"),
    st.Page("views/ai_analyst.py", title="Ask the data (AI)", icon=":material/chat:"),
    st.Page("views/methodology.py", title="Methodology", icon=":material/menu_book:"),
]
st.navigation(pages).run()
