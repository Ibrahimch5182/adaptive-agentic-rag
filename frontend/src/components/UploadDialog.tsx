"use client";
import { useRef, useState } from "react";
import { UploadCloud, FileText } from "lucide-react";
import { Modal } from "./ui/Modal";

const ACCEPTED = ".pdf,.docx,.pptx,.md,.markdown,.html,.htm";
const ACCEPTED_LABEL = "PDF, DOCX, PPTX, Markdown, or HTML";

export function UploadDialog({
  open,
  onClose,
  onUpload,
}: {
  open: boolean;
  onClose: () => void;
  onUpload: (file: File) => Promise<void>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [pendingName, setPendingName] = useState("");

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setError("");
    setUploading(true);
    setPendingName(file.name);
    try {
      await onUpload(file);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      setPendingName("");
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Upload a document">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
        className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging ? "border-accent bg-accent-soft" : "border-border bg-surface2"
        }`}
      >
        {uploading ? (
          <>
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-accent-soft text-accent">
              <FileText size={20} className="animate-pulse-soft" />
            </div>
            <p className="text-sm font-medium text-fg">Uploading {pendingName}…</p>
          </>
        ) : (
          <>
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-accent-soft text-accent">
              <UploadCloud size={20} />
            </div>
            <p className="text-sm font-medium text-fg">Drag and drop a file here</p>
            <p className="mt-1 text-xs text-subtle">{ACCEPTED_LABEL}</p>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-4 rounded-lg border border-border bg-surface px-3.5 py-1.5 text-sm font-medium text-fg transition-colors hover:bg-surface2"
            >
              Browse files
            </button>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>
      {error && <p className="mt-3 text-sm text-danger">{error}</p>}
    </Modal>
  );
}
