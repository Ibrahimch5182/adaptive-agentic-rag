"""Qdrant collection management and document indexing/deletion."""
from __future__ import annotations
import uuid
import logging
from functools import lru_cache
from app.config import settings
from app.ingestion.pipeline import ChunkData

log = logging.getLogger(__name__)

# Deterministic namespace for chunk point IDs
_CHUNK_NS = uuid.UUID("b7e9f3a1-2c4d-5e6f-7890-abcdef012345")


def _chunk_point_id(document_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_CHUNK_NS, f"{document_id}:{chunk_index}"))


@lru_cache(maxsize=1)
def _client():
    from qdrant_client import QdrantClient
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)


def ensure_collection() -> None:
    """Create the Qdrant collection and payload indexes if they do not exist."""
    from qdrant_client.models import (
        VectorParams, Distance, SparseVectorParams, SparseIndexParams,
        PayloadSchemaType,
    )
    client = _client()
    if client.collection_exists(settings.QDRANT_COLLECTION):
        return
    client.create_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config={"dense": VectorParams(size=settings.DENSE_VECTOR_SIZE, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams())},
    )
    for field in ("workspace_id", "document_id"):
        client.create_payload_index(
            settings.QDRANT_COLLECTION,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )
    log.info("Created Qdrant collection '%s'", settings.QDRANT_COLLECTION)


def delete_document_points(document_id: str) -> None:
    """Remove all Qdrant points belonging to a specific document."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = _client()
    client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        ),
        wait=True,
    )


def index_document(
    workspace_id: str,
    document_id: str,
    source_filename: str,
    chunks: list[ChunkData],
) -> None:
    """Embed and upsert all chunks for a document into Qdrant."""
    from qdrant_client.models import PointStruct, SparseVector
    from app.ingestion.embedder import embed_dense, embed_sparse

    client = _client()
    retrieval_texts = [c.retrieval_text for c in chunks]

    dense_vecs = embed_dense(retrieval_texts)
    sparse_vecs = embed_sparse(retrieval_texts)

    points: list[PointStruct] = []
    for i, chunk in enumerate(chunks):
        points.append(PointStruct(
            id=_chunk_point_id(document_id, chunk.chunk_index),
            vector={
                "dense": dense_vecs[i],
                "sparse": SparseVector(
                    indices=sparse_vecs[i][0],
                    values=sparse_vecs[i][1],
                ),
            },
            payload={
                "workspace_id": workspace_id,
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "raw_text": chunk.raw_text,
                "retrieval_text": chunk.retrieval_text,
                "section_title": chunk.section_title,
                "page_numbers": chunk.page_numbers,
                "source_filename": source_filename,
            },
        ))

    # Upsert in batches of 64
    batch_size = 64
    for start in range(0, len(points), batch_size):
        client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points[start : start + batch_size],
            wait=True,
        )
    log.info(
        "Indexed %d chunks for document %s in workspace %s",
        len(chunks), document_id, workspace_id,
    )


def count_document_points(document_id: str) -> int:
    """Return the number of indexed points for a document (for test verification)."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = _client()
    result = client.count(
        collection_name=settings.QDRANT_COLLECTION,
        count_filter=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        ),
        exact=True,
    )
    return result.count
