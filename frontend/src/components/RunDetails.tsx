"use client";
import { useState } from "react";
import { ChevronDown, ArrowDown } from "lucide-react";
import type { TimingOut, TraceOut, VerificationOut } from "@/lib/api";
import { fmtMs } from "@/lib/format";

const STOP_REASON_LABEL: Record<string, string> = {
  SUFFICIENT: "Evidence was sufficient",
  MAX_ITERATIONS: "Reached the iteration limit",
  MAX_CALLS: "Reached the retrieval-call limit",
  NO_SUPPORT: "No supporting evidence found",
  PLANNER_DONE: "Planner found nothing further to search",
};

function LatencyBars({ timing }: { timing: TimingOut }) {
  const rows: { label: string; ms: number }[] = [
    { label: "Retrieval", ms: timing.retrieval_ms },
    { label: "Generation", ms: timing.generation_ms },
    { label: "Verification", ms: timing.verification_ms },
  ];
  const max = Math.max(timing.total_ms, 1);
  return (
    <div className="space-y-2">
      {rows.map((r) => {
        const pct = Math.max(2, Math.min(100, (r.ms / max) * 100));
        return (
          <div key={r.label} className="flex items-center gap-2.5 text-xs">
            <span className="w-24 shrink-0 text-muted">{r.label}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full border border-border bg-surface2">
              <div className="gradient-accent h-full rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
            </div>
            <span className="w-14 shrink-0 text-right font-mono tabular-nums text-subtle">{fmtMs(r.ms)}</span>
          </div>
        );
      })}
      <div className="flex items-center gap-2.5 border-t border-border pt-1.5 text-xs font-medium">
        <span className="w-24 shrink-0 text-fg">Total</span>
        <div className="flex-1" />
        <span className="w-14 shrink-0 text-right font-mono tabular-nums text-fg">{fmtMs(timing.total_ms)}</span>
      </div>
    </div>
  );
}

function AgenticTrace({ trace }: { trace: TraceOut }) {
  const steps: string[] = ["Initial retrieval"];
  if (trace.route === "agentic") {
    steps.push("Coverage check");
    steps.push(`Missing evidence detected across ${trace.iterations} pass${trace.iterations !== 1 ? "es" : ""}`);
    steps.push(`${trace.retrieval_calls} targeted retrieval call${trace.retrieval_calls !== 1 ? "s" : ""}`);
    steps.push("Evidence expanded");
  } else if (trace.route === "abstain") {
    steps.push("No supporting evidence found");
    return <TraceFlow steps={steps} />;
  } else {
    steps.push("Evidence sufficient");
  }
  steps.push("Answer generated");
  steps.push("Verified");
  return <TraceFlow steps={steps} />;
}

function TraceFlow({ steps }: { steps: string[] }) {
  return (
    <div className="space-y-0.5">
      {steps.map((step, i) => (
        <div key={i}>
          <div className="rounded-lg bg-surface2 px-3 py-1.5 text-xs text-fg">{step}</div>
          {i < steps.length - 1 && (
            <div className="flex justify-center py-0.5 text-subtle">
              <ArrowDown size={12} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function RunDetails({
  retrievalMode,
  trace,
  timing,
  verification,
  evidenceCount,
}: {
  retrievalMode: string;
  trace: TraceOut | null;
  timing: TimingOut | null;
  verification: VerificationOut | null;
  evidenceCount: number;
}) {
  const [open, setOpen] = useState(false);

  const stats: { label: string; value: string }[] = [
    { label: "Route", value: retrievalMode },
    { label: "Evidence", value: `${evidenceCount} chunk${evidenceCount !== 1 ? "s" : ""}` },
  ];
  if (trace) {
    stats.push({ label: "Iterations", value: String(trace.iterations) });
    stats.push({ label: "Retrieval calls", value: String(trace.retrieval_calls) });
    stats.push({ label: "Stop reason", value: STOP_REASON_LABEL[trace.stop_reason] ?? trace.stop_reason });
  }
  if (verification) {
    stats.push({ label: "Unsupported claims", value: String(verification.unsupported_claims) });
  }

  return (
    <div className="rounded-xl border border-border bg-surface">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-medium text-muted hover:text-fg"
      >
        Run details
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="animate-slide-up space-y-4 border-t border-border px-4 py-4">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {stats.map((s) => (
              <div key={s.label}>
                <dt className="text-[11px] uppercase tracking-wide text-subtle">{s.label}</dt>
                <dd className="mt-0.5 truncate text-sm font-medium text-fg" title={s.value}>
                  {s.value}
                </dd>
              </div>
            ))}
          </dl>

          {timing && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-subtle">Latency</p>
              <LatencyBars timing={timing} />
            </div>
          )}

          {trace && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-subtle">
                Retrieval path
              </p>
              <AgenticTrace trace={trace} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
