"""Recall@K, MRR, nDCG@K computation."""
from __future__ import annotations
import math


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    for i, rid in enumerate(retrieved_ids):
        if rid in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    dcg = sum(
        1.0 / math.log2(i + 2)
        for i, rid in enumerate(retrieved_ids[:k])
        if rid in relevant_ids
    )
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant_ids), k)))
    return dcg / ideal if ideal > 0 else 0.0


def aggregate(per_query: list[dict]) -> dict:
    """Average metrics across queries. Only averages numeric fields — non-numeric
    metadata columns (id, question, mode, domain, ...) are ignored automatically."""
    if not per_query:
        return {}
    keys = [k for k in per_query[0] if isinstance(per_query[0][k], (int, float)) and not isinstance(per_query[0][k], bool)]
    return {k: round(sum(q[k] for q in per_query) / len(per_query), 4) for k in keys}
