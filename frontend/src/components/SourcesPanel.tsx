import type { CitationOut } from "@/lib/api";
import { SourceCard } from "./SourceCard";

export function SourcesPanel({
  citations,
  activeCitationId,
}: {
  citations: CitationOut[];
  activeCitationId: string | null;
}) {
  if (citations.length === 0) return null;
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">
        Sources ({citations.length})
      </h3>
      <div className="space-y-2">
        {citations.map((c) => (
          <SourceCard key={c.citation_id} citation={c} highlighted={c.citation_id === activeCitationId} />
        ))}
      </div>
    </div>
  );
}
