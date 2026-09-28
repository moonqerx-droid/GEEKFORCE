import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../../test/server";
import { AuthProvider } from "./AuthProvider";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";
import { OperatorRegisterPage } from "./OperatorRegisterPage";
import { VerifyEmailPage } from "./VerifyEmailPage";

function renderPage(page: React.ReactNode) {
  server.use(http.get("*/api/auth/me", () => HttpResponse.json({}, { status: 401 })));
  return render(<MemoryRouter><AuthProvider>{page}</AuthProvider></MemoryRouter>);
}

describe("auth pages", () => {
  it("shows local registration errors before sending", async () => {
    renderPage(<RegisterPage />);
    await userEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    expect(await screen.findAllByText(/введите коррект/i)).not.toHaveLength(0);
  });

  it("logs in and shows a clear pending action", async () => {
    server.use(http.post("*/api/auth/login", () => HttpResponse.json({
      id: "1", first_name: "Анна", last_name: "Иванова", email: "a@example.ru",
      department: "it", role: "employee", email_verified_at: "2026-09-27T00:00:00Z",
    })));
    renderPage(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "a@example.ru");
    await userEvent.type(screen.getByLabelText("Пароль"), "StrongPass7");
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText(/вход выполнен/i)).toBeInTheDocument();
  });

  it("signs in as a demo role with one click", async () => {
    let body: Record<string, unknown> | undefined;
    server.use(http.post("*/api/auth/login", async ({ request }) => {
      body = await request.json() as Record<string, unknown>;
      return HttpResponse.json({ id: "u1", email: "anna@helpflow.demo", first_name: "Анна", last_name: "Смирнова", role: "operator", department: "it", email_verified: true, must_change_password: false });
    }));
    renderPage(<LoginPage />);
    const demo = screen.getByRole("region", { name: "Быстрый вход" });
    expect(demo).toHaveTextContent("Сотрудник");
    expect(demo).toHaveTextContent("Руководитель поддержки");
    await userEvent.click(screen.getByRole("button", { name: /Войти как специалист/ }));
    await vi.waitFor(() => expect(body).toMatchObject({ email: "anna@helpflow.demo", password: "DemoPass123" }));
  });

  it("explains that demo data is missing when a demo login fails", async () => {
    server.use(http.post("*/api/auth/login", () => HttpResponse.json({ detail: "bad" }, { status: 401 })));
    renderPage(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: /Войти как сотрудник/ }));
    expect(await screen.findByRole("status")).toHaveTextContent("seed_demo");
  });

  it("registers an invited operator with the token from the link and signs them in", async () => {
    let registered: Record<string, unknown> | undefined;
    let loggedIn = false;
    server.use(http.get("*/api/auth/me", () => HttpResponse.json({}, { status: 401 })));
    server.use(
      http.post("*/api/auth/operator/register", async ({ request }) => {
        registered = await request.json() as Record<string, unknown>;
        return HttpResponse.json({
          id: "2", first_name: "Иван", last_name: "Петров", email: "operator@example.ru",
          department: "it", role: "operator", email_verified_at: "2026-09-27T00:00:00Z",
        }, { status: 201 });
      }),
      http.post("*/api/auth/login", () => {
        loggedIn = true;
        return HttpResponse.json({
          id: "2", first_name: "Иван", last_name: "Петров", email: "operator@example.ru",
          department: "it", role: "operator", email_verified_at: "2026-09-27T00:00:00Z",
        });
      }),
    );
    render(<MemoryRouter initialEntries={["/operator/register?token=invite-token-value-12345&email=operator%40example.ru&first_name=%D0%98%D0%B2%D0%B0%D0%BD&last_name=%D0%9F%D0%B5%D1%82%D1%80%D0%BE%D0%B2"]}>
      <AuthProvider><OperatorRegisterPage /></AuthProvider>
    </MemoryRouter>);
    expect(screen.getByLabelText("Имя")).toHaveValue("Иван");
    expect(screen.getByLabelText("Рабочий email")).toHaveValue("operator@example.ru");
    await userEvent.type(screen.getByLabelText("Пароль"), "StrongPass7");
    await userEvent.type(screen.getByLabelText("Повторите пароль"), "StrongPass7");
    await userEvent.click(screen.getByRole("button", { name: "Создать аккаунт и открыть очередь" }));
    await vi.waitFor(() => expect(loggedIn).toBe(true));
    expect(registered?.invite_token).toBe("invite-token-value-12345");
  });

  it("explains a temporary lockout instead of blaming the password", async () => {
    server.use(http.post("*/api/auth/login", () => HttpResponse.json({
      detail: { code: "rate_limited", message: "Слишком много неверных попыток. Подождите 10 минут и попробуйте снова" },
    }, { status: 429 })));
    renderPage(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "a@example.ru");
    await userEvent.type(screen.getByLabelText("Пароль"), "StrongPass7");
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText(/Подождите 10 минут/)).toBeInTheDocument();
    expect(screen.queryByText("Проверьте email и пароль")).not.toBeInTheDocument();
  });

  it("verifies an email with a six digit code", async () => {
    let body: unknown;
    server.use(http.post("*/api/auth/verify-email", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }));
    render(<MemoryRouter initialEntries={["/verify-email?email=user@example.ru"]}>
      <VerifyEmailPage />
    </MemoryRouter>);
    await userEvent.type(screen.getByLabelText("Код из письма"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Подтвердить email" }));
    expect(await screen.findByText(/email подтверждён/i)).toBeInTheDocument();
    expect(body).toEqual({ email: "user@example.ru", code: "123456" });
  });
});
