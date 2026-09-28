import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, ConflictError } from "../../api/client";
import type { KnowledgeDocument } from "../../api/types";
import { makeUser, renderAs } from "../../test/render";
import { server } from "../../test/server";
import { RequireAdmin } from "../auth/guards";
import { KnowledgePage } from "./KnowledgePage";

const admin = makeUser({ id: "u-admin", first_name: "Мария", last_name: "Иванова", role: "admin" });

function makeDocument(overrides: Partial<KnowledgeDocument> = {}): KnowledgeDocument {
  return {
    id: "d-travel",
    title: "Командировки",
    original_filename: "travel.docx",
    media_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes: 48_300,
    sha256: "a".repeat(64),
    service: null,
    status: "ready",
    error_message: null,
    extracted_chars: 5400,
    chunk_count: 6,
    uploaded_by: "u-admin",
    uploaded_by_name: "Мария Иванова",
    created_at: "2026-09-28T09:00:00Z",
    updated_at: "2026-09-28T09:00:05Z",
    processed_at: "2026-09-28T09:00:05Z",
    revision: 2,
    ...overrides,
  };
}

function serveDocuments(documents: KnowledgeDocument[]) {
  server.use(http.get("*/api/admin/knowledge/documents", () => HttpResponse.json(documents)));
}

function renderPage() {
  return renderAs(<KnowledgePage />, admin, "/admin/knowledge");
}

function pickFile(name: string, content = "Правила", type = "text/plain") {
  return new File([content], name, { type });
}

afterEach(() => vi.restoreAllMocks());

describe("KnowledgePage", () => {
  it("lists documents with format, size, status and author", async () => {
    serveDocuments([
      makeDocument(),
      makeDocument({
        id: "d-scan", title: "Скан приказа", original_filename: "order.pdf", media_type: "application/pdf",
        status: "failed", error_message: "В документе нет текста, который можно прочитать.", chunk_count: 0,
      }),
    ]);
    renderPage();

    const table = await screen.findByRole("table", { name: "Документы" });
    const [travel, scan] = within(table).getAllByRole("row").slice(1);
    expect(within(travel).getByText("Командировки")).toBeInTheDocument();
    expect(within(travel).getByText("travel.docx")).toBeInTheDocument();
    expect(within(travel).getByText("DOCX")).toBeInTheDocument();
    expect(within(travel).getByText("47 КБ")).toBeInTheDocument();
    expect(within(travel).getByText("Готов")).toBeInTheDocument();
    // revision is a lock counter, not a document version: it is not shown as "версия".
    expect(within(table).queryByRole("columnheader", { name: "Версия" })).not.toBeInTheDocument();
    expect(within(travel).getByText(/Мария Иванова/)).toBeInTheDocument();
    expect(within(scan).getByText("Ошибка")).toBeInTheDocument();
    expect(within(scan).getByText("В документе нет текста, который можно прочитать.")).toBeInTheDocument();
  });

  it("explains what to do when there are no documents yet", async () => {
    serveDocuments([]);
    renderPage();

    expect(await screen.findByText("Документов пока нет")).toBeInTheDocument();
  });

  it("uploads a picked file and shows it in the list", async () => {
    serveDocuments([]);
    const upload = vi.spyOn(api, "uploadKnowledgeDocument").mockResolvedValue(
      makeDocument({ id: "d-vpn", title: "vpn", original_filename: "vpn.md", media_type: "text/markdown" }),
    );
    const user = userEvent.setup();
    renderPage();

    await user.upload(await screen.findByLabelText("Выбрать файл"), pickFile("vpn.md"));

    expect(upload).toHaveBeenCalledWith(expect.objectContaining({ name: "vpn.md" }));
    expect(await screen.findByText("Документ «vpn» готов: помощник уже отвечает по нему.")).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Документы" })).getByText("vpn.md")).toBeInTheDocument();
  });

  it("refuses a wrong format before uploading", async () => {
    serveDocuments([]);
    const upload = vi.spyOn(api, "uploadKnowledgeDocument");
    const user = userEvent.setup({ applyAccept: false });
    renderPage();

    await user.upload(await screen.findByLabelText("Выбрать файл"), pickFile("tool.exe"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Подходят PDF, DOCX, TXT и Markdown.");
    expect(upload).not.toHaveBeenCalled();
  });

  it("says why the server refused: duplicate and size", async () => {
    serveDocuments([makeDocument()]);
    vi.spyOn(api, "uploadKnowledgeDocument")
      .mockRejectedValueOnce(new ConflictError({ message: "Такой документ уже загружен.", document_id: "d-travel" }))
      .mockRejectedValueOnce(new ApiError(413, "http_413", "Файл больше 10 МБ."));
    const user = userEvent.setup();
    renderPage();
    const input = await screen.findByLabelText("Выбрать файл");

    await user.upload(input, pickFile("copy.docx"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Такой документ уже загружен: «Командировки».");

    await user.upload(input, pickFile("huge.pdf"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Файл больше 10 МБ."));
  });

  it("opens a document with its fragments and deletes it", async () => {
    serveDocuments([makeDocument()]);
    let deleted = false;
    server.use(
      http.get("*/api/admin/knowledge/documents/d-travel", () => HttpResponse.json({
        ...makeDocument(),
        chunks: [{ id: "c1", position: 0, text: "# Командировки\n\nСуточные — 700 рублей в день.", char_count: 44, token_count: 6, metadata: { heading: "Командировки" } }],
      })),
      http.delete("*/api/admin/knowledge/documents/d-travel", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Командировки/ }));
    const panel = await screen.findByRole("region", { name: "Документ «Командировки»" });
    expect(await within(panel).findByText(/Суточные — 700 рублей в день/)).toBeInTheDocument();
    // The heading is shown once, as a label, and Markdown marks are not shown as text.
    const fragments = within(panel).getByRole("list");
    expect(within(fragments).getAllByText("Командировки")).toHaveLength(1);
    expect(within(fragments).queryByText(/#/)).not.toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "Удалить документ" }));
    await user.click(within(panel).getByRole("button", { name: "Да, удалить" }));

    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Документов пока нет")).toBeInTheDocument();
  });

  it("is only for the support lead", async () => {
    renderAs(
      <Routes>
        <Route path="/admin/knowledge" element={<RequireAdmin><KnowledgePage /></RequireAdmin>} />
        <Route path="/operator" element={<p>Очередь специалиста</p>} />
      </Routes>,
      makeUser({ role: "operator" }),
      "/admin/knowledge",
    );

    expect(await screen.findByText("Очередь специалиста")).toBeInTheDocument();
    expect(screen.queryByText("База знаний")).not.toBeInTheDocument();
  });
});
