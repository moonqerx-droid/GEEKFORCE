import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { makeConversation } from "../../test/fixtures";
import { ConversationPage } from "./ConversationPage";

function withStoredConversation(conversation: ReturnType<typeof makeConversation>) {
  window.localStorage.setItem("helpflow.conversationId", conversation.id);
  server.use(http.get("*/api/conversations/:id", () => HttpResponse.json(conversation)));
}

describe("ConversationPage status gating", () => {
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
