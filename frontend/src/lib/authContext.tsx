"use client";
import { createContext, useContext } from "react";
import type { AuthUser } from "@/hooks/useAuth";

const CurrentUserContext = createContext<AuthUser | null>(null);

export function CurrentUserProvider({ user, children }: { user: AuthUser; children: React.ReactNode }) {
  return <CurrentUserContext.Provider value={user}>{children}</CurrentUserContext.Provider>;
}

/** Only valid inside the (app) route group, which gates rendering on an authenticated user. */
export function useCurrentUser(): AuthUser {
  const user = useContext(CurrentUserContext);
  if (!user) throw new Error("useCurrentUser must be used within an authenticated (app) route");
  return user;
}
