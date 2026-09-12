import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Reveal } from "./Reveal";

export function FinalCTA() {
  return (
    <section className="relative overflow-hidden py-20 sm:py-28">
      <div className="mesh-bg" aria-hidden />
      <Reveal className="relative mx-auto max-w-2xl px-5 text-center sm:px-8">
        <h2 className="text-3xl font-semibold tracking-tight text-fg sm:text-4xl">
          Stop guessing what your documents say.
        </h2>
        <p className="mt-3 text-muted">
          Create a workspace, upload what you know, and start asking — grounded, cited, verified.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/register"
            className="btn-gradient inline-flex items-center gap-2 rounded-xl px-6 py-3 text-sm font-semibold"
          >
            Create your workspace
            <ArrowRight size={16} />
          </Link>
        </div>
      </Reveal>
    </section>
  );
}
