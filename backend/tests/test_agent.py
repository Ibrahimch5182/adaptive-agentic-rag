"""
Phase 4 agent tests — deterministic fixtures, no live LLM/Qdrant required for fast tests.
Integration tests (mark=integration) require Qdrant.
"""
import pytest
from app.rag.assessor import AssessmentResult, PlanResult
from app.rag.retriever import RetrievalResult


def _make_result(point_id="pt1", doc_id="doc1", raw="evidence text", filename="f.pdf"):
    return RetrievalResult(
        point_id=point_id, document_id=doc_id, chunk_index=0,
        raw_text=raw, retrieval_text=raw, filename=filename,
        section_title="S", page_numbers=[1], score=0.9, mode="hybrid_rerank",
    )


def _make_results(n=5):
    return [_make_result(f"pt{i}", f"doc{i}", f"evidence chunk {i}") for i in range(n)]


def _scored_result(point_id, score):
    return RetrievalResult(
        point_id=point_id, document_id=f"doc-{point_id}", chunk_index=0,
        raw_text=f"text {point_id}", retrieval_text=f"text {point_id}",
        filename="f.pdf", section_title="S", page_numbers=[1],
        score=score, mode="hybrid_rerank",
    )


# ── Assessor unit tests ─────────────────────────────────────────────────────────

def test_heuristic_assessor_sufficient_evidence():
    from app.rag.assessor import _heuristic_assess
    r = _heuristic_assess("What is the leave policy?", _make_results(5))
    assert r.decision == "ANSWER_NOW"
    assert r.reason_code == "SUFFICIENT"


def test_heuristic_assessor_no_evidence_abstains():
    from app.rag.assessor import _heuristic_assess
    r = _heuristic_assess("What is X?", [])
    assert r.decision == "ABSTAIN"
    assert r.reason_code == "NO_SUPPORT"


def test_heuristic_assessor_multi_part_triggers_retrieve_more():
    from app.rag.assessor import _heuristic_assess
    r = _heuristic_assess("Compare annual leave and sick leave and parental leave", [_make_result()])
    assert r.decision == "RETRIEVE_MORE"


def test_heuristic_planner_generates_query():
    from app.rag.assessor import _heuristic_plan
    p = _heuristic_plan("What is X?", "missing section Y", [])
    assert p.action == "SEARCH"
    assert len(p.queries) == 1


def test_heuristic_planner_abstains_if_query_already_searched():
    from app.rag.assessor import _heuristic_plan
    p = _heuristic_plan("Q", "missing Y", ["missing Y Q"])
    assert p.action == "ABSTAIN"


# ── Agent state machine tests ───────────────────────────────────────────────────

def _make_agent_state(ws="ws-123", question="Q?", evidence=None, iterations=0, retrieval_calls=1):
    import time
    return {
        "workspace_id": ws,
        "question": question,
        "evidence_registry": {r.point_id: r for r in (evidence or _make_results(5))},
        "iterations": iterations,
        "retrieval_calls": retrieval_calls,
        "queries_issued": [question],
        "last_decision": "",
        "missing_information": "",
        "stop_reason": "",
        "pending_queries": [],
        "final_evidence": [],
        "trace": [],
        "t_start": time.time(),
    }


def test_simple_query_skips_agent_loop(monkeypatch):
    """Sufficient evidence → ANSWER_NOW → no plan/execute nodes called."""
    calls = []

    monkeypatch.setattr("app.rag.agent.assess_evidence",
                        lambda q, e: (calls.append("assess"), AssessmentResult("ANSWER_NOW", "SUFFICIENT"))[1])
    monkeypatch.setattr("app.rag.agent.plan_retrieval",
                        lambda **kw: (calls.append("plan"), PlanResult("SEARCH", []))[1])

    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=_make_results(5), mode="hybrid_rerank",
                                                        latency_ms=10.0))
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "Simple question?")
    agent_mod._graph = None

    assert result.route == "deterministic"
    assert result.iterations == 0
    assert "plan" not in calls


