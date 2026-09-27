import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../features/auth/AuthProvider";
import { CHANGE_PASSWORD_PATH } from "../lib/routes";
import { Header } from "./Header";

export function AppShell() {
  const { user, status, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  if (status === "loading") return <div role="status" className="page-loading">Загрузка…</div>;
  // The route guards live inside this shell, so the shell must redirect itself
  // instead of rendering nothing for a signed-out visitor.
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  // No header and navigation until a temporary password is replaced.
  if (user.must_change_password) return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  return <>
    <Header role={user.role} name={`${user.first_name} ${user.last_name}`} onLogout={async () => {
      await logout();
      navigate("/login", { replace: true });
    }} />
    <main className="app-main"><Outlet /></main>
  </>;
}
