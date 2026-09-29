import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { makeConversation } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { server } from "../../test/server";
import { EmployeePage } from "../../pages/EmployeePage";

describe("«Что ты умеешь?» on the welcome screen", () => {
  it("asks the assistant at once, so the list of topics is one click away", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      http.post("*/api/conversations", () => HttpResponse.json(makeConversation({ id: "fresh" }), { status: 201 })),
      http.post("*/api/conversations/fresh/messages", async ({ request }) => {
        sent = await request.json() as Record<string, unknown>;
        return HttpResponse.json(makeConversation({ id: "fresh", revision: 2 }));
      }),
    );
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    await user.click(await screen.findByRole("button", { name: "Что ты умеешь?" }));
    await waitFor(() => expect(sent).toMatchObject({ content: "Что ты умеешь?" }));
  });
});
