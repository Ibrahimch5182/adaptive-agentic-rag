"use client";
import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme, ThemePref } from "@/hooks/useTheme";

const OPTIONS: { value: ThemePref; label: string; icon: React.ElementType }[] = [
  { value: "light", label: "Light theme", icon: Sun },
  { value: "system", label: "System theme", icon: Monitor },
  { value: "dark", label: "Dark theme", icon: Moon },
];

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className={`flex items-center gap-0.5 rounded-lg border border-border bg-surface2 p-0.5 ${compact ? "" : "w-full"}`}
    >
      {OPTIONS.map((opt) => {
        const Icon = opt.icon;
        const active = theme === opt.value;
        return (
          <button
            key={opt.value}
            role="radio"
            aria-checked={active}
            aria-label={opt.label}
            title={opt.label}
            onClick={() => setTheme(opt.value)}
            className={`flex flex-1 items-center justify-center rounded-md py-1.5 transition-colors ${
              active ? "bg-surface text-accent shadow-xs" : "text-muted hover:text-fg"
            }`}
          >
            <Icon size={15} />
          </button>
        );
      })}
    </div>
  );
}
