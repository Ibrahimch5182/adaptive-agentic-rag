"""
Phase 3 retrieval benchmark.

Creates a self-contained test corpus, indexes it, discovers ground-truth chunk IDs,
runs all 4 retrieval modes, and computes Recall@5, Recall@10, MRR, nDCG@10.

Usage:  python -m benchmark.runner
Requires: Qdrant + fastembed models available.
"""
from __future__ import annotations
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DATABASE_URL", "placeholder")
os.environ.setdefault("SECRET_KEY", "placeholder")

from benchmark.metrics import recall_at_k, mrr, ndcg_at_k, aggregate

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Corpus creation ─────────────────────────────────────────────────────────────

DOCUMENTS = [
    {
        "name": "leave_policy.pdf",
        "sections": [
            ("Annual Leave", "Employees receive 25 days of annual leave per year. Leave must be approved two weeks in advance by the line manager. Unused leave can be carried over up to 10 days."),
            ("Sick Leave", "Employees are entitled to 10 days of paid sick leave annually. A medical certificate is required for absences longer than 3 consecutive days."),
            ("Parental Leave", "Primary caregivers receive 16 weeks of paid parental leave. Secondary caregivers receive 4 weeks. Leave must be taken within 12 months of the child's birth."),
        ]
    },
    {
        "name": "remote_work_policy.pdf",
        "sections": [
            ("Eligibility", "Employees with at least 6 months tenure may apply for remote work. Remote work requires written approval from the department head."),
            ("Equipment", "The company provides a laptop and monitor for approved remote workers. Employees are responsible for their internet connection costs."),
            ("Security", "Remote workers must use the company VPN at all times. Data must not be stored on personal devices. All incidents must be reported within 24 hours."),
        ]
    },
    {
        "name": "performance_review.pdf",
        "sections": [
            ("Review Cycle", "Performance reviews occur twice yearly in June and December. Each review includes a self-assessment and a manager assessment."),
            ("Rating Scale", "Performance is rated on a 5-point scale: Outstanding, Exceeds Expectations, Meets Expectations, Needs Improvement, Unsatisfactory."),
            ("Promotion Criteria", "Promotion eligibility requires two consecutive Exceeds Expectations ratings. A promotion committee reviews all candidates in January."),
        ]
    },
]

QUESTIONS = [
    # Semantic/paraphrase questions
    {"question": "How many vacation days do employees get each year?", "doc": "leave_policy.pdf", "section": "Annual Leave", "keywords": ["25 days", "annual leave"]},
    {"question": "What is the requirement for manager sign-off on holidays?", "doc": "leave_policy.pdf", "section": "Annual Leave", "keywords": ["approved", "line manager"]},
    {"question": "Can employees save unused vacation for next year?", "doc": "leave_policy.pdf", "section": "Annual Leave", "keywords": ["carry over", "unused"]},
    {"question": "How many sick days are workers allowed?", "doc": "leave_policy.pdf", "section": "Sick Leave", "keywords": ["10 days", "sick leave"]},
    {"question": "When does a doctor's note become necessary?", "doc": "leave_policy.pdf", "section": "Sick Leave", "keywords": ["medical certificate", "3 consecutive"]},
    {"question": "How long is maternity/paternity leave?", "doc": "leave_policy.pdf", "section": "Parental Leave", "keywords": ["16 weeks", "parental leave"]},
    {"question": "What tenure is needed to work from home?", "doc": "remote_work_policy.pdf", "section": "Eligibility", "keywords": ["6 months", "tenure"]},
    {"question": "Who must approve working remotely?", "doc": "remote_work_policy.pdf", "section": "Eligibility", "keywords": ["department head", "approval"]},
    {"question": "Does the company supply equipment for remote workers?", "doc": "remote_work_policy.pdf", "section": "Equipment", "keywords": ["laptop", "monitor"]},
    {"question": "What are the cybersecurity rules for remote employees?", "doc": "remote_work_policy.pdf", "section": "Security", "keywords": ["VPN", "personal devices"]},
    # Lexical/exact-term questions
    {"question": "VPN policy for remote workers", "doc": "remote_work_policy.pdf", "section": "Security", "keywords": ["VPN"]},
    {"question": "medical certificate requirement", "doc": "leave_policy.pdf", "section": "Sick Leave", "keywords": ["medical certificate"]},
    {"question": "promotion committee review", "doc": "performance_review.pdf", "section": "Promotion Criteria", "keywords": ["promotion committee"]},
    # Multi-section questions
    {"question": "What are the performance review dates and the ratings used?", "doc": "performance_review.pdf", "section": "Review Cycle", "keywords": ["June", "December"]},
    {"question": "When are performance reviews and what is needed for promotion?", "doc": "performance_review.pdf", "section": "Promotion Criteria", "keywords": ["promotion", "Exceeds Expectations"]},
    # Specific fact retrieval
    {"question": "How many days of carry-over leave are allowed?", "doc": "leave_policy.pdf", "section": "Annual Leave", "keywords": ["10 days"]},
    {"question": "What is the secondary caregiver parental leave entitlement?", "doc": "leave_policy.pdf", "section": "Parental Leave", "keywords": ["4 weeks"]},
    {"question": "What score scale is used for performance evaluations?", "doc": "performance_review.pdf", "section": "Rating Scale", "keywords": ["5-point", "Outstanding"]},
    {"question": "What happens to data security incidents when working remotely?", "doc": "remote_work_policy.pdf", "section": "Security", "keywords": ["24 hours", "reported"]},
    {"question": "How many consecutive Exceeds ratings are needed for promotion?", "doc": "performance_review.pdf", "section": "Promotion Criteria", "keywords": ["two consecutive"]},
]


