import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { makeConversation, makeMessage, makeTicket } from "../test/fixtures";
import { makeUser, renderAs } from "../test/render";
import { server } from "../test/server";
import { EmployeePage } from "../pages/EmployeePage";
import { OperatorPage } from "./operator/OperatorPage";

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
