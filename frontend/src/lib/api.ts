// Shared API types + helpers. Mirrors backend/app/api/{workspaces,documents,query}.py response shapes.

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  role: string;
}

export type DocStatus = "queued" | "processing" | "ready" | "failed";

export interface Doc {
  id: string;
  filename: string;
  status: DocStatus;
  size_bytes: number;
  chunk_count: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface CitationOut {
  citation_id: string;
  chunk_id: string;
  document_id: string;
  filename: string;
  section_title: string;
  page_numbers: number[];
  snippet: string;
}

export type VerificationStatus = "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED" | "UNAVAILABLE";

export interface VerificationOut {
  status: VerificationStatus;
  unsupported_claims: number;
  corrected: boolean;
}

export interface TimingOut {
  retrieval_ms: number;
  generation_ms: number;
  verification_ms: number;
  total_ms: number;
}

export interface TraceOut {
  route: string;
  iterations: number;
  retrieval_calls: number;
  stop_reason: string;
  queries_issued: string[];
}

export interface QueryResult {
  answer: string;
  citations: CitationOut[];
  retrieval_mode: string;
  evidence_count: number;
  insufficient: boolean;
  verification: VerificationOut | null;
  timing: TimingOut | null;
  trace: TraceOut | null;
}

export type QueryMode = "adaptive" | "deterministic" | "dense" | "sparse" | "hybrid" | "hybrid_rerank";

export interface ProgressEvent {
  stage: string;
  message?: string;
  iteration?: number;
  retrieval_calls?: number;
  result?: QueryResult;
}

async function safeJson(res: Response): Promise<any> {
  try {
    return await res.json();
  } catch {
    return {};
  }
}

export function friendlyError(status: number, detail?: string): string {
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 404) return "That resource could not be found.";
  if (status === 409) return detail || "That document already exists in this workspace.";
  if (status === 413) return detail || "That file is too large to upload.";
  if (status === 429) return "The AI provider's rate limit was reached. Please try again shortly.";
  if (status >= 500) return "Something interrupted this request. Please try again.";
  return detail || "Something went wrong.";
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const d = await safeJson(res);
    throw new Error(friendlyError(res.status, d.detail));
  }
  return res.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const d = await safeJson(res);
    throw new Error(friendlyError(res.status, d.detail));
  }
  return res.json();
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(path, { method: "DELETE" });
  if (!res.ok) {
    const d = await safeJson(res);
    throw new Error(friendlyError(res.status, d.detail));
  }
}

/**
 * Consume the live-progress SSE query endpoint via fetch + ReadableStream (not
 * EventSource — this needs POST + JSON body + cookies). Calls `onEvent` for every
 * operational progress event as it arrives; resolves with the final QueryResult from
 * the terminal "complete" event, or throws with a safe message on "error"/network
 * failure. Falls back automatically is the caller's responsibility (see callers).
 */
export async function streamQuery(
  workspaceId: string,
  body: { question: string; mode: QueryMode; verify?: boolean },
  onEvent: (event: ProgressEvent) => void,
  signal?: AbortSignal,
): Promise<QueryResult> {
  const res = await fetch(`/api/workspaces/${workspaceId}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    const d = await safeJson(res);
    throw new Error(friendlyError(res.status, d.detail));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: QueryResult | null = null;
  let errorMessage: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      let event: ProgressEvent;
      try {
        event = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (event.stage === "complete" && event.result) {
        finalResult = event.result;
      } else if (event.stage === "error") {
        errorMessage = event.message || "Something interrupted this query.";
      } else {
        onEvent(event);
      }
    }
  }

  if (finalResult) return finalResult;
  throw new Error(errorMessage || "The query stream ended unexpectedly.");
}