def _create_pdf(sections: list[tuple[str, str]]) -> bytes:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    for heading, body in sections:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 10, heading, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 7, body)
        pdf.ln(3)
    return bytes(pdf.output())


def _index_corpus(ws_id: str, tmp_dir: Path) -> dict[str, list[str]]:
    """Index all corpus documents; return {doc_name: [point_ids]}."""
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from app.ingestion.embedder import embed_dense, embed_sparse
    from qdrant_client.models import PointStruct, SparseVector, Filter, FieldCondition, MatchValue
    from app.ingestion.qdrant_mgr import _client, _chunk_point_id
    from app.config import settings

    qdrant_mgr.ensure_collection()
    doc_point_map: dict[str, list[str]] = {}

    for doc_spec in DOCUMENTS:
        doc_id = str(uuid.uuid4())
        pdf_path = tmp_dir / doc_spec["name"]
        pdf_path.write_bytes(_create_pdf(doc_spec["sections"]))

        chunks = parse_and_chunk(pdf_path, "application/pdf")
        qdrant_mgr.index_document(ws_id, doc_id, doc_spec["name"], chunks)

        # Collect point IDs
        client = _client()
        results = client.scroll(
            collection_name=settings.QDRANT_COLLECTION,
            scroll_filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))]),
            limit=200,
            with_payload=True,
        )
        doc_point_map[doc_spec["name"]] = [str(pt.id) for pt in results[0]]
        print(f"  Indexed: {doc_spec['name']} ({len(doc_point_map[doc_spec['name']])} chunks)")

    return doc_point_map


def _find_relevant_points(question_meta: dict, doc_point_map: dict) -> set[str]:
    """
    Ground truth: points from the target document+section that contain any keyword.
    Uses direct Qdrant scroll to read actual chunk content.
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from app.ingestion.qdrant_mgr import _client
    from app.config import settings

    target_doc = question_meta["doc"]
    keywords = [kw.lower() for kw in question_meta["keywords"]]

    client = _client()
    all_points = client.scroll(
        collection_name=settings.QDRANT_COLLECTION,
        scroll_filter=Filter(must=[]),
        limit=1000,
        with_payload=True,
    )[0]

    relevant = set()
    for pt in all_points:
        p = pt.payload or {}
        if p.get("source_filename") != target_doc:
            continue
        raw = p.get("raw_text", "").lower()
        retrieval = p.get("retrieval_text", "").lower()
        if any(kw in raw or kw in retrieval for kw in keywords):
            relevant.add(str(pt.id))
    return relevant


def run_benchmark():
    import tempfile
    from app.rag.retriever import retrieve, RetrievalMode

    ws_id = str(uuid.uuid4())
    print(f"\n=== Phase 3 Benchmark (workspace={ws_id[:8]}…) ===\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        print("Indexing corpus...")
        doc_point_map = _index_corpus(ws_id, tmp_dir)

    modes = [RetrievalMode.DENSE, RetrievalMode.SPARSE, RetrievalMode.HYBRID, RetrievalMode.HYBRID_RERANK]
    all_results: dict[str, list[dict]] = {m.value: [] for m in modes}
    latencies: dict[str, list[float]] = {m.value: [] for m in modes}

    print(f"\nRunning {len(QUESTIONS)} questions × {len(modes)} modes...\n")

    for q_meta in QUESTIONS:
        relevant = _find_relevant_points(q_meta, doc_point_map)
        if not relevant:
            print(f"  [WARN] No ground-truth for: {q_meta['question'][:60]}")
            continue

        for mode in modes:
            resp = retrieve(ws_id, q_meta["question"], mode=mode, dense_k=20, sparse_k=20, fused_k=20, final_k=10)
            retrieved_ids = [r.point_id for r in resp.results]
            latencies[mode.value].append(resp.latency_ms)

            all_results[mode.value].append({
                "question": q_meta["question"],
                "mode": mode.value,
                "recall@5": recall_at_k(retrieved_ids, relevant, 5),
                "recall@10": recall_at_k(retrieved_ids, relevant, 10),
                "mrr": mrr(retrieved_ids, relevant),
                "ndcg@10": ndcg_at_k(retrieved_ids, relevant, 10),
            })

    # Aggregate
    summary = {}
    print("\n=== Results ===\n")
    print(f"{'Mode':<20} {'Recall@5':>9} {'Recall@10':>10} {'MRR':>8} {'nDCG@10':>9} {'Lat(ms)':>9}")
    print("-" * 70)
    for mode in modes:
        agg = aggregate(all_results[mode.value])
        avg_lat = sum(latencies[mode.value]) / len(latencies[mode.value]) if latencies[mode.value] else 0
        summary[mode.value] = {**agg, "avg_latency_ms": round(avg_lat, 1)}
        print(f"{mode.value:<20} {agg.get('recall@5', 0):>9.3f} {agg.get('recall@10', 0):>10.3f} "
              f"{agg.get('mrr', 0):>8.3f} {agg.get('ndcg@10', 0):>9.3f} {avg_lat:>9.1f}")

    # Save
    output = {
        "benchmark_id": str(uuid.uuid4()),
        "questions": len(QUESTIONS),
        "corpus_size": sum(len(v) for v in doc_point_map.values()),
        "summary": summary,
        "per_query": all_results,
    }
    out_path = RESULTS_DIR / "phase3_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {out_path}")

    # Cleanup
    from app.ingestion import qdrant_mgr
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    for doc_ids in doc_point_map.values():
        pass  # delete by workspace_id
    qdrant_mgr._client().delete(
        collection_name=__import__("app.config", fromlist=["settings"]).settings.QDRANT_COLLECTION,
        points_selector=Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=ws_id))]),
    )
    print("Corpus cleaned up.")
    return summary


if __name__ == "__main__":
    run_benchmark()
