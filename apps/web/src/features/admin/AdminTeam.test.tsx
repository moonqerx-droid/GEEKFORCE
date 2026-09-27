import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { AdminUser } from "../../api/types";
import { makeAdminUser, makeSpecialistMetrics } from "../../test/fixtures";
import { makeUser, renderAs } from "../../test/render";
import { server } from "../../test/server";
import { AdminTeam } from "./AdminTeam";

const admin = makeUser({ id: "u-admin", first_name: "Мария", last_name: "Иванова", role: "admin" });

const directory: AdminUser[] = [
  makeAdminUser({ id: "u-admin", name: "Мария Иванова", email: "admin@company.ru", role: "admin", revision: 1 }),
  makeAdminUser(),
  makeAdminUser({ id: "u-ivan", name: "Иван Петров", email: "ivan@company.ru", role: "employee", department: "sales" }),
  makeAdminUser({ id: "u-oleg", name: "Олег Кузнецов", email: "oleg@company.ru", is_active: false, status: "disabled", must_change_password: true, last_login_at: null }),
];

function serveDirectory(users: AdminUser[] = directory) {
  server.use(
    http.get("*/api/admin/users", () => HttpResponse.json(users)),
    http.get("*/api/admin/users/:id/metrics", ({ request }) => {
      const days = Number(new URL(request.url).searchParams.get("days"));
      return HttpResponse.json(makeSpecialistMetrics({ days }));
    }),
  );
}

function renderTeam() {
  return renderAs(<AdminTeam />, admin, "/admin/team");
}