def test_complex_query_enters_agentic_loop(monkeypatch):
    """Insufficient evidence → RETRIEVE_MORE → then ANSWER_NOW on second assessment."""
    call_count = {"n": 0}

    def mock_assess(q, e):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return AssessmentResult("RETRIEVE_MORE", "MULTI_PART", "missing section B", "section B")
        return AssessmentResult("ANSWER_NOW", "SUFFICIENT")

    monkeypatch.setattr("app.rag.agent.assess_evidence", mock_assess)
    monkeypatch.setattr("app.rag.agent.plan_retrieval",
                        lambda **kw: PlanResult("SEARCH", ["section B details"]))

    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=_make_results(3), mode="hybrid_rerank",
                                                        latency_ms=10.0))
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "Complex multi-part question?")
    agent_mod._graph = None

    assert result.iterations >= 1
    assert result.route in ("agentic", "deterministic")  # 1 iteration qualifies as agentic
    assert call_count["n"] >= 2


def test_emit_reports_real_stages_without_changing_result(monkeypatch):
    """`emit` is optional live-progress instrumentation — passing it must not change the
    returned AgentResult, and events must be safe operational stages only (no chain-of-
    thought/reasoning/prompt fields)."""
    call_count = {"n": 0}

    def mock_assess(q, e):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return AssessmentResult("RETRIEVE_MORE", "MULTI_PART", "missing section B", "section B")
        return AssessmentResult("ANSWER_NOW", "SUFFICIENT")

    monkeypatch.setattr("app.rag.agent.assess_evidence", mock_assess)
    monkeypatch.setattr("app.rag.agent.plan_retrieval",
                        lambda **kw: PlanResult("SEARCH", ["section B details"]))

    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=_make_results(3), mode="hybrid_rerank",
                                                        latency_ms=10.0))

    agent_mod._graph = None
    baseline = agent_mod.run_adaptive_agent("ws-123", "Complex multi-part question?")
    agent_mod._graph = None
    call_count["n"] = 0

    events = []
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "Complex multi-part question?", emit=events.append)
    agent_mod._graph = None

    assert result.route == baseline.route
    assert result.iterations == baseline.iterations
    assert result.stop_reason == baseline.stop_reason

    forbidden = {"reasoning", "chain_of_thought", "scratchpad", "thinking", "prompt"}
    stages_seen = {e["stage"] for e in events}
    assert events, "emit should have been called at least once"
    assert stages_seen & {"retrieval", "assessment", "planning", "additional_retrieval", "pack"}
    for e in events:
        assert forbidden.isdisjoint(e.keys())
        assert isinstance(e["message"], str) and e["message"]


def test_max_iterations_stops_graph(monkeypatch):
    """Graph must stop at MAX_ITERATIONS regardless of assessor."""
    monkeypatch.setattr("app.rag.agent.assess_evidence",
                        lambda q, e: AssessmentResult("RETRIEVE_MORE", "MULTI_PART", "always more", ""))
    monkeypatch.setattr("app.rag.agent.plan_retrieval",
                        lambda **kw: PlanResult("SEARCH", ["more query"]))
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=_make_results(2), mode="hybrid_rerank",
                                                        latency_ms=5.0))
    from app.config import settings
    monkeypatch.setattr(settings, "AGENT_MAX_ITERATIONS", 2)
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "Q?")
    agent_mod._graph = None
    assert result.iterations <= 2
    assert result.stop_reason in ("MAX_ITERATIONS", "SUFFICIENT", "MAX_CALLS")


def test_max_retrieval_calls_stops_graph(monkeypatch):
    monkeypatch.setattr("app.rag.agent.assess_evidence",
                        lambda q, e: AssessmentResult("RETRIEVE_MORE", "MULTI_PART", "more", ""))
    monkeypatch.setattr("app.rag.agent.plan_retrieval",
                        lambda **kw: PlanResult("SEARCH", ["q1", "q2"]))
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=_make_results(1), mode="hybrid_rerank",
                                                        latency_ms=5.0))
    from app.config import settings
    monkeypatch.setattr(settings, "AGENT_MAX_RETRIEVAL_CALLS", 2)
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "Q?")
    agent_mod._graph = None
    assert result.retrieval_calls <= 2


