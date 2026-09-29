import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { OperatorTicket } from "../../api/types";
import { makeTicket } from "../../test/fixtures";
import { makeUser, renderAs } from "../../test/render";
import { server } from "../../test/server";
import { OperatorPage } from "./OperatorPage";
import { arrangeQueue } from "./queueView";

const me = makeUser({ id: "op-1", first_name: "Анна", last_name: "Смирнова", role: "operator" });
const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

function ticket(id: string, summary: string, overrides: Partial<OperatorTicket> = {}): OperatorTicket {
  return makeTicket({ id, summary, original_request: summary, status: "ESCALATED", urgency: "normal",
    escalated_at: minutesAgo(10), owner_name: "Иван Петров", ...overrides });
}

const QUEUE = [
  ticket("old-high", "Старое срочное", { urgency: "high", escalated_at: minutesAgo(600) }),
  ticket("old", "Старое обычное", { escalated_at: minutesAgo(300) }),
  ticket("new", "Новое обычное", { escalated_at: minutesAgo(1) }),
  ticket("mine", "Моё в работе", { status: "IN_PROGRESS", assignee_id: "op-1", assignee_name: "Анна Смирнова" }),
  ticket("theirs", "У коллеги", { status: "IN_PROGRESS", assignee_id: "op-2", assignee_name: "Олег Кузнецов" }),
];

const options = { scope: "queue" as const, urgency: "all" as const, query: "", currentUserId: "op-1" };

describe("arrangeQueue", () => {
  it("puts the newest request on top and splits waiting, mine and colleagues'", () => {
    const sections = arrangeQueue(QUEUE, { ...options, sort: "newest" });
    expect(sections.map((s) => s.title)).toEqual(["Ждут ответа", "У вас в работе", "В работе у коллег"]);
    expect(sections[0].tickets.map((t) => t.id)).toEqual(["new", "old", "old-high"]);
  });

  it("«Сначала срочные» keeps urgency first and the newest first inside it", () => {
    const [waiting] = arrangeQueue(QUEUE, { ...options, sort: "urgent" });
    expect(waiting.tickets.map((t) => t.id)).toEqual(["old-high", "new", "old"]);
  });

  it("«Дольше всех ждут» puts the longest waiting first", () => {
    const [waiting] = arrangeQueue(QUEUE, { ...options, sort: "waiting" });
    expect(waiting.tickets.map((t) => t.id)).toEqual(["old-high", "old", "new"]);
  });

  it("filters by urgency and finds by words, employee or service", () => {
    expect(arrangeQueue(QUEUE, { ...options, sort: "newest", urgency: "high" })[0].tickets.map((t) => t.id))
      .toEqual(["old-high"]);
    expect(arrangeQueue(QUEUE, { ...options, sort: "newest", query: "коллег" }).flatMap((s) => s.tickets.map((t) => t.id)))
      .toEqual(["theirs"]);
  });
});

describe("the specialist's queue", () => {
  function serve() {
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json(QUEUE)),
      http.get("*/api/operator/tickets/:id", ({ params }) => HttpResponse.json(QUEUE.find((t) => t.id === params.id))),
    );
  }

  it("shows the newest waiting request first and folds colleagues' work", async () => {
    serve();
    renderAs(<OperatorPage />, me);
    const waiting = await screen.findByRole("region", { name: "Ждут ответа" });
    const items = within(waiting).getAllByRole("button");
    expect(items[0]).toHaveTextContent("Новое обычное");
    expect(screen.queryByText("У коллеги")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /В работе у коллег/ }));
    expect(screen.getByText("У коллеги")).toBeInTheDocument();
  });

  it("walks the queue with «Следующее» and the arrow keys", async () => {
    serve();
    const user = userEvent.setup();
    renderAs(<OperatorPage />, me, "/operator?ticket=new");

    expect(await screen.findByText("1 из 4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Следующее →" }));
    expect(await screen.findByText("2 из 4")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Старое обычное" })).toBeInTheDocument();

    screen.getByRole("button", { name: /Старое обычное/, current: true }).focus();
    await user.keyboard("{ArrowDown}");
    await waitFor(() => expect(screen.getByText("3 из 4")).toBeInTheDocument());
  });
});
