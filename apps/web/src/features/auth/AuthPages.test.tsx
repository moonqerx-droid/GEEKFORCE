import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { AuthProvider } from "./AuthProvider";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";

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
});
