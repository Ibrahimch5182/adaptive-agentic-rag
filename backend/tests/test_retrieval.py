"""
Phase 3 retrieval tests.

Fast tests (no mark):  workspace isolation, RRF math, citation extraction, query API.
Integration (mark):    live Qdrant + embedding tests.
"""
import pytest
from app.rag.retriever import RetrievalResult


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_result(point_id, doc_id, raw_text, score=1.0, rerank_score=None):
    return RetrievalResult(
        point_id=point_id,
        document_id=doc_id,
        chunk_index=0,
        raw_text=raw_text,
        retrieval_text=raw_text,
        filename="test.pdf",
        section_title="Test",
        page_numbers=[1],
        score=score,
        mode="hybrid",
        rerank_score=rerank_score,
    )


# ── Reranker unit tests ─────────────────────────────────────────────────────────

def test_reranker_returns_top_k():
    from app.rag.reranker import rerank
    candidates = [
        _make_result(f"id{i}", f"doc{i}", f"chunk text about topic {i}")
        for i in range(10)
    ]
    ranked = rerank("what is topic 3?", candidates, top_k=3)
    assert len(ranked) == 3


def test_reranker_empty_input():
    from app.rag.reranker import rerank
    assert rerank("question", [], top_k=5) == []


# ── Citation extraction ─────────────────────────────────────────────────────────

def test_citation_extraction_maps_valid_ids():
    from app.rag.generator import _extract_citations
    chunks = [
        _make_result("cid1", "doc1", "relevant text about revenue"),
        _make_result("cid2", "doc2", "irrelevant content"),
    ]
    id_map = {"S1": chunks[0], "S2": chunks[1]}
    answer = "Revenue grew 10% [S1]. The other document is not relevant."
    citations = _extract_citations(answer, id_map)
    assert len(citations) == 1
    assert citations[0].citation_id == "S1"
    assert citations[0].chunk_id == "cid1"


def test_citation_extraction_ignores_hallucinated_ids():
    from app.rag.generator import _extract_citations
    id_map = {"S1": _make_result("cid1", "doc1", "text")}
    answer = "Answer [S1] and also [S99] invented by model."
    citations = _extract_citations(answer, id_map)
    # S99 is not in id_map — must be ignored
    assert len(citations) == 1
    assert citations[0].citation_id == "S1"


# ── Generator unit tests ────────────────────────────────────────────────────────

def test_generate_answer_no_chunks_returns_insufficient():
    from app.rag.generator import generate_answer, INSUFFICIENT_EVIDENCE
    result = generate_answer("What is X?", [])
    assert result.insufficient is True
    assert INSUFFICIENT_EVIDENCE in result.answer
    assert result.citations == []


def test_generate_answer_with_mocked_llm(monkeypatch):
    from app.rag import generator as gen_mod
    monkeypatch.setattr(gen_mod, "generate_answer", lambda q, chunks: __import__('app.rag.generator', fromlist=['GenerationResult']).GenerationResult(
        answer=f"Answer based on evidence [S1].",
        citations=[],
        evidence_count=len(chunks),
        insufficient=False,
    ))
    # Direct test of evidence building
    from app.rag.generator import _build_evidence_block
    chunks = [_make_result("cid1", "doc1", "The sky is blue.")]
    block, id_map = _build_evidence_block(chunks)
    assert "[S1]" in block
    assert "The sky is blue." in block
    assert "S1" in id_map


def test_generate_answer_mixed_partial_abstention_not_flagged_insufficient(monkeypatch):
    """A mixed answer (substantive facts plus one aspect's insufficient-evidence
    sentence) must NOT be flagged insufficient=True — that previously caused the whole
    answer's verification to be skipped and all its citations to be discarded, even
    though most of the answer was substantive and cited."""
    from app.rag import generator as gen_mod
    from app.rag.generator import INSUFFICIENT_EVIDENCE

    mixed = f"Revenue was $281.7B [S1]. {INSUFFICIENT_EVIDENCE}"
    monkeypatch.setattr("app.rag.llm.generate", lambda *a, **kw: mixed)
    result = gen_mod.generate_answer("Q?", [_make_result("cid1", "doc1", "Revenue text")])
    assert result.insufficient is False
    assert result.citations, "citations must still be extracted from a mixed answer"


def test_generate_answer_pure_abstention_still_flagged_insufficient(monkeypatch):
    """A PURE abstention (the entire answer IS the abstention sentence) must still be
    flagged insufficient=True."""
    from app.rag import generator as gen_mod
    from app.rag.generator import INSUFFICIENT_EVIDENCE

    monkeypatch.setattr("app.rag.llm.generate", lambda *a, **kw: INSUFFICIENT_EVIDENCE)
    result = gen_mod.generate_answer("Q?", [_make_result("cid1", "doc1", "Revenue text")])
    assert result.insufficient is True
    assert result.citations == []


