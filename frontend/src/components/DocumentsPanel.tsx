"use client";
import { useState } from "react";
import { Upload, FileStack } from "lucide-react";
import type { Doc } from "@/lib/api";
import { DocumentRow } from "./DocumentRow";
import { UploadDialog } from "./UploadDialog";
import { Skeleton } from "./ui/Skeleton";
import { EmptyState } from "./ui/EmptyState";

export function DocumentsPanel({
  docs,
  loading,
  onUpload,
  onDelete,
  onRetry,
}: {
  docs: Doc[] | null;
  loading: boolean;
  onUpload: (file: File) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onRetry: (id: string) => Promise<void>;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-fg">Knowledge base</h2>
        <button
          onClick={() => setDialogOpen(true)}
          className="btn-gradient inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
        >
          <Upload size={13} />
          Upload
        </button>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : !docs || docs.length === 0 ? (
        <EmptyState
          icon={<FileStack size={20} />}
          title="Build your knowledge base"
          description="Upload documents to start asking grounded questions with citations."
          action={
            <button
              onClick={() => setDialogOpen(true)}
              className="btn-gradient inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium"
            >
              <Upload size={14} />
              Upload a document
            </button>
          }
        />
      ) : (
        <ul className="space-y-2">
          {docs.map((doc) => (
            <DocumentRow key={doc.id} doc={doc} onDelete={onDelete} onRetry={onRetry} />
          ))}
        </ul>
      )}

      <UploadDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onUpload={onUpload} />
    </section>
  );
}
