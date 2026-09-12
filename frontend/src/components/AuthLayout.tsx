import { ShieldCheck, Sparkles, FolderKanban } from "lucide-react";
import { Wordmark } from "./Logo";

const POINTS = [
  { icon: Sparkles, text: "Adaptive retrieval that escalates to deeper search only when it needs to." },
  { icon: FolderKanban, text: "Workspaces keep every team's documents cleanly isolated." },
  { icon: ShieldCheck, text: "Every answer is grounded in cited, verifiable evidence." },
];

export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-surface2 p-10 lg:flex">
        <div className="mesh-bg" aria-hidden />
        <div className="relative animate-slide-up">
          <Wordmark />
        </div>
        <div className="relative max-w-md animate-slide-up" style={{ animationDelay: "80ms" }}>
          <h1 className="gradient-text text-3xl font-semibold leading-tight tracking-tight">
            Adaptive AI over your documents.
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Upload your knowledge base, ask a question, and get a grounded, cited answer — with a bounded
            agentic loop that only does extra work when the evidence calls for it.
          </p>
          <ul className="mt-6 space-y-3">
            {POINTS.map((p, i) => (
              <li
                key={i}
                className="animate-slide-up flex items-start gap-2.5 text-sm text-muted"
                style={{ animationDelay: `${160 + i * 80}ms` }}
              >
                <span className="gradient-accent mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-accent-fg">
                  <p.icon size={13} />
                </span>
                {p.text}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-subtle">Domain-independent · bounded agentic RAG</p>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex justify-center lg:hidden">
            <Wordmark />
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
