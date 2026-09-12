"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { ChevronLeft, FileText } from "lucide-react";
import { apiGet, apiPost, apiDelete, streamQuery } from "@/lib/api";
import type { Doc, ProgressEvent, QueryMode, QueryResult, Workspace } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { QueryComposer } from "@/components/QueryComposer";
import { QueryActivity } from "@/components/QueryActivity";
import { AnswerCard } from "@/components/AnswerCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";

type QueryState = "idle" | "running" | "done" | "error";

export default function WorkspacePage() {
  const router = useRouter();
  const toast = useToast();
  const { id: wsId } = useParams() as { id: string };

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [docs, setDocs] = useState<Doc[] | null>(null);

  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<QueryMode>("adaptive");
  const [queryState, setQueryState] = useState<QueryState>("idle");
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [queryError, setQueryError] = useState("");
  const [querySeq, setQuerySeq] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const fetchDocs = useCallback(() => {
    apiGet<Doc[]>(`/api/workspaces/${wsId}/documents`)
      .then(setDocs)
      .catch(() => toast.push("Could not refresh document list.", "error"));
  }, [wsId, toast]);

  useEffect(() => {
    apiGet<Workspace>(`/api/workspaces/${wsId}`)
      .then(setWorkspace)
      .catch((err) => {
        if (err instanceof Error && err.message.includes("could not be found")) setNotFound(true);
        else toast.push(err instanceof Error ? err.message : "Failed to load workspace.", "error");
      });
    fetchDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsId]);

  useEffect(() => {
    const pending = docs?.some((d) => d.status === "queued" || d.status === "processing");
    if (!pending) return;
    const id = setInterval(fetchDocs, 3000);
    return () => clearInterval(id);
  }, [docs, fetchDocs]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function handleUpload(file: File) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/workspaces/${wsId}/documents`, { method: "POST", body: form });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || "Upload failed.");
    }
    const doc = await res.json();
    setDocs((prev) => [doc, ...(prev ?? [])]);
    toast.push(`"${doc.filename}" queued for processing.`, "success");
  }

  async function handleDelete(docId: string) {
    try {
      await apiDelete(`/api/workspaces/${wsId}/documents/${docId}`);
      setDocs((prev) => (prev ?? []).filter((d) => d.id !== docId));
      toast.push("Document deleted.", "success");
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Failed to delete document.", "error");
    }
  }

  async function handleRetry(docId: string) {
    try {
      const doc = await apiPost<Doc>(`/api/workspaces/${wsId}/documents/${docId}/retry`);
      setDocs((prev) => (prev ?? []).map((d) => (d.id === docId ? doc : d)));
      toast.push("Retrying ingestion.", "info");
    } catch (err) {
      toast.push(err instanceof Error ? err.message : "Failed to retry document.", "error");
    }
  }

  async function handleQuery() {
    if (!question.trim() || readyCount === 0 || queryState === "running") return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setQuerySeq((s) => s + 1);
    setProgressEvents([]);
    setResult(null);
    setQueryError("");
    setQueryState("running");

    try {
      const res = await streamQuery(
        wsId,
        { question, mode },
        (event) => setProgressEvents((prev) => [...prev, event]),
        controller.signal,
      );
      setResult(res);
      setQueryState("done");
    } catch (err) {
      if (controller.signal.aborted) return;
      setQueryError(err instanceof Error ? err.message : "Something interrupted this query.");
      setQueryState("error");
    }
  }

  const readyCount = (docs ?? []).filter((d) => d.status === "ready").length;

  if (notFound) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center px-6">
        <EmptyState
          title="Workspace not found"
          description="It may have been deleted, or you may not have access."
          action={
            <button onClick={() => router.push("/workspaces")} className="text-sm font-medium text-accent hover:underline">
              ← Back to workspaces
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div>
      <header className="sticky top-0 z-10 border-b border-border bg-surface/90 px-5 py-3.5 backdrop-blur sm:px-8">
        <div className="gradient-accent absolute inset-x-0 top-0 h-[2px] opacity-70" aria-hidden />
        <div className="mx-auto flex max-w-6xl items-center gap-3">
          <button
            onClick={() => router.push("/workspaces")}
            className="flex shrink-0 items-center gap-1 rounded-lg p-1.5 text-sm text-muted transition-colors hover:bg-surface2 hover:text-fg"
          >
            <ChevronLeft size={16} />
          </button>
          {workspace ? (
            <h1 className="truncate text-[15px] font-semibold tracking-tight text-fg">{workspace.name}</h1>
          ) : (
            <Skeleton className="h-4 w-40" />
          )}
          {docs && (
            <span className="ml-auto flex shrink-0 items-center gap-1.5 rounded-full bg-surface2 px-2.5 py-1 text-xs text-muted">
              <span
                className={`h-1.5 w-1.5 rounded-full ${readyCount === docs.length && docs.length > 0 ? "bg-success" : "bg-accent"}`}
                aria-hidden
              />
              {readyCount}/{docs.length} ready
            </span>
          )}
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-6 px-5 py-6 sm:px-8 lg:grid-cols-[300px_1fr]">
        <div className="lg:sticky lg:top-20 lg:self-start">
          <DocumentsPanel
            docs={docs}
            loading={docs === null}
            onUpload={handleUpload}
            onDelete={handleDelete}
            onRetry={handleRetry}
          />
        </div>

        <div className="space-y-5">
          <QueryComposer
            question={question}
            onQuestionChange={setQuestion}
            mode={mode}
            onModeChange={setMode}
            onSubmit={handleQuery}
            disabled={docs === null || readyCount === 0}
            busy={queryState === "running"}
          />

          {queryState === "running" && <QueryActivity key={querySeq} events={progressEvents} done={false} />}

          {queryState === "error" && (
            <div className="animate-fade-in rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
              {queryError}
            </div>
          )}

          {result && queryState === "done" && (
            <>
              {progressEvents.length > 0 && (
                <QueryActivity key={`${querySeq}-done`} events={progressEvents} done />
              )}
              <AnswerCard result={result} />
            </>
          )}

          {queryState === "idle" && !result && (
            <EmptyState
              icon={<FileText size={20} />}
              title="Ask your knowledge base"
              description="Your answers will include source-backed citations and a verification status."
            />
          )}
        </div>
      </div>
    </div>
  );
}