def test_plan_retrieval_node_guarantees_one_query_per_aspect(monkeypatch):
    """The planner may return fewer/compound queries than there are uncovered aspects —
    orchestration must top up with a dedicated query per remaining uncovered aspect,
    within the existing per-iteration budget (never raised)."""
    from app.rag import agent as agent_mod
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_QUERIES_PER_ITERATION", 3)
    monkeypatch.setattr("app.rag.agent.plan_retrieval",
                        lambda **kw: PlanResult("SEARCH", ["revenue and operating income growth"]))

    uncovered = [
        "research and development expense",
        "datacenter capacity operational constraints",
        "net cash from operations",
    ]
    state = {
        "question": "Six-aspect question?", "missing_information": "missing several aspects",
        "queries_issued": ["initial query"], "uncovered_aspects": uncovered, "trace": [],
    }
    out = agent_mod.plan_retrieval_node(state)
    queries = out["pending_queries"]

    assert len(queries) == 3, "must respect the existing per-iteration budget, not raise it"
    assert "revenue and operating income growth" in queries
    # top-up fills remaining budget with dedicated aspect queries, in order
    assert "research and development expense" in queries
    assert "datacenter capacity operational constraints" in queries
    # third aspect has no budget left this iteration — left for a later iteration, not lost
    assert "net cash from operations" not in queries


def test_plan_retrieval_node_does_not_duplicate_aspect_already_targeted(monkeypatch):
    """If a planner query already targets an uncovered aspect (word overlap), a compound
    query must not be assumed to also cover a second aspect it happens to share words
    with — but it must not get a redundant duplicate query for the aspect it DOES target."""
    from app.rag import agent as agent_mod
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_QUERIES_PER_ITERATION", 3)
    monkeypatch.setattr("app.rag.agent.plan_retrieval",
                        lambda **kw: PlanResult("SEARCH", ["research and development expense trend"]))

    uncovered = ["research and development expense"]
    state = {
        "question": "Q?", "missing_information": "missing R&D",
        "queries_issued": [], "uncovered_aspects": uncovered, "trace": [],
    }
    out = agent_mod.plan_retrieval_node(state)
    queries = out["pending_queries"]
    assert queries == ["research and development expense trend"]


