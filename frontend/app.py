import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.title("Asystent BGK")

if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex
    st.session_state.messages = []

# Wyświetl historię
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            pages = sorted({p for s in msg["sources"] for p in s["pages"]})
            st.caption(f"Źródła: strony {', '.join(map(str, pages))}")

# Input
if question := st.chat_input("Zadaj pytanie o raport BGK..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.spinner("Szukam odpowiedzi..."):
        resp = requests.post(
            f"{BACKEND_URL}/chat",
            json={
                "question": question,
                "session_id": st.session_state.session_id,
            },
        )
        data = resp.json()

    with st.chat_message("assistant"):
        st.markdown(data["answer"])
        if data.get("sources"):
            pages = sorted({p for s in data["sources"] for p in s["pages"]})
            st.caption(f"Źródła: strony {', '.join(map(str, pages))}")

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": data["answer"],
            "sources": data.get("sources", []),
        }
    )
