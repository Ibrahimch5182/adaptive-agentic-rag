import { ChevronRight, FileText, FolderKanban } from "lucide-react";
import type { Workspace } from "@/lib/api";

export interface WorkspaceDocSummary {
  total: number;
  ready: number;
}

export function WorkspaceCard({
  workspace,
  docs,
  index = 0,
  onClick,
}: {
  workspace: Workspace;
  docs?: WorkspaceDocSummary;
  index?: number;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}
      className="group animate-slide-up flex flex-col items-start rounded-2xl border border-border bg-surface p-5 text-left shadow-xs transition-all duration-200 hover:-translate-y-1 hover:border-accent/40 hover:shadow-card hover:glow-accent"
    >
      <div className="flex w-full items-start justify-between gap-3">
        <div className="gradient-accent flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-accent-fg shadow-xs transition-transform duration-200 group-hover:scale-105">
          <FolderKanban size={18} />
        </div>
        <ChevronRight size={18} className="mt-2 shrink-0 text-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-accent" />
      </div>

      <h3 className="mt-3.5 line-clamp-1 text-[15px] font-semibold text-fg">{workspace.name}</h3>
      {workspace.description && (
        <p className="mt-1 line-clamp-2 text-sm text-muted">{workspace.description}</p>
      )}

      <div className="mt-4 flex w-full items-center justify-between border-t border-border pt-3 text-xs text-subtle">
        <span className="inline-flex items-center gap-1 rounded-full bg-surface2 px-2 py-1 font-medium capitalize text-muted">
          {workspace.role}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <FileText size={13} />
          {docs ? (
            <>
              {docs.total} doc{docs.total !== 1 ? "s" : ""}
              {docs.total > 0 && ` · ${docs.ready} ready`}
            </>
          ) : (
            "…"
          )}
        </span>
      </div>
    </button>
  );
}
