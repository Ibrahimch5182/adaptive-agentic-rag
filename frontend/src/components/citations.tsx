import React from "react";

const CITATION_TOKEN = /(\[S\d+\])/g;
const CITATION_MATCH = /^\[(S\d+)\]$/;

export function CitationChip({ id, onClick }: { id: string; onClick: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onClick(id)}
      className="mx-0.5 inline-flex items-center rounded-md bg-accent-soft px-1.5 py-0.5 align-baseline text-[0.78em] font-semibold text-accent-softFg transition-colors hover:bg-accent hover:text-accent-fg"
    >
      {id}
    </button>
  );
}

/** Recursively walks react-markdown's rendered children, turning literal "[S1]"-style
 * citation tokens into interactive CitationChip buttons that jump to the matching source
 * card. Backend-authored citation IDs are display-only here — no new authority is granted. */
export function withCitations(
  node: React.ReactNode,
  onCite: (id: string) => void,
  keyPrefix = "c",
): React.ReactNode {
  if (typeof node === "string") {
    const parts = node.split(CITATION_TOKEN);
    if (parts.length === 1) return node;
    return parts.map((part, i) => {
      const m = part.match(CITATION_MATCH);
      if (m) return <CitationChip key={`${keyPrefix}-${i}`} id={m[1]} onClick={onCite} />;
      return part;
    });
  }
  if (Array.isArray(node)) {
    return node.map((child, i) => withCitations(child, onCite, `${keyPrefix}-${i}`));
  }
  if (React.isValidElement(node)) {
    const children = (node.props as { children?: React.ReactNode }).children;
    if (children === undefined) return node;
    return React.cloneElement(
      node as React.ReactElement<{ children?: React.ReactNode }>,
      undefined,
      withCitations(children, onCite, keyPrefix),
    );
  }
  return node;
}
