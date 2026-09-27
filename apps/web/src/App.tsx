import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { useAuth } from "./features/auth/AuthProvider";
import { ForgotPasswordPage } from "./features/auth/ForgotPasswordPage";
import { GuestOnly, RequireEmployee, RequireOperator } from "./features/auth/guards";
import { LoginPage } from "./features/auth/LoginPage";
import { OperatorRegisterPage } from "./features/auth/OperatorRegisterPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { ResetPasswordPage } from "./features/auth/ResetPasswordPage";
import { VerifyEmailPage } from "./features/auth/VerifyEmailPage";
import { EmployeeHistoryPage } from "./pages/EmployeeHistoryPage";
import { EmployeePage } from "./pages/EmployeePage";
import { OperatorPageRoute } from "./pages/OperatorPageRoute";

function RootRedirect() {
  const { user, status } = useAuth();
  if (status === "loading") return <div role="status">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "operator" ? "/operator" : "/employee"} replace />;
}

export default function App() {
  return <Routes>
    <Route path="/" element={<RootRedirect />} />
    <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
    <Route path="/register" element={<GuestOnly><RegisterPage /></GuestOnly>} />
    <Route path="/verify-email" element={<VerifyEmailPage />} />
    <Route path="/forgot-password" element={<GuestOnly><ForgotPasswordPage /></GuestOnly>} />
    <Route path="/reset-password" element={<GuestOnly><ResetPasswordPage /></GuestOnly>} />
    <Route path="/operator/register" element={<GuestOnly><OperatorRegisterPage /></GuestOnly>} />
    <Route element={<AppShell />}>
      <Route path="/employee" element={<RequireEmployee><EmployeePage /></RequireEmployee>} />
      <Route path="/employee/history" element={<RequireEmployee><EmployeeHistoryPage /></RequireEmployee>} />
      <Route path="/operator" element={<RequireOperator><OperatorPageRoute /></RequireOperator>} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
