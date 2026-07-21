import subprocess
import time

import requests

from app.config import (
    LLAMA_BASE_URL,
    LLAMA_CTX,
    LLAMA_GPU_LAYERS,
    LLAMA_HOST,
    LLAMA_PORT,
    LLAMA_SERVER_EXE,
    LLAMA_START_TIMEOUT_SEC,
    LLM_MODEL_PATH,
    MAX_ANSWER_TOKENS,
)
from app.logging_config import logger


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


def ensure_llama_server(project_root):
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
            cwd=str(project_root),
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


def ask_llm(prompt: str) -> str:
    payload = {
        "model": "local-model",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You answer ONLY from the provided Microsoft SLA evidence. "
                    "Never invent facts. "
                    "If evidence is insufficient, say exactly: "
                    "\"I do not have enough evidence in the uploaded document.\""
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": MAX_ANSWER_TOKENS,
    }

    response = requests.post(
        f"{LLAMA_BASE_URL}/v1/chat/completions",
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()