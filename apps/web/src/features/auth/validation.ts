import type { RegistrationPayload } from "../../api/types";

export type RegistrationErrors = Partial<Record<keyof RegistrationPayload, string>>;

const namePattern = /^[\p{L}]+(?:[ '-][\p{L}]+)*$/u;
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function validateRegistration(value: RegistrationPayload): RegistrationErrors {
  const errors: RegistrationErrors = {};
  if (value.first_name.trim().length < 2 || value.first_name.length > 50 || !namePattern.test(value.first_name)) {
    errors.first_name = "Введите корректное имя";
  }
  if (value.last_name.trim().length < 2 || value.last_name.length > 50 || !namePattern.test(value.last_name)) {
    errors.last_name = "Введите корректную фамилию";
  }
  if (!emailPattern.test(value.email.trim().toLowerCase()) || value.email.length > 254) {
    errors.email = "Введите корректный email";
  }
  if (!value.department) errors.department = "Выберите отдел";
  if (value.password.length < 10 || value.password.length > 128 || /\s/.test(value.password) ||
      !/[a-zа-яё]/u.test(value.password) || !/[A-ZА-ЯЁ]/u.test(value.password) || !/\d/.test(value.password)) {
    errors.password = "Минимум 10 символов, заглавная и строчная буквы и цифра";
  }
  if (value.password_confirmation !== value.password) {
    errors.password_confirmation = "Пароли не совпадают";
  }
  if (!value.accepted_terms) errors.accepted_terms = "Необходимо согласие";
  return errors;
}
