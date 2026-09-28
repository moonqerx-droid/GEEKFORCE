import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { makeConversation, makeMessage } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { server } from "../../test/server";
import { EmployeePage } from "../../pages/EmployeePage";

function asked(overrides = {}) {
  return makeConversation({
    id: "c1", status: "CLARIFYING", summary: "Проблема с почтой", revision: 3,
    messages: [makeMessage("user", "Не приходят письма"), makeMessage("assistant", "Где вы работаете с почтой — в программе Outlook или в браузере?")],
    quick_replies: ["В программе Outlook", "В браузере", "Не знаю"],
    ...overrides,
  });
}

function stored(conversation: ReturnType<typeof makeConversation>) {
  window.localStorage.setItem("helpflow.conversationId", conversation.id);
  server.use(
    http.get("*/api/conversations/:id", () => HttpResponse.json(conversation)),
    http.get("*/api/conversations", () => HttpResponse.json([conversation])),
  );
}

describe("quick replies", () => {
  it("answers the question with one tap", async () => {
    let body: Record<string, unknown> | undefined;
    stored(asked());
    server.use(http.post("*/api/conversations/c1/messages", async ({ request }) => {
      body = await request.json() as Record<string, unknown>;
      return HttpResponse.json(asked({ revision: 4, quick_replies: [] }));
    }));
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    const group = await screen.findByRole("group", { name: "Быстрый ответ" });
    await user.click(within(group).getByRole("button", { name: "В браузере" }));

    await waitFor(() => expect(body).toMatchObject({ content: "В браузере", expected_revision: 3 }));
    await waitFor(() => expect(screen.queryByRole("group", { name: "Быстрый ответ" })).not.toBeInTheDocument());
  });

  it("shows nothing when the question needs the employee's own words", async () => {
    stored(asked({ quick_replies: [] }));
    renderAs(<EmployeePage />, undefined, "/employee");
    const log = await screen.findByRole("log", { name: "Ход диалога" });
    await within(log).findByText(/Где вы работаете с почтой/);
    expect(screen.queryByRole("group", { name: "Быстрый ответ" })).not.toBeInTheDocument();
  });
});
