from pathlib import Path

from sentence_transformers import CrossEncoder

from app.config import RERANKER_MODEL_DIR, TOP_K_RERANK
from app.logging_config import logger


class LocalReranker:
    _model = None
    _disabled = False

    @classmethod
    def get_model(cls):
        if cls._disabled:
            return None

        if cls._model is None:
            try:
                model_path = Path(RERANKER_MODEL_DIR)
                if not model_path.exists():
                    logger.warning(f"[bold yellow]Reranker path not found[/] path={model_path}")
                    cls._disabled = True
                    return None

                cls._model = CrossEncoder(str(model_path))
            except Exception as e:
                logger.warning(f"[bold yellow]Reranker disabled[/] error={e}")
                cls._disabled = True
                return None

        return cls._model

    @classmethod
    def rerank(cls, query: str, evidences: list, top_k: int = TOP_K_RERANK):
        if not evidences:
            return []

        model = cls.get_model()
        if model is None:
            return evidences[:top_k]

        try:
            pairs = [[query, ev.content] for ev in evidences]
            scores = model.predict(pairs)

            ranked = []
            for ev, score in zip(evidences, scores):
                ev.score = float(score)
                ranked.append(ev)

            ranked.sort(key=lambda x: x.score, reverse=True)
            return ranked[:top_k]
        except Exception as e:
            logger.warning(f"[bold yellow]Reranker inference failed, using fallback[/] error={e}")
            return evidences[:top_k]