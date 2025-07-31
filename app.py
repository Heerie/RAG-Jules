import streamlit as st
import requests
import time
import os

st.set_page_config(layout="wide", page_title="Conversational RAG Q&A")

API_URL = "http://127.0.0.1:8000"

st.markdown("""
<style>
    /* CSS styles from before */
</style>
""", unsafe_allow_html=True)

st.title("💬 Conversational RAG Q&A System")
st.caption("A new, modular, and deployable RAG system.")

def get_processing_status():
    try:
        response = requests.get(f"{API_URL}/status")
        response.raise_for_status()
        return response.json().get("processing_status", "error")
    except requests.exceptions.RequestException as e:
        return f"error: Could not connect to backend at {API_URL}"

def display_document_management_ui():
    with st.sidebar.expander("📂 Document Management", expanded=True):
        st.markdown("This UI interacts with the backend API.")
        st.markdown("---")

        status_placeholder = st.empty()

        if st.button("🔄 Process Documents", key="process_docs", use_container_width=True):
            try:
                response = requests.post(f"{API_URL}/process")
                response.raise_for_status()
                st.session_state.processing_status = "processing"
                st.toast(response.json().get("message", "Processing started."))
            except requests.exceptions.RequestException as e:
                st.error(f"Error starting processing: {e}")

        # Auto-update status
        if "processing_status" not in st.session_state:
            st.session_state.processing_status = get_processing_status()

        status = st.session_state.processing_status
        if status == "processing":
            status_placeholder.warning("⏳ Processing documents...")
            time.sleep(5) # Poll every 5 seconds
            st.session_state.processing_status = get_processing_status()
            st.rerun()
        elif status == "complete":
            status_placeholder.success("✅ Processing complete.")
        elif status == "idle":
            status_placeholder.info("Ready. Click 'Process Documents' to start.")
        else: # error or other
            status_placeholder.error(f"🚨 Status: {status}")

# Main app logic
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar
st.sidebar.title("Controls & Info")
if st.sidebar.button("✨ New Chat", use_container_width=True):
    st.session_state.messages = []
    st.rerun()

display_document_management_ui()

# Main chat interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask a question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        with st.spinner("Thinking..."):
            try:
                payload = {
                    "query": prompt,
                    "chat_history": st.session_state.messages[:-1]
                }
                response = requests.post(f"{API_URL}/query", json=payload)
                response.raise_for_status()
                answer = response.json().get("answer", "Sorry, I could not get a response.")

                # Simulate stream for better UX
                for chunk in answer.split():
                    full_response += chunk + " "
                    time.sleep(0.05)
                    message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)

            except requests.exceptions.RequestException as e:
                full_response = f"Error communicating with the backend: {e}"
                message_placeholder.error(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})
