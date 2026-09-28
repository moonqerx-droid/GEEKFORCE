import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { makeConversation, makeMessage } from "../../test/fixtures";
import { renderAs } from "../../test/render";
import { ConversationPage } from "./ConversationPage";

const render = (ui: React.ReactNode) => renderAs(ui);

function withStoredConversation(conversation: ReturnType<typeof makeConversation>) {
  window.localStorage.setItem("helpflow.conversationId", conversation.id);
  server.use(http.get("*/api/conversations/:id", () => HttpResponse.json(conversation)));
}

describe("ConversationPage status gating", () => {
  it("shows the user message immediately while the assistant response is pending", async () => {
    let releaseResponse: (() => void) | undefined;
    const responseGate = new Promise<void>((resolve) => {
      releaseResponse = resolve;
    });
    const initial = makeConversation({ id: "optimistic", status: "CLARIFYING" });
    withStoredConversation(initial);
    server.use(
      http.post("*/api/conversations/optimistic/messages", async () => {
        await responseGate;
        return HttpResponse.json(makeConversation({
          id: "optimistic",
          revision: 2,
          status: "CLARIFYING",
          messages: [
            makeMessage("user", "Не работает VPN"),
            makeMessage("assistant", "Проверим подключение."),
          ],
        }));
      }),
    );

    const user = userEvent.setup();
    render(<ConversationPage />);
    const textarea = await screen.findByLabelText("Ваше сообщение");
    await user.type(textarea, "Не работает VPN");
    await user.click(screen.getByRole("button", { name: "Отправить" }));

    expect(within(screen.getByRole("log", { name: "Ход диалога" })).getByText("Не работает VPN")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Помощник думает" })).toBeInTheDocument();
    expect(textarea).toBeEnabled();
    expect(textarea).toHaveValue("");

    releaseResponse?.();
    expect(await screen.findByText("Проверим подключение.")).toBeInTheDocument();
  });

  it("keeps both a failed message and the next draft", async () => {
    let releaseFailure: (() => void) | undefined;
    const failureGate = new Promise<void>((resolve) => {
      releaseFailure = resolve;
    });
    withStoredConversation(makeConversation({ id: "failed-optimistic", status: "CLARIFYING" }));
    server.use(
      http.post("*/api/conversations/failed-optimistic/messages", async () => {
        await failureGate;
        return HttpResponse.error();
      }),
    );

    const user = userEvent.setup();
    render(<ConversationPage />);
    const textarea = await screen.findByLabelText("Ваше сообщение");
    await user.type(textarea, "Первое сообщение");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    await user.type(textarea, "Следующий черновик");
    releaseFailure?.();

    expect(await screen.findByRole("button", { name: "Отправить ещё раз" })).toBeInTheDocument();
    expect(within(screen.getByRole("log", { name: "Ход диалога" })).getByText("Первое сообщение")).toBeInTheDocument();
    expect(textarea).toHaveValue("Следующий черновик");

    await user.click(screen.getByRole("button", { name: "Отправить" }));
    expect(await screen.findAllByRole("button", { name: "Отправить ещё раз" })).toHaveLength(2);
    const log = screen.getByRole("log", { name: "Ход диалога" });
    expect(within(log).getByText("Первое сообщение")).toBeInTheDocument();
    expect(within(log).getByText("Следующий черновик")).toBeInTheDocument();
  });

  it("preserves a typed next draft when the response changes the conversation status", async () => {
    let releaseResponse: (() => void) | undefined;
    const responseGate = new Promise<void>((resolve) => {
      releaseResponse = resolve;
    });
    withStoredConversation(makeConversation({ id: "status-change", status: "CLARIFYING" }));
    server.use(
      http.post("*/api/conversations/status-change/messages", async () => {
        await responseGate;
        return HttpResponse.json(makeConversation({
          id: "status-change",
          revision: 2,
          status: "TROUBLESHOOTING",
          current_step: { code: "restart_vpn", instruction: "Перезапустите VPN-клиент" },
          messages: [makeMessage("user", "VPN не работает")],
        }));
      }),
    );

    const user = userEvent.setup();
    render(<ConversationPage />);
    const textarea = await screen.findByLabelText("Ваше сообщение");
    await user.type(textarea, "VPN не работает");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    await user.type(textarea, "Ошибка 720");
    releaseResponse?.();

    expect(await screen.findByText("Перезапустите VPN-клиент")).toBeInTheDocument();
    expect(screen.getByText("Черновик сохранён")).toBeInTheDocument();
    expect(screen.getByText("Ошибка 720")).toBeInTheDocument();
  });

  it("sends the welcome draft and preserves it after a failed send", async () => {
    let creates = 0;
    let sends = 0;
    server.use(
      http.post("*/api/conversations", () => {
        creates++;
        return HttpResponse.json(makeConversation({ id: "new-ticket" }));
      }),
      http.post("*/api/conversations/new-ticket/messages", async ({ request }) => {
        sends++;
        const payload = await request.json() as { content: string };
        if (sends === 1) return HttpResponse.error();
        return HttpResponse.json(makeConversation({
          id: "new-ticket", revision: 2, status: "CLARIFYING",
          messages: [makeMessage("user", payload.content), makeMessage("assistant", "Какая ошибка?")],
        }));
      }),
    );
    const user = userEvent.setup();
    render(<ConversationPage />);
    await user.type(await screen.findByLabelText("Опишите проблему"), "Не работает VPN");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("сервер");
    expect(screen.getByLabelText("Опишите проблему")).toHaveValue("Не работает VPN");
    await user.click(screen.getByRole("button", { name: "Отправить" }));
    expect(await screen.findByText("Какая ошибка?")).toBeInTheDocument();
    expect(screen.getByText("Не работает VPN")).toBeInTheDocument();
    expect(creates).toBe(1);
    expect(sends).toBe(2);
  });
  it("shows outcome buttons only during TROUBLESHOOTING", async () => {
    withStoredConversation(
      makeConversation({
        id: "c1",
        status: "TROUBLESHOOTING",
        current_step: { code: "clear_cookies", instruction: "Очистите куки браузера" },
      }),
    );

    render(<ConversationPage />);

    expect(await screen.findByText("Очистите куки браузера")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Помогло" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не помогло" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не получается выполнить" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Ваше сообщение")).not.toBeInTheDocument();
  });

  it("shows the message composer for NEW, CLARIFYING and VERIFYING", async () => {
    withStoredConversation(makeConversation({ id: "c2", status: "CLARIFYING" }));
    render(<ConversationPage />);
    expect(await screen.findByLabelText("Ваше сообщение")).toBeInTheDocument();
  });

  it("disables mutations and hides composer once RESOLVED", async () => {
    withStoredConversation(
      makeConversation({ id: "c3", status: "RESOLVED", summary: "CRM восстановлен" }),
    );
    render(<ConversationPage />);

    expect(await screen.findByText("Готово, проблема решена")).toBeInTheDocument();
    expect(screen.queryByLabelText("Ваше сообщение")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Помогло" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Позвать специалиста" })).not.toBeInTheDocument();
  });

  it("shows the escalation panel with completed steps once ESCALATED", async () => {
    withStoredConversation(
      makeConversation({
        id: "c4",
        status: "ESCALATED",
        summary: "Не удаётся войти в CRM",
        escalation_summary: "Пользователь не смог войти в CRM после трёх попыток",
        completed_steps: [
          {
            id: 1,
            code: "clear_cookies",
            instruction: "Очистить куки",
            outcome: "not_helped",
            position: 1,
            created_at: new Date().toISOString(),
          },
        ],
      }),
    );
    render(<ConversationPage />);

    expect(await screen.findByText("Передали специалисту")).toBeInTheDocument();
    expect(screen.getByText("Очистить куки")).toBeInTheDocument();
    expect(screen.getByText("Не помогло")).toBeInTheDocument();
    expect(screen.getByLabelText("Ваше сообщение")).toBeInTheDocument();
  });

  it("shows the specialist's reply as it arrives while the conversation is live", async () => {
    const base = { id: "live", status: "IN_PROGRESS" as const, summary: "Не удаётся войти в CRM", assignee_name: "Анна Смирнова" };
    let polls = 0;
    window.localStorage.setItem("helpflow.conversationId", "live");
    server.use(http.get("*/api/conversations/live", () => {
      polls++;
      return HttpResponse.json(makeConversation({
        ...base,
        revision: polls > 1 ? 3 : 2,
        messages: polls > 1
          ? [{ ...makeMessage("operator", "Сбросила сессию, попробуйте снова"), author_name: "Анна Смирнова" }]
          : [],
      }));
    }));

    renderAs(<ConversationPage />);

    expect(await screen.findByText("Сбросила сессию, попробуйте снова", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/Анна Смирнова подключается к обращению/)).toBeInTheDocument();
  });

  it("lets the employee rate a resolved conversation", async () => {
    let rated: unknown;
    withStoredConversation(makeConversation({ id: "rate-me", status: "RESOLVED", resolved_by: "assistant" }));
    server.use(http.post("*/api/conversations/rate-me/rating", async ({ request }) => {
      rated = await request.json();
      return HttpResponse.json(makeConversation({ id: "rate-me", status: "RESOLVED", rating: 5 }));
    }));
    const user = userEvent.setup();

    render(<ConversationPage />);
    await user.click(await screen.findByRole("radio", { name: "5 из 5" }));
    await user.click(screen.getByRole("button", { name: "Отправить оценку" }));

    expect(await screen.findByText("Спасибо за оценку: 5 из 5.")).toBeInTheDocument();
    expect(rated).toEqual({ rating: 5 });
  });

  it("starts a new request instead of reopening a rated one", async () => {
    withStoredConversation(makeConversation({ id: "done", status: "RESOLVED", rating: 5 }));
    render(<ConversationPage />);
    expect(await screen.findByRole("heading", { name: "Что случилось?" })).toBeInTheDocument();
    expect(window.localStorage.getItem("helpflow.conversationId")).toBeNull();
  });
});

describe("ConversationPage during a known outage", () => {
  it("tells the employee it is a shared outage instead of the usual waiting panel", async () => {
    withStoredConversation(makeConversation({
      id: "outage", status: "ESCALATED", service: "VPN", incident_id: "inc-1",
      messages: [makeMessage("user", "Не подключается VPN"), makeMessage("assistant", "Похоже, это общий сбой")],
    }));
    render(<ConversationPage />);

    const banner = await screen.findByRole("status", { name: "Сбой уже чинят" });
    expect(banner).toHaveTextContent("Вы в списке затронутых: когда специалисты напишут про VPN, сообщение появится здесь.");
    expect(screen.queryByText("Передали специалисту")).not.toBeInTheDocument();
  });
});

