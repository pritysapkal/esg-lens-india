"""ESG Lens India - Streamlit report-card app (placeholder)."""

import streamlit as st

st.set_page_config(page_title="ESG Lens India", page_icon=":seedling:", layout="wide")

st.title("Hello ESG Lens")
st.write(
    "Open BRSR analytics for the NIFTY 50 companies. "
    "Company report cards will appear here once the dbt marts are built."
)
st.info(
    "The Disclosure Quality Score measures the completeness and consistency of BRSR "
    "disclosures. It is **not** an ESG rating."
)
