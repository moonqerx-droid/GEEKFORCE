import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { makeIncident, makeMessage, makeTicket } from "../../test/fixtures";
import { makeUser, renderAs } from "../../test/render";
import { OperatorPage } from "./OperatorPage";

const operator = makeUser({ id: "op-1", first_name: "Анна", last_name: "Смирнова", role: "operator" });

function crmTicket(overrides = {}) {
  return makeTicket({
    id: "t1",
    summary: "Не удаётся войти в CRM с ноутбука",
    service: "CRM",
    urgency: "high",
    urgency_reason: "встреча через 20 минут",
    original_request: "Не могу войти в CRM с ноутбука, через 20 минут встреча",
    owner_name: "Иван Петров",
    owner_department: "sales",
    escalated_at: new Date().toISOString(),
    completed_steps: [{
      id: 1, code: "clear_cookies", instruction: "Очистить куки браузера",
      outcome: "not_helped", position: 1, created_at: new Date().toISOString(),
    }],
    ...overrides,
  });
}

describe("OperatorPage", () => {
  it("shows an empty queue when the assistant handled everything", async () => {
    renderAs(<OperatorPage />, operator);
    expect(await screen.findByText("Очередь пуста")).toBeInTheDocument();
  });

  it("shows an error state when the queue fails to load", async () => {
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json({}, { status: 500 })));
    renderAs(<OperatorPage />, operator);
    expect(await screen.findByText("Не удалось загрузить очередь")).toBeInTheDocument();
  });

  it("opens a ticket with the assistant's card: urgency reason, original words and tried steps", async () => {
    const ticket = crmTicket();
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([ticket])),
      http.get("*/api/operator/tickets/t1", () => HttpResponse.json(ticket)),
    );
    renderAs(<OperatorPage />, operator);

    await userEvent.click(await screen.findByRole("button", { name: /Не удаётся войти в CRM с ноутбука/ }));

    expect(await screen.findByText("встреча через 20 минут")).toBeInTheDocument();
    expect(screen.getByText("Не могу войти в CRM с ноутбука, через 20 минут встреча")).toBeInTheDocument();
    expect(screen.getByText("Очистить куки браузера")).toBeInTheDocument();
    expect(screen.getByText("Не помогло")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Взять в работу" })).toBeInTheDocument();
  });

  it("takes a ticket and answers the employee in the same thread", async () => {
    let current = crmTicket();
    let reply: unknown;
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([current])),
      http.get("*/api/operator/tickets/t1", () => HttpResponse.json(current)),
      http.post("*/api/operator/tickets/t1/assign", () => {
        current = crmTicket({ status: "IN_PROGRESS", assignee_id: "op-1", assignee_name: "Анна Смирнова" });
        return HttpResponse.json(current);
      }),
      http.post("*/api/operator/tickets/t1/messages", async ({ request }) => {
        reply = await request.json();
        current = crmTicket({
          status: "IN_PROGRESS", assignee_id: "op-1", assignee_name: "Анна Смирнова",
          messages: [{ ...makeMessage("operator", "Сбросила сессию"), author_name: "Анна Смирнова" }],
        });
        return HttpResponse.json(current);
      }),
    );
    const user = userEvent.setup();
    renderAs(<OperatorPage />, operator, "/operator?ticket=t1");

    await user.click(await screen.findByRole("button", { name: "Взять в работу" }));
    const box = await screen.findByLabelText("Ответ сотруднику");
    await user.type(box, "Сбросила сессию{Enter}");

    expect(await screen.findByText("Сбросила сессию")).toBeInTheDocument();
    expect(reply).toEqual({ content: "Сбросила сессию" });
    expect(screen.getByRole("button", { name: "Закрыть обращение" })).toBeInTheDocument();
  });

  it("is read-only when another specialist owns the ticket", async () => {
    const ticket = crmTicket({ status: "IN_PROGRESS", assignee_id: "op-2", assignee_name: "Олег Кузнецов" });
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([ticket])),
      http.get("*/api/operator/tickets/t1", () => HttpResponse.json(ticket)),
    );
    renderAs(<OperatorPage />, operator, "/operator?ticket=t1");

    expect(await screen.findByText(/Обращение ведёт Олег Кузнецов/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Ответ сотруднику")).not.toBeInTheDocument();
  });

  it("shows where grounded answers came from", async () => {
    const ticket = crmTicket({
      rag_source_ids: ["vpn.authentication"],
      ai_fallback_reason: "low_confidence",
    });
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([ticket])),
      http.get("*/api/operator/tickets/t1", () => HttpResponse.json(ticket)),
    );
    renderAs(<OperatorPage />, operator, "/operator?ticket=t1");

    expect(await screen.findByText("Откуда помощник брал ответы")).toBeInTheDocument();
    expect(screen.getByText("vpn.authentication")).toBeInTheDocument();
    expect(screen.getByText(/модель не была уверена/)).toBeInTheDocument();
  });

  it("shows mass problems above the queue and explains which requests they group", async () => {
    server.use(http.get("*/api/operator/incidents", () => HttpResponse.json([makeIncident()])));
    const user = userEvent.setup();
    renderAs(<OperatorPage />, operator);

    const radar = await screen.findByRole("region", { name: "Массовые проблемы" });
    expect(within(radar).getByText("VPN не работает у 4 сотрудников")).toBeInTheDocument();
    expect(within(radar).getByText(/первое обращение 28 мин назад/)).toBeInTheDocument();

    await user.click(within(radar).getByRole("button", { name: /VPN не работает у 4 сотрудников/ }));

    const detail = await screen.findByRole("region", { name: "Общий сбой: VPN" });
    expect(within(detail).getByText("Иван Петров")).toBeInTheDocument();
    expect(within(detail).getByText("Не могу подключиться к VPN из дома, ошибка 809")).toBeInTheDocument();
    expect(within(detail).getByText(/Объединили, потому что совпадают сервис и признаки: 809, vpn, подключается/)).toBeInTheDocument();
  });

  it("confirms an outage and sends one update to every affected employee", async () => {
    let incident = makeIncident();
    const posted: Record<string, unknown> = {};
    server.use(
      http.get("*/api/operator/incidents", () => HttpResponse.json([incident])),
      http.post("*/api/operator/incidents/inc-1/confirm", async ({ request }) => {
        posted.confirm = await request.json();
        incident = makeIncident({ status: "ACTIVE", revision: 4 });
        return HttpResponse.json(incident);
      }),
      http.post("*/api/operator/incidents/inc-1/broadcast", async ({ request }) => {
        posted.broadcast = await request.json();
        incident = makeIncident({
          status: "ACTIVE", revision: 5,
          latest_update: { message: "Чиним сервер VPN", request_key: "k", created_at: new Date().toISOString() },
        });
        return HttpResponse.json({ incident, delivered_to: incident.conversation_ids });
      }),
    );
    const user = userEvent.setup();
    renderAs(<OperatorPage />, operator, "/operator?incident=inc-1");

    await user.click(await screen.findByRole("button", { name: "Подтвердить сбой" }));
    expect(posted.confirm).toEqual({ expected_revision: 3 });
    expect(await screen.findByText("Сбой подтверждён")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Сообщение всем затронутым"), "Чиним сервер VPN");
    await user.click(screen.getByRole("button", { name: "Отправить 4 сотрудникам" }));

    expect(await screen.findByText("Отправили 4 сотрудникам. Сообщение появится у них в чате.")).toBeInTheDocument();
    expect(posted.broadcast).toMatchObject({ message: "Чиним сервер VPN", expected_revision: 4 });
    expect((posted.broadcast as { request_key: string }).request_key).toMatch(/^[A-Za-z0-9._:-]+$/);
  });

  it("marks queue tickets that belong to an outage", async () => {
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json([crmTicket({ incident_id: "inc-1" })])));
    renderAs(<OperatorPage />, operator);

    expect(await screen.findByText("Общий сбой")).toBeInTheDocument();
  });
});
