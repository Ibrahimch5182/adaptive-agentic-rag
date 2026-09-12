"use client";
import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { LayoutGrid, LogOut, Menu, X } from "lucide-react";
import { Wordmark, LogoMark } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { useApiStatus } from "@/hooks/useApiStatus";
import type { AuthUser } from "@/hooks/useAuth";

function StatusDot({ status }: { status: "checking" | "online" | "offline" }) {
  const cls =
    status === "online" ? "bg-success" : status === "offline" ? "bg-danger" : "bg-subtle animate-pulse-soft";
  return <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${cls}`} aria-hidden />;
}

function NavContent({ user, onNavigate }: { user: AuthUser | null; onNavigate?: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const apiStatus = useApiStatus();
  const onWorkspaces = pathname?.startsWith("/workspaces") ?? false;

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-5 pt-5">
        <Wordmark />
      </div>

      <nav className="flex-1 px-3">
        <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-subtle">Workspace</p>
        <button
          onClick={() => {
            router.push("/workspaces");
            onNavigate?.();
          }}
          className={`relative flex w-full items-center gap-2.5 overflow-hidden rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${
            onWorkspaces ? "bg-accent-soft text-accent-softFg" : "text-muted hover:bg-surface2 hover:text-fg"
          }`}
        >
          {onWorkspaces && (
            <span className="gradient-accent absolute inset-y-0 left-0 w-[3px] rounded-r" aria-hidden />
          )}
          <LayoutGrid size={16} />
          Workspaces
        </button>
      </nav>

      <div className="mt-auto space-y-3 border-t border-border px-4 py-4">
        <div className="flex items-center gap-1.5 px-0.5 text-xs text-subtle">
          <StatusDot status={apiStatus} />
          {apiStatus === "online" ? "Backend online" : apiStatus === "offline" ? "Backend unreachable" : "Checking status…"}
        </div>

        <ThemeToggle />

        <div className="flex items-center gap-2.5 pt-1">
          <div className="gradient-accent flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-accent-fg">
            {(user?.full_name || user?.email || "?").slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-fg">{user?.full_name ?? "…"}</p>
            <p className="truncate text-xs text-subtle">{user?.email ?? ""}</p>
          </div>
          <button
            onClick={handleLogout}
            aria-label="Sign out"
            title="Sign out"
            className="shrink-0 rounded-lg p-1.5 text-muted transition-colors hover:bg-surface2 hover:text-danger"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

export function AppShell({ user, children }: { user: AuthUser | null; children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative flex min-h-screen bg-bg">
      <div className="mesh-bg" aria-hidden />

      {/* Desktop sidebar */}
      <aside className="relative z-10 hidden w-64 shrink-0 border-r border-border bg-surface md:block">
        <div className="sticky top-0 h-screen">
          <NavContent user={user} />
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="fixed inset-x-0 top-0 z-30 flex items-center justify-between border-b border-border bg-surface px-4 py-3 md:hidden">
        <LogoMark size={26} />
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation menu"
          className="rounded-lg p-2 text-fg hover:bg-surface2"
        >
          <Menu size={20} />
        </button>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="animate-fade-in absolute inset-0 bg-black/40"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="animate-slide-up absolute inset-y-0 left-0 w-72 max-w-[85%] bg-surface shadow-pop">
            <div className="flex justify-end p-2">
              <button
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation menu"
                className="rounded-lg p-2 text-muted hover:bg-surface2 hover:text-fg"
              >
                <X size={18} />
              </button>
            </div>
            <NavContent user={user} onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      <main className="relative z-10 min-w-0 flex-1 pt-14 md:pt-0">{children}</main>
    </div>
  );
}
