"""Cross-encoder reranker using fastembed TextCrossEncoder."""
from __future__ import annotations
import logging
from functools import lru_cache
from app.config import settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _model():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder(model_name=settings.RERANKER_MODEL)


def rerank(
    question: str,
    candidates: list,  # list[RetrievalResult]
    top_k: int | None = None,
) -> list:
    """Rerank candidates using cross-encoder; returns top_k sorted by relevance."""
    if not candidates:
        return []
    top_k = top_k or settings.RERANK_TOP_K

    texts = [c.retrieval_text for c in candidates]
    model = _model()
    scores = list(model.rerank(query=question, documents=texts))

    for c, s in zip(candidates, scores):
        c.rerank_score = float(s)
        c.mode = "hybrid_rerank"

    ranked = sorted(candidates, key=lambda x: x.rerank_score or 0.0, reverse=True)
    return ranked[:top_k]
