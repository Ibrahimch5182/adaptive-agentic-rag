import { Upload, MessageCircleQuestion, Route, ShieldCheck, FileCheck2, ArrowRight } from "lucide-react";
import { Reveal } from "./Reveal";

const STEPS = [
  { icon: Upload, title: "Upload", desc: "Docling parses your PDF, DOCX, PPTX, Markdown or HTML into structure-aware chunks." },
  { icon: MessageCircleQuestion, title: "Ask", desc: "Dense + sparse embeddings index every chunk in Qdrant, scoped to your workspace." },
  { icon: Route, title: "Adaptive retrieval", desc: "A bounded agent decides — in real time — whether one pass is enough or more digging is needed." },
  { icon: ShieldCheck, title: "Verify", desc: "Claims are checked against evidence; unsupported ones get surgically corrected." },
  { icon: FileCheck2, title: "Cited answer", desc: "You get a grounded answer with clickable, page-accurate citations." },
];

export function HowItWorks() {
  return (
    <section className="border-y border-border bg-surface2/40 py-20 sm:py-28">
      <div className="mx-auto max-w-6xl px-5 sm:px-8">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="text-xs font-semibold uppercase tracking-wider text-accent">The pipeline</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-fg sm:text-4xl">
            From raw document to grounded answer.
          </h2>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-6 lg:grid-cols-5 lg:gap-4">
          {STEPS.map((s, i) => (
            <Reveal key={s.title} delay={i * 90} className="relative flex flex-col items-center text-center">
              <div className="gradient-accent glow-accent flex h-14 w-14 items-center justify-center rounded-2xl text-accent-fg">
                <s.icon size={22} />
              </div>
              <span className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-subtle">
                Step {i + 1}
              </span>
              <h3 className="mt-1 text-sm font-semibold text-fg">{s.title}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{s.desc}</p>

              {i < STEPS.length - 1 && (
                <ArrowRight
                  size={16}
                  className="absolute right-[-14px] top-5 hidden shrink-0 text-border lg:block"
                  aria-hidden
                />
              )}
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
