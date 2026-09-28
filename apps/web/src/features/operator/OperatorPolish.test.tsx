import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { OperatorTicket } from "../../api/types";
import { makeTicket } from "../../test/fixtures";
import { makeUser, renderAs } from "../../test/render";
import { server } from "../../test/server";
import type { ReplyTemplate, Sla } from "./operatorApi";
import { OperatorPage } from "./OperatorPage";

const operator = makeUser({ id: "op-1", first_name: "Анна", last_name: "Смирнова", role: "operator" });

function minutesFromNow(minutes: number) {
  return new Date(Date.now() + minutes * 60000).toISOString();
}

function slaFor(urgency: "critical" | "high" | "normal", waited: number): Sla {
  const target = { critical: 15, high: 60, normal: 240 }[urgency];
  return {
    target_minutes: target, started_at: minutesFromNow(-waited), due_at: minutesFromNow(target - waited),
    replied_at: null, state: "ok", waited_minutes: waited, remaining_minutes: target - waited,
  };
}

function ticket(id: string, overrides: Partial<OperatorTicket> & { sla?: Sla | null }) {
  return makeTicket({
    id, summary: `Обращение ${id}`, owner_name: "Иван Петров", escalated_at: minutesFromNow(-5),
    ...overrides,
  } as Partial<OperatorTicket>);
}

const TEMPLATES: ReplyTemplate[] = [
  { id: "t1", title: "Сброс сессии CRM", body: "{имя}, сбросила зависшую сессию CRM. Попробуйте войти ещё раз.", created_at: "", updated_at: "" },
  { id: "t2", title: "Доступ выдан", body: "{имя}, доступ открыт, перезайдите в систему.", created_at: "", updated_at: "" },
];

describe("SLA in the specialist's desk", () => {
  it("marks waiting tickets with how much time is left, in words", async () => {
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json([
      ticket("calm", { urgency: "normal", sla: slaFor("normal", 20) }),
      ticket("close", { urgency: "critical", sla: slaFor("critical", 13) }),
      ticket("late", { urgency: "high", sla: slaFor("high", 85) }),
    ])));
    renderAs(<OperatorPage />, operator);

    const queue = await screen.findByRole("region", { name: "Очередь обращений" });
    expect(await within(queue).findByText("Ответить за 3 ч 40 мин")).toBeInTheDocument();
    expect(within(queue).getByText("Осталось 2 мин")).toHaveClass("sla-warning");
    expect(within(queue).getByText("Просрочено на 25 мин")).toHaveClass("sla-breached");
  });

  it("shows the SLA in the ticket header", async () => {
    const late = ticket("late", { urgency: "high", sla: slaFor("high", 85) });
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([late])),
      http.get("*/api/operator/tickets/late", () => HttpResponse.json(late)),
    );
    renderAs(<OperatorPage />, operator, "/operator?ticket=late");

    const workspace = await screen.findByRole("region", { name: "Переписка по обращению" });
    expect(await within(workspace).findByText(/Первый ответ: норма 1 ч\. Просрочено на 25 мин/)).toBeInTheDocument();
  });
});

describe("reply templates", () => {
  it("inserts a template with the employee's name into the reply without sending it", async () => {
    const open = ticket("t-open", { status: "IN_PROGRESS", assignee_id: "op-1", assignee_name: "Анна Смирнова" });
    let sent = false;
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([open])),
      http.get("*/api/operator/tickets/t-open", () => HttpResponse.json(open)),
      http.get("*/api/operator/templates", () => HttpResponse.json(TEMPLATES)),
      http.post("*/api/operator/tickets/t-open/messages", () => { sent = true; return HttpResponse.json(open); }),
    );
    const user = userEvent.setup();
    renderAs(<OperatorPage />, operator, "/operator?ticket=t-open");

    await user.click(await screen.findByRole("button", { name: "Шаблоны" }));
    const picker = await screen.findByRole("dialog", { name: "Шаблоны ответов" });
    await user.type(within(picker).getByLabelText("Найти шаблон"), "crm");
    expect(within(picker).queryByText("Доступ выдан")).not.toBeInTheDocument();
    await user.click(within(picker).getByRole("button", { name: /Сброс сессии CRM/ }));

    expect(screen.getByLabelText("Ответ сотруднику")).toHaveValue(
      "Иван, сбросила зависшую сессию CRM. Попробуйте войти ещё раз.",
    );
    expect(screen.queryByRole("dialog", { name: "Шаблоны ответов" })).not.toBeInTheDocument();
    await waitFor(() => expect(sent).toBe(false));
  });

  it("explains where templates come from when there are none", async () => {
    const open = ticket("t-open", { status: "IN_PROGRESS", assignee_id: "op-1" });
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([open])),
      http.get("*/api/operator/tickets/t-open", () => HttpResponse.json(open)),
      http.get("*/api/operator/templates", () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderAs(<OperatorPage />, operator, "/operator?ticket=t-open");

    await user.click(await screen.findByRole("button", { name: "Шаблоны" }));
    expect(await screen.findByText("Шаблонов пока нет: их добавляет руководитель поддержки.")).toBeInTheDocument();
  });
});