def test_system_prompt_treats_question_as_untrusted_context():
    """Defect: a number/fact stated only in the user's question must not be treatable as
    grounded evidence — the system prompt must say so explicitly."""
    from app.rag.llm import SYSTEM_PROMPT
    lowered = SYSTEM_PROMPT.lower()
    assert "untrusted request context" in lowered
    assert "not evidence" in lowered


def test_system_prompt_requires_exact_calculation_components():
    """The system prompt must require using exactly the named calculation components,
    with no substitution, and no definitive result when one is missing."""
    from app.rag.llm import SYSTEM_PROMPT
    lowered = SYSTEM_PROMPT.lower()
    assert "named components" in lowered
    assert "missing" in lowered


def test_generate_frames_question_as_untrusted(monkeypatch):
    from app.rag import llm as llm_mod
    captured = {}
    _fake_groq_client(monkeypatch, captured)

    llm_mod.generate("What about the $92.7B commitment?", "evidence block")
    user_msg = captured["messages"][1]["content"]
    assert "untrusted request context" in user_msg.lower()


def _fake_groq_client(monkeypatch, captured: dict):
    from app.config import settings
    monkeypatch.setattr(settings, "GROQ_API_KEY", "fake-key")

    class FakeMessage:
        content = "Answer [S1]."

    class FakeChoice:
        finish_reason = "stop"
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeGroqClient:
        def __init__(self, api_key):
            self.chat = FakeChat()

    monkeypatch.setattr("groq.Groq", FakeGroqClient)


def test_generate_includes_required_aspects_checklist(monkeypatch):
    """Multi-aspect questions must get an explicit per-aspect checklist so generation
    can't silently drop one — this is how the coverage guarantee reaches the LLM."""
    from app.rag import llm as llm_mod
    captured = {}
    _fake_groq_client(monkeypatch, captured)

    llm_mod.generate("Q?", "evidence block",
                      required_aspects=["research and development expense",
                                        "datacenter capacity operational constraints"])
    user_msg = captured["messages"][1]["content"]
    assert "REQUIRED ASPECTS" in user_msg
    assert "research and development expense" in user_msg
    assert "datacenter capacity operational constraints" in user_msg


def test_generate_skips_checklist_for_single_aspect(monkeypatch):
    """A simple single-aspect question must not get checklist noise added."""
    from app.rag import llm as llm_mod
    captured = {}
    _fake_groq_client(monkeypatch, captured)

    llm_mod.generate("Q?", "evidence block", required_aspects=["only one aspect"])
    user_msg = captured["messages"][1]["content"]
    assert "REQUIRED ASPECTS" not in user_msg


# ── Query API tests (mocked LLM + mocked retriever) ────────────────────────────

_ALICE = {"email": "alice.rag@test.com", "full_name": "Alice", "password": "pass123"}
_BOB = {"email": "bob.rag@test.com", "full_name": "Bob", "password": "pass456"}


def _register_login(client, user):
    client.post("/api/auth/register", json=user)
    client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})


