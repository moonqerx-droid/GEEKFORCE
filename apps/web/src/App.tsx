import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { useAuth } from "./features/auth/AuthProvider";
import { ForgotPasswordPage } from "./features/auth/ForgotPasswordPage";
import { ForcedPasswordChangePage } from "./features/auth/ForcedPasswordChangePage";
import {
  GuestOnly,
  RequireAdmin,
  RequireEmployee,
  RequireOperator,
  RequirePendingPasswordChange,
  RequireSignedIn,
} from "./features/auth/guards";
import { CHANGE_PASSWORD_PATH, landingPathFor } from "./lib/routes";
import { LoginPage } from "./features/auth/LoginPage";
import { OperatorRegisterPage } from "./features/auth/OperatorRegisterPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { ResetPasswordPage } from "./features/auth/ResetPasswordPage";
import { VerifyEmailPage } from "./features/auth/VerifyEmailPage";
import { AdminDashboard } from "./features/admin/AdminDashboard";
import { AdminTeam } from "./features/admin/AdminTeam";
import { AdminChats } from "./features/admin/AdminChats";
import { KnowledgePage } from "./features/knowledge/KnowledgePage";
import { ProfilePage } from "./features/profile/ProfilePage";
import { EmployeeHistoryPage } from "./pages/EmployeeHistoryPage";
import { EmployeePage } from "./pages/EmployeePage";
import { OperatorPageRoute } from "./pages/OperatorPageRoute";

function RootRedirect() {
  const { user, status } = useAuth();
  if (status === "loading") return <div role="status" className="page-loading">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={landingPathFor(user)} replace />;
}

export default function App() {
  return <Routes>
    <Route path="/" element={<RootRedirect />} />
    <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
    <Route path="/register" element={<GuestOnly><RegisterPage /></GuestOnly>} />
    <Route path="/verify-email" element={<VerifyEmailPage />} />
    <Route path="/forgot-password" element={<GuestOnly><ForgotPasswordPage /></GuestOnly>} />
    <Route path="/reset-password" element={<GuestOnly><ResetPasswordPage /></GuestOnly>} />
    {/* Deprecated: specialists are now created by an admin. Kept so already sent links still open. */}
    <Route path="/operator/register" element={<GuestOnly><OperatorRegisterPage /></GuestOnly>} />
    <Route path={CHANGE_PASSWORD_PATH} element={<RequirePendingPasswordChange><ForcedPasswordChangePage /></RequirePendingPasswordChange>} />
    <Route element={<AppShell />}>
      <Route path="/employee" element={<RequireEmployee><EmployeePage /></RequireEmployee>} />
      <Route path="/employee/history" element={<RequireEmployee><EmployeeHistoryPage /></RequireEmployee>} />
      <Route path="/operator" element={<RequireOperator><OperatorPageRoute /></RequireOperator>} />
      <Route path="/admin" element={<RequireAdmin><AdminDashboard /></RequireAdmin>} />
      <Route path="/admin/team" element={<RequireAdmin><AdminTeam /></RequireAdmin>} />
      <Route path="/admin/knowledge" element={<RequireAdmin><KnowledgePage /></RequireAdmin>} />
      <Route path="/admin/chats" element={<RequireAdmin><AdminChats /></RequireAdmin>} />
      <Route path="/profile" element={<RequireSignedIn><ProfilePage /></RequireSignedIn>} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
