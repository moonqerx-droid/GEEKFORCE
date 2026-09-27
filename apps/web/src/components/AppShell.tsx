import { Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../features/auth/AuthProvider";
import { Header } from "./Header";

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  return <>
    <Header role={user.role} name={`${user.first_name} ${user.last_name}`} onLogout={async () => {
      await logout();
      navigate("/login", { replace: true });
    }} />
    <main className="app-main"><Outlet /></main>
  </>;
}
