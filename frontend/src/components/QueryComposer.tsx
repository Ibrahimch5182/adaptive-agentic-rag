"use client";
import { X, ArrowUp } from "lucide-react";
import { ModeSelector } from "./ModeSelector";
import type { QueryMode } from "@/lib/api";

export function QueryComposer({
  question,
  onQuestionChange,
  mode,
  onModeChange,
  onSubmit,
  disabled,
  busy,
}: {
  question: string;
  onQuestionChange: (q: string) => void;
  mode: QueryMode;
  onModeChange: (m: QueryMode) => void;
  onSubmit: () => void;
  disabled: boolean;
  busy: boolean;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy) onSubmit();
      }}
      className="rounded-2xl border border-border bg-surface p-3 shadow-xs transition-all focus-within:border-accent/50 focus-within:shadow-card focus-within:glow-accent"
    >
      <div className="relative">
        <textarea
          value={question}
          onChange={(e) => onQuestionChange(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !busy && question.trim()) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={
            disabled
              ? "Upload and process a document before asking questions…"
              : "Ask anything about your documents — e.g. \"What changed in the remote work policy this year?\""
          }
          rows={3}
          disabled={disabled}
          className="w-full resize-none bg-transparent text-sm text-fg placeholder:text-subtle focus:outline-none disabled:text-subtle"
        />
        {question && !busy && (
          <button
            type="button"
            onClick={() => onQuestionChange("")}
            aria-label="Clear question"
            className="absolute right-0 top-0 rounded-lg p-1 text-subtle hover:bg-surface2 hover:text-fg"
          >
            <X size={14} />
          </button>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        <ModeSelector value={mode} onChange={onModeChange} />
        <div className="flex items-center gap-2">
          <span className="hidden text-[11px] text-subtle sm:inline">⌘/Ctrl + Enter</span>
          <button
            type="submit"
            disabled={disabled || busy || !question.trim()}
            className="btn-gradient inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium disabled:cursor-not-allowed"
          >
            {busy ? "Working…" : "Ask"}
            {!busy && <ArrowUp size={14} className="rotate-45" />}
          </button>
        </div>
      </div>
    </form>
  );
}
