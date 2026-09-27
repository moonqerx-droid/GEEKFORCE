import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "../../api/client";
import type { AuthUser, LoginPayload } from "../../api/types";

type AuthStatus = "loading" | "authenticated" | "anonymous" | "error";

interface AuthContextValue {
  user: AuthUser | null;
  status: AuthStatus;
  login: (payload: LoginPayload) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const refresh = async () => {
    try {
      const current = await api.me();
      setUser(current);
      setStatus("authenticated");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setUser(null);
        setStatus("anonymous");
      } else {
        setStatus("error");
      }
    }
  };

  useEffect(() => { void refresh(); }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    status,
    login: async (payload) => {
      const current = await api.login(payload);
      setUser(current);
      setStatus("authenticated");
      return current;
    },
    logout: async () => {
      await api.logout();
      setUser(null);
      setStatus("anonymous");
    },
    refresh,
  }), [user, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
