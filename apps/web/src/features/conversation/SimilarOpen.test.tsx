import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { makeConversation, makeMessage } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { server } from "../../test/server";
import { EmployeePage } from "../../pages/EmployeePage";

const repeat = makeConversation({
  id: "c2", status: "CLARIFYING", summary: "Не подключается VPN",
  messages: [makeMessage("user", "впн опять не работает")],
  similar_open: { id: "c1", summary: "Не подключается VPN" },
});

function serveRepeat() {
  window.localStorage.setItem("helpflow.conversationId", "c2");
  server.use(
    http.get("*/api/conversations/:id", () => HttpResponse.json(repeat)),
    http.get("*/api/conversations", () => HttpResponse.json([repeat])),
  );
}

describe("a repeated request", () => {
  it("continues in the open request: the words move there and the duplicate goes away", async () => {
    let merged = "";
    serveRepeat();
    server.use(http.post("*/api/conversations/:id/merge", ({ params }) => {
      merged = String(params.id);
      return HttpResponse.json(makeConversation({
        id: "c1", status: "ESCALATED", summary: "Не подключается VPN",
        messages: [makeMessage("user", "Не подключается VPN"), makeMessage("user", "впн опять не работает")],
      }));
    }));
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    const note = await screen.findByRole("note", { name: "Похожее открытое обращение" });
    expect(note).toHaveTextContent("У вас уже есть открытое обращение «Не подключается VPN»");
    await user.click(within(note).getByRole("button", { name: "Продолжить там" }));

    await waitFor(() => expect(merged).toBe("c2"));
    await waitFor(() => expect(screen.queryByRole("note", { name: "Похожее открытое обращение" })).not.toBeInTheDocument());
    expect(window.localStorage.getItem("helpflow.conversationId")).toBe("c1");
  });

  it("«Это другое» keeps the new request and hides the hint", async () => {
    serveRepeat();
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    const note = await screen.findByRole("note", { name: "Похожее открытое обращение" });
    await user.click(within(note).getByRole("button", { name: "Это другое" }));
    expect(screen.queryByRole("note", { name: "Похожее открытое обращение" })).not.toBeInTheDocument();
  });
});
