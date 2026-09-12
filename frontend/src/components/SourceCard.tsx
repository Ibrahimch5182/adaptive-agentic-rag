"use client";
import { useEffect, useRef, useState } from "react";
import { FileText } from "lucide-react";
import type { CitationOut } from "@/lib/api";

export function SourceCard({ citation, highlighted }: { citation: CitationOut; highlighted: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    if (!highlighted) return;
    ref.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(true);
    const id = setTimeout(() => setFlash(false), 1400);
    return () => clearTimeout(id);
  }, [highlighted]);

  return (
    <div
      ref={ref}
      id={`source-${citation.citation_id}`}
      className={`rounded-xl border border-border bg-surface p-3.5 transition-colors ${flash ? "animate-highlight" : ""}`}
    >
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 shrink-0 rounded-md bg-accent-soft px-1.5 py-0.5 text-[0.7rem] font-bold text-accent-softFg">
          {citation.citation_id}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <FileText size={13} className="shrink-0 text-subtle" />
            <p className="truncate text-xs font-medium text-fg">{citation.filename}</p>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[11px] text-subtle">
            {citation.section_title && <span>{citation.section_title}</span>}
            {citation.page_numbers.length > 0 && (
              <span className="rounded bg-surface2 px-1.5 py-0.5 font-medium">
                p.{citation.page_numbers.join(", ")}
              </span>
            )}
          </div>
          {citation.snippet && (
            <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-muted">&ldquo;{citation.snippet}&rdquo;</p>
          )}
        </div>
      </div>
    </div>
  );
}
