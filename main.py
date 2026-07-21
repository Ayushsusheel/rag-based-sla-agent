import os
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import (
    LLAMA_BASE_URL,
    LLAMA_CTX,
    LLAMA_GPU_LAYERS,
    LLAMA_HOST,
    LLAMA_PORT,
    LLAMA_SERVER_EXE,
    LLAMA_START_TIMEOUT_SEC,
    LLM_MODEL_PATH,
)
from app.logging_config import logger
from app.pipeline import clear_all_runtime, delete_document_runtime, ingest_document
from app.query_engine import answer_query
from app.storage import clear_chat_history, fetch_document, get_chat_history, init_db, list_documents
from app.utils import safe_filename


def llama_server_running() -> bool:
    try:
        r = requests.get(f"{LLAMA_BASE_URL}/health", timeout=2)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    try:
        r = requests.get(f"{LLAMA_BASE_URL}/v1/models", timeout=2)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    return False


def ensure_llama_server():
    if llama_server_running():
        return True, "already running"

    if not LLAMA_SERVER_EXE.exists():
        return False, f"llama-server.exe not found: {LLAMA_SERVER_EXE}"

    if not LLM_MODEL_PATH.exists():
        return False, f"GGUF model not found: {LLM_MODEL_PATH}"

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        subprocess.Popen(
            [
                str(LLAMA_SERVER_EXE),
                "-m", str(LLM_MODEL_PATH),
                "-c", str(LLAMA_CTX),
                "-ngl", str(LLAMA_GPU_LAYERS),
                "--host", str(LLAMA_HOST),
                "--port", str(LLAMA_PORT),
            ],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as e:
        return False, f"failed to start llama-server: {e}"

    start = time.time()
    while time.time() - start < LLAMA_START_TIMEOUT_SEC:
        if llama_server_running():
            return True, "started now"
        time.sleep(1)

    return False, "llama-server did not become ready in time"


def save_uploaded_file(uploaded_file) -> Path:
    raw_dir = PROJECT_ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    out_path = raw_dir / f"_incoming_{safe_filename(uploaded_file.name)}"
    with open(out_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return out_path


st.set_page_config(page_title="Chat with my document (Microsoft SLA)", layout="wide")
init_db()

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "selected_doc_id" not in st.session_state:
    st.session_state.selected_doc_id = None

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "indexing_in_progress" not in st.session_state:
    st.session_state.indexing_in_progress = False


st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
}
.hero-box {
    padding: 1.2rem 1.4rem;
    border-radius: 16px;
    background: linear-gradient(90deg, #0f62fe 0%, #0043ce 100%);
    color: white;
    margin-bottom: 1rem;
}
.feature-box {
    padding: 0.9rem 1rem;
    border-radius: 12px;
    background: #f7f9fc;
    border: 1px solid #dde4ee;
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("Microsoft SLA Hybrid RAG")

    ok, msg = ensure_llama_server()
    if ok:
        st.success(f"LLM server: {msg}")
    else:
        st.error(f"LLM server error: {msg}")

    st.markdown("### Upload SLA")
    uploaded = st.file_uploader(
        "Upload Microsoft SLA PDF / DOCX",
        type=["pdf", "docx"],
        accept_multiple_files=False,
    )

    if uploaded is not None and st.button("Process Uploaded File", use_container_width=True):
        try:
            temp_path = save_uploaded_file(uploaded)
            st.session_state.indexing_in_progress = True
            with st.spinner("Parsing, extracting, embedding, and building indexes..."):
                row = ingest_document(temp_path)
            st.session_state.indexing_in_progress = False
            st.session_state.selected_doc_id = row["doc_id"]
            st.success(f"Indexed: {row['file_name']}")
            st.rerun()
        except Exception as e:
            st.session_state.indexing_in_progress = False
            logger.exception(f"Upload failed: {e}")
            st.error(f"Failed to ingest uploaded file: {e}")

    st.divider()

    docs = list_documents()
    options = {f"{d['file_name']} [{d['file_type']}] [{d['doc_id']}]": d["doc_id"] for d in docs}
    selected_label = st.selectbox("Stored documents", options=[""] + list(options.keys()))
    if selected_label:
        st.session_state.selected_doc_id = options[selected_label]

    if st.session_state.selected_doc_id and st.button("Delete Selected Document", use_container_width=True):
        try:
            delete_document_runtime(st.session_state.selected_doc_id)
            st.session_state.selected_doc_id = None
            st.session_state.last_result = None
            st.success("Document deleted.")
            st.rerun()
        except Exception as e:
            logger.exception(f"Delete failed: {e}")
            st.error(f"Delete failed: {e}")

    if st.button("Clear Current Chat", use_container_width=True):
        try:
            if st.session_state.selected_doc_id:
                clear_chat_history(st.session_state.session_id, st.session_state.selected_doc_id)
            st.success("Chat cleared.")
            st.rerun()
        except Exception as e:
            logger.exception(f"Clear chat failed: {e}")
            st.error(f"Clear chat failed: {e}")

    if st.button("Clear ALL Stored Data", use_container_width=True):
        try:
            clear_all_runtime()
            st.session_state.selected_doc_id = None
            st.session_state.last_result = None
            st.success("All stored data cleared.")
            st.rerun()
        except Exception as e:
            logger.exception(f"Clear all failed: {e}")
            st.error(f"Clear all failed: {e}")

    st.divider()
    st.caption("Logs are stored in data/logs/")


st.markdown("""
<div class="hero-box">
    <h2 style="margin:0;">Chat with my document (Microsoft SLA)</h2>
    <p style="margin:0.5rem 0 0 0;">
        Local, offline, structured hybrid RAG for Microsoft SLA documents.
    </p>
</div>
""", unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("""
    <div class="feature-box">
        <b>Structured deterministic QA</b><br/>
        Tables, service-credit rules, formulas, definitions, and Appendix A are extracted at ingestion time.
    </div>
    """, unsafe_allow_html=True)
with c2:
    st.markdown("""
    <div class="feature-box">
        <b>Hybrid retrieval</b><br/>
        Narrative chunks are stored in a local vector database and reranked before answer synthesis.
    </div>
    """, unsafe_allow_html=True)
with c3:
    st.markdown("""
    <div class="feature-box">
        <b>Fully local and persistent</b><br/>
        Upload once, store locally until deleted, then ask questions instantly during the session.
    </div>
    """, unsafe_allow_html=True)

docs = list_documents()
if not docs:
    st.info("Upload a Microsoft SLA PDF / DOCX to begin.")
    st.stop()

if not st.session_state.selected_doc_id:
    st.warning("Select an uploaded SLA document from the sidebar.")
    st.stop()

selected_doc = fetch_document(st.session_state.selected_doc_id)
if selected_doc:
    st.markdown("### Selected Document")
    st.write(
        {
            "file_name": selected_doc["file_name"],
            "file_type": selected_doc["file_type"],
            "doc_id": selected_doc["doc_id"],
            "pipeline_version": selected_doc["pipeline_version"],
        }
    )

history = get_chat_history(st.session_state.session_id, st.session_state.selected_doc_id, limit=20)

st.markdown("### Chat")
for msg in history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

chat_disabled = st.session_state.indexing_in_progress
if chat_disabled:
    st.info("Document indexing is in progress. Chat will be enabled after parsing, extraction, embedding, and indexing complete.")

user_query = st.chat_input(
    "Ask anything about the uploaded Microsoft SLA document...",
    disabled=chat_disabled,
)

if user_query:
    with st.chat_message("user"):
        st.write(user_query)

    try:
        with st.spinner("Resolving deterministic facts and hybrid evidence..."):
            result = answer_query(
                st.session_state.selected_doc_id,
                st.session_state.session_id,
                user_query,
            )
        st.session_state.last_result = result

        with st.chat_message("assistant"):
            st.write(result["answer"])
    except Exception as e:
        logger.exception(f"Answer failed: {e}")
        with st.chat_message("assistant"):
            st.error(f"Query failed: {e}")

if st.session_state.last_result:
    res = st.session_state.last_result

    st.markdown("---")
    st.subheader("Last Retrieval Details")
    st.write(
        {
            "resolved_mode": res["resolved_mode"],
            "subqueries": res["subqueries"],
        }
    )

    st.subheader("Primary Evidence")
    for i, ev in enumerate(res["evidence"], start=1):
        with st.expander(f"Primary {i}: {ev.get('citation','Source')}"):
            st.markdown(
                f"""
- **Entity Type:** {ev.get('entity_type','')}
- **Page:** {ev.get('page_num','')}
- **Service Name:** {ev.get('service_name','')}
- **Topic Name:** {ev.get('topic_name','')}
- **Score:** {ev.get('score','')}
"""
            )
            st.code(ev.get("content", ""), language="text")