"use client";
import Link from "next/link";
import { useRef } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import { Spotlight } from "./Spotlight";
import { DemoPreview } from "./DemoPreview";

export function Hero() {
  const sectionRef = useRef<HTMLElement>(null);

  function handlePointerMove(e: React.PointerEvent<HTMLElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    sectionRef.current?.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
    sectionRef.current?.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
  }

  return (
    <section
      ref={sectionRef}
      onPointerMove={handlePointerMove}
      className="relative overflow-hidden border-b border-border"
    >
      <div className="mesh-bg" aria-hidden />
      <Spotlight />

      <div className="relative mx-auto grid max-w-6xl grid-cols-1 items-center gap-14 px-5 pb-20 pt-16 sm:px-8 sm:pb-28 sm:pt-24 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="animate-slide-up">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface2/80 px-3 py-1 text-xs font-medium text-muted backdrop-blur">
            <Sparkles size={12} className="text-accent" />
            Bounded agentic RAG · domain-independent
          </span>

          <h1 className="mt-5 text-4xl font-semibold leading-[1.08] tracking-tight text-fg sm:text-5xl lg:text-6xl">
            Ask your documents.
            <br />
            <span className="gradient-text">Get answers you can trust.</span>
          </h1>

          <p className="mt-5 max-w-lg text-base leading-relaxed text-muted sm:text-lg">
            Upload any knowledge base and ask real questions. ContextGuard retrieves evidence,
            escalates to deeper search only when it has to, and grounds every answer in citations
            it can prove — verified before you ever see it.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link href="/register" className="btn-gradient inline-flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold">
              Start for free
              <ArrowRight size={16} />
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-5 py-3 text-sm font-semibold text-fg transition-colors hover:bg-surface2"
            >
              Sign in
            </Link>
          </div>

          <p className="mt-5 text-xs text-subtle">
            No credit card. Bring your own documents — PDF, DOCX, PPTX, Markdown, or HTML.
          </p>
        </div>

        <div className="animate-slide-up [animation-delay:120ms]">
          <DemoPreview />
        </div>
      </div>
    </section>
  );
}
