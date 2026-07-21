from typing import Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from app.config import (
    CHROMA_COLLECTION_APPENDIX,
    CHROMA_COLLECTION_DEFINITION_TEXT,
    CHROMA_COLLECTION_FORMULA_TEXT,
    CHROMA_COLLECTION_SERVICE_CHUNKS,
    CHROMA_COLLECTION_SERVICE_SUMMARIES,
    CHROMA_COLLECTION_TABLE_TEXT,
    CHROMA_DIR,
    EMBEDDING_MODEL_DIR,
)
from app.logging_config import logger


class LocalEmbedder:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            cls._model = SentenceTransformer(str(EMBEDDING_MODEL_DIR))
        return cls._model

    @classmethod
    def encode(cls, texts: list[str]) -> list[list[float]]:
        model = cls.get_model()
        arr = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return arr.tolist()


class ChromaStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

    def _get_or_create(self, name: str):
        return self.client.get_or_create_collection(name=name)

    def _upsert_rows(self, collection_name: str, rows: list[dict]):
        if not rows:
            return

        col = self._get_or_create(collection_name)
        ids = [r["entity_id"] for r in rows]
        docs = [r["content"] for r in rows]

        metas = []
        for r in rows:
            metas.append(
                {
                    "doc_id": r["doc_id"],
                    "entity_type": r["entity_type"],
                    "service_name": r.get("service_name", ""),
                    "topic_name": r.get("topic_name", ""),
                    "page_num": int(r["page_num"]) if r.get("page_num") is not None else -1,
                    "citation": r.get("citation", ""),
                }
            )

        embs = LocalEmbedder.encode(docs)
        col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embs)

    def upsert_service_chunks(self, rows: list[dict]):
        self._upsert_rows(CHROMA_COLLECTION_SERVICE_CHUNKS, rows)

    def upsert_service_summaries(self, rows: list[dict]):
        self._upsert_rows(CHROMA_COLLECTION_SERVICE_SUMMARIES, rows)

    def upsert_appendix_chunks(self, rows: list[dict]):
        self._upsert_rows(CHROMA_COLLECTION_APPENDIX, rows)

    def upsert_table_text(self, rows: list[dict]):
        self._upsert_rows(CHROMA_COLLECTION_TABLE_TEXT, rows)

    def upsert_definition_text(self, rows: list[dict]):
        self._upsert_rows(CHROMA_COLLECTION_DEFINITION_TEXT, rows)

    def upsert_formula_text(self, rows: list[dict]):
        self._upsert_rows(CHROMA_COLLECTION_FORMULA_TEXT, rows)

    def query_collection(self, collection_name: str, query: str, top_k: int = 8, where: dict[str, Any] | None = None):
        col = self._get_or_create(collection_name)
        qemb = LocalEmbedder.encode([query])[0]

        res = col.query(
            query_embeddings=[qemb],
            n_results=top_k,
            where=where,
        )

        out = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]

        for i in range(len(ids)):
            meta = metas[i] or {}
            out.append(
                {
                    "entity_id": ids[i],
                    "entity_type": meta.get("entity_type", ""),
                    "service_name": meta.get("service_name", ""),
                    "topic_name": meta.get("topic_name", ""),
                    "page_num": None if meta.get("page_num", -1) == -1 else meta.get("page_num"),
                    "citation": meta.get("citation", ""),
                    "content": docs[i],
                    "score": float(dists[i]) if i < len(dists) else 0.0,
                }
            )
        return out

    def delete_doc(self, doc_id: str):
        for name in [
            CHROMA_COLLECTION_SERVICE_CHUNKS,
            CHROMA_COLLECTION_SERVICE_SUMMARIES,
            CHROMA_COLLECTION_APPENDIX,
            CHROMA_COLLECTION_TABLE_TEXT,
            CHROMA_COLLECTION_DEFINITION_TEXT,
            CHROMA_COLLECTION_FORMULA_TEXT,
        ]:
            col = self._get_or_create(name)
            try:
                col.delete(where={"doc_id": doc_id})
            except Exception as e:
                logger.warning(f"Chroma delete warning for {name}: {e}")


def get_vector_store():
    return ChromaStore()