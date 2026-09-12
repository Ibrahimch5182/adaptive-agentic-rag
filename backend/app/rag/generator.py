"""
Grounded generation with evidence packing and citation extraction.

raw_text is the authoritative evidence for answers.
retrieval_text was used for retrieval/reranking but is NOT sent as evidence.
The LLM never sees workspace_id or other internal identifiers.
"""
from __future__ import annotations
import re
import logging
from dataclasses import dataclass, field
from app.rag.retriever import RetrievalResult

log = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE = "The available documents do not contain enough information to answer this question."


def is_pure_abstention(answer: str) -> bool:
    """True only when the ENTIRE answer is the abstention sentence (or empty) — a mixed
    answer that states several facts and merely mentions, for one aspect, that evidence
    was insufficient is NOT a pure abstention. Substring matching here previously caused
    substantive multi-aspect answers to be flagged `insufficient=True` in full (skipping
    verification and discarding all citations) just because one sentence echoed that
    phrase for a single unresolved aspect."""
    stripped = answer.strip()
    return not stripped or stripped == INSUFFICIENT_EVIDENCE


@dataclass
class Citation:
    citation_id: str
    chunk_id: str
    document_id: str
    filename: str
    section_title: str
    page_numbers: list[int]
    snippet: str = ""  # truncated raw_text for source card display


@dataclass
class GenerationResult:
    answer: str
    citations: list[Citation]
    evidence_count: int
    insufficient: bool
    id_map: dict = field(default_factory=dict)  # citation_id -> RetrievalResult (for verifier)


def _build_evidence_block(chunks: list[RetrievalResult]) -> tuple[str, dict[str, RetrievalResult]]:
    lines = []
    id_map: dict[str, RetrievalResult] = {}
    for i, c in enumerate(chunks):
        cid = f"S{i+1}"
        id_map[cid] = c
        lines.append(
            f"[{cid}]\n"
            f"Document: {c.filename}\n"
            f"Section: {c.section_title or 'N/A'}\n"
            f"Page(s): {', '.join(str(p) for p in c.page_numbers) if c.page_numbers else 'N/A'}\n"
            f"{c.raw_text}"
        )
    return "\n\n---\n\n".join(lines), id_map


def _extract_citations(answer: str, id_map: dict[str, RetrievalResult]) -> list[Citation]:
    """Extract [Sn] references; discard any IDs not in id_map (hallucination guard).

    Also tolerates the fullwidth CJK bracket variant (【Sn】) the model occasionally
    emits instead of the prompted ASCII brackets — same ID, different glyph.
    """
    found = sorted(set(re.findall(r"[\[【]S(\d+)[\]】]", answer)))
    citations = []
    for num in found:
        cid = f"S{num}"
        if cid in id_map:
            c = id_map[cid]
            citations.append(Citation(
                citation_id=cid,
                chunk_id=c.point_id,
                document_id=c.document_id,
                filename=c.filename,
                section_title=c.section_title,
                page_numbers=c.page_numbers,
                snippet=c.raw_text[:250].strip(),
            ))
    return citations


def generate_answer(
    question: str,
    chunks: list[RetrievalResult],
    unresolved_note: str = "",
    required_aspects: list[str] | None = None,
) -> GenerationResult:
    """
    Build evidence pack, call LLM, extract citations.
    Falls back to INSUFFICIENT_EVIDENCE if no chunks or LLM is unavailable.
    Returns id_map for downstream verification.

    unresolved_note: aspects the adaptive agent could not find evidence for before
    hitting its retrieval bound — the LLM is told to state this explicitly rather
    than implying full coverage.

    required_aspects: every distinct aspect the adaptive agent's assessor identified in
    the question (multi-part questions only) — passed through so generation can require
    one section per aspect instead of letting the model silently drop one.
    """
    if not chunks:
        return GenerationResult(
            answer=INSUFFICIENT_EVIDENCE,
            citations=[], evidence_count=0, insufficient=True,
        )

    evidence_block, id_map = _build_evidence_block(chunks)

    try:
        from app.rag.llm import generate
        answer = generate(question, evidence_block, unresolved_note=unresolved_note,
                           required_aspects=required_aspects)
    except RuntimeError as e:
        log.warning("LLM unavailable: %s", e)
        answer = INSUFFICIENT_EVIDENCE
    except Exception as e:
        # Provider-level failure (e.g. Groq 429 rate limit) — degrade the same as
        # "LLM unavailable" rather than letting it surface as an unhandled 500.
        # Logged distinctly so a quota error is never mistaken for an application bug.
        from groq import RateLimitError
        if isinstance(e, RateLimitError):
            log.warning("Groq rate limit hit during generation (provider quota, not an application bug): %s", e)
        else:
            log.warning("Generation LLM call failed: %s", e)
        answer = INSUFFICIENT_EVIDENCE

    insufficient = is_pure_abstention(answer)
    citations = _extract_citations(answer, id_map) if not insufficient else []

    return GenerationResult(
        answer=answer,
        citations=citations,
        evidence_count=len(chunks),
        insufficient=insufficient,
        id_map=id_map,
    )