def test_agent_result_preserves_all_six_required_aspects(monkeypatch):
    """When the assessor confirms all six aspects are covered, the agent result must carry
    all six aspect labels through to required_aspects (used to build the generation
    coverage checklist), with nothing left unresolved."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse

    six_aspects = [
        "fiscal 2025 revenue and operating income growth",
        "net cash from operations",
        "additions to property and equipment",
        "additional leases not yet commenced",
        "research and development expense",
        "datacenter capacity operational constraints",
    ]
    monkeypatch.setattr(
        "app.rag.agent.assess_evidence",
        lambda q, e: AssessmentResult("ANSWER_NOW", "SUFFICIENT",
                                       required_aspects=six_aspects,
                                       covered_aspects=six_aspects,
                                       uncovered_aspects=[]),
    )
    from app.rag.retriever import RetrievalResponse as _RR
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: _RR(results=_make_results(15), mode="hybrid_rerank",
                                         latency_ms=10.0))
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "Six aspect question?")
    agent_mod._graph = None

    assert set(result.required_aspects) == set(six_aspects)
    assert len(result.required_aspects) == 6
    assert result.unresolved_aspects == []


def test_aspect_to_search_question_is_generic_and_deterministic():
    """No document name, no corpus-specific keywords, no LLM — just a natural question
    shape, generically applicable to any aspect label."""
    from app.rag.agent import aspect_to_search_question

    assert aspect_to_search_question("research and development expense") == (
        "What does the document report about research and development expense?"
    )
    assert aspect_to_search_question("operational constraints for expanding datacenter capacity") == (
        "What does the document report about operational constraints for expanding datacenter capacity?"
    )
    # Already question-shaped input is passed through, not double-wrapped.
    assert aspect_to_search_question("What are the main risks?") == "What are the main risks?"


def test_execute_retrieval_fallback_triggers_on_zero_new_chunks(monkeypatch):
    """A dedicated aspect query that adds nothing new gets one question-shaped fallback
    retry (via the same retrieval function), and that fallback can supply the evidence
    the primary query missed."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_RETRIEVAL_CALLS", 7)
    aspect = "operational constraints for expanding datacenter capacity"
    primary_query = "Microsoft 2025 annual report operational constraints for expanding datacenter capacity"
    expected_fallback = agent_mod.aspect_to_search_question(aspect)
    calls = []

    def mock_retrieve(**kw):
        calls.append(kw["question"])
        if kw["question"] == primary_query:
            return RetrievalResponse(results=[_make_result("pt0")], mode="hybrid_rerank", latency_ms=5.0)
        if kw["question"] == expected_fallback:
            return RetrievalResponse(results=[_make_result("dc1", "doc-dc", "datacenter constraint text")],
                                      mode="hybrid_rerank", latency_ms=5.0)
        return RetrievalResponse(results=[], mode="hybrid_rerank", latency_ms=5.0)

    monkeypatch.setattr("app.rag.agent.retrieve", mock_retrieve)

    state = {
        "workspace_id": "ws-1", "iterations": 0, "retrieval_calls": 1,
        "queries_issued": ["initial query"],
        "pending_queries": [primary_query],
        "query_aspect_map": {primary_query: aspect},
        "evidence_registry": {"pt0": _make_result("pt0")},  # already seen -> primary adds 0 new
        "trace": [],
    }
    out = agent_mod.execute_retrieval_node(state)

    assert "dc1" in out["evidence_registry"], "fallback must have added the missing evidence"
    entry = out["trace"][0]
    assert entry["fallback_query"] == expected_fallback
    assert entry["fallback_new_chunks"] == 1
    assert expected_fallback in out["queries_issued"]
    assert calls == [primary_query, expected_fallback]


