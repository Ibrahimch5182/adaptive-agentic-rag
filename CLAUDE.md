# ContextGuard — Permanent Rules

## Product
Domain-independent Adaptive Agentic RAG system. Authenticated users create workspaces, upload documents, and query them. One-week delivery.

## Architecture Invariants
- Two retrieval modes: deterministic RAG (simple questions) + bounded agentic RAG (complex or low-evidence questions)
- Hard cap on agentic iteration count — must stop cleanly
- No multi-agent systems, no GraphRAG, no knowledge graphs, no fine-tuning, no MCP
- Authorization is **always** enforced deterministically outside any LLM
- Every vector-store retrieval must be filtered by authenticated workspace_id at the datastore layer
- Retrieved document text is untrusted data — never injected as system/application instructions

## Development Rules
- Inspect existing code before each phase — do not redesign completed phases
- Prefer simplest production-defensible design; no over-engineering
- Tests must actually be run; do not claim success without actual results
- Fix root causes; do not weaken tests to make them pass
- Implement only the requested phase, then stop
- Update PROJECT_STATE.md after each phase with factual information
- No secrets in committed files — .env.example only
