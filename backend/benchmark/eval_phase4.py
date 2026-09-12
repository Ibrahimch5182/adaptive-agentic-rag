"""
Phase 4 evaluation: Deterministic HYBRID_RERANK vs Adaptive Agentic RAG.

Corpus: same HR policy PDFs from Phase 3 benchmark (re-indexed for this eval).
Evaluates:
  1. Routing correctness (simple/complex/unanswerable)
  2. Retrieval success on complex questions
  3. Adaptive vs deterministic coverage comparison
  4. Latency and agent iteration counts

No live LLM required for retrieval evaluation (generation is separate).
"""
from __future__ import annotations
import json
import os
import sys
import uuid
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DATABASE_URL", "placeholder")
os.environ.setdefault("SECRET_KEY", "placeholder")

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Corpus (same as Phase 3 benchmark) ─────────────────────────────────────────

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

# Labeled questions with routing type and relevant sections
QUESTIONS = [
    # SIMPLE — single section, clear answer
    {"q": "How many sick days do employees get per year?", "type": "simple",
     "relevant_docs": ["leave_policy.pdf"], "relevant_sections": ["Sick Leave"],
     "keywords": ["10 days"]},
    {"q": "What is the VPN requirement for remote workers?", "type": "simple",
     "relevant_docs": ["remote_work_policy.pdf"], "relevant_sections": ["Security"],
     "keywords": ["VPN"]},
    {"q": "When are performance reviews held?", "type": "simple",
     "relevant_docs": ["performance_review.pdf"], "relevant_sections": ["Review Cycle"],
     "keywords": ["June", "December"]},
    {"q": "How many days of annual leave carry-over is allowed?", "type": "simple",
     "relevant_docs": ["leave_policy.pdf"], "relevant_sections": ["Annual Leave"],
     "keywords": ["10 days"]},
    {"q": "What equipment does the company provide to remote workers?", "type": "simple",
     "relevant_docs": ["remote_work_policy.pdf"], "relevant_sections": ["Equipment"],
     "keywords": ["laptop", "monitor"]},

    # COMPLEX — multiple sections or documents required
    {"q": "Describe all leave types available and their respective durations.", "type": "complex",
     "relevant_docs": ["leave_policy.pdf"], "relevant_sections": ["Annual Leave", "Sick Leave", "Parental Leave"],
     "keywords": ["25 days", "10 days", "16 weeks"]},
    {"q": "What are all the requirements and equipment for an approved remote worker?", "type": "complex",
     "relevant_docs": ["remote_work_policy.pdf"],
     "relevant_sections": ["Eligibility", "Equipment", "Security"],
     "keywords": ["6 months", "laptop", "VPN"]},
    {"q": "Compare annual leave and sick leave in terms of number of days and documentation requirements.", "type": "complex",
     "relevant_docs": ["leave_policy.pdf"], "relevant_sections": ["Annual Leave", "Sick Leave"],
     "keywords": ["25 days", "10 days", "medical certificate"]},
    {"q": "What is needed to qualify for promotion, including ratings required and review timeline?", "type": "complex",
     "relevant_docs": ["performance_review.pdf"],
     "relevant_sections": ["Review Cycle", "Rating Scale", "Promotion Criteria"],
     "keywords": ["Exceeds Expectations", "January", "5-point"]},
    {"q": "What are all the security obligations for remote workers, and how does the approval process work?", "type": "complex",
     "relevant_docs": ["remote_work_policy.pdf"],
     "relevant_sections": ["Eligibility", "Security"],
     "keywords": ["VPN", "department head", "24 hours"]},
    {"q": "Summarize all leave policies including annual, sick, and parental leave durations and conditions.", "type": "complex",
     "relevant_docs": ["leave_policy.pdf"],
     "relevant_sections": ["Annual Leave", "Sick Leave", "Parental Leave"],
     "keywords": ["25 days", "10 days", "16 weeks", "medical certificate"]},
    {"q": "What are the performance review dates, rating categories, and what rating is needed for promotion?", "type": "complex",
     "relevant_docs": ["performance_review.pdf"],
     "relevant_sections": ["Review Cycle", "Rating Scale", "Promotion Criteria"],
     "keywords": ["June", "December", "Outstanding", "Exceeds Expectations", "two consecutive"]},

    # UNANSWERABLE — not in documents
    {"q": "What is the company's annual revenue?", "type": "unanswerable",
     "relevant_docs": [], "relevant_sections": [], "keywords": []},
    {"q": "Who is the CEO of the company?", "type": "unanswerable",
     "relevant_docs": [], "relevant_sections": [], "keywords": []},
    {"q": "What is the office address?", "type": "unanswerable",
     "relevant_docs": [], "relevant_sections": [], "keywords": []},
]


