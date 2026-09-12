"""
Deterministic arithmetic sanity-check for generated answers.

The generator LLM is instructed (see app/rag/llm.py SYSTEM_PROMPT rule 9) to write out
explicit calculations ("A - B - C - D = E") using exactly the evidence-supported inputs
the question requested. Prompt wording alone cannot guarantee correct arithmetic or
correct input selection, so this module re-derives the same numbers deterministically
with Decimal and corrects the answer text in place. No LLM call, no new workflow.

Generic by design: no domain/finance vocabulary is hard-coded. The only structural
assumption is the common phrasing "<quantity> remaining/left after A, B, and C" used to
count how many components the user explicitly requested.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# ── number tokenizing ────────────────────────────────────────────────────────────

_UNIT = r"(?:%|billion|million|thousand|[BMK])"
_NUM = rf"\$?\d[\d,]*(?:\.\d+)?(?:\s?{_UNIT})?\b"

_TOKEN_RE = re.compile(
    rf"(?P<num>{_NUM})|(?P<plus>\+)|(?P<minus>-)|(?P<eq>=)",
    re.IGNORECASE,
)

_UNIT_SUFFIX_RE = re.compile(rf"\s*{_UNIT}\s*$", re.IGNORECASE)

# Real evidence-derived amounts are exact; the LLM sometimes rounds differently.
# Tolerance is small relative to typical inputs (units of whole numbers with
# up to 3 decimals) but forgives sub-cent rounding noise, not real math errors.
_TOLERANCE = Decimal("0.01")


def _clean_number(raw: str) -> Decimal:
    s = _UNIT_SUFFIX_RE.sub("", raw.strip())
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


@dataclass
class _Operand:
    sign: int
    value: Decimal
    start: int
    end: int


@dataclass
class CalcExpression:
    start: int
    end: int
    operands: list
    result_value: Decimal
    result_start: int
    result_end: int
    raw: str


def _find_expressions(text: str) -> list:
    """Scan text for patterns of the form N (op N)+ = N, deterministically, with no
    assumptions about labels. Returns matches with original character spans so the
    caller can surgically edit just the offending substring."""
    tokens = list(_TOKEN_RE.finditer(text))

    def kind(m):
        if m.group("num") is not None:
            return "num"
        if m.group("plus") is not None:
            return "plus"
        if m.group("minus") is not None:
            return "minus"
        return "eq"

    kinds = [kind(m) for m in tokens]
    n = len(tokens)
    exprs = []
    i = 0
    while i < n:
        if kinds[i] == "num":
            operands = [_Operand(1, _clean_number(tokens[i].group("num")),
                                  tokens[i].start(), tokens[i].end())]
            j = i + 1
            while j + 1 < n and kinds[j] in ("plus", "minus") and kinds[j + 1] == "num":
                sign = 1 if kinds[j] == "plus" else -1
                operands.append(_Operand(sign, _clean_number(tokens[j + 1].group("num")),
                                          tokens[j + 1].start(), tokens[j + 1].end()))
                j += 2
            if len(operands) >= 2 and j < n and kinds[j] == "eq":
                # The result may carry its own leading sign ("= -5"), distinct from the
                # chain operators above.
                k = j + 1
                result_sign = 1
                sign_start = None
                if k < n and kinds[k] in ("plus", "minus"):
                    if kinds[k] == "minus":
                        result_sign = -1
                    sign_start = tokens[k].start()
                    k += 1
                if k < n and kinds[k] == "num":
                    result_tok = tokens[k]
                    result_start = sign_start if sign_start is not None else result_tok.start()
                    exprs.append(CalcExpression(
                        start=operands[0].start,
                        end=result_tok.end(),
                        operands=operands,
                        result_value=result_sign * _clean_number(result_tok.group("num")),
                        result_start=result_start,
                        result_end=result_tok.end(),
                        raw=text[operands[0].start:result_tok.end()],
                    ))
                    i = k + 1
                    continue
        i += 1
    return exprs


def _sum(operands: list) -> Decimal:
    total = Decimal("0")
    for op in operands:
        total += op.sign * op.value
    return total


def _matches(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= _TOLERANCE


_RESULT_DECOR_RE = re.compile(
    rf"^(?P<prefix>\$?)(?P<number>[\d,]+(?:\.\d+)?)(?P<suffix>\s*{_UNIT}?)$",
    re.IGNORECASE,
)


def _format_like(original_raw: str, value: Decimal) -> str:
    # The corrected value carries its own sign; strip any leading "-" from the original
    # decoration text so it isn't duplicated when the recomputed value is negative.
    raw = original_raw.strip()
    if raw.startswith("-"):
        raw = raw[1:]
    m = _RESULT_DECOR_RE.match(raw)
    if not m:
        return str(value)
    prefix, number, suffix = m.group("prefix"), m.group("number"), m.group("suffix")
    decimals = len(number.split(".")[1]) if "." in number else 0
    quant = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    return f"{prefix}{value.quantize(quant)}{suffix}"


# ── requested-component counting (generic, no domain vocabulary) ───────────────

_AFTER_RE = re.compile(r"\bafter\s+(.+?)(?=[.?!]|$)", re.IGNORECASE)
_SPLIT_RE = re.compile(r",\s*(?:and\s+)?|\s+and\s+", re.IGNORECASE)


def extract_requested_component_count(question: str) -> int | None:
    """How many components the question explicitly lists after 'after' (as in
    "... remaining after A, B, and C"). Returns None when no such explicit list is
    present, so callers can skip the component-count check entirely rather than guess."""
    m = _AFTER_RE.search(question)
    if not m:
        return None
    clause = m.group(1).strip()
    if not clause:
        return None
    parts = [p.strip() for p in _SPLIT_RE.split(clause) if p.strip()]
    return len(parts) if parts else None


# ── evidence support check ──────────────────────────────────────────────────────

_PLAIN_NUM_RE = re.compile(_NUM, re.IGNORECASE)


def _numbers_in_text(text: str) -> list:
    return [_clean_number(m.group(0)) for m in _PLAIN_NUM_RE.finditer(text)]


def _is_supported(value: Decimal, evidence_numbers: list) -> bool:
    return any(abs(value - n) <= _TOLERANCE for n in evidence_numbers)


# ── public API ───────────────────────────────────────────────────────────────────

@dataclass
class CalculationFix:
    original: str
    corrected: str
    reason: str  # arithmetic_corrected | extra_component_removed | missing_component | unsupported_operand


_MISSING_MSG = (
    "a definitive result could not be computed because one or more requested "
    "components were not found as separate evidence-supported values"
)
_UNSUPPORTED_MSG = (
    "a definitive result could not be computed because at least one value in this "
    "calculation is not independently supported by the retrieved evidence"
)


def enforce_deterministic_calculations(question: str, answer: str, evidence_chunks: list) -> tuple:
    """
    Deterministic post-generation sanity check + fix for explicit calculations the model
    wrote out in its own answer text.

    - Recomputes every "N (op N)+ = N" expression with Decimal and replaces a wrong
      stated result with the correct one (arithmetic_corrected).
    - When the question explicitly enumerates requested components ("... after A, B, and
      C"), an expression with MORE operands than requested (an extra/unrelated value)
      is truncated back down to the requested count before recomputing
      (extra_component_removed) — this is what stops an unrelated fifth value from
      entering an explicitly four-component calculation.
    - An expression with FEWER operands than requested, or any operand not supported by
      the retrieved evidence, is replaced with an explicit "not computable" statement
      instead of a fabricated/definitive number.

    Returns (possibly-corrected answer text, list of CalculationFix applied).
    """
    expected_n = extract_requested_component_count(question)
    expected_operands = expected_n + 1 if expected_n is not None else None

    evidence_text = "\n".join(getattr(c, "raw_text", "") or "" for c in (evidence_chunks or []))
    evidence_numbers = _numbers_in_text(evidence_text)

    exprs = _find_expressions(answer)
    fixes = []

    for expr in reversed(exprs):
        operand_count = len(expr.operands)
        unsupported = [op.value for op in expr.operands if not _is_supported(op.value, evidence_numbers)]

        if expected_operands is not None and operand_count > expected_operands:
            kept = expr.operands[:expected_operands]
            new_value = _sum(kept)
            chain_text = answer[expr.start:kept[-1].end]
            replacement = f"{chain_text} = {_format_like(answer[expr.result_start:expr.result_end], new_value)}"
            answer = answer[:expr.start] + replacement + answer[expr.end:]
            fixes.append(CalculationFix(expr.raw, replacement, "extra_component_removed"))
            continue

        if expected_operands is not None and operand_count < expected_operands:
            answer = answer[:expr.start] + _MISSING_MSG + answer[expr.end:]
            fixes.append(CalculationFix(expr.raw, _MISSING_MSG, "missing_component"))
            continue

        if unsupported:
            answer = answer[:expr.start] + _UNSUPPORTED_MSG + answer[expr.end:]
            fixes.append(CalculationFix(expr.raw, _UNSUPPORTED_MSG, "unsupported_operand"))
            continue

        computed = _sum(expr.operands)
        if not _matches(computed, expr.result_value):
            corrected = _format_like(answer[expr.result_start:expr.result_end], computed)
            answer = answer[:expr.result_start] + corrected + answer[expr.result_end:]
            fixes.append(CalculationFix(expr.raw, corrected, "arithmetic_corrected"))

    return answer, fixes
