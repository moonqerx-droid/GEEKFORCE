import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { AdminConversation } from "../../api/types";
import { makeUser, renderAs } from "../../test/render";
import { server } from "../../test/server";
import { AdminChats } from "./AdminChats";

const admin = makeUser({ id: "u-admin", first_name: "Мария", last_name: "Иванова", role: "admin" });

function chat(overrides: Partial<AdminConversation> = {}): AdminConversation {
  return {
    id: "c-1", status: "RESOLVED", created_at: "2026-09-29T09:00:00Z",
    owner_name: "Иван Петров", owner_email: "ivan@helpflow.demo",
    first_message: "не печатает принтер", match: null, messages: 4, ...overrides,
  };
}

describe("AdminChats", () => {
  it("finds a chat by its words and deletes it after confirmation", async () => {
    const queries: string[] = [];
    const deleted: string[] = [];
    let rows = [chat(), chat({ id: "c-rude", first_message: "здравствуйте", match: "грубое слово тут" })];
    server.use(
      http.get("*/api/admin/conversations", ({ request }) => {
        const q = new URL(request.url).searchParams.get("q") ?? "";
        queries.push(q);
        return HttpResponse.json(q ? rows.filter((row) => row.match?.includes(q)) : rows);
      }),
      http.delete("*/api/admin/conversations/:id", ({ params }) => {
        deleted.push(String(params.id));
        rows = rows.filter((row) => row.id !== params.id);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderAs(<AdminChats />, admin, "/admin/chats");

    expect(await screen.findByText("не печатает принтер")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Слова из переписки"), "грубое");
    await user.click(screen.getByRole("button", { name: "Найти" }));

    const list = await screen.findByRole("list", { name: "Чаты" });
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(1));
    expect(queries.at(-1)).toBe("грубое");
    expect(within(list).getByText(/грубое слово тут/)).toBeInTheDocument();

    await user.click(within(list).getByRole("button", { name: "Удалить чат" }));
    expect(deleted).toEqual([]);  // nothing is deleted before the confirmation
    await user.click(screen.getByRole("button", { name: "Удалить навсегда" }));

    await waitFor(() => expect(deleted).toEqual(["c-rude"]));
    expect(await screen.findByRole("status")).toHaveTextContent("Чат удалён");
    expect(screen.queryByText(/грубое слово тут/)).not.toBeInTheDocument();
  });

  it("cancel keeps the chat", async () => {
    const deleted: string[] = [];
    server.use(
      http.get("*/api/admin/conversations", () => HttpResponse.json([chat()])),
      http.delete("*/api/admin/conversations/:id", ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderAs(<AdminChats />, admin, "/admin/chats");

    await user.click(await screen.findByRole("button", { name: "Удалить чат" }));
    await user.click(screen.getByRole("button", { name: "Отмена" }));

    expect(deleted).toEqual([]);
    expect(screen.getByText("не печатает принтер")).toBeInTheDocument();
  });
});
