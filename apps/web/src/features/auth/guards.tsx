import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";

function Loading() { return <div role="status">Загрузка…</div>; }

export function GuestOnly({ children }: { children: ReactNode }) {
  const { user, status } = useAuth();
  if (status === "loading") return <Loading />;
  if (user) return <Navigate to={user.role === "operator" ? "/operator" : "/employee"} replace />;
  return children;
}

function RequireRole({ role, children }: { role: "employee" | "operator"; children: ReactNode }) {
  const { user, status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (user.role !== role) return <Navigate to={user.role === "operator" ? "/operator" : "/employee"} replace />;
  return children;
}

export function RequireEmployee({ children }: { children: ReactNode }) {
  return <RequireRole role="employee">{children}</RequireRole>;
}

export function RequireOperator({ children }: { children: ReactNode }) {
  return <RequireRole role="operator">{children}</RequireRole>;
}
