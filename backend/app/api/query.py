"""RAG query endpoint — deterministic and adaptive modes with lightweight verification."""
from __future__ import annotations
import json
import logging
import queue
import threading
import time
from typing import Callable, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.models.document import Document, DocumentStatus
from app.rag.retriever import RetrievalMode, retrieve
from app.rag.generator import generate_answer, Citation, _extract_citations

EmitFn = Callable[[dict], None]
_NOOP_EMIT: EmitFn = lambda event: None

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["query"])

# A surgical correction touches only the flagged claim(s); it should not shrink a long,
# multi-aspect answer down to a fragment. Below this length ratio (or a near-total citation
# collapse), treat the correction as unsafe and keep the original answer instead — the same
# "never silently present something worse as fixed" principle as the UNAVAILABLE status.
_MIN_CORRECTION_LENGTH_RATIO = 0.5

_DETERMINISTIC_MODES = {m.value for m in RetrievalMode}
_VALID_MODES = _DETERMINISTIC_MODES | {"adaptive", "deterministic"}


class QueryRequest(BaseModel):
    question: str
    mode: Optional[str] = "adaptive"
    verify: bool = True  # enable lightweight verification


class CitationOut(BaseModel):
    citation_id: str
    chunk_id: str
    document_id: str
    filename: str
    section_title: str
    page_numbers: list[int]
    snippet: str = ""


class VerificationOut(BaseModel):
    status: str           # SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED
    unsupported_claims: int
    corrected: bool


class TimingOut(BaseModel):
    retrieval_ms: float
    generation_ms: float
    verification_ms: float
    total_ms: float


class TraceOut(BaseModel):
    route: str
    iterations: int
    retrieval_calls: int
    stop_reason: str
    queries_issued: list[str]


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    retrieval_mode: str
    evidence_count: int
    insufficient: bool
    verification: Optional[VerificationOut] = None
    timing: Optional[TimingOut] = None
    trace: Optional[TraceOut] = None
    # legacy field kept for compatibility
    retrieval_latency_ms: float = 0.0


def _require_member(db: Session, user_id, workspace_id) -> WorkspaceMembership:
    m = (db.query(WorkspaceMembership)
         .filter(WorkspaceMembership.user_id == user_id,
                 WorkspaceMembership.workspace_id == workspace_id)
         .first())
    if not m:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return m


def _citation_out(c: Citation) -> CitationOut:
    return CitationOut(
        citation_id=c.citation_id, chunk_id=c.chunk_id, document_id=c.document_id,
        filename=c.filename, section_title=c.section_title, page_numbers=c.page_numbers,
        snippet=c.snippet,
    )


def _correction_preserves_completeness(original: str, corrected: str, orig_citation_count: int,
                                        new_citation_count: int) -> bool:
    """Deterministic guard: reject a correction that looks like it destroyed content rather
    than surgically fixing the flagged claim(s), instead of trusting the LLM's own claim that
    it only made a targeted edit."""
    if not corrected or not corrected.strip():
        return False
    if len(corrected) < len(original) * _MIN_CORRECTION_LENGTH_RATIO:
        return False
    if orig_citation_count >= 3 and new_citation_count == 0:
        return False
    return True


