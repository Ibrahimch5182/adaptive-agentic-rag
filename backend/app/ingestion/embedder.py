"""Dense + sparse embedding via fastembed. Models are loaded lazily and cached per-process."""
from __future__ import annotations
from functools import lru_cache
from app.config import settings


@lru_cache(maxsize=1)
def _dense_model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=settings.DENSE_EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _sparse_model():
    from fastembed import SparseTextEmbedding
    return SparseTextEmbedding(model_name=settings.SPARSE_EMBEDDING_MODEL)


def embed_dense(texts: list[str]) -> list[list[float]]:
    model = _dense_model()
    return [vec.tolist() for vec in model.embed(texts)]


def embed_sparse(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    """Returns list of (indices, values) tuples."""
    model = _sparse_model()
    result = []
    for sv in model.embed(texts):
        result.append((sv.indices.tolist(), sv.values.tolist()))
    return result
