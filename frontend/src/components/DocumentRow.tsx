"use client";
import { useState } from "react";
import { Clock, Loader2, CheckCircle2, AlertTriangle, RotateCcw, Trash2, FileText } from "lucide-react";
import type { Doc } from "@/lib/api";
import { fmtBytes } from "@/lib/format";
import { Tooltip } from "./ui/Tooltip";

const STATUS_META: Record<
  Doc["status"],
  { label: string; icon: React.ElementType; tone: string; spin?: boolean }
> = {
  queued: { label: "Queued", icon: Clock, tone: "text-warning bg-warning-soft" },
  processing: { label: "Processing", icon: Loader2, tone: "text-accent bg-accent-soft", spin: true },
  ready: { label: "Ready", icon: CheckCircle2, tone: "text-success bg-success-soft" },
  failed: { label: "Failed", icon: AlertTriangle, tone: "text-danger bg-danger-soft" },
};

export function DocumentRow({
  doc,
  onDelete,
  onRetry,
}: {
  doc: Doc;
  onDelete: (id: string) => Promise<void>;
  onRetry: (id: string) => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const meta = STATUS_META[doc.status];
  const Icon = meta.icon;

  async function handleDeleteClick() {
    if (!confirming) {
      setConfirming(true);
      setTimeout(() => setConfirming(false), 3000);
      return;
    }
    setBusy(true);
    try {
      await onDelete(doc.id);
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <li className="animate-slide-up flex items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 transition-colors hover:border-borderStrong">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface2 text-muted">
        <FileText size={16} />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-fg">{doc.filename}</span>
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-subtle">
          <span>{fmtBytes(doc.size_bytes)}</span>
          {doc.status === "ready" && doc.chunk_count != null && (
            <>
              <span aria-hidden>·</span>
              <span>{doc.chunk_count} chunks indexed</span>
            </>
          )}
        </div>
        {doc.status === "failed" && doc.error_message && (
          <p className="mt-1 truncate text-xs text-danger" title={doc.error_message}>
            {doc.error_message}
          </p>
        )}
      </div>

      <span
        className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${meta.tone}`}
      >
        <Icon size={12} className={meta.spin ? "animate-spin-slow" : ""} />
        {meta.label}
      </span>

      <div className="flex shrink-0 items-center gap-1">
        {doc.status === "failed" && (
          <Tooltip label="Retry ingestion">
            <button
              onClick={() => onRetry(doc.id)}
              aria-label="Retry ingestion"
              className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface2 hover:text-accent"
            >
              <RotateCcw size={15} />
            </button>
          </Tooltip>
        )}
        <button
          onClick={handleDeleteClick}
          disabled={busy}
          aria-label={confirming ? "Confirm delete" : "Delete document"}
          className={`rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
            confirming ? "bg-danger text-danger-fg" : "text-muted hover:bg-surface2 hover:text-danger"
          }`}
        >
          {confirming ? "Confirm?" : busy ? "…" : <Trash2 size={15} />}
        </button>
      </div>
    </li>
  );
}
