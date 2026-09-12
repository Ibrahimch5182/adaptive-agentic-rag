import Link from "next/link";
import { Wordmark } from "@/components/Logo";

export function MarketingFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-5 py-8 text-sm text-subtle sm:flex-row sm:px-8">
        <Wordmark />
        <p>Domain-independent adaptive agentic RAG.</p>
        <div className="flex items-center gap-4">
          <Link href="/login" className="transition-colors hover:text-fg">
            Sign in
          </Link>
          <Link href="/register" className="transition-colors hover:text-fg">
            Get started
          </Link>
        </div>
      </div>
    </footer>
  );
}
