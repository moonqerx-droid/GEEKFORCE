import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { makeConversation, makeMessage } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { ConversationPage } from "./ConversationPage";

function stored(conversation: ReturnType<typeof makeConversation>) {
  window.localStorage.setItem("helpflow.conversationId", conversation.id);
  server.use(http.get("*/api/conversations/:id", () => HttpResponse.json(conversation)));
}

describe("«Срочно»", () => {
  it("hands the request over at once and shows when a specialist answers", async () => {
    stored(makeConversation({
      id: "hurry", status: "TROUBLESHOOTING",
      messages: [makeMessage("user", "принтер не печатает"), makeMessage("assistant", "Проверьте бумагу.")],
    }));
    let called = false;
    server.use(http.post("*/api/conversations/hurry/urgent", () => {
      called = true;
      return HttpResponse.json(makeConversation({
        id: "hurry", status: "ESCALATED", urgency: "high", revision: 3,
        escalated_at: "2026-09-30T10:00:00Z", reply_due_at: "2026-09-30T11:00:00Z", reply_target_minutes: 60,
        messages: [makeMessage("user", "принтер не печатает"),
          makeMessage("assistant", "Отметил как срочное и сразу передал специалисту по оргтехнике.")],
      }));
    }));

    const user = userEvent.setup();
    renderAs(<ConversationPage />);
    await user.click(await screen.findByRole("button", { name: /Срочно/ }));

    expect(called).toBe(true);
    expect(await screen.findByText(/Отметил как срочное/)).toBeInTheDocument();
    expect(screen.getByText(/Ответ специалиста до \d{1,2}:\d{2}/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Срочно/ })).not.toBeInTheDocument();
    expect(screen.getByText("Срочное")).toBeInTheDocument();
  });

  it("is offered while a specialist already has the request, but not once it is solved", async () => {
    stored(makeConversation({
      id: "calm", status: "ESCALATED", urgency: "normal",
      messages: [makeMessage("user", "позовите специалиста")],
    }));
    renderAs(<ConversationPage />);
    expect(await screen.findByRole("button", { name: /Срочно/ })).toBeInTheDocument();
  });

  it("is not offered for a solved request", async () => {
    stored(makeConversation({ id: "done", status: "RESOLVED", messages: [makeMessage("user", "забыл пароль")] }));
    renderAs(<ConversationPage />);
    await screen.findAllByText("забыл пароль");
    expect(screen.queryByRole("button", { name: /Срочно/ })).not.toBeInTheDocument();
  });
});
