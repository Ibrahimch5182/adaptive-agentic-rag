# Demo Script (3–5 minutes)

## Setup (before recording/presenting)

```bash
cp .env.example .env   # fill in SECRET_KEY, POSTGRES_PASSWORD
docker compose build
docker compose up -d
```

Demo corpus: 4 documents already in the repo at `evaluation/corpus/domain_a_general/` —
synthetic, non-sensitive HR/policy documents (not real patient or company data). Use
`leave_policy.pdf` for the simple query, then also upload `general_faqs.pdf` and
`staff_handbook.pdf` for the cross-document query (step 8) — both genuinely state the same
password-policy fact independently, confirmed while building `evaluation/benchmark.json`
(question `A28`).

## Flow

1. **Login.** Register a user at `http://localhost:3000/register`, log in. Point out the
   cookie is HttpOnly — open devtools, show it's not readable from JS.
2. **Create/open a workspace.** Create "Demo Workspace."
3. **Upload a document.** Upload `evaluation/corpus/domain_a_general/leave_policy.pdf`.
   Point out the status pill starts at **Queued**.
4. **Watch the lifecycle.** Refresh (or wait — the UI polls automatically) through
   **Processing** → **Ready**. Mention what's happening underneath: Redis/RQ picked up the
   job, a worker ran Docling parsing + HybridChunker + dense/sparse embedding + Qdrant upsert —
   this is the same real pipeline verified end-to-end in Phase 6, not a mock.
5. **Ask a simple question.** *"How many days of Earned Leave can clinical staff carry
   forward?"* Mode: Adaptive (default).
6. **Show the deterministic route.** Open "Technical details" — `route: deterministic`,
   `iterations: 0`. Explain: the assessor judged first-pass evidence sufficient, so no extra
   retrieval loop ran — this is adaptive routing working *correctly*, not failing to engage.
7. **Show the answer + citation + source snippet.** Point at the `[S1]` citation, the source
   card underneath with the real filename, section, page number, and a real text snippet —
   not a generic "source: document.pdf."
8. **Ask a harder, cross-document question** (upload `general_faqs.pdf` and
   `staff_handbook.pdf` too first): *"What is the minimum password length required for
   MediAssist systems, and how often must it be changed?"* — this fact is genuinely
   corroborated across those two separate documents.
9. **Adaptive behavior — say this honestly, don't fake it.**
   - **If `GROQ_API_KEY` is configured**: this is your best shot at a real escalation —
     Phase 7's evaluation corpus has several multi-document/multi-part questions like this one
     where deterministic single-pass retrieval measurably misses part of the answer (see
     `evaluation/summary.md`, Section 2). Show the trace panel; if `route: agentic` appears,
     point out `iterations`/`retrieval_calls` and narrate that the planner issued a focused
     follow-up query.
   - **If no `GROQ_API_KEY`** (the default local setup): say so directly. "Without a
     configured assessor LLM, this system's own Phase 7 evaluation found the adaptive route
     doesn't escalate — it correctly falls back to the deterministic path rather than
     pretending to loop." Show `route: deterministic` in the trace panel and explain this is
     the honest, measured behavior, not a missing feature in the demo. This is a stronger
     story in an interview than a faked "look, it's thinking!" moment.
10. **Show the verification indicator.** With no `GROQ_API_KEY`, this correctly shows no
    "Verified" badge at all (verifier `UNAVAILABLE`, never mislabeled as passed). With a key
    configured, show the `SUPPORTED`/`PARTIALLY_SUPPORTED` badge and mention the bounded
    correction pass.
11. **Explain workspace isolation briefly.** "Every retrieval call is filtered by
    `workspace_id` at the Qdrant layer, not just the application layer — a document in one
    workspace is structurally unreachable from another, even if the model tried."

## What not to do

- Don't manually force `route: agentic` in the UI or fabricate a trace — if the live demo
  environment has no `GROQ_API_KEY`, narrate the honest deterministic-only result (step 9).
- Don't use real patient/company data — the shipped demo corpus is synthetic.