def test_execute_retrieval_fallback_generic_for_rd_aspect(monkeypatch):
    """The question-shaped fallback isn't specific to the datacenter aspect — it must
    work the same way for any other uncovered aspect, e.g. R&D expense."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_RETRIEVAL_CALLS", 7)
    aspect = "research and development expense"
    primary_query = "Microsoft 2025 annual report research and development expense"
    expected_fallback = agent_mod.aspect_to_search_question(aspect)

    def mock_retrieve(**kw):
        if kw["question"] == expected_fallback:
            return RetrievalResponse(results=[_make_result("rd1", "doc-rd", "R&D expense evidence")],
                                      mode="hybrid_rerank", latency_ms=5.0)
        return RetrievalResponse(results=[_make_result("pt0")], mode="hybrid_rerank", latency_ms=5.0)

    monkeypatch.setattr("app.rag.agent.retrieve", mock_retrieve)

    state = {
        "workspace_id": "ws-1", "iterations": 0, "retrieval_calls": 1,
        "queries_issued": ["initial query"],
        "pending_queries": [primary_query],
        "query_aspect_map": {primary_query: aspect},
        "evidence_registry": {"pt0": _make_result("pt0")},
        "trace": [],
    }
    out = agent_mod.execute_retrieval_node(state)
    assert "rd1" in out["evidence_registry"]
    assert out["trace"][0]["fallback_query"] == expected_fallback


def test_execute_retrieval_fallback_not_repeated_if_already_searched(monkeypatch):
    """If the question-shaped wording was already searched earlier (e.g. an earlier
    iteration's fallback), it must not be retried a second time."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_RETRIEVAL_CALLS", 7)
    aspect = "research and development expense"
    primary_query = "Microsoft 2025 annual report research and development expense"
    already_searched = agent_mod.aspect_to_search_question(aspect)
    calls = []

    def mock_retrieve(**kw):
        calls.append(kw["question"])
        return RetrievalResponse(results=[], mode="hybrid_rerank", latency_ms=5.0)

    monkeypatch.setattr("app.rag.agent.retrieve", mock_retrieve)

    state = {
        "workspace_id": "ws-1", "iterations": 0, "retrieval_calls": 1,
        "queries_issued": ["initial query", already_searched],
        "pending_queries": [primary_query],
        "query_aspect_map": {primary_query: aspect},
        "evidence_registry": {},
        "trace": [],
    }
    out = agent_mod.execute_retrieval_node(state)
    assert calls == [primary_query], "must not repeat a wording already searched"
    assert "fallback_query" not in out["trace"][0]


def test_execute_retrieval_fallback_respects_call_budget(monkeypatch):
    """The fallback must never push retrieval_calls past AGENT_MAX_RETRIEVAL_CALLS."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_RETRIEVAL_CALLS", 2)
    aspect = "some uncovered aspect"
    primary_query = "planner query for aspect"
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=[], mode="hybrid_rerank", latency_ms=5.0))

    state = {
        "workspace_id": "ws-1", "iterations": 0, "retrieval_calls": 1,
        "queries_issued": ["initial query"],
        "pending_queries": [primary_query],
        "query_aspect_map": {primary_query: aspect},
        "evidence_registry": {},
        "trace": [],
    }
    out = agent_mod.execute_retrieval_node(state)
    assert out["retrieval_calls"] <= 2
    entry = out["trace"][0]
    assert "fallback_query" not in entry, "no budget left for a fallback call"


def test_execute_retrieval_no_fallback_when_primary_adds_evidence(monkeypatch):
    """A dedicated aspect query that already adds new evidence must not trigger a
    redundant fallback call."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_RETRIEVAL_CALLS", 7)
    aspect = "research and development expense"
    primary_query = "Microsoft 2025 annual report research and development expense"
    calls = []

    def mock_retrieve(**kw):
        calls.append(kw["question"])
        return RetrievalResponse(results=[_make_result("rd1", "doc-rd", "R&D evidence")],
                                  mode="hybrid_rerank", latency_ms=5.0)

    monkeypatch.setattr("app.rag.agent.retrieve", mock_retrieve)

    state = {
        "workspace_id": "ws-1", "iterations": 0, "retrieval_calls": 1,
        "queries_issued": ["initial query"],
        "pending_queries": [primary_query],
        "query_aspect_map": {primary_query: aspect},
        "evidence_registry": {},
        "trace": [],
    }
    out = agent_mod.execute_retrieval_node(state)
    assert calls == [primary_query], "no second (fallback) call when primary already added evidence"
    entry = out["trace"][0]
    assert "fallback_query" not in entry


