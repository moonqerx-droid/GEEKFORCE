import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { Metrics } from "../../api/types";
import { makeUser, renderAs } from "../../test/render";
import { server } from "../../test/server";
import type { ReplyTemplate } from "../operator/operatorApi";
import { AdminDashboard } from "./AdminDashboard";

const admin = makeUser({ id: "admin-1", first_name: "Мария", last_name: "Иванова", role: "admin" });

function metrics(): Metrics {
  return {
    days: 7, total: 40, resolved_by_assistant: 24, resolved_by_operator: 10, open: 6, waiting: 4,
    self_service_rate: 0.7, median_resolution_minutes: 12, median_first_reply_minutes: 4,
    average_rating: 4.6, ratings_count: 20, daily: [], top_problems: [],
    urgency: { low: 5, normal: 20, high: 10, critical: 5 }, operators: [],
  };
}

function template(overrides: Partial<ReplyTemplate> = {}): ReplyTemplate {
  return { id: "t1", title: "Сброс сессии CRM", body: "{имя}, сбросила сессию.", created_at: "", updated_at: "", ...overrides };
}

describe("AdminDashboard: first-reply SLA", () => {
  it("shows the share of requests answered within the norm", async () => {
    server.use(
      http.get("*/api/admin/metrics", () => HttpResponse.json(metrics())),
      http.get("*/api/operator/sla", () => HttpResponse.json({
        days: 7, met: 8, missed: 1, breached_open: 1, pending: 2, met_rate: 0.8,
        targets: { critical: 15, high: 60, normal: 240, low: 240 },
      })),
    );
    renderAs(<AdminDashboard />, admin);

    const tile = await screen.findByText("первый ответ в норму, 8 из 10");
    expect(tile.closest(".admin-fact")).toHaveTextContent("80%");
    expect(screen.getByText(/Норма: критичные — 15 мин, срочные — 1 ч, остальные — 4 ч/)).toBeInTheDocument();
  });
});

describe("AdminDashboard: reply templates", () => {
  it("creates a template", async () => {
    let posted: unknown;
    server.use(
      http.get("*/api/admin/metrics", () => HttpResponse.json(metrics())),
      http.post("*/api/operator/templates", async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(template({ id: "t-new", title: "Доступ выдан", body: "{имя}, доступ открыт." }), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderAs(<AdminDashboard />, admin);

    const section = await screen.findByRole("region", { name: "Шаблоны ответов" });
    expect(await within(section).findByText(/Шаблонов пока нет/)).toBeInTheDocument();
    await user.type(within(section).getByLabelText("Название"), "Доступ выдан");
    await user.type(within(section).getByLabelText("Текст ответа"), "{{имя}, доступ открыт.");
    await user.click(within(section).getByRole("button", { name: "Добавить шаблон" }));

    expect(posted).toEqual({ title: "Доступ выдан", body: "{имя}, доступ открыт." });
    expect(await within(section).findByText("Доступ выдан")).toBeInTheDocument();
  });

  it("edits and deletes a template", async () => {
    let patched: unknown;
    let deleted = false;
    server.use(
      http.get("*/api/admin/metrics", () => HttpResponse.json(metrics())),
      http.get("*/api/operator/templates", () => HttpResponse.json([template()])),
      http.patch("*/api/operator/templates/t1", async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json(template({ title: "Сброс сессии" }));
      }),
      http.delete("*/api/operator/templates/t1", () => { deleted = true; return new HttpResponse(null, { status: 204 }); }),
    );
    const user = userEvent.setup();
    renderAs(<AdminDashboard />, admin);

    const section = await screen.findByRole("region", { name: "Шаблоны ответов" });
    await user.click(await within(section).findByRole("button", { name: "Изменить «Сброс сессии CRM»" }));
    const title = within(section).getByLabelText("Название");
    await user.clear(title);
    await user.type(title, "Сброс сессии");
    await user.click(within(section).getByRole("button", { name: "Сохранить" }));
    expect(patched).toEqual({ title: "Сброс сессии", body: "{имя}, сбросила сессию." });
    expect(await within(section).findByText("Сброс сессии")).toBeInTheDocument();

    await user.click(within(section).getByRole("button", { name: "Удалить «Сброс сессии»" }));
    await user.click(within(section).getByRole("button", { name: "Да, удалить" }));
    await waitFor(() => expect(deleted).toBe(true));
    expect(await within(section).findByText(/Шаблонов пока нет/)).toBeInTheDocument();
  });

  it("refuses an empty template before sending", async () => {
    server.use(http.get("*/api/admin/metrics", () => HttpResponse.json(metrics())));
    const user = userEvent.setup();
    renderAs(<AdminDashboard />, admin);

    const section = await screen.findByRole("region", { name: "Шаблоны ответов" });
    expect(within(section).getByRole("button", { name: "Добавить шаблон" })).toBeDisabled();
    await user.type(within(section).getByLabelText("Название"), "Без текста");
    expect(within(section).getByRole("button", { name: "Добавить шаблон" })).toBeDisabled();
  });
});
