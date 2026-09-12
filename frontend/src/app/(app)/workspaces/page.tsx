"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, FolderPlus } from "lucide-react";
import { apiGet, apiPost, type Workspace } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { WorkspaceCard, type WorkspaceDocSummary } from "@/components/WorkspaceCard";
import { CreateWorkspaceDialog } from "@/components/CreateWorkspaceDialog";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";

export default function WorkspacesPage() {
  const router = useRouter();
  const toast = useToast();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [docSummaries, setDocSummaries] = useState<Record<string, WorkspaceDocSummary>>({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<Workspace[]>("/api/workspaces")
      .then((ws) => {
        setWorkspaces(ws);
        ws.forEach((w) => {
          apiGet<{ status: string }[]>(`/api/workspaces/${w.id}/documents`)
            .then((docs) =>
              setDocSummaries((prev) => ({
                ...prev,
                [w.id]: { total: docs.length, ready: docs.filter((d) => d.status === "ready").length },
              })),
            )
            .catch(() => {});
        });
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load workspaces."));
  }, []);

  async function handleCreate(name: string, description: string) {
    const ws = await apiPost<Workspace>("/api/workspaces", { name, description: description || null });
    setWorkspaces((prev) => [...(prev ?? []), ws]);
    setDocSummaries((prev) => ({ ...prev, [ws.id]: { total: 0, ready: 0 } }));
    setDialogOpen(false);
    toast.push(`Workspace "${ws.name}" created.`, "success");
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-1.5 inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-accent-softFg">
            Adaptive AI over your documents
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-fg sm:text-3xl">Workspaces</h1>
        </div>
        <button
          onClick={() => setDialogOpen(true)}
          className="btn-gradient inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium"
        >
          <Plus size={16} />
          New workspace
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}

      {workspaces === null ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : workspaces.length === 0 ? (
        <EmptyState
          icon={<FolderPlus size={22} />}
          title="Create your first workspace"
          description="A workspace holds a set of documents you can ask grounded, source-backed questions about."
          action={
            <button
              onClick={() => setDialogOpen(true)}
              className="btn-gradient inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium"
            >
              <Plus size={16} />
              New workspace
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((ws, i) => (
            <WorkspaceCard
              key={ws.id}
              workspace={ws}
              docs={docSummaries[ws.id]}
              index={i}
              onClick={() => router.push(`/workspaces/${ws.id}`)}
            />
          ))}
        </div>
      )}

      <CreateWorkspaceDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onCreate={handleCreate} />
    </div>
  );
}