def _create_pdf(sections):
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


def _retrieve_and_check(ws_id, q_meta, mode) -> dict:
    from app.rag.retriever import retrieve, RetrievalMode
    from app.ingestion.qdrant_mgr import _client
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from app.config import settings

    start = time.perf_counter()
    resp = retrieve(workspace_id=ws_id, question=q_meta["q"], mode=RetrievalMode(mode),
                    dense_k=20, sparse_k=20, fused_k=20, final_k=10)
    lat = (time.perf_counter() - start) * 1000

    retrieved_texts = " ".join(r.raw_text.lower() for r in resp.results)
    retrieved_sections = {r.section_title for r in resp.results}
    retrieved_docs = {r.filename for r in resp.results}

    # Check keyword coverage
    keywords = q_meta["keywords"]
    kw_hits = sum(1 for kw in keywords if kw.lower() in retrieved_texts) if keywords else 0
    kw_coverage = kw_hits / len(keywords) if keywords else 1.0  # unanswerable = 1.0 if nothing expected

    # For unanswerable: success means low keyword hits (nothing to find)
    if q_meta["type"] == "unanswerable":
        success = (len(resp.results) == 0) or (kw_coverage < 0.5)
    else:
        success = kw_coverage >= 0.5

    return {
        "q_type": q_meta["type"],
        "mode": mode,
        "chunks_retrieved": len(resp.results),
        "kw_coverage": round(kw_coverage, 2),
        "success": success,
        "latency_ms": round(lat, 1),
    }


def _adaptive_retrieve_and_check(ws_id, q_meta) -> dict:
    from app.rag.agent import run_adaptive_agent

    start = time.perf_counter()
    result = run_adaptive_agent(ws_id, q_meta["q"])
    lat = (time.perf_counter() - start) * 1000

    retrieved_texts = " ".join(r.raw_text.lower() for r in result.final_evidence)
    keywords = q_meta["keywords"]
    kw_hits = sum(1 for kw in keywords if kw.lower() in retrieved_texts) if keywords else 0
    kw_coverage = kw_hits / len(keywords) if keywords else 1.0

    if q_meta["type"] == "unanswerable":
        success = (len(result.final_evidence) == 0) or (kw_coverage < 0.5)
    else:
        success = kw_coverage >= 0.5

    return {
        "q_type": q_meta["type"],
        "mode": "adaptive",
        "route": result.route,
        "iterations": result.iterations,
        "retrieval_calls": result.retrieval_calls,
        "chunks_retrieved": len(result.final_evidence),
        "kw_coverage": round(kw_coverage, 2),
        "success": success,
        "stop_reason": result.stop_reason,
        "latency_ms": round(lat, 1),
    }


