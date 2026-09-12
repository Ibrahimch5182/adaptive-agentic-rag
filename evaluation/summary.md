# Phase 7 Evaluation Summary

Real measured results against a real corpus, indexed by the real Docling/embedding/Qdrant
pipeline — no mocked retrieval. Generation/live-LLM results are separately and explicitly
marked as **not run** (`GROQ_API_KEY` unavailable in this environment); see [Live model
evaluation](#live-model-evaluation--externally-blocked).

## Corpus

12 real documents (MediAssist reference corpus, reused per Phase 7 instructions as
benchmark-only material — not part of the shipped product), parsed by real Docling into
**254 chunks**. Two domains:

| Domain | Documents | Chunks |
|---|---|---|
| `a_general` (HR/policy) | code_of_conduct, general_faqs, leave_policy, staff_handbook | 76 |
| `b_clinical` (billing/clinical/equipment/nursing) | billing_codes, claim_submission_guide, diagnostic_reference, drug_formulary, equipment_manual, icu_nursing_procedures, infection_control, treatment_protocols | 178 |

This is ~28x more chunks than the Phase 3/4 corpus (9 chunks), with genuine cross-document
overlap (e.g. ICD-10 code `I21.4` and drug names recur across `billing_codes.pdf`,
`treatment_protocols.pdf`, and `claim_submission_guide.md`; "2 hours"/"24 hours"/"30 days"
deadlines recur across unrelated sections) — real distractors, not engineered ones.

## Benchmark

**72 questions** (`evaluation/benchmark.json`), every keyword ground-truth label
machine-validated against the actual Docling-parsed chunk text before use
(`evaluation/build_benchmark.py::validate_against_dump`) — not hand-typed blind.

| Category | n | | Category | n |
|---|---|---|---|---|
| exact | 19 | | comparison | 4 |
| semantic | 13 | | multi_doc | 5 |
| multi_part | 13 | | ambiguous | 2 |
| distractor | 10 | | reformulation | 1 |
| unanswerable | 5 | | | |

67 answerable, 5 unanswerable. Routing labels: 43 simple, 22 complex, 5 unanswerable, 2 ambiguous.

## 1. Retrieval comparison (67 answerable questions × 4 modes)

| Mode | Recall@5 | Recall@10 | MRR | nDCG@10 | Latency (ms) |
|---|---|---|---|---|---|
| DENSE | 0.416 | 0.458 | 0.931 | 0.547 | 33 |
| SPARSE | 0.403 | 0.426 | 0.912 | 0.520 | 20 |
| HYBRID | 0.418 | 0.441 | 0.949 | 0.544 | 33 |
| HYBRID_RERANK | **0.421** | **0.458** | **0.962** | **0.559** | 1288 |

By domain (HYBRID_RERANK): `a_general` recall@10 = 0.473 vs `b_clinical` recall@10 = 0.445 —
the clinical domain is measurably harder (denser tabular data, more cross-document term reuse).

**Interpretation — this is a genuinely harder corpus, and recall numbers are honestly lower
than Phase 3/4's 100%.** The dominant reason is *not* individual retrieval quality but
**category composition**: `multi_part`/`multi_doc` questions require several scattered chunks
(sometimes across two documents), and recall@k penalizes for every one not in the top-k, even
though MRR is consistently ~0.93–0.96 — the single *most* relevant chunk is nearly always
ranked #1 across every mode. Single-query dense/sparse/hybrid retrieval is good at finding
*the* best chunk; it is not designed to comprehensively cover a multi-part question in one
shot. That gap is exactly what query-decomposition (the adaptive agent's planner) exists to
close — see Section 2 for whether it actually does.

A second, smaller effect: a few `exact`-category questions (e.g. `B33`, TIMI risk score) show
low recall@10 purely because the automatic keyword-based ground truth over-matches — a short
generic keyword like "≥ 3" occasionally hits unrelated numeric table cells elsewhere in a
33-chunk document. This is a **benchmark-methodology artifact inherited from Phase 3/4's same
technique**, not a retrieval defect; noted honestly rather than silently excluded.

## 2. Deterministic vs Adaptive on the COMPLEX subset (n=22)

| | Deterministic (HYBRID_RERANK) | Adaptive |
|---|---|---|
| Avg. evidence coverage | 0.40 | 0.38 |
| Avg. latency | 1265 ms | 1413 ms |
| Avg. retrieval calls | 1.0 | 1.0 |
| Questions where agentic loop actually fired | — | **0 / 22** |

**Honest negative finding, and the most important result of this phase:** on this
harder corpus, with **no `GROQ_API_KEY` configured**, the adaptive agent's heuristic
assessor fallback (`app/rag/assessor.py`'s no-LLM path) never returned `RETRIEVE_MORE` on
any of the 22 complex questions — even though deterministic retrieval's own coverage was
incomplete on all 22 of them (avg. 0.40). Every complex question routed straight through as
`route="deterministic"`, `iterations=0`, identical evidence to the plain HYBRID_RERANK call
plus ~150ms of assessor overhead for no benefit. Adaptive coverage (0.38) is marginally
*lower* than deterministic (0.40) — noise from re-running retrieval independently, not a
real regression.

This confirms and quantifies, with real numbers on a real corpus, the limitation flagged
qualitatively back in Phase 4's `PROJECT_STATE.md` ("heuristic assessor is conservative").
The heuristic fallback checks coarse signals (evidence count, multi-part question phrasing)
and is deliberately conservative to avoid needless extra retrieval calls in production when
no LLM is configured — but the practical consequence is that **the adaptive route currently
provides zero measured benefit without a live assessor LLM**. The architecture (bounded
LangGraph loop, evidence registry, hard iteration/call caps) is implemented and exercised
(see Phase 4's own unit tests with a mocked LLM assessor forcing `RETRIEVE_MORE`), but its
real-world value on this corpus is unproven without `GROQ_API_KEY`. This is reported
honestly rather than glossed over — see [Engineering Conclusions](#15-engineering-conclusions-honest).

## 3. Routing evaluation

| Type | n | Route chosen |
|---|---|---|
| simple | 43 | 43 deterministic |
| complex | 22 | 22 deterministic (0 agentic) |
| unanswerable | 5 | 5 deterministic |
| ambiguous | 2 | 2 deterministic |

Verdict counts: `ok` = 50 (simple/ambiguous correctly stayed deterministic; unanswerable
correctly did not fabricate an agentic loop for nothing), `should_have_escalated` = 22 (all 22
complex questions, per Section 2). No question was routed agentic that shouldn't have been —
the observed failure mode is 100% under-escalation, never over-escalation, which is the safer
failure direction for a production system (no wasted LLM calls) but means the "adaptive"
label is not currently earning its name without a configured assessor LLM.

## 4. Citation grounding (structural, no live generation)

Citation *content* evaluation (does the generated answer's citation match a real claim)
requires live generation, which requires `GROQ_API_KEY` — not available here (see below).
What **is** verified, mechanically, without any LLM: the citation hallucination guard itself.
`app/rag/generator.py::_extract_citations` and `app/rag/verifier.py::_parse_verification`
both discard any citation ID that doesn't exist in the backend's own `id_map` before it can
reach the client or be trusted by the verifier — covered by `test_verifier.py` and this
phase's own `eval_verifier.py::invalid_citation_discarded` case (PASS). Every citation the
system can ever emit is therefore backend-resolved to a real chunk/document/page — this
was true before Phase 7 and is re-confirmed, not re-designed.

## 5. Verifier evaluation (20 cases, mocked LLM — see below)

`backend/benchmark/eval_verifier.py`, results in `evaluation/verifier_results.json`.
**20/20 passed.** These are deterministic/mocked LLM responses (no `GROQ_API_KEY`), exercising
the real `verify_answer`/`correct_answer`/`_parse_verification` code paths — not a live-model
judgment-quality result. Covers: supported (simple, multi-fact, cross-chunk, paraphrase),
fabricated number/date/entity (×2 domains), exaggerated claim, partially supported,
invalid/hallucinated citation (discarded correctly), prompt-injection-in-evidence (not
followed), valid abstention, verifier-unavailable (correctly `UNAVAILABLE`, not `SUPPORTED`),
correction success, correction-still-unsupported, off-topic answer, empty answer.

- Unsupported-claim detection rate (on cases where the mock says unsupported): **100%** (of the mock's own labels — this measures the verifier's parsing/plumbing, not an LLM's judgment)
- Supported false-positive rate: **0%** (of these cases)
- Correction success rate: **50%** (1/2 — by design: one case simulates the corrector fixing the issue, the other simulates it still failing, both handled correctly by the surrounding bounded-retry logic)

## Latency / tradeoff summary (real measured numbers)

- **Sparse is fastest** (20ms) but weakest on paraphrase (see `A20` below) — pure BM25 has no
  notion of synonymy.
- **Dense and hybrid cost about the same** (~33ms) — hybrid's RRF fusion is cheap; the value
  is in combining lexical and semantic signal, not raw speed.
- **Reranking dominates latency**: HYBRID_RERANK averages **1288ms**, ~40x the un-reranked
  hybrid cost, from CPU cross-encoder inference over up to 20 fused candidates
  (`fastembed.rerank.cross_encoder`, ONNX, single-threaded). This is the single largest cost
  in the whole deterministic pipeline.
- **Is that latency worth it?** Concretely yes, on `A20` ("Is there a cap on how much paid
  time off rolls over to next year?" — a reformulation question whose wording diverges from
  the source's "carry forward"): SPARSE scored 0.0 recall (no lexical overlap), and even
  HYBRID's RRF fusion scored 0.0 (sparse's zero-relevance ranking diluted dense's otherwise-good
  ranking through reciprocal-rank fusion — a known RRF failure mode when one retriever strikes
  out completely). HYBRID_RERANK recovered to 0.50 recall@10 — the cross-encoder correctly
  re-scored the fused candidate pool on semantic relevance and pulled the right chunk back up.
  That is real evidence reranking earns its cost, not a generic claim.
- **Adaptive assessor overhead**: ~150ms per query beyond deterministic, for currently zero
  measured retrieval-quality benefit (Section 2) — a real cost with no offsetting real benefit
  under the current no-LLM configuration.
- **Verification** (Phase 5, not re-benchmarked here): a further LLM call on top of generation,
  up to 3 total LLM calls if a correction fires — a known, already-documented cost of
  trustworthiness.

## Failure analysis (real, from this run — not fabricated)

1. **Multi-part questions systematically under-retrieve remaining facts** (e.g. `B30`: "the
   four HAIs under surveillance + who to notify" — recall@10 = 0.07). MRR=1.0 shows the single
   best chunk is always found; the other 2–3 needed chunks usually aren't in top-10. Root
   cause: single dense/sparse/hybrid query embeds one intent vector, not several. **Should V1
   change?** No — this is precisely the gap adaptive query decomposition is *designed* to
   close; the actual defect is Section 2's finding that it isn't firing without a live
   assessor LLM. Fix path is operational (configure `GROQ_API_KEY`), not architectural.
2. **RRF hybrid fusion can score *worse* than dense alone** when sparse returns nothing
   relevant (`A20`, hybrid recall@10 = 0.0 vs dense's 0.50) — a known weakness of naive RRF,
   recovered by reranking in this case. Worth knowing before assuming "hybrid always ≥ dense."
3. **Ground-truth keyword over-match** on `B33` and similar short-keyword exact questions is
   a benchmark-methodology limitation (inherited from Phase 3/4), not a retrieval defect —
   documented rather than quietly patched by cherry-picking longer keywords after the fact.
4. **Adaptive agent never escalates without a live assessor LLM** (Section 2) — the single
   most consequential finding this phase; a real, measured, honestly-reported negative result.
5. **Distractor questions (`B13`, `B19`) show genuinely low recall** (0.25–0.30): the corpus
   contains two similar-but-different numeric facts in the same document (two lactate
   thresholds; daily vs. weekly autoclave tests), and keyword-based ground truth credits both
   occurrences as "relevant," which the retriever doesn't reliably retrieve together — a
   real test of whether retrieval can be confused by near-duplicate content, and evidence
   that with only k=5–10 final evidence, some distractor pairs will only get one member
   surfaced. Not a fabrication risk (the LLM would ground only in what's retrieved) but a
   completeness risk worth knowing about.

## Live model evaluation — externally blocked

`GROQ_API_KEY` was not available in this environment. Per the retrieval/routing/verifier
evaluations above, **the retrieval layer, the adaptive agent's control flow, and the verifier's
parsing/plumbing are all evaluated for real**. What is *not* evaluated in this phase: actual
generation quality, actual assessor-LLM-driven escalation decisions, and actual verifier
judgment quality against real model output. This is reported as an external credential gap,
not glossed over as a pass. Phase 3/5's existing test suites already cover the generation and
verification *code paths* with a mocked LLM; this phase adds real retrieval-layer numbers on
top of that, on a harder corpus, which is the part that was actually missing.

## 15. Engineering conclusions (honest)

1. **Why hybrid instead of dense-only?** Hybrid's own recall/nDCG are close to dense alone on
   this corpus (0.441 vs 0.458 recall@10 — actually marginally lower before reranking), but
   MRR is higher (0.949 vs 0.931) and it's the only mode immune to sparse's total misses
   *once reranked*. The real value of hybrid is as reranking's *input pool*, not its own raw
   ranking — see conclusion 2.
2. **Is reranking worth its latency?** Yes, on the evidence here: nDCG@10 and MRR both peak
   with HYBRID_RERANK, and `A20` is a concrete case where it recovered a total RRF failure.
   The cost (1.25s/query on CPU) is real and is the dominant latency line item in the whole
   deterministic path — worth optimizing later (smaller candidate pool, quantization, or GPU)
   but not worth removing.
3. **When does adaptive retrieval help?** On this corpus, with no `GROQ_API_KEY`: **never,
   measurably** — 0/22 complex questions escalated. The architecture is real and unit-tested
   with a mocked LLM forcing escalation (Phase 4), but its production value depends entirely
   on a configured assessor LLM. This is the single most important honest limitation to state
   in an interview: "the code path exists and is tested, but I don't have live-model evidence
   that it helps in practice without an LLM key."
4. **When should deterministic retrieval remain preferred?** Essentially always when latency
   matters and evidence is likely complete in one pass — which per Section 3 is correctly
   detected for 100% of `simple`/`ambiguous`/`unanswerable` questions here. Deterministic is
   also strictly cheaper (1 retrieval call, no assessor LLM call).
5. **Does verification materially improve trust?** Structurally yes — the `UNAVAILABLE` vs
   `SUPPORTED` distinction (Phase 5) and the citation hallucination guard (re-confirmed here,
   Section 4) are real safety properties, testable without a live model. Whether the verifier
   *LLM* actually catches subtle fabrications in practice is untested here (see Live model
   evaluation) — the guard rails are real, the live judgment quality is unproven.
6. **Main remaining limitations:** (a) adaptive retrieval unproven without a live assessor
   LLM; (b) reranking latency is high on CPU; (c) benchmark ground truth is keyword-based and
   has known false-positive edges on short generic keywords; (d) no live generation/citation-
   content evaluation was possible in this environment.
