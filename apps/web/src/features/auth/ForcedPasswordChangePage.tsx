import { useNavigate } from "react-router-dom";
import { Button } from "../../components/Button";
import { ChangePasswordForm } from "../profile/ChangePasswordForm";
import { useAuth } from "./AuthProvider";
import "./ForcedPasswordChangePage.css";

/**
 * A temporary password from an admin opens only this screen. The guards send every
 * protected route here until `must_change_password` clears, and send this route home after.
 */
export function ForcedPasswordChangePage() {
  const { user, refresh, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <main className="forced">
      <div className="forced-card">
        <img className="forced-logo" src="/brand/helpflow-logo-512.png" alt="" aria-hidden="true" />
        <h1 className="forced-title">Задайте постоянный пароль</h1>
        <p className="forced-lead">
          {user ? `${user.first_name}, в` : "В"}аш аккаунт создан или сброшен руководителем поддержки с временным паролем.
          Придумайте свой, чтобы продолжить: временный после этого перестанет работать, а другие сеансы завершатся.
        </p>
        <ChangePasswordForm
          name="Постоянный пароль"
          currentLabel="Временный пароль"
          submitLabel="Сохранить пароль"
          successMessage={null}
          onChanged={refresh}
        />
        <div className="forced-footer">
          <span>Не вы получали этот пароль?</span>
          <Button variant="ghost" onClick={async () => { await logout(); navigate("/login", { replace: true }); }}>Выйти</Button>
        </div>
      </div>
    </main>
  );
}
