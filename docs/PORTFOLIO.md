# Portfolio Material

## CV bullets (4)

1. Built a production adaptive RAG engine (FastAPI/Next.js/Qdrant/LangGraph) with hybrid
   dense+sparse retrieval, RRF fusion, and cross-encoder reranking, measured at MRR 0.96 /
   nDCG@10 0.56 on a real 254-chunk, 72-question, two-domain benchmark.
2. Designed a bounded LangGraph retrieval agent (hard-capped at 3 iterations / 5 calls / 15
   evidence chunks, workspace_id immutable through the graph) with deterministic-first
   routing — then ran an honest evaluation that measured its escalation rate at 0% without a
   configured assessor LLM, and reported that limitation rather than hiding it.
3. Implemented a citation-grounding and post-generation verification pipeline
   (`SUPPORTED`/`PARTIALLY_SUPPORTED`/`UNSUPPORTED`/`UNAVAILABLE`) with a hallucination guard
   that discards any model-invented citation ID against a backend-owned evidence map, and a
   prompt-injection-resistant evidence framing verified with a dedicated test case.
4. Took the system from local dev to production-hardened infrastructure: fixed a real
   torch/torchvision ABI mismatch and an RQ job-ID compatibility bug found only via live
   Docker E2E testing (not unit tests), built a shared CPU-only backend/worker image with zero
   CUDA dependencies, added an S3-capable storage abstraction, and wrote CI + deployment config.

## 30-second interview explanation

"It's a multi-tenant RAG system where retrieval escalates only when it needs to. Most queries
go through one deterministic hybrid-search-plus-rerank pass; a bounded LangGraph agent only
kicks in when an assessor judges the evidence incomplete, capped at 3 extra iterations so it
can never run away. Everything's grounded — citations are backend-resolved, not model-trusted,
and a lightweight verifier checks answers against evidence before they're shown. I ran a real
evaluation on a 72-question two-domain benchmark and found the adaptive escalation doesn't
actually fire without a live assessor LLM configured — which was the most useful thing the
evaluation told me, and I reported it instead of burying it."

## 2-minute technical explanation

"The core design question was: when is an agent loop actually worth its cost? So the
architecture routes every query through deterministic HYBRID_RERANK first — dense embeddings,
sparse BM25, reciprocal rank fusion, then a cross-encoder reranker. That alone handles
single-hop questions well. For questions that need more — multi-part, multi-document,
comparison — an evidence-sufficiency assessor can trigger a bounded LangGraph loop: a planner
proposes up to two focused follow-up queries per iteration, results get deduplicated into an
evidence registry, and the whole thing is hard-capped at 3 iterations, 5 retrieval calls, and
15 evidence chunks — it cannot become an unbounded agent loop.

Security-wise, the workspace_id is resolved server-side after auth and threaded through the
agent graph as an immutable field the LLM never sees — so even if a malicious document tried
prompt injection, it has no path to redirect retrieval into another tenant's data, because
authorization happens at the Qdrant filter layer, not in the prompt.

For trust, citations are backend-resolved: the LLM can reference [S1], [S2], etc., but if it
invents an ID that isn't in the backend's own evidence map, it's silently stripped before the
client ever sees it. A post-generation verifier then checks the answer against evidence and
can trigger one bounded correction pass — and critically, if the verifier itself is
unreachable, that state is surfaced as UNAVAILABLE, never silently defaulted to 'verified.'

I built a 72-question benchmark on a real 254-chunk two-domain corpus — HR/policy and
clinical/billing — validated every keyword ground-truth label against the actual parsed
content programmatically before using it. The most interesting finding wasn't a success
metric: the adaptive agent's heuristic fallback never escalated on any of the 22 complex
questions, even though deterministic retrieval's own evidence coverage was measurably
incomplete on all of them. That's a real, quantified limitation — the architecture and its
control flow are implemented and unit-tested, but its production value depends on a
configured LLM assessor, and I don't have live evidence yet that it delivers when one is
configured. I'd rather say that clearly than claim a benefit I haven't measured."

