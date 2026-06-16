# ERP Assistant — Frontend

Streamlit chat UI for the ERP Assistant backend.

## Two modes

| File | Connects to |
|---|---|
| `streamlit_app.py` | FastAPI backend (`http://localhost:8001`) |
| `streamlit_app_runpod.py` | RunPod Serverless endpoint (via SSE streaming) |

## Setup

```bash
cd frontend
pip install -r requirements.txt
```

### FastAPI mode
```bash
streamlit run streamlit_app.py
```
Requires backend running at `http://localhost:8001`.

### RunPod mode
1. Copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml`
2. Fill in your `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID`
3. Run:
```bash
streamlit run streamlit_app_runpod.py
```

## Deploy (Streamlit Community Cloud)

1. Push this folder as its own repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app
3. Set main file to `streamlit_app_runpod.py`
4. Add secrets in Advanced settings → Secrets (same keys as `secrets.toml.example`)
