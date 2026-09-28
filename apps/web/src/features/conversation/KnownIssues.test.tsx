import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { makeConversation } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { server } from "../../test/server";
import { EmployeePage } from "../../pages/EmployeePage";

describe("known issues on the welcome screen", () => {
  it("shows a confirmed outage and joins it with one click", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      http.get("*/api/known-issues", () => HttpResponse.json([
        { id: "i1", service: "VPN", since: new Date().toISOString(), affected: 5, update: "Перезапускаем шлюз" },
      ])),
      http.post("*/api/conversations", () => HttpResponse.json(makeConversation({ id: "fresh" }), { status: 201 })),
      http.post("*/api/conversations/fresh/messages", async ({ request }) => {
        sent = await request.json() as Record<string, unknown>;
        return HttpResponse.json(makeConversation({ id: "fresh", status: "ESCALATED", revision: 2 }));
      }),
    );
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    const status = await screen.findByRole("region", { name: "Известные сбои" });
    expect(status).toHaveTextContent("VPN: известный сбой, уже чиним");
    expect(status).toHaveTextContent("затронуто сотрудников: 5");
    expect(status).toHaveTextContent("Перезапускаем шлюз");

    await user.click(within(status).getByRole("button", { name: "У меня то же самое" }));
    await waitFor(() => expect(sent).toMatchObject({ content: "У меня тоже не работает VPN" }));
  });

  it("stays quiet when nothing is known to be down", async () => {
    renderAs(<EmployeePage />, undefined, "/employee");
    await screen.findByRole("heading", { name: "Что случилось?" });
    expect(screen.queryByRole("region", { name: "Известные сбои" })).not.toBeInTheDocument();
  });
});
