import streamlit as st

st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            width: 200px !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- PAGE SETUP ---

page_utama = st.Page(
  page="pages/dashboard.py",
  title="Utama",
  icon=":material/bar_chart:",
  default=True,
)
page_fakulti = st.Page(
  page="pages/fakulti.py",
  title="PTj",
  icon=":material/bar_chart:",
)

pg = st.navigation(pages=[
    page_utama,
    page_fakulti
])

pg.run()