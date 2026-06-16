"""
Streamlit chatbot UI for the ERP Assistant — RunPod Serverless edition.

Configure these secrets in Streamlit Community Cloud (Advanced settings → Secrets):
    RUNPOD_API_KEY     = "rp_your_api_key"
    RUNPOD_ENDPOINT_ID = "your_endpoint_id"

Streaming: submits via /run, then reads SSE from /stream/{job_id} token by token.
The RunPod handler must use `yield` to emit {"type": "token", "content": "..."} chunks.
"""

import json
import time
import uuid

import requests
import streamlit as st

RUNPOD_API_KEY = st.secrets.get("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT_ID = st.secrets.get("RUNPOD_ENDPOINT_ID", "")

RUN_URL = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/run"
RUNPOD_HEADERS = {
    "Authorization": f"Bearer {RUNPOD_API_KEY}",
    "Content-Type": "application/json",
}

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
        tool_ph = st.empty()
        response_ph = st.empty()

        status_ph.markdown(THINKING_HTML, unsafe_allow_html=True)

        full_response = ""
        error_msg = None
        tokens_started = False

        # Send full conversation history (excluding current prompt — handler appends it)
        prior_messages = st.session_state.messages[:-1]

        payload = {
            "input": {
                "message": prompt,
                "session_id": st.session_state.session_id,
                "messages": prior_messages,
            }
        }

        try:
            # Step 1: submit job asynchronously
            run_resp = requests.post(
                RUN_URL,
                headers=RUNPOD_HEADERS,
                json=payload,
                timeout=30,
            )
            run_resp.raise_for_status()
            job_id = run_resp.json().get("id")
            if not job_id:
                raise ValueError("No job ID returned from RunPod.")

            # Step 2: open a persistent SSE connection to /stream/{job_id}.
            # RunPod keeps this connection alive and pushes each yielded chunk
            # as an SSE event — true streaming, no polling needed.
            stream_url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/stream/{job_id}"
            with requests.get(
                stream_url,
                headers={**RUNPOD_HEADERS, "Accept": "text/event-stream"},
                stream=True,
                timeout=180,
            ) as stream_resp:
                stream_resp.raise_for_status()
                for line in stream_resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "):
                        continue
                    data = json.loads(line[len("data: "):])
                    job_status = data.get("status")

                    for item in data.get("stream", []):
                        output = item.get("output", {})
                        if isinstance(output, str):
                            try:
                                output = json.loads(output)
                            except json.JSONDecodeError:
                                continue
                        if isinstance(output, dict):
                            etype = output.get("type")
                            if etype == "token":
                                if not tokens_started:
                                    tokens_started = True
                                    status_ph.empty()
                                    tool_ph.empty()
                                full_response += output.get("content", "")
                                if full_response.strip():
                                    response_ph.markdown(full_response + "▌")
                            elif etype == "status":
                                tool_ph.caption(f"🔍 {output.get('message', 'Processing...')}")
                            elif etype == "done":
                                tool_ph.empty()
                                response_ph.markdown(full_response or "_(no response)_")
                            elif etype == "error":
                                error_msg = output.get("message", "Unknown error")

                    if job_status == "FAILED":
                        error_msg = data.get("error", "RunPod job failed.")
                        break
                    if job_status in ("COMPLETED", "CANCELLED"):
                        break

        except ValueError as e:
            error_msg = str(e)
        except requests.exceptions.Timeout:
            error_msg = "Request timed out. The ERP query may be too complex — try again."
        except requests.exceptions.ConnectionError:
            error_msg = "Could not reach the RunPod endpoint. Check your RUNPOD_ENDPOINT_ID in secrets."
        except requests.exceptions.RequestException as e:
            error_msg = str(e)

        status_ph.empty()
        tool_ph.empty()
        if error_msg:
            full_response = ""
            response_ph.error(error_msg)
        elif full_response:
            response_ph.markdown(full_response)

    st.session_state.messages.append({
        "role": "assistant",
        "content": full_response or error_msg or "",
    })
    if not error_msg:
        st.rerun()