describe("AdminTeam — directory", () => {
  it("lists every account with role, department, status and a password-change flag", async () => {
    serveDirectory();
    renderTeam();

    const table = await screen.findByRole("table", { name: "Пользователи" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    const oleg = within(table).getByRole("row", { name: /Олег Кузнецов/ });
    expect(within(oleg).getByText("oleg@company.ru")).toBeInTheDocument();
    expect(within(oleg).getByText("Отключён")).toBeInTheDocument();
    expect(within(oleg).getByText("Ждёт смены пароля")).toBeInTheDocument();
    expect(within(oleg).getByText("ещё не входил")).toBeInTheDocument();
    const ivan = within(table).getByRole("row", { name: /Иван Петров/ });
    expect(within(ivan).getByText("Сотрудник")).toBeInTheDocument();
    expect(within(ivan).getByText("Продажи")).toBeInTheDocument();
  });

  it("searches by name or email and filters by role and status", async () => {
    serveDirectory();
    const user = userEvent.setup();
    renderTeam();
    const table = await screen.findByRole("table", { name: "Пользователи" });

    await user.type(screen.getByLabelText("Поиск по имени или почте"), "ivan@");
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(1);
    await user.clear(screen.getByLabelText("Поиск по имени или почте"));

    await user.selectOptions(screen.getByLabelText("Роль"), "operator");
    expect(within(table).getAllByRole("row").slice(1).map((row) => row.textContent)).toEqual([
      expect.stringContaining("Анна Смирнова"),
      expect.stringContaining("Олег Кузнецов"),
    ]);

    await user.selectOptions(screen.getByLabelText("Статус"), "disabled");
    expect(within(table).getAllByRole("row").slice(1)).toHaveLength(1);

    await user.type(screen.getByLabelText("Поиск по имени или почте"), "никого");
    expect(screen.getByText("Никого не нашли")).toBeInTheDocument();
  });

  it("shows loading, then an error with retry", async () => {
    let calls = 0;
    server.use(http.get("*/api/admin/users", () => {
      calls++;
      return calls === 1 ? HttpResponse.json({}, { status: 500 }) : HttpResponse.json(directory);
    }));
    const user = userEvent.setup();
    renderTeam();

    expect(screen.getByRole("status", { name: /Загружаем пользователей/ })).toBeInTheDocument();
    expect(await screen.findByText("Не удалось загрузить пользователей")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByRole("table", { name: "Пользователи" })).toBeInTheDocument();
  });
});

describe("AdminTeam — creating a specialist", () => {
  it("creates an account and shows the temporary password exactly once", async () => {
    serveDirectory();
    let body: unknown;
    server.use(http.post("*/api/admin/users/operators", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        user: makeAdminUser({ id: "u-petr", name: "Пётр Сидоров", email: "petr@company.ru", must_change_password: true }),
        temporary_password: "Tmp-9xQ4-LmZ2",
      }, { status: 201 });
    }));
    const user = userEvent.setup();
    renderTeam();
    await screen.findByRole("table", { name: "Пользователи" });

    await user.type(screen.getByLabelText("Имя и фамилия"), "Пётр Сидоров");
    await user.type(screen.getByLabelText("Рабочая почта"), "petr@company.ru");
    await user.selectOptions(screen.getByLabelText("Подразделение"), "it");
    await user.click(screen.getByRole("button", { name: "Создать специалиста" }));

    const dialog = await screen.findByRole("dialog", { name: /Временный пароль/ });
    expect(body).toEqual({ full_name: "Пётр Сидоров", email: "petr@company.ru", department: "it" });
    expect(within(dialog).getByText("Tmp-9xQ4-LmZ2")).toBeInTheDocument();
    expect(within(dialog).getByText(/После закрытия пароль больше нельзя будет посмотреть/)).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Пользователи" })).getByText("Пётр Сидоров")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Готово, пароль передан" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("Tmp-9xQ4-LmZ2")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Имя и фамилия")).toHaveValue("");
  });

  it("copies the temporary password to the clipboard", async () => {
    serveDirectory();
    server.use(http.post("*/api/admin/users/operators", () => HttpResponse.json({
      user: makeAdminUser({ id: "u-petr", name: "Пётр Сидоров" }), temporary_password: "Tmp-9xQ4-LmZ2",
    }, { status: 201 })));
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    renderTeam();
    await screen.findByRole("table", { name: "Пользователи" });

    await user.type(screen.getByLabelText("Имя и фамилия"), "Пётр Сидоров");
    await user.type(screen.getByLabelText("Рабочая почта"), "petr@company.ru");
    await user.selectOptions(screen.getByLabelText("Подразделение"), "it");
    await user.click(screen.getByRole("button", { name: "Создать специалиста" }));
    const dialog = await screen.findByRole("dialog", { name: /Временный пароль/ });
    await user.click(within(dialog).getByRole("button", { name: "Скопировать" }));

    expect(writeText).toHaveBeenCalledWith("Tmp-9xQ4-LmZ2");
    expect(await within(dialog).findByRole("button", { name: "Скопировано" })).toBeInTheDocument();
  });

  it("validates the form locally and explains a duplicate email", async () => {
    serveDirectory();
    server.use(http.post("*/api/admin/users/operators", () => HttpResponse.json(
      { detail: "Пользователь с таким email уже есть" }, { status: 409 },
    )));
    const user = userEvent.setup();
    renderTeam();
    await screen.findByRole("table", { name: "Пользователи" });

    await user.click(screen.getByRole("button", { name: "Создать специалиста" }));
    expect(screen.getByText("Укажите имя и фамилию")).toBeInTheDocument();
    expect(screen.getByText("Укажите рабочую почту")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Имя и фамилия"), "Анна Смирнова");
    await user.type(screen.getByLabelText("Рабочая почта"), "anna@company.ru");
    await user.selectOptions(screen.getByLabelText("Подразделение"), "it");
    await user.click(screen.getByRole("button", { name: "Создать специалиста" }));
    expect(await screen.findByText("Человек с такой почтой уже есть в системе.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("AdminTeam — editing a user", () => {
  async function openAccount(user: ReturnType<typeof userEvent.setup>, name: RegExp) {
    const table = await screen.findByRole("table", { name: "Пользователи" });
    await user.click(within(table).getByRole("button", { name }));
    const panel = await screen.findByRole("dialog", { name });
    await user.click(within(panel).getByRole("tab", { name: "Аккаунт" }));
    return panel;
  }

  it("saves changes with the revision it was loaded with", async () => {
    serveDirectory();
    let body: Record<string, unknown> | undefined;
    server.use(http.patch("*/api/admin/users/u-ivan", async ({ request }) => {
      body = await request.json() as Record<string, unknown>;
      return HttpResponse.json(makeAdminUser({
        id: "u-ivan", name: "Иван Петров", email: "ivan@company.ru", role: "operator", department: "sales", revision: 4,
      }));
    }));
    const user = userEvent.setup();
    renderTeam();

    const panel = await openAccount(user, /Иван Петров/);
    await user.selectOptions(within(panel).getByLabelText("Роль"), "operator");
    await user.click(within(panel).getByRole("button", { name: "Сохранить изменения" }));

    expect(await within(panel).findByText("Изменения сохранены")).toBeInTheDocument();
    expect(body).toEqual({ revision: 3, role: "operator" });
    const row = within(screen.getByRole("table", { name: "Пользователи" })).getByRole("row", { name: /Иван Петров/ });
    expect(within(row).getByText("Специалист")).toBeInTheDocument();
  });

  it("does not lose edits on a revision conflict and lets the admin choose", async () => {
    let listCalls = 0;
    server.use(
      http.get("*/api/admin/users", () => {
        listCalls++;
        return HttpResponse.json(listCalls === 1 ? directory : directory.map((item) => (
          item.id === "u-ivan" ? { ...item, name: "Иван Петров-Водкин", revision: 5 } : item
        )));
      }),
    );
    const patches: Record<string, unknown>[] = [];
    server.use(http.patch("*/api/admin/users/u-ivan", async ({ request }) => {
      const body = await request.json() as Record<string, unknown>;
      patches.push(body);
      if (body.revision === 3) return HttpResponse.json({ detail: "Данные пользователя уже изменились" }, { status: 409 });
      return HttpResponse.json(makeAdminUser({ id: "u-ivan", name: "Иван Петров-Водкин", department: "finance", revision: 6 }));
    }));
    const user = userEvent.setup();
    renderTeam();

    const panel = await openAccount(user, /Иван Петров/);
    await user.selectOptions(within(panel).getByLabelText("Подразделение"), "finance");
    await user.click(within(panel).getByRole("button", { name: "Сохранить изменения" }));

    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent("Пока вы редактировали, данные этого пользователя изменились");
    expect(within(panel).getByLabelText("Подразделение")).toHaveValue("finance");
    expect(alert).toHaveTextContent("Иван Петров-Водкин");

    await user.click(within(alert).getByRole("button", { name: "Сохранить мои изменения поверх" }));
    expect(await within(panel).findByText("Изменения сохранены")).toBeInTheDocument();
    expect(patches[1]).toEqual({ revision: 5, department: "finance" });
  });

  it("can discard edits in favour of the latest data after a conflict", async () => {
    let listCalls = 0;
    server.use(
      http.get("*/api/admin/users", () => {
        listCalls++;
        return HttpResponse.json(listCalls === 1 ? directory : directory.map((item) => (
          item.id === "u-ivan" ? { ...item, department: "hr", revision: 5 } : item
        )));
      }),
      http.patch("*/api/admin/users/u-ivan", () => HttpResponse.json({ detail: "conflict" }, { status: 409 })),
    );
    const user = userEvent.setup();
    renderTeam();

    const panel = await openAccount(user, /Иван Петров/);
    await user.selectOptions(within(panel).getByLabelText("Подразделение"), "finance");
    await user.click(within(panel).getByRole("button", { name: "Сохранить изменения" }));
    await user.click(await within(panel).findByRole("button", { name: "Взять актуальные данные" }));

    expect(within(panel).getByLabelText("Подразделение")).toHaveValue("hr");
    expect(within(panel).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("resets a password only after confirmation and shows the new one once", async () => {
    serveDirectory();
    let resets = 0;
    server.use(http.post("*/api/admin/users/u-anna/reset-password", () => {
      resets++;
      return HttpResponse.json({
        user: makeAdminUser({ must_change_password: true, revision: 4 }), temporary_password: "New-7tR2-Kp9w",
      });
    }));
    const user = userEvent.setup();
    renderTeam();

    const panel = await openAccount(user, /Анна Смирнова/);
    await user.click(within(panel).getByRole("button", { name: "Сбросить пароль" }));
    const confirm = await screen.findByRole("alertdialog", { name: /Сбросить пароль/ });
    expect(confirm).toHaveTextContent("Текущий пароль перестанет работать");
    await user.click(within(confirm).getByRole("button", { name: "Отмена" }));
    expect(resets).toBe(0);

    await user.click(within(panel).getByRole("button", { name: "Сбросить пароль" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Сбросить и показать новый" }));

    const dialog = await screen.findByRole("dialog", { name: /Временный пароль/ });
    expect(within(dialog).getByText("New-7tR2-Kp9w")).toBeInTheDocument();
    expect(resets).toBe(1);
    await user.click(within(dialog).getByRole("button", { name: "Готово, пароль передан" }));
    expect(screen.queryByText("New-7tR2-Kp9w")).not.toBeInTheDocument();
  });
});

describe("AdminTeam — specialist metrics", () => {
  it("opens a specialist's full metrics and switches the period", async () => {
    serveDirectory();
    const requested: number[] = [];
    server.use(http.get("*/api/admin/users/u-anna/metrics", ({ request }) => {
      const days = Number(new URL(request.url).searchParams.get("days"));
      requested.push(days);
      return HttpResponse.json(makeSpecialistMetrics({ days, resolved: days === 90 ? 70 : 24 }));
    }));
    const user = userEvent.setup();
    renderTeam();

    const table = await screen.findByRole("table", { name: "Пользователи" });
    await user.click(within(table).getByRole("button", { name: /Анна Смирнова/ }));
    const panel = await screen.findByRole("dialog", { name: /Анна Смирнова/ });

    expect(await within(panel).findByText("83%")).toBeInTheDocument();
    for (const label of ["Назначено", "Закрыто", "В работе", "Ждут первого ответа", "Ответ в целевое время", "Оценка"]) {
      expect(within(panel).getByText(label)).toBeInTheDocument();
    }
    expect(within(panel).getByText("18 мин")).toBeInTheDocument();
    expect(within(panel).getByText("VPN")).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "90 дней" }));
    await waitFor(() => expect(requested).toContain(90));
    expect(await within(panel).findByText("70")).toBeInTheDocument();
  });

  it("shows a calm empty state when the period has no work", async () => {
    serveDirectory();
    server.use(http.get("*/api/admin/users/u-anna/metrics", () => HttpResponse.json(makeSpecialistMetrics({
      assigned: 0, resolved: 0, in_progress: 0, waiting_first_reply: 0,
      median_first_reply_minutes: null, p90_first_reply_minutes: null,
      median_resolution_minutes: null, p90_resolution_minutes: null,
      first_reply_sla_rate: null, average_rating: null, ratings_count: 0,
      daily: [], topics: [], urgency: {},
    }))));
    const user = userEvent.setup();
    renderTeam();

    const table = await screen.findByRole("table", { name: "Пользователи" });
    await user.click(within(table).getByRole("button", { name: /Анна Смирнова/ }));
    const panel = await screen.findByRole("dialog", { name: /Анна Смирнова/ });
    expect(await within(panel).findByText("За этот период обращений не было")).toBeInTheDocument();
    expect(within(panel).queryByText("NaN")).not.toBeInTheDocument();
  });

  it("opens employees straight on the account tab: they have no support metrics", async () => {
    serveDirectory();
    const user = userEvent.setup();
    renderTeam();

    const table = await screen.findByRole("table", { name: "Пользователи" });
    await user.click(within(table).getByRole("button", { name: /Иван Петров/ }));
    const panel = await screen.findByRole("dialog", { name: /Иван Петров/ });
    expect(within(panel).queryByRole("tab", { name: "Показатели" })).not.toBeInTheDocument();
    expect(within(panel).getByLabelText("Роль")).toBeInTheDocument();
  });
});
