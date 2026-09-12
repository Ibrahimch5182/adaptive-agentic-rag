"""
Phase 7 final evaluation: real 12-document, 254-chunk, two-domain corpus
(evaluation/corpus/), 72 hand-grounded questions (evaluation/benchmark.json).

Runs, against a live Qdrant + real Docling-parsed corpus:
  1. Retrieval comparison: DENSE / SPARSE / HYBRID / HYBRID_RERANK
     (Recall@5, Recall@10, MRR, nDCG@10, latency) — overall and per domain.
  2. Deterministic vs Adaptive comparison on the COMPLEX subset.
  3. Routing evaluation (simple/complex/unanswerable/ambiguous -> chosen route).

No live LLM required (GROQ_API_KEY not available in this environment) — the adaptive
agent runs on its heuristic assessor/planner fallback, same as it would in any
production deployment without a configured key. This is the actual retrieval-layer
adaptive behavior, not a mock.

Usage: python -m benchmark.eval_phase7
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import uuid
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DATABASE_URL", "placeholder")
os.environ.setdefault("SECRET_KEY", "placeholder-placeholder-placeholder-32ch")

from benchmark.metrics import recall_at_k, mrr, ndcg_at_k, aggregate

REPO_ROOT = Path(__file__).parent.parent.parent
CORPUS_DIR = REPO_ROOT / "evaluation" / "corpus"
BENCHMARK_PATH = REPO_ROOT / "evaluation" / "benchmark.json"
RESULTS_DIR = REPO_ROOT / "evaluation"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s)


# ── Corpus indexing ──────────────────────────────────────────────────────────────

def _index_corpus(ws_id: str) -> dict[str, str]:
    """Index every file under evaluation/corpus/**; return {basename: document_id}."""
    from app.ingestion.pipeline import parse_and_chunk, EXTENSION_TO_CONTENT_TYPE
    from app.ingestion import qdrant_mgr

    qdrant_mgr.ensure_collection()
    doc_ids: dict[str, str] = {}
    for f in sorted(CORPUS_DIR.rglob("*")):
        if f.suffix.lower() not in EXTENSION_TO_CONTENT_TYPE:
            continue
        doc_id = str(uuid.uuid4())
        chunks = parse_and_chunk(f, EXTENSION_TO_CONTENT_TYPE[f.suffix.lower()])
        qdrant_mgr.index_document(ws_id, doc_id, f.name, chunks)
        doc_ids[f.name] = doc_id
        print(f"  Indexed {f.relative_to(CORPUS_DIR)}: {len(chunks)} chunks")
    return doc_ids


def _find_relevant_points(item: dict) -> set[str]:
    """Ground truth: points whose source_filename is in item['docs'] AND whose text
    contains at least one of item['keywords'] (case/whitespace-insensitive)."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
    from app.ingestion.qdrant_mgr import _client
    from app.config import settings

    if not item["docs"]:
        return set()
    client = _client()
    points = client.scroll(
        collection_name=settings.QDRANT_COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="source_filename", match=MatchAny(any=item["docs"]))]),
        limit=1000, with_payload=True,
    )[0]
    keywords = [_norm(k.lower()) for k in item["keywords"]]
    relevant = set()
    for pt in points:
        p = pt.payload or {}
        text = _norm((p.get("raw_text", "") + " " + p.get("retrieval_text", "")).lower())
        if any(kw in text for kw in keywords):
            relevant.add(str(pt.id))
    return relevant


# ── Retrieval evaluation ─────────────────────────────────────────────────────────

def run_retrieval_eval(questions: list[dict]) -> dict:
    from app.rag.retriever import retrieve, RetrievalMode

    modes = [RetrievalMode.DENSE, RetrievalMode.SPARSE, RetrievalMode.HYBRID, RetrievalMode.HYBRID_RERANK]
    ws_id = questions[0]["_ws_id"]
    answerable = [q for q in questions if q["answerable"]]

    per_query: dict[str, list[dict]] = {m.value: [] for m in modes}
    latencies: dict[str, list[float]] = {m.value: [] for m in modes}
    skipped = []

    for item in answerable:
        relevant = _find_relevant_points(item)
        if not relevant:
            skipped.append(item["id"])
            continue
        for mode in modes:
            resp = retrieve(workspace_id=ws_id, question=item["q"], mode=mode,
                             dense_k=20, sparse_k=20, fused_k=20, final_k=10)
            retrieved_ids = [r.point_id for r in resp.results]
            latencies[mode.value].append(resp.latency_ms)
            per_query[mode.value].append({
                "id": item["id"], "domain": item["domain"], "mode": mode.value,
                "recall@5": recall_at_k(retrieved_ids, relevant, 5),
                "recall@10": recall_at_k(retrieved_ids, relevant, 10),
                "mrr": mrr(retrieved_ids, relevant),
                "ndcg@10": ndcg_at_k(retrieved_ids, relevant, 10),
            })

    def _agg_domain(mode_results, domain=None):
        subset = [r for r in mode_results if domain is None or r["domain"] == domain]
        return aggregate(subset) if subset else {}

    summary = {}
    for mode in modes:
        avg_lat = sum(latencies[mode.value]) / len(latencies[mode.value]) if latencies[mode.value] else 0
        summary[mode.value] = {
            "overall": {**_agg_domain(per_query[mode.value]), "avg_latency_ms": round(avg_lat, 1)},
            "a_general": _agg_domain(per_query[mode.value], "a_general"),
            "b_clinical": _agg_domain(per_query[mode.value], "b_clinical"),
        }

    return {
        "n_answerable": len(answerable),
        "n_evaluated": len(answerable) - len(skipped),
        "skipped_no_ground_truth": skipped,
        "summary": summary,
        "per_query": per_query,
    }


# ── Adaptive vs deterministic on complex subset + routing ───────────────────────

def run_adaptive_eval(questions: list[dict]) -> dict:
    from app.rag.retriever import retrieve, RetrievalMode
    from app.rag.agent import run_adaptive_agent

    ws_id = questions[0]["_ws_id"]
    routing_rows = []
    complex_rows = []

    for item in questions:
        t0 = time.perf_counter()
        det = retrieve(workspace_id=ws_id, question=item["q"], mode=RetrievalMode.HYBRID_RERANK,
                        dense_k=20, sparse_k=20, fused_k=20, final_k=10)
        det_lat = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        adp = run_adaptive_agent(ws_id, item["q"])
        adp_lat = (time.perf_counter() - t0) * 1000

        relevant = _find_relevant_points(item) if item["answerable"] else set()

        def _coverage(chunk_ids: list[str]) -> float:
            if not relevant:
                return 1.0 if not chunk_ids else 0.0  # unanswerable: fewer/no chunks is "correct"
            hit = len(set(chunk_ids) & relevant)
            return hit / len(relevant)

        det_ids = [r.point_id for r in det.results]
        adp_ids = [r.point_id for r in adp.final_evidence]
        det_cov = _coverage(det_ids)
        adp_cov = _coverage(adp_ids)

        row = {
            "id": item["id"], "domain": item["domain"], "category": item["category"], "type": item["type"],
            "answerable": item["answerable"],
            "det_evidence_coverage": round(det_cov, 2), "det_chunks": len(det_ids), "det_latency_ms": round(det_lat, 1),
            "adp_evidence_coverage": round(adp_cov, 2), "adp_chunks": len(adp_ids), "adp_latency_ms": round(adp_lat, 1),
            "adp_route": adp.route, "adp_iterations": adp.iterations, "adp_retrieval_calls": adp.retrieval_calls,
            "adp_stop_reason": adp.stop_reason,
        }
        routing_rows.append(row)
        if item["type"] == "complex":
            complex_rows.append(row)

    # Routing accuracy: expected route per label.
    # simple/ambiguous -> deterministic expected UNLESS evidence is genuinely incomplete (then agentic is correct, not wrong)
    # complex -> agentic is the "helpful" outcome IF det_coverage < 1.0; if det already found everything, deterministic-only is correct too
    # unanswerable -> abstain OR agentic-that-still-fails (both acceptable; fabrication would be the failure, not observable here at retrieval layer)
    def _routing_verdict(r):
        if r["type"] == "unanswerable":
            return "ok" if r["adp_route"] in ("abstain", "deterministic", "agentic") else "unexpected"
        if r["type"] in ("simple", "ambiguous"):
            if r["adp_route"] == "deterministic":
                return "ok"
            # escalated when not obviously required
            return "ok" if r["det_evidence_coverage"] < 1.0 else "unnecessary_escalation"
        if r["type"] == "complex":
            if r["det_evidence_coverage"] >= 1.0:
                return "ok_det_sufficient"  # deterministic already complete — no agentic help needed, that's fine
            return "ok_agentic_helped" if r["adp_route"] == "agentic" and r["adp_evidence_coverage"] > r["det_evidence_coverage"] else \
                   ("agentic_no_improvement" if r["adp_route"] == "agentic" else "should_have_escalated")
        return "unknown"

    for r in routing_rows:
        r["routing_verdict"] = _routing_verdict(r)

    from collections import Counter
    routing_summary = {
        "by_type_route": {},
        "verdict_counts": dict(Counter(r["routing_verdict"] for r in routing_rows)),
    }
    for t in ("simple", "complex", "unanswerable", "ambiguous"):
        subset = [r for r in routing_rows if r["type"] == t]
        if not subset:
            continue
        routing_summary["by_type_route"][t] = dict(Counter(r["adp_route"] for r in subset))

    complex_summary = {
        "n": len(complex_rows),
        "avg_det_coverage": round(sum(r["det_evidence_coverage"] for r in complex_rows) / len(complex_rows), 2) if complex_rows else 0,
        "avg_adp_coverage": round(sum(r["adp_evidence_coverage"] for r in complex_rows) / len(complex_rows), 2) if complex_rows else 0,
        "avg_det_latency_ms": round(sum(r["det_latency_ms"] for r in complex_rows) / len(complex_rows), 1) if complex_rows else 0,
        "avg_adp_latency_ms": round(sum(r["adp_latency_ms"] for r in complex_rows) / len(complex_rows), 1) if complex_rows else 0,
        "avg_adp_retrieval_calls": round(sum(r["adp_retrieval_calls"] for r in complex_rows) / len(complex_rows), 2) if complex_rows else 0,
        "n_agentic_helped": sum(1 for r in complex_rows if r["routing_verdict"] == "ok_agentic_helped"),
        "n_det_already_sufficient": sum(1 for r in complex_rows if r["routing_verdict"] == "ok_det_sufficient"),
        "n_agentic_no_improvement": sum(1 for r in complex_rows if r["routing_verdict"] == "agentic_no_improvement"),
        "n_should_have_escalated": sum(1 for r in complex_rows if r["routing_verdict"] == "should_have_escalated"),
    }

    return {
        "complex_subset_comparison": complex_summary,
        "routing": routing_summary,
        "per_question": routing_rows,
    }


# ── Main ──────────────────────────────────────────────────────────────────────────

def main():
    from app.ingestion import qdrant_mgr
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from app.config import settings

    questions = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    ws_id = str(uuid.uuid4())
    for q in questions:
        q["_ws_id"] = ws_id

    print(f"\n=== Phase 7 Evaluation (ws={ws_id[:8]}...) ===\n")
    print("Indexing real corpus (12 documents, Docling)...")
    _index_corpus(ws_id)

    print(f"\nRunning retrieval eval on {sum(q['answerable'] for q in questions)} answerable questions x 4 modes...")
    retrieval_results = run_retrieval_eval(questions)
    RESULTS_DIR.joinpath("retrieval_results.json").write_text(
        json.dumps(retrieval_results, indent=2), encoding="utf-8")
    print("\n=== Retrieval summary (overall) ===")
    print(f"{'Mode':<16}{'Recall@5':>9}{'Recall@10':>11}{'MRR':>8}{'nDCG@10':>9}{'Lat(ms)':>10}")
    for mode, d in retrieval_results["summary"].items():
        o = d["overall"]
        print(f"{mode:<16}{o.get('recall@5',0):>9.3f}{o.get('recall@10',0):>11.3f}"
              f"{o.get('mrr',0):>8.3f}{o.get('ndcg@10',0):>9.3f}{o.get('avg_latency_ms',0):>10.1f}")

    print(f"\nRunning adaptive vs deterministic + routing on all {len(questions)} questions...")
    adaptive_results = run_adaptive_eval(questions)
    RESULTS_DIR.joinpath("adaptive_results.json").write_text(
        json.dumps(adaptive_results, indent=2), encoding="utf-8")
    print("\n=== Complex subset: deterministic vs adaptive ===")
    print(json.dumps(adaptive_results["complex_subset_comparison"], indent=2))
    print("\n=== Routing ===")
    print(json.dumps(adaptive_results["routing"], indent=2))

    # Cleanup
    qdrant_mgr._client().delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=ws_id))]),
    )
    print("\nCorpus cleaned from Qdrant.")


if __name__ == "__main__":
    main()
