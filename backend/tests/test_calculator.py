"""
Deterministic calculation sanity-check tests (no LLM involved — pure functions).

Regression target: a live query asked for cash remaining after PPE additions, share
repurchases, and dividends (exactly 3 named components + 1 base = 4 operands,
136.162 - 64.551 - 18.420 - 24.082 = 29.109). Previous LLM answers added an unrelated
debt-repayment figure and/or got the arithmetic wrong.
"""
from decimal import Decimal
from app.rag.retriever import RetrievalResult
from app.rag.calculator import (
    enforce_deterministic_calculations,
    extract_requested_component_count,
    _find_expressions,
    _sum,
)

QUESTION = (
    "Calculate the approximate cash remaining after property-and-equipment additions, "
    "share repurchases, and dividends."
)


def _chunk(raw: str, point_id="pt1"):
    return RetrievalResult(
        point_id=point_id, document_id="doc1", chunk_index=0,
        raw_text=raw, retrieval_text=raw, filename="msft.pdf",
        section_title="Cash Flow", page_numbers=[1], score=0.9, mode="hybrid_rerank",
    )


_EVIDENCE = _chunk(
    "Net cash from operations was $136.162 billion. Additions to property and equipment "
    "were $64.551 billion. Share repurchases were $18.420 billion. Cash dividends paid "
    "were $24.082 billion. Repayments of debt were $3.216 billion."
)


# ── 1. exact deterministic arithmetic ───────────────────────────────────────────

def test_exact_four_component_subtraction():
    exprs = _find_expressions("136.162 - 64.551 - 18.420 - 24.082 = 29.109")
    assert len(exprs) == 1
    assert _sum(exprs[0].operands) == Decimal("29.109")


def test_wrong_stated_result_is_corrected():
    answer = "Cash remaining is 136.162 - 64.551 - 18.420 - 24.082 = 25.893 [S1]."
    fixed, fixes = enforce_deterministic_calculations(QUESTION, answer, [_EVIDENCE])
    assert "29.109" in fixed
    assert "25.893" not in fixed
    assert any(f.reason == "arithmetic_corrected" for f in fixes)


def test_already_correct_arithmetic_untouched():
    answer = "Cash remaining is 136.162 - 64.551 - 18.420 - 24.082 = 29.109 [S1]."
    fixed, fixes = enforce_deterministic_calculations(QUESTION, answer, [_EVIDENCE])
    assert fixed == answer
    assert fixes == []


# ── 2. an unrelated fifth value cannot enter an explicit four-component calc ────

def test_extra_unrelated_value_is_stripped():
    """The LLM adds debt repayment (3.216) even though only 3 components (+1 base) were
    requested — the extra value must not survive into the final computed result."""
    answer = ("Cash remaining is 136.162 - 64.551 - 18.420 - 24.082 - 3.216 = 25.893 [S1].")
    fixed, fixes = enforce_deterministic_calculations(QUESTION, answer, [_EVIDENCE])
    assert "3.216" not in fixed
    assert "29.109" in fixed
    assert any(f.reason == "extra_component_removed" for f in fixes)


def test_requested_component_count_extraction():
    assert extract_requested_component_count(QUESTION) == 3
    assert extract_requested_component_count("What is the revenue?") is None


# ── 3. missing requested component prevents a definitive result ────────────────

def test_missing_component_blocks_definitive_result():
    """Only 3 operands present (base + 2) when the question requires base + 3 — must not
    fabricate a confident number."""
    answer = "Cash remaining is 136.162 - 64.551 - 18.420 = 53.191 [S1]."
    fixed, fixes = enforce_deterministic_calculations(QUESTION, answer, [_EVIDENCE])
    assert "53.191" not in fixed
    assert "not" in fixed.lower()
    assert any(f.reason == "missing_component" for f in fixes)


def test_operand_not_supported_by_evidence_blocks_definitive_result():
    answer = "Cash remaining is 136.162 - 64.551 - 18.420 - 999.999 = -866.808 [S1]."
    fixed, fixes = enforce_deterministic_calculations(QUESTION, answer, [_EVIDENCE])
    assert "-866.808" not in fixed
    assert any(f.reason == "unsupported_operand" for f in fixes)


def test_no_calculation_in_answer_is_a_no_op():
    answer = "Revenue was $281.7 billion [S1]."
    fixed, fixes = enforce_deterministic_calculations(QUESTION, answer, [_EVIDENCE])
    assert fixed == answer
    assert fixes == []
