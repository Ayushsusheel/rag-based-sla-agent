from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import NARRATIVE_CHUNK_OVERLAP, NARRATIVE_CHUNK_SIZE
from app.logging_config import logger
from app.utils import normalize_ws, build_citation, stable_hash


def extract_chunks(doc_id: str, services: list[dict]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=NARRATIVE_CHUNK_SIZE,
        chunk_overlap=NARRATIVE_CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " "],
    )

    chunks = []

    for svc in services:
        text = normalize_ws(svc["text"])
        if not text:
            continue

        parts = splitter.split_text(text)
        for idx, ch in enumerate(parts):
            ch = normalize_ws(ch)
            if not ch:
                continue

            chunks.append(
                {
                    "chunk_id": f"chunk_{stable_hash(doc_id, svc['service_name'], str(idx), ch[:150])}",
                    "doc_id": doc_id,
                    "service_name": svc["service_name"],
                    "topic_name": "",
                    "entity_type": "chunk",
                    "page_num": svc.get("start_page"),
                    "citation": build_citation(svc["service_name"], svc.get("start_page"), "chunk"),
                    "content": ch,
                }
            )

    logger.info(f"[bold yellow]Narrative chunks extracted[/] count={len(chunks)}")
    return chunks