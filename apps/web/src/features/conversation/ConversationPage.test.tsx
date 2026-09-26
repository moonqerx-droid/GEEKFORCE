import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { makeConversation, makeMessage } from "../../test/fixtures";
import { ConversationPage } from "./ConversationPage";

function withStoredConversation(conversation: ReturnType<typeof makeConversation>) {
  window.localStorage.setItem("helpflow.conversationId", conversation.id);
  server.use(http.get("*/api/conversations/:id", () => HttpResponse.json(conversation)));
}

describe("ConversationPage status gating", () => {
  it("sends the welcome draft and preserves it after a failed send", async () => {
    let creates = 0;
    let sends = 0;
    server.use(
      http.post("*/api/conversations", () => {
        creates++;
        return HttpResponse.json(makeConversation({ id: "new-ticket" }));
      }),
      http.post("*/api/conversations/new-ticket/messages", async ({ request }) => {
        sends++;
        const payload = await request.json() as { content: string };
        if (sends === 1) return HttpResponse.error();
        return HttpResponse.json(makeConversation({
          id: "new-ticket", revision: 2, status: "CLARIFYING",
          messages: [makeMessage("user", payload.content), makeMessage("assistant", "Какая ошибка?")],
        }));
      }),
    );
    const user = userEvent.setup();
    render(<ConversationPage />);
    await user.type(await screen.findByLabelText("Описание проблемы"), "Не работает VPN");
    await user.click(screen.getByRole("button", { name: "Отправить обращение" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("сервер");
    expect(screen.getByLabelText("Описание проблемы")).toHaveValue("Не работает VPN");
    await user.click(screen.getByRole("button", { name: "Отправить обращение" }));
    expect(await screen.findByText("Какая ошибка?")).toBeInTheDocument();
    expect(screen.getByText("Не работает VPN")).toBeInTheDocument();
    expect(creates).toBe(1);
    expect(sends).toBe(2);
  });
  it("shows outcome buttons only during TROUBLESHOOTING", async () => {
    withStoredConversation(
      makeConversation({
        id: "c1",
        status: "TROUBLESHOOTING",
        current_step: { code: "clear_cookies", instruction: "Очистите куки браузера" },
      }),
    );

    render(<ConversationPage />);

    expect(await screen.findByText("Очистите куки браузера")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Помогло" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не помогло" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не могу выполнить" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Ваше сообщение")).not.toBeInTheDocument();
  });

  it("shows the message composer for NEW, CLARIFYING and VERIFYING", async () => {
    withStoredConversation(makeConversation({ id: "c2", status: "CLARIFYING" }));
    render(<ConversationPage />);
    expect(await screen.findByLabelText("Ваше сообщение")).toBeInTheDocument();
  });

  it("disables mutations and hides composer once RESOLVED", async () => {
    withStoredConversation(
      makeConversation({ id: "c3", status: "RESOLVED", summary: "CRM восстановлен" }),
    );
    render(<ConversationPage />);

    expect(await screen.findByText("Проблема решена")).toBeInTheDocument();
    expect(screen.queryByLabelText("Ваше сообщение")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Помогло" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Передать специалисту" })).not.toBeInTheDocument();
  });

  it("shows the escalation panel with completed steps once ESCALATED", async () => {
    withStoredConversation(
      makeConversation({
        id: "c4",
        status: "ESCALATED",
        escalation_summary: "Пользователь не смог войти в CRM после трёх попыток",
        completed_steps: [
          {
            id: 1,
            code: "clear_cookies",
            instruction: "Очистить куки",
            outcome: "not_helped",
            position: 1,
            created_at: new Date().toISOString(),
          },
        ],
      }),
    );
    render(<ConversationPage />);

    expect(await screen.findByText("Обращение передано специалисту")).toBeInTheDocument();
    expect(screen.getByText("Очистить куки")).toBeInTheDocument();
    expect(screen.getByText("Не помогло")).toBeInTheDocument();
  });
});
