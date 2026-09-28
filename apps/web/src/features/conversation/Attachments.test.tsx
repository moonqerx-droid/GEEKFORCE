import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { Attachment } from "../../api/types";
import { makeConversation, makeMessage } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { server } from "../../test/server";
import { EmployeePage } from "../../pages/EmployeePage";

function attachment(overrides: Partial<Attachment> = {}): Attachment {
  return {
    id: "a1", filename: "error.png", content_type: "image/png", size: 48213, kind: "image",
    url: "/api/attachments/a1", created_at: new Date().toISOString(), ...overrides,
  };
}

function stored(conversation: ReturnType<typeof makeConversation>) {
  window.localStorage.setItem("helpflow.conversationId", conversation.id);
  server.use(
    http.get("*/api/conversations/:id", () => HttpResponse.json(conversation)),
    http.get("*/api/conversations", () => HttpResponse.json([conversation])),
  );
}

// jsdom's FormData cannot travel through Node's fetch, so the multipart transport is
// covered by the API tests; here the upload call itself is replaced.
afterEach(() => vi.restoreAllMocks());

describe("attachments in the employee chat", () => {
  it("uploads the files first, then sends the message that references them", async () => {
    const uploads: string[] = [];
    let messageBody: Record<string, unknown> | undefined;
    stored(makeConversation({ id: "c1", status: "CLARIFYING", summary: "Не подключается VPN" }));
    vi.spyOn(api, "uploadAttachment").mockImplementation(async (conversationId, file) => {
      expect(conversationId).toBe("c1");
      uploads.push(file.name);
      return attachment({ id: `a-${uploads.length}`, filename: file.name });
    });
    server.use(
      http.post("*/api/conversations/c1/messages", async ({ request }) => {
        messageBody = await request.json() as Record<string, unknown>;
        return HttpResponse.json(makeConversation({
          id: "c1", status: "CLARIFYING", revision: 2, summary: "Не подключается VPN",
          messages: [{ ...makeMessage("user", "Вот ошибка"), attachments: [attachment({ id: "a-1" })] }],
        }));
      }),
    );
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    await user.upload(await screen.findByLabelText("Прикрепить файлы"), new File([new Uint8Array(10)], "error.png", { type: "image/png" }));
    await user.type(screen.getByLabelText("Ваше сообщение"), "Вот ошибка");
    await user.click(screen.getByRole("button", { name: "Отправить" }));

    await waitFor(() => expect(messageBody).toBeDefined());
    expect(uploads).toEqual(["error.png"]);
    expect(messageBody).toMatchObject({ content: "Вот ошибка", attachment_ids: ["a-1"] });
    expect(await screen.findByRole("img", { name: "error.png" })).toBeInTheDocument();
  });

  it("attaches a screenshot to the very first message", async () => {
    let messageBody: Record<string, unknown> | undefined;
    server.use(
      http.get("*/api/conversations", () => HttpResponse.json([])),
      http.post("*/api/conversations", () => HttpResponse.json(makeConversation({ id: "fresh" }), { status: 201 })),
      http.post("*/api/conversations/fresh/messages", async ({ request }) => {
        messageBody = await request.json() as Record<string, unknown>;
        return HttpResponse.json(makeConversation({ id: "fresh", status: "CLARIFYING", revision: 2 }));
      }),
    );
    const uploadedTo: string[] = [];
    vi.spyOn(api, "uploadAttachment").mockImplementation(async (conversationId) => {
      uploadedTo.push(conversationId);
      return attachment({ id: "a-9" });
    });
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    await user.upload(await screen.findByLabelText("Прикрепить файлы"), new File([new Uint8Array(10)], "error.png", { type: "image/png" }));
    await user.type(screen.getByLabelText("Опишите проблему"), "Outlook пишет ошибку");
    await user.click(screen.getByRole("button", { name: "Отправить" }));

    await waitFor(() => expect(messageBody).toMatchObject({ content: "Outlook пишет ошибку", attachment_ids: ["a-9"] }));
    expect(uploadedTo).toEqual(["fresh"]);
  });

  it("keeps text and files when an upload is refused", async () => {
    stored(makeConversation({ id: "c1", status: "CLARIFYING" }));
    vi.spyOn(api, "uploadAttachment").mockRejectedValue(new ApiError(415, "http_415", "Такой файл прикрепить нельзя"));
    let sent = false;
    server.use(http.post("*/api/conversations/c1/messages", () => { sent = true; return HttpResponse.json({}); }));
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    await user.upload(await screen.findByLabelText("Прикрепить файлы"), new File([new Uint8Array(10)], "error.png", { type: "image/png" }));
    await user.type(screen.getByLabelText("Ваше сообщение"), "Вот ошибка");
    await user.click(screen.getByRole("button", { name: "Отправить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Такой файл прикрепить нельзя");
    expect(screen.getByLabelText("Ваше сообщение")).toHaveValue("Вот ошибка");
    expect(screen.getByRole("list", { name: "Прикреплённые файлы" })).toBeInTheDocument();
    expect(sent).toBe(false);
  });

  it("shows pictures as previews that open larger, and files as downloads", async () => {
    stored(makeConversation({
      id: "c2", status: "ESCALATED", summary: "Не открывается отчёт",
      messages: [{
        ...makeMessage("user", "Скриншот и отчёт"),
        attachments: [
          attachment(),
          attachment({ id: "a2", filename: "report.pdf", content_type: "application/pdf", kind: "file", url: "/api/attachments/a2", size: 2_400_000 }),
        ],
      }],
    }));
    const user = userEvent.setup();
    renderAs(<EmployeePage />, undefined, "/employee");

    const log = await screen.findByRole("log", { name: "Ход диалога" });
    const download = within(log).getByRole("link", { name: /report\.pdf/ });
    expect(download).toHaveAttribute("href", "/api/attachments/a2");
    expect(download).toHaveTextContent("2,3 МБ");

    await user.click(within(log).getByRole("button", { name: "Открыть error.png" }));
    const viewer = await screen.findByRole("dialog", { name: "error.png" });
    expect(within(viewer).getByRole("img", { name: "error.png" })).toHaveAttribute("src", "/api/attachments/a1");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("the employee's list of requests", () => {
  it("lists requests with their state and marks the open one", async () => {
    const open = makeConversation({ id: "c1", status: "IN_PROGRESS", summary: "Не подключается VPN", assignee_name: "Анна Смирнова" });
    const done = makeConversation({ id: "c2", status: "RESOLVED", summary: "Забыт пароль", messages: [makeMessage("user", "Забыл пароль")] });
    window.localStorage.setItem("helpflow.conversationId", "c1");
    server.use(
      http.get("*/api/conversations", () => HttpResponse.json([
        { ...open, messages: [makeMessage("user", "VPN")] }, done,
      ])),
      http.get("*/api/conversations/c1", () => HttpResponse.json(open)),
    );
    renderAs(<EmployeePage />, undefined, "/employee");

    const nav = await screen.findByRole("navigation", { name: "Мои обращения" });
    const current = await within(nav).findByRole("link", { name: /Не подключается VPN/ });
    await waitFor(() => expect(current).toHaveAttribute("aria-current", "page"));
    expect(current).toHaveTextContent("Специалист в работе");
    expect(within(nav).getByRole("link", { name: /Забыт пароль/ })).toHaveTextContent("Решено");
    expect(within(nav).getByRole("link", { name: "Новое обращение" })).toBeInTheDocument();
  });
});