def run_eval():
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from app.config import settings

    ws_id = str(uuid.uuid4())
    print(f"\n=== Phase 4 Evaluation (ws={ws_id[:8]}…) ===\n")

    # Index corpus
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        qdrant_mgr.ensure_collection()
        for doc_spec in DOCUMENTS:
            doc_id = str(uuid.uuid4())
            p = tmp_dir / doc_spec["name"]
            p.write_bytes(_create_pdf(doc_spec["sections"]))
            chunks = parse_and_chunk(p, "application/pdf")
            qdrant_mgr.index_document(ws_id, doc_id, doc_spec["name"], chunks)
            print(f"  Indexed: {doc_spec['name']} ({len(chunks)} chunks)")

    # Evaluate all questions
    det_results = []
    adp_results = []

    print(f"\nRunning {len(QUESTIONS)} questions...\n")
    for q in QUESTIONS:
        det = _retrieve_and_check(ws_id, q, "hybrid_rerank")
        adp = _adaptive_retrieve_and_check(ws_id, q)
        det_results.append({**det, "question": q["q"]})
        adp_results.append({**adp, "question": q["q"]})

    # Aggregate
    def _agg(results, q_type=None):
        subset = [r for r in results if q_type is None or r["q_type"] == q_type]
        if not subset:
            return {}
        return {
            "n": len(subset),
            "success_rate": round(sum(r["success"] for r in subset) / len(subset), 2),
            "avg_kw_coverage": round(sum(r["kw_coverage"] for r in subset) / len(subset), 2),
            "avg_latency_ms": round(sum(r["latency_ms"] for r in subset) / len(subset), 1),
            "avg_chunks": round(sum(r["chunks_retrieved"] for r in subset) / len(subset), 1),
        }

    # Routing analysis
    simple_adp = [r for r in adp_results if r["q_type"] == "simple"]
    complex_adp = [r for r in adp_results if r["q_type"] == "complex"]
    unanswerable_adp = [r for r in adp_results if r["q_type"] == "unanswerable"]

    routing_table = {
        "simple_routed_deterministic": sum(1 for r in simple_adp if r.get("route") == "deterministic"),
        "simple_total": len(simple_adp),
        "complex_entered_agentic": sum(1 for r in complex_adp if r.get("iterations", 0) > 0),
        "complex_total": len(complex_adp),
        "unanswerable_abstained_or_low_coverage": sum(1 for r in unanswerable_adp if r.get("success", False)),
        "unanswerable_total": len(unanswerable_adp),
    }

    # Print summary
    print("\n=== Deterministic vs Adaptive Comparison ===")
    for q_type in ("simple", "complex", "unanswerable"):
        det_agg = _agg(det_results, q_type)
        adp_agg = _agg(adp_results, q_type)
        print(f"\n{q_type.upper()} (n={det_agg['n']}):")
        print(f"  Deterministic: success={det_agg['success_rate']:.0%}  kw_cov={det_agg['avg_kw_coverage']:.0%}  lat={det_agg['avg_latency_ms']:.0f}ms")
        print(f"  Adaptive:      success={adp_agg['success_rate']:.0%}  kw_cov={adp_agg['avg_kw_coverage']:.0%}  lat={adp_agg['avg_latency_ms']:.0f}ms  avg_calls={sum(r.get('retrieval_calls',1) for r in adp_results if r['q_type']==q_type)/len([r for r in adp_results if r['q_type']==q_type]):.1f}")

    print("\n=== Routing ===")
    print(f"  Simple   -> deterministic: {routing_table['simple_routed_deterministic']}/{routing_table['simple_total']}")
    print(f"  Complex  -> agentic loop: {routing_table['complex_entered_agentic']}/{routing_table['complex_total']}")
    print(f"  Unanswerable -> abstain/low: {routing_table['unanswerable_abstained_or_low_coverage']}/{routing_table['unanswerable_total']}")

    # Save
    output = {
        "eval_id": str(uuid.uuid4()),
        "routing": routing_table,
        "deterministic": {qt: _agg(det_results, qt) for qt in ("simple", "complex", "unanswerable")},
        "adaptive": {qt: _agg(adp_results, qt) for qt in ("simple", "complex", "unanswerable")},
        "per_question": list(zip(
            [{"question": r["question"], "type": r["q_type"]} for r in det_results],
            [{"det_success": d["success"], "adp_success": a["success"],
              "det_kw": d["kw_coverage"], "adp_kw": a["kw_coverage"],
              "route": a.get("route", "?"), "iterations": a.get("iterations", 0)}
             for d, a in zip(det_results, adp_results)]
        )),
    }

    out_path = RESULTS_DIR / "phase4_eval.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {out_path}")

    # Cleanup
    qdrant_mgr._client().delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=ws_id))]),
    )
    print("Corpus cleaned.")
    return output


if __name__ == "__main__":
    run_eval()
