from pathlib import Path

# Current runnable project
BASE_DIR = Path(__file__).resolve().parents[1]

# Shared assets source project
ASSET_BASE_DIR = BASE_DIR.parent / "in_progress_OLD"

PIPELINE_VERSION = "ms_sla_prod_final_v2"

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHROMA_DIR = DATA_DIR / "chroma"
DUCKDB_DIR = DATA_DIR / "duckdb"
LOG_DIR = DATA_DIR / "logs"
TMP_DIR = DATA_DIR / "tmp"

DUCKDB_PATH = DUCKDB_DIR / "ms_sla.duckdb"

# Use llama.cpp binaries from in_progress_OLD
LLAMA_SERVER_EXE = ASSET_BASE_DIR / "bin" / "llama.cpp" / "llama-server.exe"

# Use local GGUF model from in_progress_OLD
LLM_MODEL_PATH = ASSET_BASE_DIR / "models" / "llm" / "qwen2.5-3b-instruct-q4_k_m.gguf"

LLAMA_HOST = "127.0.0.1"
LLAMA_PORT = 8080
LLAMA_BASE_URL = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
LLAMA_CTX = 4096
LLAMA_GPU_LAYERS = 0
LLAMA_START_TIMEOUT_SEC = 45
LLAMA_TIMEOUT_SEC = 180
MAX_ANSWER_TOKENS = 320

# Use embedding model from in_progress_OLD
EMBEDDING_MODEL_DIR = ASSET_BASE_DIR / "models" / "embedding" / "bge-small-en-v1.5"

# Use reranker model from in_progress_OLD
RERANKER_MODEL_DIR = ASSET_BASE_DIR / "models" / "cross-encoder" / "ms-marco-MiniLM-L6-v2"

NARRATIVE_CHUNK_SIZE = 1000
NARRATIVE_CHUNK_OVERLAP = 120

TOP_K_VECTOR = 12
TOP_K_RERANK = 8
TOP_K_EVIDENCE = 6

CHROMA_COLLECTION_SERVICE_CHUNKS = "service_chunks"
CHROMA_COLLECTION_SERVICE_SUMMARIES = "service_summaries"
CHROMA_COLLECTION_APPENDIX = "appendix_chunks"
CHROMA_COLLECTION_TABLE_TEXT = "table_text_chunks"
CHROMA_COLLECTION_DEFINITION_TEXT = "definition_chunks"
CHROMA_COLLECTION_FORMULA_TEXT = "formula_chunks"

MS_SLA_TOP_SECTION_NAMES = [
    "INTRODUCTION",
    "GENERAL TERMS",
    "SERVICE SPECIFIC TERMS",
    "APPENDIX A – SERVICE LEVEL COMMITMENT FOR VIRUS DETECTION AND BLOCKING, SPAM EFFECTIVENESS, OR FALSE POSITIVE",
]

MS_SLA_GROUP_NAMES = {
    "MICROSOFT DYNAMICS 365",
    "OFFICE 365 SERVICES",
    "MICROSOFT AZURE SERVICES AND PLANS",
    "OTHER ONLINE SERVICES",
}

APPENDIX_TOPIC_NAMES = [
    "VIRUS DETECTION AND BLOCKING SERVICE LEVEL",
    "SPAM EFFECTIVENESS SERVICE LEVEL",
    "FALSE POSITIVE SERVICE LEVEL",
]

SMALLTALK = {
    "hi", "hello", "hey", "good morning", "good evening", "how are you",
}

LIBREOFFICE_CANDIDATES = [
    Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
]

for p in [DATA_DIR, RAW_DIR, PROCESSED_DIR, CHROMA_DIR, DUCKDB_DIR, LOG_DIR, TMP_DIR]:
    p.mkdir(parents=True, exist_ok=True)