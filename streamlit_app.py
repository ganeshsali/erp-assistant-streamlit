"""
Streamlit chatbot UI for the ERP Assistant.

Run the FastAPI backend first:
    uvicorn app.main:app --reload --port 8001

Then run this app:
    streamlit run streamlit_app.py
"""

import json
import os
import uuid

import requests
import streamlit as st

_backend_base = os.getenv("BACKEND_URL", "http://localhost:8000")
API_URL = f"{_backend_base.rstrip('/')}/chat/stream"

SUGGESTED_PROMPTS = [
    "Show me top 10 products by sales",
    "Who are my top 5 customers this month?",
    "What's the GST summary for this quarter?",
    "Show overdue invoices",
    "What's the current stock level?",
]

st.set_page_config(page_title="ERP Assistant", page_icon="💬", layout="centered")

st.markdown("""
<style>
@keyframes blink {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.2; }
}
.dot { display: inline-block; animation: blink 1.2s ease-in-out infinite; font-size: 1.4rem; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
</style>
""", unsafe_allow_html=True)

THINKING_HTML = '<span class="dot">●</span><span class="dot"> ●</span><span class="dot"> ●</span>'

st.title("💬 ERP Assistant")
st.caption("Ask me about sales, purchases, inventory, customers, vendors, outstanding invoices, GST/TDS/TCS, and more.")

# --- Session state ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

# --- Sidebar ---
with st.sidebar:
    st.subheader("Session")
    st.text(f"ID: {st.session_state.session_id[:8]}...")
    if st.button("New conversation", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.subheader("Quick actions")
    for suggestion in SUGGESTED_PROMPTS:
        if st.button(suggestion, use_container_width=True, key=f"suggestion_{suggestion}"):
            st.session_state.pending_prompt = suggestion
            st.rerun()

# --- Render chat history ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Pick up prompt from sidebar suggestion or text input
prompt = st.session_state.pending_prompt or st.chat_input("Ask about your business data...")
if st.session_state.pending_prompt:
    st.session_state.pending_prompt = None

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        status_ph = st.empty()
        response_ph = st.empty()

        status_ph.markdown(THINKING_HTML, unsafe_allow_html=True)

        full_response = ""
        error_msg = None
        tokens_started = False

        try:
            with requests.post(
                API_URL,
                json={"message": prompt, "session_id": st.session_state.session_id},
                stream=True,
                timeout=180,
            ) as resp:
                resp.raise_for_status()

                # Read byte-by-byte so the first token renders the instant the
                # backend yields it — iter_lines() buffers 512 bytes internally.
                buf = ""
                for raw in resp.iter_content(chunk_size=1, decode_unicode=True):
                    buf += raw
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        payload = json.loads(line[len("data: "):])
                        event_type = payload.get("type")

                        if event_type == "token":
                            if not tokens_started:
                                tokens_started = True
                                status_ph.empty()
                            full_response += payload["content"]
                            if full_response.strip():
                                response_ph.markdown(full_response + "▌")

                        elif event_type == "error":
                            error_msg = payload.get("message", "Unknown error")

                        elif event_type == "done":
                            break

        except requests.exceptions.ConnectionError:
            error_msg = f"Backend not reachable — is the FastAPI server running at {_backend_base}?"
        except requests.exceptions.Timeout:
            error_msg = "The request timed out. Please try again."
        except requests.exceptions.RequestException as e:
            error_msg = str(e)

        status_ph.empty()
        if error_msg:
            full_response = ""
            response_ph.error(error_msg)
        else:
            response_ph.markdown(full_response or "_(no response)_")

    st.session_state.messages.append({"role": "assistant", "content": full_response or error_msg or ""})
    if not error_msg:
        st.rerun()