def _run_verification(question: str, gen, chunks: list, verify: bool, emit: EmitFn = _NOOP_EMIT):
    """
    Run verify + optional correction (max 1 each). Returns (gen, verification_result, v_ms).
    If LLM unavailable, returns gen unchanged with SUPPORTED status.

    After a correction is accepted, re-verification targets ONLY the claims/sentences the
    correction actually changed (against only the evidence those sentences cite) rather
    than re-sending the full answer and full evidence set a second time — this is the
    dominant cost of the verify->correct->reverify cascade on long multi-aspect answers.
    Falls back to a full re-verify when the correction cannot be safely treated as
    surgical (see `is_surgical_correction`), and never upgrades to SUPPORTED when the
    targeted re-verification call itself is unavailable.
    """
    from app.rag.verifier import (
        verify_answer, correct_answer, verify_targeted,
        diff_changed_sentences, is_surgical_correction, combine_verification_status,
        VerificationResult,
    )
    from app.rag.generator import INSUFFICIENT_EVIDENCE

    if not verify or gen.insufficient:
        return gen, None, 0.0

    t0 = time.perf_counter()
    emit({"stage": "verification", "message": "Verifying claims"})
    v_result = verify_answer(question, gen.answer, chunks, gen.id_map)

    # Correction: at most once, only if not SUPPORTED and LLM available
    if v_result.status != "SUPPORTED" and v_result.llm_calls > 0:
        emit({"stage": "correction", "message": "Applying supported corrections"})
        corrected_text = correct_answer(question, gen.answer, v_result, chunks)
        new_citations = _extract_citations(corrected_text, gen.id_map) if corrected_text else []

        if corrected_text and _correction_preserves_completeness(
            gen.answer, corrected_text, len(gen.citations), len(new_citations),
        ):
            insufficient = INSUFFICIENT_EVIDENCE in corrected_text or not corrected_text.strip()
            flagged_count = sum(1 for c in v_result.claims if c.status != "SUPPORTED")
            changed_sentences = diff_changed_sentences(gen.answer, corrected_text)
            original_answer = gen.answer

            import dataclasses
            gen = dataclasses.replace(gen, answer=corrected_text,
                                      citations=new_citations, insufficient=insufficient)

            if is_surgical_correction(original_answer, corrected_text, changed_sentences, flagged_count):
                v2 = verify_targeted(question, changed_sentences, gen.id_map)
                preserved = [c for c in v_result.claims if c.status == "SUPPORTED"]

                if v2.status == "UNAVAILABLE":
                    # Targeted re-verification couldn't confirm the fix — do not present
                    # the (possibly still-wrong) corrected claims as SUPPORTED.
                    v_result = VerificationResult(
                        status=v_result.status,
                        claims=v_result.claims,
                        unsupported_claim_count=v_result.unsupported_claim_count,
                        corrected=True,
                        llm_calls=v_result.llm_calls + 1 + v2.llm_calls,
                    )
                else:
                    merged_claims = preserved + v2.claims
                    merged_statuses = ["SUPPORTED"] * len(preserved) + [c.status for c in v2.claims]
                    v_result = VerificationResult(
                        status=combine_verification_status(merged_statuses),
                        claims=merged_claims,
                        unsupported_claim_count=sum(1 for s in merged_statuses if s != "SUPPORTED"),
                        corrected=True,
                        llm_calls=v_result.llm_calls + 1 + v2.llm_calls,
                    )
            else:
                # Correction touched too much of the answer to safely scope re-verification
                # — fall back to the original full-answer, full-evidence re-verify.
                v2 = verify_answer(question, corrected_text, chunks, gen.id_map)
                v2.corrected = True
                v2.llm_calls += v_result.llm_calls + 1
                v_result = v2
        elif corrected_text:
            log.warning(
                "Correction rejected by completeness guard (orig=%d chars/%d citations, "
                "corrected=%d chars/%d citations); keeping original answer",
                len(gen.answer), len(gen.citations), len(corrected_text), len(new_citations),
            )

    v_result.verification_latency_ms = (time.perf_counter() - t0) * 1000
    return gen, v_result, v_result.verification_latency_ms


def _extract_queries(trace: list[dict]) -> list[str]:
    queries = []
    for entry in trace:
        if entry.get("step") == "initial_retrieve":
            if (q := entry.get("query", "")):
                queries.append(q)
        elif entry.get("step") == "plan":
            for q in entry.get("queries", []):
                if q:
                    queries.append(q)
    return queries


