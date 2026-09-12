"use client";
import { useEffect, useState } from "react";
import { Search, ListChecks, PenLine, ShieldCheck, Check, Sparkles, Circle } from "lucide-react";

const QUESTION = "What changed in our remote work policy this year?";
const STAGES = [
  { icon: Search, label: "Searching your knowledge base" },
  { icon: ListChecks, label: "Assessing evidence coverage" },
  { icon: PenLine, label: "Generating grounded answer" },
  { icon: ShieldCheck, label: "Verifying claims" },
];

type Phase = "typing" | "thinking" | "answered" | "hold";

export function DemoPreview() {
  const [phase, setPhase] = useState<Phase>("typing");
  const [typed, setTyped] = useState(0);
  const [stageIx, setStageIx] = useState(-1);

  useEffect(() => {
    let timers: ReturnType<typeof setTimeout>[] = [];

    if (phase === "typing") {
      if (typed < QUESTION.length) {
        timers.push(setTimeout(() => setTyped((n) => n + 1), 28));
      } else {
        timers.push(setTimeout(() => setPhase("thinking"), 500));
      }
    } else if (phase === "thinking") {
      if (stageIx < STAGES.length - 1) {
        timers.push(setTimeout(() => setStageIx((i) => i + 1), 550));
      } else {
        timers.push(setTimeout(() => setPhase("answered"), 500));
      }
    } else if (phase === "answered") {
      timers.push(setTimeout(() => setPhase("hold"), 4200));
    } else {
      timers.push(
        setTimeout(() => {
          setTyped(0);
          setStageIx(-1);
          setPhase("typing");
        }, 900),
      );
    }

    return () => timers.forEach(clearTimeout);
  }, [phase, typed, stageIx]);

  const showActivity = phase === "thinking" || phase === "answered" || phase === "hold";
  const showAnswer = phase === "answered" || phase === "hold";

  return (
    <div className="relative rounded-2xl border border-border bg-surface/90 shadow-pop backdrop-blur">
      {/* window chrome */}
      <div className="flex items-center gap-1.5 border-b border-border px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-danger/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-warning/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-success/70" />
        <span className="ml-3 flex items-center gap-1.5 rounded-md bg-surface2 px-2.5 py-1 text-[11px] text-subtle">
          <Sparkles size={11} className="text-accent" />
          Adaptive
        </span>
      </div>

      <div className="min-h-[280px] p-5">
        {/* question bar */}
        <div className="flex items-center gap-2 rounded-xl border border-border bg-surface2 px-3.5 py-2.5">
          <Search size={14} className="shrink-0 text-subtle" />
          <span className="text-sm text-fg">
            {QUESTION.slice(0, typed)}
            {phase === "typing" && <span className="animate-pulse-soft">▍</span>}
          </span>
        </div>

        {/* activity */}
        {showActivity && (
          <div className="animate-fade-in mt-4 space-y-2 rounded-xl border border-accent/20 bg-surface p-3.5">
            {STAGES.map((s, i) => {
              const Icon = s.icon;
              const done = i < stageIx || showAnswer;
              const active = i === stageIx && !showAnswer;
              if (i > stageIx && !showAnswer) return null;
              return (
                <div key={s.label} className="flex items-center gap-2 text-xs">
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${
                      done ? "bg-success-soft text-success" : "gradient-accent text-accent-fg"
                    }`}
                  >
                    {done ? <Check size={10} /> : <Icon size={9} />}
                  </span>
                  <span className={done ? "text-muted" : "font-medium text-fg"}>{s.label}</span>
                  {active && <Circle size={5} className="ml-auto animate-pulse-soft fill-accent text-accent" />}
                </div>
              );
            })}
          </div>
        )}

        {/* answer */}
        {showAnswer && (
          <div className="animate-slide-up mt-4 rounded-xl border border-l-4 border-l-success border-border bg-surface p-3.5">
            <p className="text-sm leading-relaxed text-fg">
              Remote work is now permitted{" "}
              <strong className="font-semibold text-fg">up to 3 days per week</strong>, up from 2 in the
              prior policy, subject to manager approval{" "}
              <span className="mx-0.5 rounded-md bg-accent-soft px-1.5 py-0.5 text-[0.75em] font-semibold text-accent-softFg">
                S1
              </span>
              .
            </p>
            <div className="mt-3 flex items-center gap-2 border-t border-border pt-2.5">
              <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent-softFg">
                <Sparkles size={10} /> Adaptive
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-[10px] font-medium text-success">
                <ShieldCheck size={10} /> Verified
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
