import { useId } from "react";

export function LogoMark({ size = 30 }: { size?: number }) {
  const gid = `logo-grad-${useId()}`;
  return (
    <span className="glow-accent inline-flex shrink-0 rounded-[9px]">
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="var(--accent)" />
            <stop offset="100%" stopColor="var(--accent-2)" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="9" fill={`url(#${gid})`} />
        <path
          d="M10 21.5V10.5C10 9.67 10.67 9 11.5 9H18l4 4v8.5c0 .83-.67 1.5-1.5 1.5h-9c-.83 0-1.5-.67-1.5-1.5Z"
          stroke="var(--accent-fg)"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <path d="M18 9v3.5c0 .55.45 1 1 1H22" stroke="var(--accent-fg)" strokeWidth="1.4" strokeLinejoin="round" />
        <circle cx="14.5" cy="18" r="1.15" fill="var(--accent-fg)" />
        <circle cx="18.5" cy="18" r="1.15" fill="var(--accent-fg)" opacity="0.55" />
      </svg>
    </span>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-tight text-fg">ContextGuard</span>
    </span>
  );
}