def _execute_query(
    workspace_id: UUID,
    req: QueryRequest,
    db: Session,
    emit: EmitFn = _NOOP_EMIT,
) -> QueryResponse:
    """Shared query pipeline. `emit` receives safe operational progress events (stage +
    message only — no chain-of-thought, no prompts) at real phase boundaries; it is a
    no-op for the plain JSON endpoint and forwards to an SSE stream for the live-progress
    endpoint. Behavior/response shape is identical regardless of `emit`."""
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")

    mode = (req.mode or "adaptive").lower()
    if mode not in _VALID_MODES:
        raise HTTPException(400, f"Invalid mode. Valid: {sorted(_VALID_MODES)}")

    emit({"stage": "received", "message": "Query received"})

    ready_count = (db.query(Document)
                   .filter(Document.workspace_id == workspace_id,
                           Document.status == DocumentStatus.ready)
                   .count())
    if ready_count == 0:
        return QueryResponse(
            answer="No documents are ready in this workspace.",
            citations=[], retrieval_mode=mode, retrieval_latency_ms=0.0,
            evidence_count=0, insufficient=True,
        )

    ws_id = str(workspace_id)
    t_total_start = time.perf_counter()

    if mode in ("adaptive", "deterministic"):
        use_adaptive = (mode == "adaptive")
    else:
        use_adaptive = False

    t_ret_start = time.perf_counter()

    unresolved_note = ""
    required_aspects: list = []
    if use_adaptive:
        from app.rag.agent import run_adaptive_agent
        agent_result = run_adaptive_agent(ws_id, req.question, emit=emit)
        chunks = agent_result.final_evidence
        ret_ms = agent_result.total_latency_ms
        trace = TraceOut(
            route=agent_result.route,
            iterations=agent_result.iterations,
            retrieval_calls=agent_result.retrieval_calls,
            stop_reason=agent_result.stop_reason,
            queries_issued=_extract_queries(agent_result.trace),
        )
        retrieval_mode_str = f"adaptive/{agent_result.route}"
        # Hard bound reached before the assessor found full coverage — tell generation
        # to say so explicitly rather than silently presenting a partial answer as complete.
        unresolved_note = "; ".join(agent_result.unresolved_aspects)
        required_aspects = agent_result.required_aspects
    else:
        emit({"stage": "retrieval", "message": "Searching your knowledge base"})
        det_mode = RetrievalMode.HYBRID_RERANK if mode == "deterministic" else RetrievalMode(mode)
        retrieval = retrieve(workspace_id=ws_id, question=req.question, mode=det_mode)
        chunks = retrieval.results
        ret_ms = retrieval.latency_ms
        retrieval_mode_str = retrieval.mode
        trace = None

    t_gen_start = time.perf_counter()
    emit({"stage": "generation", "message": "Generating grounded answer"})
    gen = generate_answer(req.question, chunks, unresolved_note=unresolved_note,
                           required_aspects=required_aspects)
    gen_ms = (time.perf_counter() - t_gen_start) * 1000

    if not gen.insufficient:
        from app.rag.calculator import enforce_deterministic_calculations
        fixed_answer, calc_fixes = enforce_deterministic_calculations(req.question, gen.answer, chunks)
        if calc_fixes:
            log.info("Deterministic calculation fixes applied: %s", [f.reason for f in calc_fixes])
            gen.answer = fixed_answer

    gen, v_result, v_ms = _run_verification(req.question, gen, chunks, req.verify, emit=emit)

    total_ms = (time.perf_counter() - t_total_start) * 1000

    verification_out = None
    if v_result:
        verification_out = VerificationOut(
            status=v_result.status,
            unsupported_claims=v_result.unsupported_claim_count,
            corrected=v_result.corrected,
        )

    emit({"stage": "finalizing", "message": "Finalizing response"})

    return QueryResponse(
        answer=gen.answer,
        citations=[_citation_out(c) for c in gen.citations],
        retrieval_mode=retrieval_mode_str,
        retrieval_latency_ms=ret_ms,
        evidence_count=gen.evidence_count,
        insufficient=gen.insufficient,
        verification=verification_out,
        timing=TimingOut(
            retrieval_ms=round(ret_ms, 1),
            generation_ms=round(gen_ms, 1),
            verification_ms=round(v_ms, 1),
            total_ms=round(total_ms, 1),
        ),
        trace=trace,
    )


@router.post("/{workspace_id}/query", response_model=QueryResponse)
def query_workspace(
    workspace_id: UUID,
    req: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_member(db, current_user.id, workspace_id)
    return _execute_query(workspace_id, req, db)


@router.post("/{workspace_id}/query/stream")
def query_workspace_stream(
    workspace_id: UUID,
    req: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Same pipeline as /query, but streamed as Server-Sent Events so the client can show
    real operational progress (no chain-of-thought, no fabricated percentages) during a
    long adaptive query. Terminal event is either {"stage": "complete", "result": <QueryResponse>}
    or {"stage": "error", "message": <safe user-facing message>}."""
    _require_member(db, current_user.id, workspace_id)

    events: "queue.Queue[Optional[dict]]" = queue.Queue()

    def worker():
        try:
            def emit(event: dict):
                events.put(event)
            result = _execute_query(workspace_id, req, db, emit=emit)
            events.put({"stage": "complete", "result": json.loads(result.model_dump_json())})
        except HTTPException as exc:
            events.put({"stage": "error", "message": str(exc.detail)})
        except Exception:
            log.exception("Streaming query failed")
            events.put({"stage": "error", "message": "Something interrupted this query."})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_source():
        while True:
            event = events.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
