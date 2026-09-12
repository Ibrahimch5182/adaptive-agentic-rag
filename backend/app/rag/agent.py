"""
Bounded Agentic RAG — LangGraph state machine.

Graph: initial_retrieve → assess_evidence →┬→ pack_evidence → END
                          ↑                 └→ plan_retrieval → execute_retrieval ┘
                          └────────────────────────────── (bounded loop, max iterations)

Security invariants (enforced by application, not LLM):
- workspace_id is server-validated before this call and NEVER modified inside the graph
- every retrieve() call passes workspace_id → Qdrant mandatory filter
- retrieved text is treated as UNTRUSTED evidence; LLM cannot gain tool/workspace authority
- iteration and call counts are hard-capped by configuration
"""
from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import TypedDict, Any, Callable, Optional
from langgraph.graph import StateGraph, END
from app.config import settings
from app.rag.retriever import RetrievalResult, RetrievalMode, retrieve
from app.rag.assessor import assess_evidence, plan_retrieval, AssessmentResult

log = logging.getLogger(__name__)

# Cap how many new chunks a single targeted follow-up query may claim from the shared
# evidence budget. Without this, an early query with many results (e.g. 5 hits) can
# exhaust AGENT_MAX_EVIDENCE_CHUNKS before a later query — for an aspect the assessor
# explicitly flagged as still uncovered — gets a chance to contribute anything at all.
_MAX_NEW_CHUNKS_PER_QUERY = 3


# ── LangGraph state ────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    workspace_id: str             # IMMUTABLE — application-set, agent cannot alter
    question: str
    evidence_registry: dict       # chunk_id → RetrievalResult
    evidence_aspects: dict        # chunk_id → aspect label it was retrieved for ("" = generic/initial)
    iterations: int
    retrieval_calls: int
    queries_issued: list
    last_decision: str
    missing_information: str
    required_aspects: list        # every distinct aspect the last real assessment identified
    uncovered_aspects: list       # aspects still unsupported after the last real assessment
    stop_reason: str
    pending_queries: list         # transient: populated by plan, consumed by execute
    query_aspect_map: dict        # transient: query -> aspect label it targets, for tracing
    final_evidence: list          # output: set by pack_evidence
    trace: list
    t_start: float


# ── Nodes ──────────────────────────────────────────────────────────────────────

def initial_retrieve_node(state: AgentState) -> dict:
    t0 = time.perf_counter()
    resp = retrieve(
        workspace_id=state["workspace_id"],
        question=state["question"],
        mode=RetrievalMode.HYBRID_RERANK,
    )
    lat = (time.perf_counter() - t0) * 1000
    registry = {r.point_id: r for r in resp.results}
    # Initial-pass chunks are generic (no aspect is known yet — assessment hasn't run) —
    # "" marks them as not representing any specific required aspect, which makes them
    # the safe/first eviction pool later if a still-uncovered aspect needs registry room.
    aspects = {pid: "" for pid in registry}
    return {
        "evidence_registry": registry,
        "evidence_aspects": aspects,
        "retrieval_calls": 1,
        "queries_issued": [state["question"]],
        "trace": [{"step": "initial_retrieve", "query": state["question"],
                   "chunks_retrieved": len(resp.results), "latency_ms": round(lat, 1)}],
    }


def assess_evidence_node(state: AgentState) -> dict:
    evidence = list(state["evidence_registry"].values())

    # Hard bounds checked BEFORE calling LLM
    if state["iterations"] >= settings.AGENT_MAX_ITERATIONS:
        return {"last_decision": "ANSWER_NOW", "stop_reason": "MAX_ITERATIONS",
                "trace": state["trace"] + [{"step": "assess", "decision": "ANSWER_NOW",
                                             "reason": "MAX_ITERATIONS"}]}
    if state["retrieval_calls"] >= settings.AGENT_MAX_RETRIEVAL_CALLS:
        return {"last_decision": "ANSWER_NOW", "stop_reason": "MAX_CALLS",
                "trace": state["trace"] + [{"step": "assess", "decision": "ANSWER_NOW",
                                             "reason": "MAX_CALLS"}]}

    result: AssessmentResult = assess_evidence(state["question"], evidence)
    stop = ""
    if result.decision == "ABSTAIN":
        stop = "NO_SUPPORT"
    elif result.decision == "ANSWER_NOW":
        stop = "SUFFICIENT"

    return {
        "last_decision": result.decision,
        "missing_information": result.missing_information,
        "required_aspects": result.required_aspects,
        "uncovered_aspects": result.uncovered_aspects,
        "stop_reason": stop,
        "trace": state["trace"] + [{"step": "assess", "decision": result.decision,
                                     "reason_code": result.reason_code,
                                     "missing": result.missing_information,
                                     "required_aspects": result.required_aspects,
                                     "covered_aspects": result.covered_aspects,
                                     "uncovered_aspects": result.uncovered_aspects,
                                     "evidence_count": len(evidence),
                                     "iteration": state["iterations"]}],
    }


