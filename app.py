"""
Streamlit UI for the Apartment Portfolio AI Agent.

Run:  streamlit run app.py

Reuses every function from agent.py — this file is purely presentation.
"""
import os
import sqlite3

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from agent import DB_PATH, get_schema_text, run_agent

load_dotenv()

st.set_page_config(page_title="Apartment Portfolio AI Agent", page_icon="🏢", layout="centered")

st.title("🏢 Apartment Portfolio AI Agent")
st.caption(
    "Ask a question in plain English. The agent translates it to SQL, runs it "
    "against the apartment portfolio database, and explains the result — with "
    "a guardrail that only ever allows read-only SELECT queries."
)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error(
        "No OPENAI_API_KEY found. Create a `.env` file in this folder "
        "(copy `.env.example`) with your key, then restart this app."
    )
    st.stop()

if not os.path.exists(DB_PATH):
    st.error(f"`{DB_PATH}` not found. Run `python seed_data.py` first, then restart this app.")
    st.stop()


@st.cache_resource
def get_client_and_schema():
    client = OpenAI(api_key=api_key)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    schema = get_schema_text(conn)
    return client, conn, schema


client, conn, schema = get_client_and_schema()

with st.expander("Example questions"):
    st.markdown(
        "- Which property has the lowest occupancy rate?\n"
        "- Who are the top 3 technicians by completed maintenance requests?\n"
        "- How many leases are expiring in the next 60 days?\n"
        "- Delete all tenant records *(try this — watch it get blocked)*"
    )

if "history" not in st.session_state:
    st.session_state.history = []

question = st.chat_input("Ask a question about the apartment portfolio...")

if question:
    with st.spinner("Thinking..."):
        result = run_agent(client, conn, schema, question)
    st.session_state.history.append((question, result))

for question, result in reversed(st.session_state.history):
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        for t in result["trace"]:
            if t["status"] == "blocked":
                st.warning(f"**Attempt {t['attempt']} blocked:** {t['detail']}")
                st.code(t["sql"], language="sql")
            elif t["status"] == "error":
                st.warning(f"**Attempt {t['attempt']} failed:** {t['detail']}")
                st.code(t["sql"], language="sql")

        if result["success"]:
            st.markdown("**SQL used:**")
            st.code(result["sql"], language="sql")
            st.markdown("**Answer:**")
            st.write(result["answer"])
            if result["rows"]:
                st.markdown("**Raw result:**")
                st.dataframe(
                    [dict(zip(result["columns"], row)) for row in result["rows"]],
                    use_container_width=True,
                )
        else:
            st.error(result["answer"])