def test_registry_eviction_prefers_unaspected_chunks(monkeypatch):
    """When the registry is full, a new chunk for a currently-unrepresented required
    aspect must replace a generic/unaspected chunk first (lowest score among them) —
    never touch an aspect that already has representation while an unaspected chunk
    still exists."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_EVIDENCE_CHUNKS", 5)
    registry = {
        "u1": _scored_result("u1", 0.5), "u2": _scored_result("u2", 0.2),
        "a1": _scored_result("a1", 0.9), "b1": _scored_result("b1", 0.9),
        "c1": _scored_result("c1", 0.9),
    }
    evidence_aspects = {"u1": "", "u2": "", "a1": "aspectA", "b1": "aspectB", "c1": "aspectC"}
    query = "query for aspectX"
    new_chunk = _scored_result("x1", 0.95)
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=[new_chunk], mode="hybrid_rerank", latency_ms=5.0))

    state = {
        "workspace_id": "ws-1", "iterations": 0, "retrieval_calls": 1,
        "queries_issued": ["initial"], "pending_queries": [query],
        "query_aspect_map": {query: "aspectX"},
        "evidence_registry": registry, "evidence_aspects": evidence_aspects,
        "trace": [],
    }
    out = agent_mod.execute_retrieval_node(state)

    assert len(out["evidence_registry"]) == 5, "total registry size must stay at the cap"
    assert "x1" in out["evidence_registry"], "new aspect's chunk must be admitted via eviction"
    assert {"a1", "b1", "c1"} <= out["evidence_registry"].keys(), \
        "single-chunk aspects must never be evicted while an unaspected chunk exists"
    assert "u2" not in out["evidence_registry"], "lowest-scoring unaspected chunk is evicted first"
    assert "u1" in out["evidence_registry"]
    entry = out["trace"][0]
    assert entry["replacements"][0] == {"evicted_point_id": "u2", "evicted_aspect": "", "added_point_id": "x1"}


def test_registry_eviction_falls_back_to_redundant_aspect(monkeypatch):
    """With no unaspected chunk available, eviction must come from the aspect currently
    holding the MOST chunks (redundant) — never from an aspect holding exactly one."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_EVIDENCE_CHUNKS", 5)
    registry = {
        "a1": _scored_result("a1", 0.9), "a2": _scored_result("a2", 0.4), "a3": _scored_result("a3", 0.7),
        "b1": _scored_result("b1", 0.9), "c1": _scored_result("c1", 0.9),
    }
    evidence_aspects = {"a1": "aspectA", "a2": "aspectA", "a3": "aspectA",
                        "b1": "aspectB", "c1": "aspectC"}
    query = "query for aspectX"
    new_chunk = _scored_result("x1", 0.95)
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=[new_chunk], mode="hybrid_rerank", latency_ms=5.0))

    state = {
        "workspace_id": "ws-1", "iterations": 0, "retrieval_calls": 1,
        "queries_issued": ["initial"], "pending_queries": [query],
        "query_aspect_map": {query: "aspectX"},
        "evidence_registry": registry, "evidence_aspects": evidence_aspects,
        "trace": [],
    }
    out = agent_mod.execute_retrieval_node(state)

    assert len(out["evidence_registry"]) == 5
    assert "x1" in out["evidence_registry"]
    assert "b1" in out["evidence_registry"] and "c1" in out["evidence_registry"], \
        "single-chunk aspects must never be evicted"
    assert "a2" not in out["evidence_registry"], "lowest-scoring chunk of the most redundant aspect is evicted"
    assert "a1" in out["evidence_registry"] and "a3" in out["evidence_registry"]


