import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { renderAs } from "../../test/render";
import { ColleaguesPage } from "./ColleaguesPage";
import { ELENA, ME } from "./fixtures";

describe("Коллеги", () => {
  it("shows how many times a colleague helped and opens a direct chat", async () => {
    const sent: string[] = [];
    server.use(
      http.get("*/api/colleagues", () => HttpResponse.json([ELENA])),
      http.get("*/api/colleagues/emp-elena/messages", () => HttpResponse.json(sent.map((content, index) => (
        { id: index + 1, sender: ME, recipient: ELENA, content, created_at: "2026-10-01T09:00:00Z" })))),
      http.post("*/api/colleagues/emp-elena/messages", async ({ request }) => {
        const { content } = await request.json() as { content: string };
        sent.push(content);
        return HttpResponse.json({ id: sent.length, sender: ME, recipient: ELENA, content, created_at: "2026-10-01T09:00:00Z" }, { status: 201 });
      }),
    );
    renderAs(<ColleaguesPage />, undefined, "/employee/colleagues");

    expect(await screen.findByText("Помог коллегам: 2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Елена Соколова/ }));
    await userEvent.type(await screen.findByLabelText("Сообщение коллеге"), "Как настроила VPN?");
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));

    expect(await screen.findByText("Как настроила VPN?")).toBeInTheDocument();
  });
});