_QUESTION_STARTERS = ("what", "how", "why", "when", "where", "who", "which")


def aspect_to_search_question(aspect: str) -> str:
    """Deterministic, corpus-agnostic transform of a noun-phrase aspect label into a
    natural question. No document name, no corpus-specific keywords, no LLM call — a
    direct retrieval probe against a real indexed corpus showed retrieval quality for
    this aspect was already good under the raw label; this exists to make the fallback
    robust in general (and never worse), not because raw noun phrases were disproven."""
    a = aspect.strip().rstrip("?.!").strip()
    if not a:
        return aspect.strip()
    if a.lower().startswith(_QUESTION_STARTERS):
        return a + "?"
    return f"What does the document report about {a}?"


def _best_matching_aspect(query: str, uncovered_aspects: list[str]) -> str | None:
    """Which uncovered aspect (if any) a query is already targeting, by word overlap.
    A query only ever claims its single best-matching aspect — a compound query that
    happens to share words with two aspects still leaves the other one uncovered, so it
    gets its own dedicated query below rather than being assumed "handled"."""
    q_words = set(query.lower().split())
    best, best_overlap = None, 0
    for aspect in uncovered_aspects:
        a_words = {w for w in aspect.lower().split() if len(w) > 3}
        overlap = len(q_words & a_words)
        if overlap > best_overlap:
            best, best_overlap = aspect, overlap
    return best


def plan_retrieval_node(state: AgentState) -> dict:
    uncovered = state.get("uncovered_aspects", [])
    plan = plan_retrieval(
        question=state["question"],
        missing_information=state["missing_information"],
        already_searched=state["queries_issued"],
        max_queries=settings.AGENT_MAX_QUERIES_PER_ITERATION,
        uncovered_aspects=uncovered,
    )
    if plan.action in ("ANSWER", "ABSTAIN") or not plan.queries:
        return {"last_decision": "ANSWER_NOW", "stop_reason": "PLANNER_DONE",
                "pending_queries": [], "query_aspect_map": {},
                "trace": state["trace"] + [{"step": "plan", "action": plan.action,
                                             "queries": []}]}

    budget = settings.AGENT_MAX_QUERIES_PER_ITERATION
    new_queries = [q for q in plan.queries if q not in state["queries_issued"]][:budget]
    aspect_map = {q: _best_matching_aspect(q, uncovered) for q in new_queries}

    # Deterministic one-query-per-aspect guarantee: the LLM planner is only asked (not
    # required) to give each uncovered aspect its own query, and may combine several into
    # one compound query. Top up — within the same per-iteration budget, no bound raised —
    # with the aspect label itself for any uncovered aspect no planned query already
    # targets, so orchestration (not the LLM alone) guarantees the coverage.
    for aspect in uncovered:
        if len(new_queries) >= budget:
            break
        aspect_q = aspect.strip()
        if not aspect_q or aspect_q in state["queries_issued"] or aspect_q in new_queries:
            continue
        if any(aspect_map.get(q) == aspect for q in new_queries):
            continue
        new_queries.append(aspect_q)
        aspect_map[aspect_q] = aspect

    return {
        "pending_queries": new_queries,
        "queries_issued": state["queries_issued"] + new_queries,
        "query_aspect_map": aspect_map,
        "trace": state["trace"] + [{"step": "plan", "queries": new_queries,
                                     "missing": plan.missing_information,
                                     "aspect_map": aspect_map}],
    }


