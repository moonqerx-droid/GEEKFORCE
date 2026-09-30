import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { makeConversation, makeMessage, makeTicket } from "../test/fixtures";
import { makeUser, renderAs } from "../test/render";
import { server } from "../test/server";
import { AuthProvider } from "./auth/AuthProvider";
import { LoginPage } from "./auth/LoginPage";
import { EmployeePage } from "../pages/EmployeePage";
import { OperatorPage } from "./operator/OperatorPage";

afterEach(() => window.sessionStorage.clear());

describe("the jury's case scenarios", () => {
  it("one click signs in as an employee and remembers the scenario to send", async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      http.get("*/api/auth/me", () => HttpResponse.json({}, { status: 401 })),
      http.post("*/api/auth/login", async ({ request }) => {
        body = await request.json() as Record<string, unknown>;
        return HttpResponse.json({ id: "u1", email: "ivan@helpflow.demo", first_name: "Иван", last_name: "Петров",
          role: "employee", department: "sales", email_verified: true, must_change_password: false });
      }),
    );
    render(<MemoryRouter><AuthProvider><LoginPage /></AuthProvider></MemoryRouter>);

    expect(screen.getByRole("region", { name: "Проверка кейса за две минуты" })).toHaveTextContent("Нерешаемое самостоятельно");
    await userEvent.click(screen.getByRole("button", { name: /Срочное/ }));

    await waitFor(() => expect(body).toMatchObject({ email: "ivan@helpflow.demo", password: "DemoPass123" }));
    expect(window.sessionStorage.getItem("helpflow.scenario")).toBe("Через 5 минут звонок с клиентом, не запускается Teams, горит!");
  });

  it("the employee page starts a fresh request with the scenario already sent", async () => {
    let sent: Record<string, unknown> | undefined;
    window.sessionStorage.setItem("helpflow.scenario", "Ничего не работает, помогите пожалуйста");
    server.use(
      http.post("*/api/conversations", () => HttpResponse.json(makeConversation({ id: "s1" }), { status: 201 })),
      http.post("*/api/conversations/s1/messages", async ({ request }) => {
        sent = await request.json() as Record<string, unknown>;
        return HttpResponse.json(makeConversation({ id: "s1", status: "CLARIFYING", revision: 2 }));
      }),
    );
    renderAs(<EmployeePage />, undefined, "/employee");
    await waitFor(() => expect(sent).toMatchObject({ content: "Ничего не работает, помогите пожалуйста" }));
    expect(window.sessionStorage.getItem("helpflow.scenario")).toBeNull();  // once, not on every reload
  });
});

describe("«Почему спрашиваю»", () => {
  it("shows why the question on screen is asked", async () => {
    const asking = makeConversation({
      id: "q1", status: "CLARIFYING", messages: [makeMessage("assistant", "Вы сейчас подключены к VPN?")],
      question_reason: "Рабочая система с ноутбука открывается только через VPN.",
    });
    window.localStorage.setItem("helpflow.conversationId", "q1");
    server.use(http.get("*/api/conversations/:id", () => HttpResponse.json(asking)),
      http.get("*/api/conversations", () => HttpResponse.json([asking])));
    renderAs(<EmployeePage />, undefined, "/employee");
    expect(await screen.findByText(/Рабочая система с ноутбука открывается только через VPN/)).toBeInTheDocument();
    expect(screen.getByText("Почему спрашиваю:")).toBeInTheDocument();
  });
});

describe("the specialist's reply draft", () => {
  it("puts a draft written from the card into the reply box", async () => {
    const ticket = makeTicket({ id: "t1", status: "IN_PROGRESS", assignee_id: "op-1", summary: "VPN",
      original_request: "впн не работает", owner_name: "Иван Петров", escalated_at: new Date().toISOString() });
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([ticket])),
      http.get("*/api/operator/tickets/t1", () => HttpResponse.json(ticket)),
      http.get("*/api/operator/tickets/t1/draft", () => HttpResponse.json({
        text: "Иван, здравствуйте! В похожем случае помогло: обновлены сертификаты.", based_on: "old",
      })),
    );
    const user = userEvent.setup();
    renderAs(<OperatorPage />, makeUser({ id: "op-1", role: "operator" }), "/operator?ticket=t1");

    await user.click(await screen.findByRole("button", { name: "Черновик ответа" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Ответ сотруднику" }))
      .toHaveValue("Иван, здравствуйте! В похожем случае помогло: обновлены сертификаты."));
    expect(screen.getByText(/решение из похожего закрытого обращения/)).toBeInTheDocument();
  });
});
