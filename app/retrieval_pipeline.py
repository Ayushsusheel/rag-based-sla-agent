from app.config import (
    CHROMA_COLLECTION_APPENDIX,
    CHROMA_COLLECTION_DEFINITION_TEXT,
    CHROMA_COLLECTION_FORMULA_TEXT,
    CHROMA_COLLECTION_SERVICE_CHUNKS,
    CHROMA_COLLECTION_SERVICE_SUMMARIES,
    CHROMA_COLLECTION_TABLE_TEXT,
    TOP_K_VECTOR,
)
from app.models import RetrievedEvidence
from app.reranker import LocalReranker
from app.storage import search_lexical_entities
from app.utils import normalize_key
from app.vector_store import get_vector_store


def _build_where(doc_id: str, service_name: str = "", topic_name: str = ""):
    conditions = [{"doc_id": doc_id}]
    if service_name:
        conditions.append({"service_name": service_name})
    if topic_name:
        conditions.append({"topic_name": topic_name})

    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _rows_to_evidences(rows: list[dict]) -> list[RetrievedEvidence]:
    out = []
    for r in rows:
        out.append(
            RetrievedEvidence(
                entity_id=r["entity_id"],
                entity_type=r["entity_type"],
                service_name=r.get("service_name", ""),
                topic_name=r.get("topic_name", ""),
                page_num=r.get("page_num"),
                citation=r.get("citation", ""),
                content=r.get("content", ""),
                score=float(r.get("score", 0.0)),
            )
        )
    return out


def hybrid_retrieve(doc_id: str, query: str, service_name: str = "", topic_name: str = "", top_k: int = TOP_K_VECTOR):
    # lexical-first
    lexical_rows = search_lexical_entities(
        doc_id=doc_id,
        query=query,
        service_name=service_name,
        topic_name=topic_name,
        limit=25,
    )
    lexical_evidences = _rows_to_evidences(lexical_rows)

    # vector semantic
    store = get_vector_store()
    where = _build_where(doc_id, service_name=service_name, topic_name=topic_name)

    vector_rows = []
    collections = [
        CHROMA_COLLECTION_SERVICE_SUMMARIES,
        CHROMA_COLLECTION_SERVICE_CHUNKS,
        CHROMA_COLLECTION_TABLE_TEXT,
        CHROMA_COLLECTION_DEFINITION_TEXT,
        CHROMA_COLLECTION_FORMULA_TEXT,
    ]

    if topic_name:
        collections.append(CHROMA_COLLECTION_APPENDIX)

    for collection_name in collections:
        rows = store.query_collection(collection_name, query, top_k=top_k, where=where)
        vector_rows.extend(rows)

    vector_evidences = _rows_to_evidences(vector_rows)

    merged = {}
    for ev in lexical_evidences + vector_evidences:
        key = (ev.entity_id, ev.entity_type)
        prev = merged.get(key)
        if prev is None or ev.score > prev.score:
            merged[key] = ev

    evidences = list(merged.values())

    if service_name:
        local = [e for e in evidences if normalize_key(e.service_name) == normalize_key(service_name)]
        if local:
            evidences = local + [e for e in evidences if normalize_key(e.service_name) != normalize_key(service_name)]

    if topic_name:
        local = [e for e in evidences if normalize_key(e.topic_name) == normalize_key(topic_name)]
        if local:
            evidences = local + [e for e in evidences if normalize_key(e.topic_name) != normalize_key(topic_name)]

    return LocalReranker.rerank(query, evidences)