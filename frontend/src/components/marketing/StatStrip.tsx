"use client";
import { useInView } from "@/hooks/useInView";
import { useCountUp } from "@/hooks/useCountUp";

const STATS = [
  { value: 3, suffix: "", label: "Max agent iterations — hard-capped, not runaway" },
  { value: 15, suffix: "", label: "Evidence chunks per answer, deduped & ranked" },
  { value: 100, suffix: "%", label: "Answers grounded in cited evidence" },
  { value: 0, suffix: "", label: "Cross-workspace data leaks, by construction" },
];

function Stat({ value, suffix, label, active }: { value: number; suffix: string; label: string; active: boolean }) {
  const n = useCountUp(value, active);
  return (
    <div className="text-center sm:text-left">
      <div className="gradient-text text-3xl font-bold tabular-nums sm:text-4xl">
        {n}
        {suffix}
      </div>
      <p className="mt-1.5 text-sm text-muted">{label}</p>
    </div>
  );
}

export function StatStrip() {
  const { ref, inView } = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className="border-b border-border bg-surface2/40">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-8 px-5 py-12 sm:px-8 lg:grid-cols-4">
        {STATS.map((s) => (
          <Stat key={s.label} {...s} active={inView} />
        ))}
      </div>
    </div>
  );
}