def _aspect_counts(evidence_aspects: dict) -> dict:
    counts: dict[str, int] = {}
    for a in evidence_aspects.values():
        key = a or "(unaspected)"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _pick_eviction_candidate(registry: dict, evidence_aspects: dict, protect_aspect: str) -> str | None:
    """Choose a chunk to evict to make room for `protect_aspect` (a required aspect that
    currently has ZERO chunks). Never evicts the only chunk representing another aspect
    that already has exactly one — eviction only ever comes from: (1) generic/unaspected
    initial-pass chunks, preferring the lowest-scoring one, or failing that (2) the
    aspect currently holding the MOST chunks (a redundant aspect), again lowest score
    first. Returns None if no safe eviction candidate exists (every other aspect already
    holds exactly one chunk and there are no unaspected chunks left)."""
    unaspected = [pid for pid, a in evidence_aspects.items() if not a]
    if unaspected:
        return min(unaspected, key=lambda pid: registry[pid].score)

    counts = _aspect_counts(evidence_aspects)
    redundant = [pid for pid, a in evidence_aspects.items()
                 if a and a != protect_aspect and counts.get(a, 0) > 1]
    if redundant:
        redundant.sort(key=lambda pid: (-counts[evidence_aspects[pid]], registry[pid].score))
        return redundant[0]
    return None


def execute_retrieval_node(state: AgentState) -> dict:
    registry = dict(state["evidence_registry"])
    evidence_aspects = dict(state.get("evidence_aspects", {}))
    call_count = state["retrieval_calls"]
    trace_entries = []
    aspect_map = state.get("query_aspect_map", {})
    queries_issued = list(state["queries_issued"])

    def _do_retrieve(q: str, aspect_for_query: str) -> dict:
        nonlocal call_count
        t0 = time.perf_counter()
        resp = retrieve(
            workspace_id=state["workspace_id"],  # IMMUTABLE — always workspace-filtered
            question=q,
            mode=RetrievalMode.HYBRID_RERANK,
        )
        lat = (time.perf_counter() - t0) * 1000
        call_count += 1
        added = dupes = skipped = 0
        replacements = []
        for r in resp.results:
            if r.point_id in registry:
                dupes += 1
                continue
            if added >= _MAX_NEW_CHUNKS_PER_QUERY:
                skipped += 1
                continue
            if len(registry) < settings.AGENT_MAX_EVIDENCE_CHUNKS:
                registry[r.point_id] = r
                evidence_aspects[r.point_id] = aspect_for_query
                added += 1
                continue
            # Registry is at the hard cap. Only make room when this chunk is the FIRST
            # for a currently-unrepresented required aspect — never to pile on more
            # evidence for an aspect that already has at least one chunk. Total registry
            # size never changes (1-for-1 swap); the 15-chunk cap is preserved exactly.
            if aspect_for_query and _aspect_counts(evidence_aspects).get(aspect_for_query, 0) == 0:
                victim = _pick_eviction_candidate(registry, evidence_aspects, aspect_for_query)
                if victim is not None:
                    replacements.append({"evicted_point_id": victim,
                                          "evicted_aspect": evidence_aspects.get(victim, ""),
                                          "added_point_id": r.point_id})
                    del registry[victim]
                    del evidence_aspects[victim]
                    registry[r.point_id] = r
                    evidence_aspects[r.point_id] = aspect_for_query
                    added += 1
                    continue
            skipped += 1
        return {"added": added, "dupes": dupes, "skipped": skipped,
                "retrieved": len(resp.results), "latency_ms": round(lat, 1),
                "replacements": replacements}

    for query in state.get("pending_queries", []):
        if call_count >= settings.AGENT_MAX_RETRIEVAL_CALLS:
            break
        aspect = aspect_map.get(query, "")
        r1 = _do_retrieve(query, aspect)
        entry = {"step": "retrieve", "aspect": aspect,
                  "query": query, "primary_query": query,
                  "retrieved": r1["retrieved"], "primary_retrieved": r1["retrieved"],
                  "added": r1["added"], "primary_new_chunks": r1["added"],
                  "dupes": r1["dupes"], "skipped": r1["skipped"],
                  "latency_ms": r1["latency_ms"]}
        if r1["replacements"]:
            entry["replacements"] = r1["replacements"]

        # Question-shaped fallback: a dedicated aspect query that surfaced zero new
        # chunks gets ONE deterministic retry, transformed into a natural question (no
        # document-name prefix, no combined aspects, no corpus-specific keywords) — same
        # retrieval function, same call budget, no new LLM call. Skipped when the
        # transformed wording equals the primary query or was already searched (avoids a
        # pointless duplicate call), and runs immediately (before any later pending
        # query) so a scarce remaining call is spent on the still-uncovered aspect first.
        if aspect and r1["added"] == 0 and call_count < settings.AGENT_MAX_RETRIEVAL_CALLS:
            fallback_query = aspect_to_search_question(aspect)
            if fallback_query != query and fallback_query not in queries_issued:
                r2 = _do_retrieve(fallback_query, aspect)
                queries_issued.append(fallback_query)
                entry["fallback_query"] = fallback_query
                entry["fallback_retrieved"] = r2["retrieved"]
                entry["fallback_new_chunks"] = r2["added"]
                entry["fallback_latency_ms"] = r2["latency_ms"]
                if r2["replacements"]:
                    entry.setdefault("replacements", []).extend(r2["replacements"])

        entry["registry_aspect_counts"] = _aspect_counts(evidence_aspects)
        trace_entries.append(entry)

    return {
        "evidence_registry": registry,
        "evidence_aspects": evidence_aspects,
        "retrieval_calls": call_count,
        "iterations": state["iterations"] + 1,
        "pending_queries": [],
        "query_aspect_map": {},
        "queries_issued": queries_issued,
        "trace": state["trace"] + trace_entries,
    }


