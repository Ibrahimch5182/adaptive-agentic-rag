/** Subtle cursor-follow radial glow, purely presentational. Reads `--spot-x`/`--spot-y`
 * CSS custom properties set by an ancestor's onPointerMove handler (they inherit down
 * the DOM automatically) — this element itself stays pointer-events-none so it never
 * blocks clicks on real content. Disabled entirely for reduced-motion. */
export function Spotlight({ className = "" }: { className?: string }) {
  return (
    <div
      className={`pointer-events-none absolute inset-0 motion-reduce:hidden ${className}`}
      style={{
        background:
          "radial-gradient(480px circle at var(--spot-x, 50%) var(--spot-y, -20%), color-mix(in srgb, var(--accent) 18%, transparent), transparent 70%)",
      }}
      aria-hidden
    />
  );
}