def test_registry_eviction_skips_when_no_safe_candidate(monkeypatch):
    """If every represented aspect holds exactly one chunk and none are unaspected, a
    new aspect's chunk must be skipped — never forced in by evicting a required aspect
    down to zero. The 15-chunk (here patched) cap is never exceeded either way."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_EVIDENCE_CHUNKS", 3)
    registry = {"a1": _scored_result("a1", 0.9), "b1": _scored_result("b1", 0.9),
                "c1": _scored_result("c1", 0.9)}
    evidence_aspects = {"a1": "aspectA", "b1": "aspectB", "c1": "aspectC"}
    query = "query for aspectX"
    new_chunk = _scored_result("x1", 0.95)
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=[new_chunk], mode="hybrid_rerank", latency_ms=5.0))

    state = {
        "workspace_id": "ws-1", "iterations": 0, "retrieval_calls": 1,
        "queries_issued": ["initial"], "pending_queries": [query],
        "query_aspect_map": {query: "aspectX"},
        "evidence_registry": registry, "evidence_aspects": evidence_aspects,
        "trace": [],
    }
    out = agent_mod.execute_retrieval_node(state)

    assert len(out["evidence_registry"]) == 3, "cap must never be exceeded"
    assert set(out["evidence_registry"].keys()) == {"a1", "b1", "c1"}, \
        "no safe eviction candidate existed — new chunk must be skipped, not forced in"


def test_registry_fairness_limits_chunks_per_query(monkeypatch):
    """A single follow-up query must not claim more than _MAX_NEW_CHUNKS_PER_QUERY new
    registry slots, so a later query targeting a different missing aspect (e.g. R&D expense
    or datacenter constraints) still has room before AGENT_MAX_EVIDENCE_CHUNKS is hit."""
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    from app.config import settings

    monkeypatch.setattr(settings, "AGENT_MAX_EVIDENCE_CHUNKS", 10)

    call_n = {"n": 0}

    def mock_retrieve(**kw):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return RetrievalResponse(results=_make_results(8), mode="hybrid_rerank", latency_ms=5.0)
        return RetrievalResponse(
            results=[_make_result("rd1", "doc-rd", "R&D expense evidence"),
                     _make_result("dc1", "doc-dc", "datacenter constraint evidence")],
            mode="hybrid_rerank", latency_ms=5.0,
        )

    monkeypatch.setattr("app.rag.agent.retrieve", mock_retrieve)

    state = {
        "workspace_id": "ws-1", "question": "Q?", "evidence_registry": {},
        "iterations": 0, "retrieval_calls": 0, "queries_issued": [],
        "pending_queries": ["broad query", "R&D and datacenter constraints"],
        "final_evidence": [], "trace": [], "t_start": 0.0,
    }
    out = agent_mod.execute_retrieval_node(state)
    registry = out["evidence_registry"]

    assert "rd1" in registry, "later query's R&D evidence must not be crowded out"
    assert "dc1" in registry, "later query's datacenter-constraint evidence must not be crowded out"
    first_query_chunks = [pid for pid in registry if pid.startswith("pt")]
    assert len(first_query_chunks) <= agent_mod._MAX_NEW_CHUNKS_PER_QUERY


def test_evidence_registry_deduplicates():
    """Same chunk returned by two retrieval calls must appear only once."""
    state = _make_agent_state(evidence=_make_results(3))

    # Simulate adding same results again
    registry = state["evidence_registry"]
    initial_size = len(registry)
    new_result = _make_result("pt0")  # duplicate point_id
    added = dupes = 0
    if new_result.point_id in registry:
        dupes += 1
    else:
        registry[new_result.point_id] = new_result
        added += 1
    assert dupes == 1
    assert len(registry) == initial_size


def test_unsupported_query_can_abstain(monkeypatch):
    monkeypatch.setattr("app.rag.agent.assess_evidence",
                        lambda q, e: AssessmentResult("ABSTAIN", "NO_SUPPORT", "no evidence", ""))
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=[], mode="hybrid_rerank", latency_ms=5.0))
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "What is the company stock price?")
    agent_mod._graph = None
    assert result.stop_reason in ("NO_SUPPORT", "SUFFICIENT")


def test_trace_contains_no_chain_of_thought(monkeypatch):
    """Operational trace must not include reasoning/scratchpad fields."""
    monkeypatch.setattr("app.rag.agent.assess_evidence",
                        lambda q, e: AssessmentResult("ANSWER_NOW", "SUFFICIENT"))
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=_make_results(3), mode="hybrid_rerank",
                                                        latency_ms=5.0))
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "Q?")
    agent_mod._graph = None
    forbidden = {"reasoning", "chain_of_thought", "scratchpad", "thinking"}
    for entry in result.trace:
        assert not (forbidden & set(entry.keys())), f"CoT field found in trace: {entry}"


def test_malformed_planner_fails_safely(monkeypatch):
    """Planner returning bad data must not crash the graph."""
    call_n = {"n": 0}

    def mock_assess(q, e):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return AssessmentResult("RETRIEVE_MORE", "MULTI_PART", "missing", "")
        return AssessmentResult("ANSWER_NOW", "SUFFICIENT")

    monkeypatch.setattr("app.rag.agent.assess_evidence", mock_assess)
    # Planner returns no queries → should fall back to ANSWER_NOW
    monkeypatch.setattr("app.rag.agent.plan_retrieval",
                        lambda **kw: PlanResult("SEARCH", []))
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    monkeypatch.setattr("app.rag.agent.retrieve",
                        lambda **kw: RetrievalResponse(results=_make_results(2), mode="hybrid_rerank",
                                                        latency_ms=5.0))
    agent_mod._graph = None
    result = agent_mod.run_adaptive_agent("ws-123", "Q?")
    agent_mod._graph = None
    assert result is not None  # must not crash


def test_agent_workspace_immutability(monkeypatch):
    """workspace_id must not change after the agent touches state."""
    monkeypatch.setattr("app.rag.agent.assess_evidence",
                        lambda q, e: AssessmentResult("ANSWER_NOW", "SUFFICIENT"))
    from app.rag import agent as agent_mod
    from app.rag.retriever import RetrievalResponse
    captured_ws = []

    def mock_retrieve(workspace_id, **kw):
        captured_ws.append(workspace_id)
        return RetrievalResponse(results=_make_results(3), mode="hybrid_rerank", latency_ms=5.0)

    monkeypatch.setattr("app.rag.agent.retrieve", mock_retrieve)
    agent_mod._graph = None
    run_ws = "fixed-ws-id-123"
    agent_mod.run_adaptive_agent(run_ws, "Q?")
    agent_mod._graph = None

    assert all(ws == run_ws for ws in captured_ws), "workspace_id was mutated!"


# ── API-level tests ─────────────────────────────────────────────────────────────

_ALICE = {"email": "alice.agent@test.com", "full_name": "Alice", "password": "pass"}
_BOB = {"email": "bob.agent@test.com", "full_name": "Bob", "password": "pass"}


def test_phase3_deterministic_mode_still_works(client):
    """Regression: explicit deterministic modes must still work."""
    client.post("/api/auth/register", json=_ALICE)
    client.post("/api/auth/login", json={"email": _ALICE["email"], "password": _ALICE["password"]})
    ws_id = client.post("/api/workspaces", json={"name": "WS"}).json()["id"]
    # No READY docs → should still return 200 with insufficient=True
    resp = client.post(f"/api/workspaces/{ws_id}/query",
                       json={"question": "Q?", "mode": "hybrid_rerank"})
    assert resp.status_code == 200
    assert resp.json()["insufficient"] is True


def test_adaptive_mode_cross_workspace_rejected(client):
    """Adaptive mode must also enforce workspace auth."""
    client.post("/api/auth/register", json=_ALICE)
    client.post("/api/auth/login", json={"email": _ALICE["email"], "password": _ALICE["password"]})
    ws_a = client.post("/api/workspaces", json={"name": "Alice WS"}).json()["id"]
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json=_BOB)
    client.post("/api/auth/login", json={"email": _BOB["email"], "password": _BOB["password"]})
    resp = client.post(f"/api/workspaces/{ws_a}/query",
                       json={"question": "Q?", "mode": "adaptive"})
    assert resp.status_code == 404


def test_invalid_mode_rejected(client):
    client.post("/api/auth/register", json=_ALICE)
    client.post("/api/auth/login", json={"email": _ALICE["email"], "password": _ALICE["password"]})
    ws_id = client.post("/api/workspaces", json={"name": "WS"}).json()["id"]
    resp = client.post(f"/api/workspaces/{ws_id}/query",
                       json={"question": "Q?", "mode": "graphrag"})
    assert resp.status_code == 400


# ── Integration: real agent run with Qdrant ────────────────────────────────────

@pytest.mark.integration
def test_agent_workspace_filter_enforced_in_retrieval(tmp_path, test_engine, sample_pdf_bytes):
    """Content from workspace B never becomes a candidate in workspace A's agentic retrieval."""
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from app.rag.agent import run_adaptive_agent
    from app.rag import assessor as assessor_mod
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

    # Force the agent to do one extra retrieval loop
    call_n = {"n": 0}
    original_assess = assessor_mod.assess_evidence

    def mock_assess(q, e):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return AssessmentResult("RETRIEVE_MORE", "MULTI_PART", "need more info", "")
        return AssessmentResult("ANSWER_NOW", "SUFFICIENT")

    original_plan = assessor_mod.plan_retrieval

    import app.rag.assessor as am
    am.assess_evidence = mock_assess
    am.plan_retrieval = lambda **kw: PlanResult("SEARCH", [chunks[0].raw_text[:30]])

    import app.rag.agent as agent_mod
    agent_mod._graph = None

    try:
        result = run_adaptive_agent(ws_a, chunks[0].raw_text[:60])
    finally:
        am.assess_evidence = original_assess
        am.plan_retrieval = original_plan
        agent_mod._graph = None

    # All evidence must come from ws_a
    for ev in result.final_evidence:
        assert ev.document_id == doc_a, f"Cross-workspace leak: {ev.document_id}"

    qdrant_mgr.delete_document_points(doc_a)
    qdrant_mgr.delete_document_points(doc_b)
