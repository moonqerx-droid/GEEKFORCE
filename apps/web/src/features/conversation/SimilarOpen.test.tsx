import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { makeConversation, makeMessage } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { server } from "../../test/server";
import { EmployeePage } from "../../pages/EmployeePage";

describe("a repeated request", () => {
  it("points to the request that is already open", async () => {
    const repeat = makeConversation({
      id: "c2", status: "CLARIFYING", summary: "Не подключается VPN",
      messages: [makeMessage("user", "впн опять не работает")],
      similar_open: { id: "c1", summary: "Не подключается VPN" },
    });
    window.localStorage.setItem("helpflow.conversationId", "c2");
    server.use(
      http.get("*/api/conversations/:id", () => HttpResponse.json(repeat)),
      http.get("*/api/conversations", () => HttpResponse.json([repeat])),
    );
    renderAs(<EmployeePage />, undefined, "/employee");

    const note = await screen.findByRole("note", { name: "Похожее открытое обращение" });
    expect(note).toHaveTextContent("У вас уже есть открытое обращение «Не подключается VPN»");
    expect(within(note).getByRole("link", { name: "Открыть его" })).toHaveAttribute("href", "/employee?conversation=c1");
  });
});