def pack_evidence_node(state: AgentState) -> dict:
    evidence = list(state["evidence_registry"].values())
    if not evidence:
        return {"final_evidence": []}
    if state["iterations"] == 0:
        # initial_retrieve already ran HYBRID_RERANK and capped to RERANK_TOP_K —
        # no extra retrieval happened, so the registry is already the final reranked
        # set. Re-running the cross-encoder here would just reproduce the same order.
        final = evidence
    else:
        # Extra retrieval ran to cover aspects the initial pass missed — cropping back
        # down to RERANK_TOP_K here would re-lose exactly the aspect just fetched for.
        # Keep the full deduped registry (already hard-capped at AGENT_MAX_EVIDENCE_CHUNKS),
        # only using the cross-encoder to order it.
        from app.rag.reranker import rerank
        pack_k = min(len(evidence), settings.AGENT_MAX_EVIDENCE_CHUNKS)
        try:
            final = rerank(state["question"], evidence, top_k=pack_k)
        except Exception:
            final = evidence[:pack_k]
    total_ms = (time.perf_counter() - state["t_start"]) * 1000
    return {
        "final_evidence": final,
        "trace": state["trace"] + [{"step": "pack", "registry_size": len(evidence),
                                     "packed": len(final),
                                     "total_latency_ms": round(total_ms, 1)}],
    }


# ── Routing ────────────────────────────────────────────────────────────────────

def _route_after_assess(state: AgentState) -> str:
    return "plan" if state.get("last_decision") == "RETRIEVE_MORE" else "pack"


def _route_after_plan(state: AgentState) -> str:
    return "pack" if state.get("last_decision") == "ANSWER_NOW" else "execute"


# ── Graph ─────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    g = StateGraph(AgentState)
    g.add_node("initial_retrieve", initial_retrieve_node)
    g.add_node("assess_evidence", assess_evidence_node)
    g.add_node("plan_retrieval", plan_retrieval_node)
    g.add_node("execute_retrieval", execute_retrieval_node)
    g.add_node("pack_evidence", pack_evidence_node)
    g.set_entry_point("initial_retrieve")
    g.add_edge("initial_retrieve", "assess_evidence")
    g.add_conditional_edges("assess_evidence", _route_after_assess,
                            {"pack": "pack_evidence", "plan": "plan_retrieval"})
    g.add_conditional_edges("plan_retrieval", _route_after_plan,
                            {"pack": "pack_evidence", "execute": "execute_retrieval"})
    g.add_edge("execute_retrieval", "assess_evidence")
    g.add_edge("pack_evidence", END)
    return g.compile()