## Likely technical questions

1. **Why Qdrant instead of pgvector?** Native hybrid (dense+sparse) support with RRF fusion
   built in, sub-collection payload filtering for workspace isolation without extra joins, and
   a purpose-built vector index rather than bolting vectors onto a relational engine already
   handling transactional workspace/user state.
2. **Why hybrid retrieval?** Dense alone misses exact lexical matches (codes, names, exact
   phrases); sparse alone misses paraphrase/semantic questions. Measured concretely: question
   `A20` (a reformulation-heavy question) scored 0.0 recall on sparse alone but 0.5 on dense —
   hybrid+rerank is what keeps both failure modes covered.
3. **Why RRF instead of just averaging scores?** Reciprocal rank fusion doesn't require dense
   and sparse scores to be on comparable scales (cosine similarity vs BM25 score aren't
   directly comparable) — it fuses by rank position, which is scale-free.
4. **Why cross-encoder reranking if it's the dominant latency cost (~1.25s/query on CPU)?**
   Because it measurably recovers cases hybrid fusion gets wrong — same `A20` example: RRF
   fusion alone scored 0.0 (sparse's zero-relevance ranking diluted dense's good ranking),
   reranking recovered it to 0.5. MRR and nDCG both peak with reranking in the real evaluation.
5. **Why not send every query to an agent?** Measured: the deterministic path is ~40x faster
   than reranking alone and correctly handles 100% of simple/ambiguous/unanswerable questions
   in the evaluation without ever needing the agent loop — sending everything through an agent
   would mean paying LLM assessor+planner latency and cost on questions that don't need it.
6. **How do you prevent cross-workspace leakage?** Two layers: the API resolves and verifies
   `workspace_id` server-side after auth (never client-supplied), and every single Qdrant
   query — deterministic or inside the agent loop — carries that `workspace_id` as a mandatory
   filter at the datastore layer, not just an application-level check.
7. **Why does the LLM not control authorization?** Because prompt injection is a real,
   demonstrated attack surface, and authorization is exactly the kind of decision that must be
   correct 100% of the time — it's implemented in plain server code with a database membership
   check, with the retrieval filter as defense-in-depth even if that check were ever bypassed.
8. **How are citations grounded?** The backend builds its own `id_map` (citation_id → actual
   retrieved chunk) before calling the LLM. The LLM can only reference IDs from that map; any
   `[Sn]` it invents that isn't in the map is discarded during citation extraction — the model
   cannot manufacture a citation to something that wasn't actually retrieved.
9. **Why one retrieval agent instead of multi-agent?** The problem — "decide if evidence is
   enough, and if not, fetch more" — doesn't need role specialization or inter-agent
   negotiation; a single bounded graph with clear stop conditions is simpler to reason about,
   test, and cap resource usage on, and multi-agent was explicitly out of scope for this system.
10. **What happens when verification fails?** `UNSUPPORTED`/`PARTIALLY_SUPPORTED` triggers
    exactly one correction attempt (regenerate excluding unsupported claims) and one
    re-verification — then it stops, whatever the outcome, and reports the final status
    honestly (including if correction didn't fully fix it).
11. **How would you scale ingestion?** The worker is already stateless and horizontally
    scalable behind Redis/RQ; the storage abstraction already supports S3 so backend/worker
    don't need shared local disk. Next step would be more worker replicas and a job-priority
    queue if ingestion volume grew past a single worker's throughput.
12. **What did the benchmark actually show?** Real hybrid+rerank numbers (Recall@10 0.458,
    MRR 0.962) on a genuinely harder corpus than earlier phases, and one important negative
    result: the adaptive agent doesn't escalate without a configured assessor LLM, even when
    deterministic retrieval's own coverage is measurably incomplete — a real, quantified gap
    between "the code exists" and "the code is proven to help," reported honestly.
