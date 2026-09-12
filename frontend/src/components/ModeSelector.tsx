"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Sparkles, Target, Layers, Check } from "lucide-react";
import type { QueryMode } from "@/lib/api";

interface ModeOption {
  value: QueryMode;
  label: string;
  description: string;
  icon: React.ElementType;
}

const PRIMARY: ModeOption[] = [
  {
    value: "adaptive",
    label: "Adaptive",
    description: "Automatically decides when additional retrieval is needed. Recommended.",
    icon: Sparkles,
  },
  {
    value: "deterministic",
    label: "Deterministic",
    description: "A single high-quality retrieval pass, no adaptive loop.",
    icon: Target,
  },
];

const ADVANCED: ModeOption[] = [
  { value: "dense", label: "Dense", description: "Semantic vector search only.", icon: Layers },
  { value: "sparse", label: "Sparse", description: "Keyword-style BM25 search only.", icon: Layers },
  { value: "hybrid", label: "Hybrid", description: "Dense + sparse fused with RRF.", icon: Layers },
  { value: "hybrid_rerank", label: "Hybrid + Rerank", description: "Hybrid, then cross-encoder reranked.", icon: Layers },
];

const ALL = [...PRIMARY, ...ADVANCED];

export function ModeSelector({ value, onChange }: { value: QueryMode; onChange: (m: QueryMode) => void }) {
  const [open, setOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = ALL.find((m) => m.value === value) ?? PRIMARY[0];
  const CurrentIcon = current.icon;

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function Option({ opt }: { opt: ModeOption }) {
    const Icon = opt.icon;
    const selected = opt.value === value;
    return (
      <button
        type="button"
        role="option"
        aria-selected={selected}
        onClick={() => {
          onChange(opt.value);
          setOpen(false);
        }}
        className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors ${
          selected ? "bg-accent-soft" : "hover:bg-surface2"
        }`}
      >
        <Icon size={15} className={`mt-0.5 shrink-0 ${selected ? "text-accent-softFg" : "text-muted"}`} />
        <span className="min-w-0 flex-1">
          <span className={`block text-sm font-medium ${selected ? "text-accent-softFg" : "text-fg"}`}>
            {opt.label}
          </span>
          <span className="mt-0.5 block text-xs leading-snug text-subtle">{opt.description}</span>
        </span>
        {selected && <Check size={14} className="mt-0.5 shrink-0 text-accent" />}
      </button>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-fg transition-colors hover:bg-surface2"
      >
        <CurrentIcon size={13} className="text-accent" />
        {current.label}
        <ChevronDown size={13} className={`text-subtle transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          role="listbox"
          className="animate-slide-up absolute bottom-full left-0 z-20 mb-2 w-72 rounded-xl border border-border bg-surface p-1.5 shadow-pop"
        >
          {PRIMARY.map((opt) => (
            <Option key={opt.value} opt={opt} />
          ))}
          <button
            type="button"
            onClick={() => setAdvancedOpen((v) => !v)}
            className="mt-1 flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wide text-subtle hover:bg-surface2"
          >
            Retrieval modes
            <ChevronDown size={12} className={`transition-transform ${advancedOpen ? "rotate-180" : ""}`} />
          </button>
          {advancedOpen && (
            <div className="border-t border-border pt-1">
              {ADVANCED.map((opt) => (
                <Option key={opt.value} opt={opt} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
