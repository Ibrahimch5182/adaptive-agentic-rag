import { ShieldCheck, ShieldAlert, ShieldX, ShieldQuestion, Sparkles, Target, Wrench } from "lucide-react";
import { Badge } from "./ui/Badge";
import type { VerificationStatus } from "@/lib/api";

const VERIFY_META: Record<
  VerificationStatus,
  { label: string; tone: "success" | "warning" | "danger" | "neutral"; icon: React.ElementType; tooltip: string }
> = {
  SUPPORTED: {
    label: "Verified",
    tone: "success",
    icon: ShieldCheck,
    tooltip: "Claims were checked against retrieved evidence.",
  },
  PARTIALLY_SUPPORTED: {
    label: "Partially verified",
    tone: "warning",
    icon: ShieldAlert,
    tooltip: "Some claims could not be fully supported by retrieved evidence.",
  },
  UNSUPPORTED: {
    label: "Unverified",
    tone: "danger",
    icon: ShieldX,
    tooltip: "Claims could not be supported by the retrieved evidence.",
  },
  UNAVAILABLE: {
    label: "Verification unavailable",
    tone: "neutral",
    icon: ShieldQuestion,
    tooltip: "The verification step could not complete.",
  },
};

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const meta = VERIFY_META[status];
  const Icon = meta.icon;
  return <Badge label={meta.label} tone={meta.tone} icon={<Icon size={12} />} tooltip={meta.tooltip} />;
}

export function CorrectedBadge() {
  return (
    <Badge
      label="Corrected"
      tone="warning"
      icon={<Wrench size={12} />}
      tooltip="Unsupported claims were automatically revised."
    />
  );
}

export function RouteBadge({ retrievalMode }: { retrievalMode: string }) {
  const isAdaptive = retrievalMode.startsWith("adaptive/");
  const route = isAdaptive ? retrievalMode.split("/")[1] : null;
  const label = isAdaptive
    ? `Adaptive · ${route ? route[0].toUpperCase() + route.slice(1) : ""}`
    : "Deterministic";
  const tooltip = isAdaptive
    ? "Automatically decided how much retrieval this question needed."
    : "A single high-quality retrieval pass was used.";
  return (
    <Badge
      label={label}
      tone="accent"
      icon={isAdaptive ? <Sparkles size={12} /> : <Target size={12} />}
      tooltip={tooltip}
    />
  );
}
