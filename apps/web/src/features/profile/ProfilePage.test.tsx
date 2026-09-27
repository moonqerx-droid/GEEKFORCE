import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { makePersonalMetrics, makeProfile } from "../../test/fixtures";
import { makeUser, renderAs } from "../../test/render";
import { server } from "../../test/server";
import { ProfilePage } from "./ProfilePage";

const employee = makeUser();
const operator = makeUser({ id: "u-anna", first_name: "Анна", last_name: "Смирнова", role: "operator" });
const admin = makeUser({ id: "u-admin", first_name: "Мария", last_name: "Иванова", role: "admin" });

describe("ProfilePage", () => {
  it("shows the account: name, role, department, status and last sign-in", async () => {
    server.use(http.get("*/api/profile", () => HttpResponse.json(makeProfile())));
    renderAs(<ProfilePage />, employee, "/profile");

    expect(await screen.findByRole("heading", { level: 1, name: "Иван Петров" })).toBeInTheDocument();
    expect(screen.getByText("ivan@example.ru")).toBeInTheDocument();
    expect(screen.getAllByText("Сотрудник").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Продажи").length).toBeGreaterThan(0);
    expect(screen.getByText("Активен")).toBeInTheDocument();
    expect(screen.getByText(/Последний вход/)).toBeInTheDocument();
  });

  it("shows loading and a retryable error", async () => {
    let calls = 0;
    server.use(http.get("*/api/profile", () => {
      calls++;
      return calls === 1 ? HttpResponse.json({}, { status: 500 }) : HttpResponse.json(makeProfile());
    }));
    const user = userEvent.setup();
    renderAs(<ProfilePage />, employee, "/profile");

    expect(await screen.findByText("Не удалось загрузить профиль")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Иван Петров" })).toBeInTheDocument();
  });

  it("edits own name and department", async () => {
    let body: unknown;
    server.use(
      http.get("*/api/profile", () => HttpResponse.json(makeProfile())),
      http.patch("*/api/profile", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeProfile({ name: "Иван Петров-Водкин", department: "finance", revision: 3 }));
      }),
    );
    const user = userEvent.setup();
    renderAs(<ProfilePage />, employee, "/profile");

    const form = await screen.findByRole("form", { name: "Данные аккаунта" });
    await user.clear(within(form).getByLabelText("Имя и фамилия"));
    await user.type(within(form).getByLabelText("Имя и фамилия"), "Иван Петров-Водкин");
    await user.selectOptions(within(form).getByLabelText("Подразделение"), "finance");
    await user.click(within(form).getByRole("button", { name: "Сохранить" }));

    expect(await within(form).findByText("Сохранено")).toBeInTheDocument();
    expect(body).toEqual({ full_name: "Иван Петров-Водкин", department: "finance" });
    expect(screen.getByRole("heading", { level: 1, name: "Иван Петров-Водкин" })).toBeInTheDocument();
  });

  it("changes the password with the current one and checks the rules first", async () => {
    let body: unknown;
    server.use(
      http.get("*/api/profile", () => HttpResponse.json(makeProfile())),
      http.post("*/api/auth/change-password", async ({ request }) => {
        body = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderAs(<ProfilePage />, employee, "/profile");

    const form = await screen.findByRole("form", { name: "Смена пароля" });
    await user.type(within(form).getByLabelText("Текущий пароль"), "OldPass123");
    await user.type(within(form).getByLabelText("Новый пароль"), "short");
    await user.type(within(form).getByLabelText("Повторите новый пароль"), "short");
    await user.click(within(form).getByRole("button", { name: "Сменить пароль" }));
    expect(within(form).getByText(/Минимум 10 символов/)).toBeInTheDocument();
    expect(body).toBeUndefined();

    await user.clear(within(form).getByLabelText("Новый пароль"));
    await user.clear(within(form).getByLabelText("Повторите новый пароль"));
    await user.type(within(form).getByLabelText("Новый пароль"), "NewStrong123");
    await user.type(within(form).getByLabelText("Повторите новый пароль"), "NewStrong123");
    await user.click(within(form).getByRole("button", { name: "Сменить пароль" }));

    expect(await within(form).findByText("Пароль изменён. Другие сеансы завершены.")).toBeInTheDocument();
    expect(body).toEqual({ current_password: "OldPass123", password: "NewStrong123", password_confirmation: "NewStrong123" });
    expect(within(form).getByLabelText("Текущий пароль")).toHaveValue("");
  });

  it("says plainly when the current password is wrong", async () => {
    server.use(
      http.get("*/api/profile", () => HttpResponse.json(makeProfile())),
      http.post("*/api/auth/change-password", () => HttpResponse.json(
        { detail: { code: "invalid_current_password", message: "Текущий пароль указан неверно" } }, { status: 400 },
      )),
    );
    const user = userEvent.setup();
    renderAs(<ProfilePage />, employee, "/profile");

    const form = await screen.findByRole("form", { name: "Смена пароля" });
    await user.type(within(form).getByLabelText("Текущий пароль"), "Wrong12345");
    await user.type(within(form).getByLabelText("Новый пароль"), "NewStrong123");
    await user.type(within(form).getByLabelText("Повторите новый пароль"), "NewStrong123");
    await user.click(within(form).getByRole("button", { name: "Сменить пароль" }));
    expect(await within(form).findByText("Текущий пароль указан неверно")).toBeInTheDocument();
  });

  it("shows a specialist their own metrics and switches the period", async () => {
    const requested: number[] = [];
    server.use(
      http.get("*/api/profile", () => HttpResponse.json(makeProfile({ id: "u-anna", name: "Анна Смирнова", role: "operator", department: "it" }))),
      http.get("*/api/profile/metrics", ({ request }) => {
        const days = Number(new URL(request.url).searchParams.get("days"));
        requested.push(days);
        return HttpResponse.json(makePersonalMetrics({ days, resolved: days === 7 ? 6 : 24 }));
      }),
    );
    const user = userEvent.setup();
    renderAs(<ProfilePage />, operator, "/profile");

    const metrics = await screen.findByRole("region", { name: "Мои показатели" });
    expect(await within(metrics).findByText("24")).toBeInTheDocument();
    expect(within(metrics).getByText("Закрыто")).toBeInTheDocument();
    expect(within(metrics).getByText("6 мин")).toBeInTheDocument();
    expect(within(metrics).getByText("4,6")).toBeInTheDocument();

    await user.click(within(metrics).getByRole("button", { name: "7 дней" }));
    await waitFor(() => expect(requested).toContain(7));
    expect(await within(metrics).findByText("6")).toBeInTheDocument();
  });

  it("never shows support metrics to an employee", async () => {
    let metricsRequested = false;
    server.use(
      http.get("*/api/profile", () => HttpResponse.json(makeProfile())),
      http.get("*/api/profile/metrics", () => { metricsRequested = true; return HttpResponse.json(makePersonalMetrics()); }),
    );
    renderAs(<ProfilePage />, employee, "/profile");

    await screen.findByRole("heading", { level: 1, name: "Иван Петров" });
    expect(screen.queryByRole("region", { name: "Мои показатели" })).not.toBeInTheDocument();
    expect(metricsRequested).toBe(false);
  });

  it("shows an admin their own account without team metrics", async () => {
    let metricsRequested = false;
    server.use(
      http.get("*/api/profile", () => HttpResponse.json(makeProfile({ id: "u-admin", name: "Мария Иванова", role: "admin" }))),
      http.get("*/api/profile/metrics", () => { metricsRequested = true; return HttpResponse.json(makePersonalMetrics()); }),
    );
    renderAs(<ProfilePage />, admin, "/profile");

    await screen.findByRole("heading", { level: 1, name: "Мария Иванова" });
    expect(screen.getAllByText("Руководитель поддержки").length).toBeGreaterThan(0);
    expect(screen.queryByRole("region", { name: "Мои показатели" })).not.toBeInTheDocument();
    expect(metricsRequested).toBe(false);
  });

  it("keeps the page calm when a specialist has no work in the period", async () => {
    server.use(
      http.get("*/api/profile", () => HttpResponse.json(makeProfile({ role: "operator" }))),
      http.get("*/api/profile/metrics", () => HttpResponse.json(makePersonalMetrics({
        resolved: 0, in_progress: 0, waiting_first_reply: 0,
        median_first_reply_minutes: null, median_resolution_minutes: null, average_rating: null, ratings_count: 0,
      }))),
    );
    renderAs(<ProfilePage />, operator, "/profile");

    const metrics = await screen.findByRole("region", { name: "Мои показатели" });
    expect(await within(metrics).findByText("За этот период обращений не было")).toBeInTheDocument();
    expect(within(metrics).queryByText("NaN")).not.toBeInTheDocument();
  });
});
