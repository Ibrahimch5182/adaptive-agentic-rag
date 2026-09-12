# Architecture

## Component responsibilities

| Component | Responsibility | Persistent? |
|---|---|---|
| Next.js frontend | Auth/workspace/query UI, same-origin `/api` proxy to backend | No (stateless) |
| FastAPI backend | AuthN/authZ, workspace scoping, orchestration, query API, migrations | No (stateless) |
| PostgreSQL | Users, workspaces, memberships, document metadata/status | Yes |
| Redis | Transient RQ ingestion job queue | No (jobs are transient by design) |
| RQ worker | Docling parsing, chunking, embedding, Qdrant indexing | No (stateless; re-runnable) |
| Qdrant | Dense + sparse vectors, chunk text, provenance payload | Yes |
| Local disk / S3 | Original uploaded files | Yes |
| Groq | Generation, agent assessment/planning, verification | External, no state owned |

## Ingestion path

```
Upload (multipart) → validate extension + size → SHA-256 dedup check (per workspace)
  → storage.save() [local or S3] → Document row (QUEUED) → enqueue_ingestion (RQ)
  → [async, worker process]
  → Document → PROCESSING
  → storage.materialize() [local: real path; S3: download to temp file, cleaned up after]
  → Docling DocumentConverter → HybridChunker (contextualized retrieval_text + faithful raw_text)
  → dense embed (BAAI/bge-small-en-v1.5) + sparse embed (Qdrant/bm25)
  → Qdrant upsert (deterministic point IDs: uuid5(document_id, chunk_index))
  → Document → READY (or FAILED, with error_message, on any exception)
```

If the enqueue call itself fails (found as a real bug in Phase 6, via live E2E — see
`PROJECT_STATE.md`), the document is marked `FAILED` synchronously rather than left silently
`QUEUED` forever with no job behind it.

## Query path

```
POST /api/workspaces/{id}/query   (mode=adaptive | deterministic | hybrid_rerank | ...)
  ← workspace_id verified server-side against the authenticated user's membership
  ↓
HYBRID_RERANK: dense (top 20) + sparse (top 20) → RRF fusion (top 20) → cross-encoder rerank (top 5)
  ↓
mode=adaptive only: evidence-sufficiency assessor (heuristic, or LLM if GROQ_API_KEY set)
  ├── ANSWER_NOW  → pack evidence as-is
  ├── ABSTAIN     → pack empty evidence
  └── RETRIEVE_MORE → LangGraph loop: planner proposes ≤2 focused sub-queries per iteration,
                       execute_retrieval appends deduplicated results to an evidence registry,
                       re-assess — hard caps: 3 iterations, 5 retrieval calls, 15 evidence chunks
  ↓
Grounded generation (Groq): evidence-only prompt, citations extracted and validated against
the backend's own id_map (any invented [Sn] ID is discarded, never trusted)
  ↓
Verifier (bounded): verify → [one correction if unsupported] → [one re-verification] → stop
  status ∈ {SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, UNAVAILABLE}
  ↓
Response: answer + citations (with real snippets/pages) + verification + timing + trace
```

## Trust / security boundaries

- **`workspace_id` is application-owned, not model-owned.** It's resolved from the
  authenticated session before the agent graph is entered, passed as an immutable
  `TypedDict` field, and used as a mandatory Qdrant filter on every retrieval call — inside
  and outside the agent loop. The LLM's prompts never contain it, so no amount of prompt
  injection in a document can redirect retrieval to another workspace.
- **Retrieved document text is always untrusted data.** Both the generator and verifier
  prompts explicitly frame evidence as data to read, not instructions to follow — tested with
  a real prompt-injection-in-evidence case (evidence containing "IGNORE ALL PREVIOUS
  INSTRUCTIONS...") that the verifier correctly does not act on.
- **Citations are backend-resolved, not model-trusted.** The LLM may reference `[Sn]` IDs; the
  backend's own `id_map` (built from real retrieved chunks) is the only source of truth for
  what those IDs mean. An ID the model invents that isn't in that map is silently stripped
  before the response is built.
- **The agent has one authorized tool: `retrieve()`.** No filesystem, shell, or arbitrary
  network access — the same function the deterministic path calls, with the same
  workspace-scoped filter.
- **Operational trace only, no chain-of-thought.** The agent's trace records structured
  events (`step`, `decision`, `reason_code`, `chunks_retrieved`, `latency_ms`, ...); fields
  like `reasoning`/`chain_of_thought`/`scratchpad` are explicitly forbidden and tested against.

## Deterministic vs. LLM decisions

| Decision | Made by | Why |
|---|---|---|
| Is this user allowed to see this workspace? | FastAPI (deterministic) | Security must never depend on model behavior |
| Which Qdrant points can this query touch? | Qdrant filter (deterministic) | Same reason — enforced at the datastore, not just the app |
| Is retrieved evidence sufficient? | Heuristic or LLM assessor | Judgment call; bounded either way |
| What to search for next (if escalating) | LLM planner (bounded: ≤2 queries/iteration) | Needs language understanding |
| Does this citation ID exist? | Backend `id_map` lookup (deterministic) | Cannot be allowed to hallucinate |
| Is this answer supported by evidence? | LLM verifier (bounded: ≤2 calls) | Needs language understanding; result is still schema-validated deterministically |
| Is the verifier itself reachable? | Deterministic status check (`UNAVAILABLE`) | Never let "couldn't check" look like "checked and passed" |