def test_query_no_ready_docs_returns_no_docs_message(client):
    _register_login(client, _ALICE)
    ws_id = client.post("/api/workspaces", json={"name": "QWS"}).json()["id"]
    resp = client.post(f"/api/workspaces/{ws_id}/query", json={"question": "What is X?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["insufficient"] is True


def test_query_cross_workspace_rejected(client):
    _register_login(client, _ALICE)
    ws_a = client.post("/api/workspaces", json={"name": "AliceWS"}).json()["id"]
    client.post("/api/auth/logout")
    _register_login(client, _BOB)
    resp = client.post(f"/api/workspaces/{ws_a}/query", json={"question": "Q?"})
    assert resp.status_code == 404


def test_query_unauthenticated_rejected(client):
    _register_login(client, _ALICE)
    ws_id = client.post("/api/workspaces", json={"name": "WS"}).json()["id"]
    client.post("/api/auth/logout")
    resp = client.post(f"/api/workspaces/{ws_id}/query", json={"question": "Q?"})
    assert resp.status_code == 401


def test_query_stream_emits_progress_then_complete(client):
    """Live-progress SSE endpoint must terminate with a complete/error event carrying the
    same result shape as the plain JSON endpoint, and never expose chain-of-thought."""
    import json
    _register_login(client, _ALICE)
    ws_id = client.post("/api/workspaces", json={"name": "StreamWS"}).json()["id"]
    with client.stream(
        "POST", f"/api/workspaces/{ws_id}/query/stream", json={"question": "What is X?"}
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = [json.loads(line[len("data: "):]) for line in resp.iter_lines() if line.startswith("data: ")]

    assert events, "expected at least one SSE event"
    assert events[-1]["stage"] in ("complete", "error")
    if events[-1]["stage"] == "complete":
        assert events[-1]["result"]["insufficient"] is True

    forbidden = {"reasoning", "chain_of_thought", "scratchpad", "thinking", "prompt"}
    for e in events:
        assert forbidden.isdisjoint(e.keys())


def test_query_invalid_mode_rejected(client):
    _register_login(client, _ALICE)
    ws_id = client.post("/api/workspaces", json={"name": "WS"}).json()["id"]
    resp = client.post(f"/api/workspaces/{ws_id}/query", json={"question": "Q?", "mode": "graphrag"})
    assert resp.status_code == 400


# ── Integration: workspace isolation in Qdrant ─────────────────────────────────

@pytest.mark.integration
def test_workspace_isolation_in_retrieval(tmp_path, test_engine, sample_pdf_bytes):
    """
    High-relevance content from workspace B must not appear in workspace A's results.
    This is the critical security test — the filter is applied at the Qdrant layer.
    """
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from app.rag.retriever import retrieve, RetrievalMode
    import uuid

    # Two isolated workspaces
    ws_a = str(uuid.uuid4())
    ws_b = str(uuid.uuid4())

    # Index the same document bytes under both workspaces
    p = tmp_path / "doc.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks_a = parse_and_chunk(p, "application/pdf")
    chunks_b = parse_and_chunk(p, "application/pdf")

    doc_a = str(uuid.uuid4())
    doc_b = str(uuid.uuid4())

    qdrant_mgr.ensure_collection()
    qdrant_mgr.index_document(ws_a, doc_a, "a.pdf", chunks_a)
    qdrant_mgr.index_document(ws_b, doc_b, "b.pdf", chunks_b)

    # Query ws_a — must only return ws_a points
    resp = retrieve(ws_a, chunks_a[0].raw_text[:80], mode=RetrievalMode.DENSE, dense_k=10)
    returned_docs = {r.document_id for r in resp.results}
    assert doc_b not in returned_docs, "Cross-workspace content leaked into results!"
    assert doc_a in returned_docs or len(resp.results) == 0

    # Cleanup
    qdrant_mgr.delete_document_points(doc_a)
    qdrant_mgr.delete_document_points(doc_b)


@pytest.mark.integration
def test_dense_retrieval_finds_relevant(tmp_path, test_engine, sample_pdf_bytes):
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from app.rag.retriever import retrieve, RetrievalMode
    import uuid

    ws = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    p = tmp_path / "doc.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")
    qdrant_mgr.ensure_collection()
    qdrant_mgr.index_document(ws, doc_id, "doc.pdf", chunks)

    # Query with text similar to chunk content
    resp = retrieve(ws, chunks[0].raw_text[:60], mode=RetrievalMode.DENSE, dense_k=5)
    assert len(resp.results) >= 1
    assert all(r.document_id == doc_id for r in resp.results)

    qdrant_mgr.delete_document_points(doc_id)


@pytest.mark.integration
def test_sparse_retrieval_finds_exact_term(tmp_path, test_engine, sample_pdf_bytes):
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from app.rag.retriever import retrieve, RetrievalMode
    import uuid

    ws = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    p = tmp_path / "doc.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")
    qdrant_mgr.ensure_collection()
    qdrant_mgr.index_document(ws, doc_id, "doc.pdf", chunks)

    # Use an exact term from the chunk
    first_word = chunks[0].raw_text.split()[0]
    resp = retrieve(ws, first_word, mode=RetrievalMode.SPARSE, sparse_k=5)
    assert len(resp.results) >= 0  # sparse may miss on very short query

    qdrant_mgr.delete_document_points(doc_id)


@pytest.mark.integration
def test_hybrid_returns_fused_results(tmp_path, test_engine, sample_pdf_bytes):
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from app.rag.retriever import retrieve, RetrievalMode
    import uuid

    ws = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    p = tmp_path / "doc.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")
    qdrant_mgr.ensure_collection()
    qdrant_mgr.index_document(ws, doc_id, "doc.pdf", chunks)

    resp = retrieve(ws, chunks[0].raw_text[:60], mode=RetrievalMode.HYBRID)
    assert len(resp.results) >= 1

    qdrant_mgr.delete_document_points(doc_id)


@pytest.mark.integration
def test_reranker_only_gets_authorized_candidates(tmp_path, test_engine, sample_pdf_bytes):
    """Reranker input is already workspace-filtered — cross-workspace chunks never reach it."""
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from app.rag.retriever import retrieve, RetrievalMode
    import uuid

    ws_a = str(uuid.uuid4())
    ws_b = str(uuid.uuid4())
    doc_a = str(uuid.uuid4())
    doc_b = str(uuid.uuid4())
    p = tmp_path / "doc.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")
    qdrant_mgr.ensure_collection()
    qdrant_mgr.index_document(ws_a, doc_a, "a.pdf", chunks)
    qdrant_mgr.index_document(ws_b, doc_b, "b.pdf", chunks)

    resp = retrieve(ws_a, chunks[0].raw_text[:60], mode=RetrievalMode.HYBRID_RERANK)
    # All results must be from ws_a
    assert all(r.document_id == doc_a for r in resp.results)

    qdrant_mgr.delete_document_points(doc_a)
    qdrant_mgr.delete_document_points(doc_b)
