/** Mirrors the backend rules (apps/api RegistrationBase.validate_password) so errors show before sending. */
export const PASSWORD_RULES = "Минимум 10 символов, заглавная и строчная буквы и цифра, без пробелов";

export interface PasswordErrors {
  current_password?: string;
  password?: string;
  password_confirmation?: string;
}

export function validateNewPassword(current: string, password: string, confirmation: string): PasswordErrors {
  const errors: PasswordErrors = {};
  if (!current) errors.current_password = "Введите текущий пароль";
  if (password.length < 10 || password.length > 128 || /\s/.test(password)
    || !/[a-zа-яё]/u.test(password) || !/[A-ZА-ЯЁ]/u.test(password) || !/\d/.test(password)) {
    errors.password = PASSWORD_RULES;
  } else if (password === current) {
    errors.password = "Новый пароль должен отличаться от текущего";
  }
  if (confirmation !== password) errors.password_confirmation = "Пароли не совпадают";
  return errors;
}
