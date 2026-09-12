import { Sparkles, ShieldCheck, Quote, Lock, Gauge, Wrench } from "lucide-react";
import { Reveal } from "./Reveal";

const FEATURES = [
  {
    icon: Sparkles,
    title: "Adaptive retrieval",
    desc: "Simple questions get one fast retrieval pass. Complex or low-evidence questions trigger a bounded agentic loop that plans and runs targeted follow-up searches — automatically.",
    span: "lg:col-span-2",
  },
  {
    icon: Gauge,
    title: "Hard-bounded, always",
    desc: "Iteration, retrieval-call, and evidence-chunk caps stop the agent cleanly — no runaway loops, no surprise bills.",
    span: "",
  },
  {
    icon: Quote,
    title: "Real citations",
    desc: "Every claim traces back to a filename, section, and page — click a citation to jump straight to its source.",
    span: "",
  },
  {
    icon: ShieldCheck,
    title: "Verified before you see it",
    desc: "A lightweight verifier checks claims against retrieved evidence and surgically corrects unsupported ones — or tells you honestly when it couldn't check at all.",
    span: "lg:col-span-2",
  },
  {
    icon: Lock,
    title: "Workspace isolation",
    desc: "Every retrieval is filtered by your authenticated workspace at the datastore layer — enforced deterministically, never by an LLM's judgment.",
    span: "",
  },
  {
    icon: Wrench,
    title: "Untrusted by design",
    desc: "Retrieved document text is treated as data, never as instructions — prompt injection embedded in a document can't hijack the agent.",
    span: "",
  },
];

export function FeatureGrid() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8 sm:py-28">
      <Reveal className="mx-auto max-w-2xl text-center">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent">How it&apos;s built</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-fg sm:text-4xl">
          Engineered to be trustworthy, not just clever.
        </h2>
        <p className="mt-3 text-muted">
          Every architectural decision favors provable correctness over impressive-looking magic.
        </p>
      </Reveal>

      <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f, i) => (
          <Reveal key={f.title} delay={i * 60} className={f.span}>
            <div className="group relative h-full overflow-hidden rounded-2xl border border-border bg-surface p-6 transition-all duration-300 hover:-translate-y-1 hover:border-accent/40 hover:shadow-card">
              <div className="gradient-accent flex h-10 w-10 items-center justify-center rounded-xl text-accent-fg shadow-xs transition-transform duration-300 group-hover:scale-110">
                <f.icon size={18} />
              </div>
              <h3 className="mt-4 text-[15px] font-semibold text-fg">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{f.desc}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
