import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { AuthProvider } from "./AuthProvider";
import { ForgotPasswordPage } from "./ForgotPasswordPage";
import { VerifyEmailPage } from "./VerifyEmailPage";

afterEach(() => window.sessionStorage.clear());

function renderPage(page: React.ReactNode, path = "/") {
  server.use(http.get("*/api/auth/me", () => HttpResponse.json({}, { status: 401 })));
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider>{page}</AuthProvider></MemoryRouter>);
}

describe("waiting before another email", () => {
  it("«Отправить новый код» is locked with a countdown after sending", async () => {
    let requests = 0;
    server.use(http.post("*/api/auth/resend-verification", () => {
      requests += 1;
      return HttpResponse.json({ code: "verification_requested", retry_after: 60 }, { status: 202 });
    }));
    renderPage(<VerifyEmailPage />, "/verify-email?email=anna@example.ru");

    await userEvent.click(screen.getByRole("button", { name: "Отправить новый код" }));
    const locked = await screen.findByRole("button", { name: /Новый код можно запросить через \d+ с/ });
    expect(locked).toBeDisabled();
    await userEvent.click(locked);
    expect(requests).toBe(1);
  });

  it("the password link can be requested again only after the countdown", async () => {
    server.use(http.post("*/api/auth/forgot-password", () =>
      HttpResponse.json({ code: "password_reset_requested", retry_after: 60 }, { status: 202 })));
    renderPage(<ForgotPasswordPage />);

    await userEvent.type(screen.getByLabelText("Email"), "anna@example.ru");
    await userEvent.click(screen.getByRole("button", { name: "Отправить ссылку" }));
    expect(await screen.findByRole("button", { name: /Отправить ещё раз через \d+ с/ })).toBeDisabled();
  });

  it("says plainly when the server refuses because of too many emails", async () => {
    server.use(http.post("*/api/auth/forgot-password", () => HttpResponse.json(
      { detail: { code: "email_rate_limited", message: "Слишком много писем" } }, { status: 429 })));
    renderPage(<ForgotPasswordPage />);

    await userEvent.type(screen.getByLabelText("Email"), "anna@example.ru");
    await userEvent.click(screen.getByRole("button", { name: "Отправить ссылку" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Попробуйте через 10 минут");
  });
});
