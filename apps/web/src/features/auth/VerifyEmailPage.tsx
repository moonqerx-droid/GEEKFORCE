import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import { AuthLayout } from "./AuthLayout";

export function VerifyEmailPage() {
  const [params] = useSearchParams(); const [state, setState] = useState("Проверяем ссылку…");
  useEffect(() => { const token = params.get("token"); if (!token) { setState("В ссылке нет токена подтверждения."); return; }
    api.verifyEmail(token).then(() => setState("Email подтверждён. Теперь можно войти.")).catch(() => setState("Ссылка недействительна или истекла."));
  }, [params]);
  return <AuthLayout title="Подтверждение email" subtitle={state}><Link className="auth-submit auth-button-link" to="/login">Перейти ко входу</Link></AuthLayout>;
}
