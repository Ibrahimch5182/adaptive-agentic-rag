import { Tooltip } from "./Tooltip";

export type BadgeTone = "accent" | "success" | "warning" | "danger" | "neutral";

const TONE_CLASS: Record<BadgeTone, string> = {
  accent: "bg-accent-soft text-accent-softFg",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  neutral: "bg-surface2 text-muted",
};

export function Badge({
  label,
  tone = "neutral",
  icon,
  tooltip,
}: {
  label: string;
  tone?: BadgeTone;
  icon?: React.ReactNode;
  tooltip?: string;
}) {
  const el = (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium leading-none ${TONE_CLASS[tone]}`}
    >
      {icon}
      {label}
    </span>
  );
  if (!tooltip) return el;
  return <Tooltip label={tooltip}>{el}</Tooltip>;
}
