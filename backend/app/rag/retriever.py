"""
Workspace-scoped retrieval service.

Every retrieval path enforces workspace_id as a mandatory Qdrant filter —
the filter is applied at the datastore layer, not post-retrieval.

Modes:
  DENSE          — single dense vector query
  SPARSE         — single sparse (BM25) query
  HYBRID         — Qdrant built-in RRF over dense+sparse prefetch
  HYBRID_RERANK  — HYBRID followed by cross-encoder reranking
"""
from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from app.config import settings

log = logging.getLogger(__name__)


class RetrievalMode(str, Enum):
    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


@dataclass
class RetrievalResult:
    point_id: str
    document_id: str
    chunk_index: int
    raw_text: str
    retrieval_text: str
    filename: str
    section_title: str
    page_numbers: list[int]
    score: float
    mode: str
    dense_rank: int | None = None
    sparse_rank: int | None = None
    rerank_score: float | None = None


@dataclass
class RetrievalResponse:
    results: list[RetrievalResult]
    mode: str
    latency_ms: float
    dense_latency_ms: float = 0.0
    sparse_latency_ms: float = 0.0
    rerank_latency_ms: float = 0.0


@lru_cache(maxsize=1)
def _qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)


def _workspace_filter(workspace_id: str):
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    return Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id))])


def _payload_to_result(point, mode: str, rank: int | None = None) -> RetrievalResult:
    p = point.payload or {}
    return RetrievalResult(
        point_id=str(point.id),
        document_id=p.get("document_id", ""),
        chunk_index=p.get("chunk_index", 0),
        raw_text=p.get("raw_text", ""),
        retrieval_text=p.get("retrieval_text", ""),
        filename=p.get("source_filename", ""),
        section_title=p.get("section_title", ""),
        page_numbers=p.get("page_numbers", []),
        score=point.score,
        mode=mode,
    )


def retrieve(
    workspace_id: str,
    question: str,
    mode: RetrievalMode = RetrievalMode.HYBRID_RERANK,
    dense_k: int | None = None,
    sparse_k: int | None = None,
    fused_k: int | None = None,
    final_k: int | None = None,
) -> RetrievalResponse:
    """
    Main retrieval entry point.

    workspace_id is already server-validated before this call.
    All Qdrant queries carry workspace_id as a mandatory filter.
    """
    dense_k = dense_k or settings.RETRIEVAL_DENSE_K
    sparse_k = sparse_k or settings.RETRIEVAL_SPARSE_K
    fused_k = fused_k or settings.RETRIEVAL_FUSED_K
    final_k = final_k or settings.RERANK_TOP_K

    t0 = time.perf_counter()

    if mode == RetrievalMode.DENSE:
        resp = _dense(workspace_id, question, dense_k)
    elif mode == RetrievalMode.SPARSE:
        resp = _sparse(workspace_id, question, sparse_k)
    elif mode == RetrievalMode.HYBRID:
        resp = _hybrid(workspace_id, question, dense_k, sparse_k, fused_k)
    else:  # HYBRID_RERANK
        resp = _hybrid_rerank(workspace_id, question, dense_k, sparse_k, fused_k, final_k)

    resp.latency_ms = (time.perf_counter() - t0) * 1000
    return resp


def _dense(workspace_id: str, question: str, k: int) -> RetrievalResponse:
    from app.ingestion.embedder import embed_dense
    t0 = time.perf_counter()
    vec = embed_dense([question])[0]
    points = _qdrant().query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=vec,
        using="dense",
        query_filter=_workspace_filter(workspace_id),
        limit=k,
        with_payload=True,
    ).points
    lat = (time.perf_counter() - t0) * 1000
    results = [_payload_to_result(p, "dense") for p in points]
    for i, r in enumerate(results):
        r.dense_rank = i + 1
    return RetrievalResponse(results=results, mode="dense", latency_ms=lat, dense_latency_ms=lat)


def _sparse(workspace_id: str, question: str, k: int) -> RetrievalResponse:
    from app.ingestion.embedder import embed_sparse
    from qdrant_client.models import SparseVector
    t0 = time.perf_counter()
    indices, values = embed_sparse([question])[0]
    points = _qdrant().query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=SparseVector(indices=indices, values=values),
        using="sparse",
        query_filter=_workspace_filter(workspace_id),
        limit=k,
        with_payload=True,
    ).points
    lat = (time.perf_counter() - t0) * 1000
    results = [_payload_to_result(p, "sparse") for p in points]
    for i, r in enumerate(results):
        r.sparse_rank = i + 1
    return RetrievalResponse(results=results, mode="sparse", latency_ms=lat, sparse_latency_ms=lat)


def _hybrid(workspace_id: str, question: str, dense_k: int, sparse_k: int, fused_k: int) -> RetrievalResponse:
    from app.ingestion.embedder import embed_dense, embed_sparse
    from qdrant_client.models import Prefetch, FusionQuery, Fusion, SparseVector
    ws_filter = _workspace_filter(workspace_id)

    t_dense = time.perf_counter()
    dense_vec = embed_dense([question])[0]
    d_lat = (time.perf_counter() - t_dense) * 1000

    t_sparse = time.perf_counter()
    indices, values = embed_sparse([question])[0]
    s_lat = (time.perf_counter() - t_sparse) * 1000

    t0 = time.perf_counter()
    points = _qdrant().query_points(
        collection_name=settings.QDRANT_COLLECTION,
        prefetch=[
            Prefetch(query=dense_vec, using="dense", limit=dense_k, filter=ws_filter),
            Prefetch(
                query=SparseVector(indices=indices, values=values),
                using="sparse",
                limit=sparse_k,
                filter=ws_filter,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        query_filter=ws_filter,
        limit=fused_k,
        with_payload=True,
    ).points
    q_lat = (time.perf_counter() - t0) * 1000

    results = [_payload_to_result(p, "hybrid") for p in points]
    return RetrievalResponse(
        results=results,
        mode="hybrid",
        latency_ms=d_lat + s_lat + q_lat,
        dense_latency_ms=d_lat,
        sparse_latency_ms=s_lat,
    )


def _hybrid_rerank(
    workspace_id: str,
    question: str,
    dense_k: int,
    sparse_k: int,
    fused_k: int,
    final_k: int,
) -> RetrievalResponse:
    from app.rag.reranker import rerank
    hybrid_resp = _hybrid(workspace_id, question, dense_k, sparse_k, fused_k)

    t0 = time.perf_counter()
    reranked = rerank(question, hybrid_resp.results, top_k=final_k)
    r_lat = (time.perf_counter() - t0) * 1000

    return RetrievalResponse(
        results=reranked,
        mode="hybrid_rerank",
        latency_ms=hybrid_resp.latency_ms + r_lat,
        dense_latency_ms=hybrid_resp.dense_latency_ms,
        sparse_latency_ms=hybrid_resp.sparse_latency_ms,
        rerank_latency_ms=r_lat,
    )
