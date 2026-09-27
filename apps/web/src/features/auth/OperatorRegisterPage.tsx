import { AuthLayout } from "./AuthLayout";

export function OperatorRegisterPage() {
  return <AuthLayout title="Регистрация специалиста" subtitle="Откройте персональную ссылку-приглашение. Без действующего приглашения регистрация недоступна.">
    <p className="auth-message">Форма использует те же защищённые правила, что и регистрация сотрудника, и будет активна при наличии токена приглашения.</p>
  </AuthLayout>;
}
