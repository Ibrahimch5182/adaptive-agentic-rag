"use client";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertCircle } from "lucide-react";
import type { QueryResult } from "@/lib/api";
import { normalizeMathText } from "@/lib/mathNormalize";
import { withCitations } from "./citations";
import { VerificationBadge, CorrectedBadge, RouteBadge } from "./AnswerBadges";
import { SourcesPanel } from "./SourcesPanel";
import { RunDetails } from "./RunDetails";
import { fmtMs } from "@/lib/format";

export function AnswerCard({ result }: { result: QueryResult }) {
  const [activeCitationId, setActiveCitationId] = useState<string | null>(null);

  function handleCite(id: string) {
    setActiveCitationId(id);
    document.getElementById(`source-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const md = {
    p: ({ children }: { children?: React.ReactNode }) => <p>{withCitations(children, handleCite)}</p>,
    li: ({ children }: { children?: React.ReactNode }) => <li>{withCitations(children, handleCite)}</li>,
    td: ({ children }: { children?: React.ReactNode }) => <td>{withCitations(children, handleCite)}</td>,
    th: ({ children }: { children?: React.ReactNode }) => <th>{withCitations(children, handleCite)}</th>,
    strong: ({ children }: { children?: React.ReactNode }) => <strong>{withCitations(children, handleCite)}</strong>,
  };

  const statusBorder = result.insufficient
    ? "border-l-warning"
    : result.verification?.status === "SUPPORTED"
      ? "border-l-success"
      : result.verification?.status === "PARTIALLY_SUPPORTED"
        ? "border-l-warning"
        : result.verification?.status === "UNSUPPORTED"
          ? "border-l-danger"
          : "border-l-accent";

  return (
    <div className="animate-slide-up space-y-4">
      <div
        className={`rounded-2xl border border-l-4 p-5 shadow-xs ${statusBorder} ${
          result.insufficient ? "border-warning/30 bg-warning-soft/30" : "border-border bg-surface"
        }`}
      >
        {result.insufficient && (
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-warning">
            <AlertCircle size={15} />
            Insufficient evidence
          </div>
        )}

        <div className="answer-prose">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>
            {normalizeMathText(result.answer)}
          </ReactMarkdown>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3.5">
          <RouteBadge retrievalMode={result.retrieval_mode} />
          {result.verification && <VerificationBadge status={result.verification.status} />}
          {result.verification?.corrected && <CorrectedBadge />}
          {result.timing && (
            <span className="ml-auto rounded-full bg-surface2 px-2.5 py-1 text-xs text-subtle">
              Answered in {fmtMs(result.timing.total_ms)}
            </span>
          )}
        </div>
      </div>

      {result.citations.length > 0 && (
        <SourcesPanel citations={result.citations} activeCitationId={activeCitationId} />
      )}

      <RunDetails
        retrievalMode={result.retrieval_mode}
        trace={result.trace}
        timing={result.timing}
        verification={result.verification}
        evidenceCount={result.evidence_count}
      />
    </div>
  );
}