_graph: Any = None


def _get_graph() -> Any:
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── Live progress events (operational stages only — no chain-of-thought) ───────
# Emitted from real per-node LangGraph boundaries so elapsed time between events reflects
# actual work, not a simulated/fake progress animation.

_NODE_EVENTS: dict[str, dict] = {
    "initial_retrieve": {"stage": "retrieval", "message": "Searching your knowledge base"},
    "assess_evidence": {"stage": "assessment", "message": "Assessing evidence coverage"},
    "plan_retrieval": {"stage": "planning", "message": "Planning additional retrieval"},
    "execute_retrieval": {"stage": "additional_retrieval", "message": "Retrieving missing evidence"},
    "pack_evidence": {"stage": "pack", "message": "Building evidence set"},
}


def _node_event(node_name: str, state: dict) -> dict:
    event = dict(_NODE_EVENTS.get(node_name, {"stage": node_name, "message": node_name}))
    event["iteration"] = state.get("iterations", 0)
    if node_name == "execute_retrieval":
        event["retrieval_calls"] = state.get("retrieval_calls", 0)
    return event


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    final_evidence: list[RetrievalResult]
    route: str           # "deterministic" | "agentic" | "abstain"
    iterations: int
    retrieval_calls: int
    stop_reason: str
    trace: list[dict]
    total_latency_ms: float
    unresolved_aspects: list[str] = field(default_factory=list)
    required_aspects: list[str] = field(default_factory=list)


def run_adaptive_agent(
    workspace_id: str,
    question: str,
    emit: Optional[Callable[[dict], None]] = None,
) -> AgentResult:
    """
    Run the bounded agentic RAG pipeline.

    workspace_id must already be server-validated by the caller.
    The agent cannot see or modify workspace_id — it flows through as an
    immutable context variable, ensuring every Qdrant query is workspace-filtered.

    `emit`, when provided, is called with a safe operational progress event (stage +
    message only, no chain-of-thought) after each graph node completes, for live query
    UX. When omitted, behavior/performance is identical to a plain `.invoke()` call —
    existing callers/tests are unaffected.
    """
    t_start = time.perf_counter()
    initial: AgentState = {
        "workspace_id": workspace_id,
        "question": question,
        "evidence_registry": {},
        "evidence_aspects": {},
        "iterations": 0,
        "retrieval_calls": 0,
        "queries_issued": [],
        "last_decision": "",
        "missing_information": "",
        "required_aspects": [],
        "uncovered_aspects": [],
        "stop_reason": "",
        "pending_queries": [],
        "query_aspect_map": {},
        "final_evidence": [],
        "trace": [],
        "t_start": t_start,
    }

    if emit is None:
        final = _get_graph().invoke(initial)
    else:
        state: dict = dict(initial)
        for step in _get_graph().stream(initial):
            for node_name, update in step.items():
                state.update(update)
                try:
                    emit(_node_event(node_name, state))
                except Exception:
                    log.warning("Progress emit callback failed; continuing query", exc_info=True)
        final = state
    total_ms = (time.perf_counter() - t_start) * 1000

    evidence = final.get("final_evidence", [])
    stop = final.get("stop_reason", "SUFFICIENT")
    route = "abstain" if (stop == "NO_SUPPORT" and not evidence) else (
        "agentic" if final.get("iterations", 0) > 0 else "deterministic"
    )
    # Only surface as "unresolved" when the hard bound cut the loop short (not a real
    # ANSWER_NOW/ABSTAIN) — the last real assessment's uncovered aspects are still in state.
    unresolved = final.get("uncovered_aspects", []) if stop in ("MAX_ITERATIONS", "MAX_CALLS") else []

    return AgentResult(
        final_evidence=evidence,
        route=route,
        iterations=final.get("iterations", 0),
        retrieval_calls=final.get("retrieval_calls", 1),
        stop_reason=stop,
        trace=final.get("trace", []),
        total_latency_ms=round(total_ms, 1),
        unresolved_aspects=unresolved,
        required_aspects=final.get("required_aspects", []),
    )
