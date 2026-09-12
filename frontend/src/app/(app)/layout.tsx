"use client";
import { useAuth } from "@/hooks/useAuth";
import { AppShell } from "@/components/AppShell";
import { LogoMark } from "@/components/Logo";
import { CurrentUserProvider } from "@/lib/authContext";

export default function AppGroupLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="animate-pulse-soft">
          <LogoMark size={36} />
        </div>
      </div>
    );
  }

  if (!user) return null; // useAuth already redirects to /login

  return (
    <CurrentUserProvider user={user}>
      <AppShell user={user}>{children}</AppShell>
    </CurrentUserProvider>
  );
}
