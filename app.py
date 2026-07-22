import streamlit as st
import os

st.set_page_config(
    page_title="RAmos Controller Hub",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  #MainMenu, header, footer { display: none !important; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  section[data-testid="stSidebar"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

html_path = os.path.join(os.path.dirname(__file__), "controller_hub.html")
with open(html_path, "r", encoding="utf-8") as f:
    html_content = f.read()

st.components.v1.html(html_content, height=950, scrolling=True)
