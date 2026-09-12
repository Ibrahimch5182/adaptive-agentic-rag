"use client";
import { useId } from "react";

export function Tooltip({
  label,
  children,
  side = "top",
}: {
  label: string;
  children: React.ReactNode;
  side?: "top" | "bottom";
}) {
  const id = useId();
  return (
    <span className="group/tip relative inline-flex">
      <span aria-describedby={id} tabIndex={-1} className="inline-flex">
        {children}
      </span>
      <span
        id={id}
        role="tooltip"
        className={`pointer-events-none absolute left-1/2 z-20 w-max max-w-[220px] -translate-x-1/2 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs leading-snug text-fg opacity-0 shadow-card transition-opacity duration-150 group-hover/tip:opacity-100 group-focus-within/tip:opacity-100 ${
          side === "top" ? "bottom-full mb-2" : "top-full mt-2"
        }`}
      >
        {label}
      </span>
    </span>
  );
}
