"use client";
import { useEffect, useRef, useState } from "react";
import {
  Search,
  ListChecks,
  Route,
  RefreshCw,
  Layers,
  PenLine,
  ShieldCheck,
  Wrench,
  CheckCheck,
  Check,
  Sparkles,
} from "lucide-react";
import type { ProgressEvent } from "@/lib/api";

const STAGE_ICON: Record<string, React.ElementType> = {
  received: Sparkles,
  retrieval: Search,
  assessment: ListChecks,
  planning: Route,
  additional_retrieval: RefreshCw,
  pack: Layers,
  generation: PenLine,
  verification: ShieldCheck,
  correction: Wrench,
  finalizing: CheckCheck,
};

interface Row {
  stage: string;
  message: string;
  order: number;
  occurrences: number;
  iteration?: number;
  retrieval_calls?: number;
}

export function QueryActivity({ events, done }: { events: ProgressEvent[]; done: boolean }) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number>(Date.now());

  // Mount once per query (parent remounts this component per submission via `key`).
  useEffect(() => {
    startRef.current = Date.now();
  }, []);

  // Tick while in progress; stop (freeze) the instant `done` flips true.
  useEffect(() => {
    if (done) return;
    const id = setInterval(() => setElapsed((Date.now() - startRef.current) / 1000), 100);
    return () => clearInterval(id);
  }, [done]);

  const rows: Row[] = [];
  const index = new Map<string, number>();
  for (const e of events) {
    if (index.has(e.stage)) {
      const row = rows[index.get(e.stage)!];
      row.occurrences += 1;
      row.message = e.message ?? row.message;
      row.iteration = e.iteration;
      row.retrieval_calls = e.retrieval_calls;
    } else {
      index.set(e.stage, rows.length);
      rows.push({
        stage: e.stage,
        message: e.message ?? e.stage,
        order: rows.length,
        occurrences: 1,
        iteration: e.iteration,
        retrieval_calls: e.retrieval_calls,
      });
    }
  }

  const activeStage = done ? null : events[events.length - 1]?.stage ?? null;

  return (
    <div
      className={`animate-fade-in overflow-hidden rounded-2xl border bg-surface p-4 transition-shadow ${
        done ? "border-success/30" : "border-accent/30 glow-accent"
      }`}
    >
      <div className={`-mx-4 -mt-4 mb-3.5 h-[3px] ${done ? "gradient-accent" : "progress-indeterminate bg-surface2"}`} />

      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-subtle">
          {done ? (
            <Check size={13} className="text-success" />
          ) : (
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
            </span>
          )}
          {done ? "Query complete" : "Working on your question"}
        </h3>
        <span className="font-mono text-xs tabular-nums text-subtle">{elapsed.toFixed(1)}s</span>
      </div>

      <ul className="space-y-1.5">
        {rows.map((row) => {
          const Icon = STAGE_ICON[row.stage] ?? Sparkles;
          const isActive = row.stage === activeStage;
          const isDone = done || !isActive;
          return (
            <li key={row.stage} className="flex items-center gap-2.5 text-sm">
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-colors ${
                  isDone ? "bg-success-soft text-success" : "gradient-accent animate-ring-pulse text-accent-fg"
                }`}
              >
                {isDone ? <Check size={12} /> : <Icon size={11} />}
              </span>
              <span className={isDone ? "text-muted" : "font-medium text-fg"}>{row.message}</span>
              {row.stage === "assessment" && typeof row.iteration === "number" && row.iteration > 0 && (
                <span className="text-xs text-subtle">· pass {row.iteration + 1}</span>
              )}
              {row.stage === "additional_retrieval" && typeof row.retrieval_calls === "number" && (
                <span className="text-xs text-subtle">· {row.retrieval_calls} retrieval calls so far</span>
              )}
              {!isDone && (
                <span className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-accent animate-pulse-soft" />
              )}
            </li>
          );
        })}
      </ul>

      {!done && elapsed > 30 && (
        <p className="mt-3.5 border-t border-border pt-3 text-xs text-subtle">
          Still working — this query is using multiple evidence-retrieval steps.
        </p>
      )}
      {!done && elapsed > 10 && elapsed <= 30 && (
        <p className="mt-3.5 border-t border-border pt-3 text-xs text-subtle">
          Complex questions may require additional retrieval passes.
        </p>
      )}
    </div>
  );
}
