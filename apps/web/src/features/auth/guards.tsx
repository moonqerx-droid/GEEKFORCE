import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import type { UserRole } from "../../api/types";
import { homePathFor } from "../../lib/labels";
import { useAuth } from "./AuthProvider";

function Loading() { return <div role="status" className="page-loading">Загрузка…</div>; }

export function GuestOnly({ children }: { children: ReactNode }) {
  const { user, status } = useAuth();
  if (status === "loading") return <Loading />;
  if (user) return <Navigate to={homePathFor(user.role)} replace />;
  return children;
}

function RequireRole({ roles, children }: { roles: UserRole[]; children: ReactNode }) {
  const { user, status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (!roles.includes(user.role)) return <Navigate to={homePathFor(user.role)} replace />;
  return children;
}

export function RequireEmployee({ children }: { children: ReactNode }) {
  return <RequireRole roles={["employee"]}>{children}</RequireRole>;
}

/** Support leads work the queue too, so admins pass this guard. */
export function RequireOperator({ children }: { children: ReactNode }) {
  return <RequireRole roles={["operator", "admin"]}>{children}</RequireRole>;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  return <RequireRole roles={["admin"]}>{children}</RequireRole>;
}
