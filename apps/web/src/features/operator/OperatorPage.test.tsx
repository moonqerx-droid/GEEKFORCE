import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { makeTicket } from "../../test/fixtures";
import { OperatorPage } from "./OperatorPage";

describe("OperatorPage", () => {
  it("shows an empty state when there are no tickets", async () => {
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json([])));
    render(<OperatorPage />);
    expect(await screen.findByText("Нет обращений")).toBeInTheDocument();
  });

  it("shows an error state when the queue fails to load", async () => {
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json({}, { status: 500 })));
    render(<OperatorPage />);
    expect(await screen.findByText("Не удалось загрузить очередь")).toBeInTheDocument();
  });

  it("shows ticket details including escalation info and completed steps", async () => {
    const ticket = makeTicket({
      id: "t1",
      service: "CRM",
      urgency: "high",
      urgency_reason: "встреча через 20 минут",
      original_request: "Не могу войти в CRM с ноутбука",
      completed_steps: [
        {
          id: 1,
          code: "clear_cookies",
          instruction: "Очистить куки браузера",
          outcome: "not_helped",
          position: 1,
          created_at: new Date().toISOString(),
        },
      ],
    });
    server.use(http.get("*/api/operator/tickets", () => HttpResponse.json([ticket])));

    render(<OperatorPage />);

    await userEvent.click(await screen.findByText("Не могу войти в CRM с ноутбука"));

    expect(screen.getAllByText("Не могу войти в CRM с ноутбука").length).toBeGreaterThan(0);
    expect(screen.getByText("встреча через 20 минут")).toBeInTheDocument();
    expect(screen.getByText("Очистить куки браузера")).toBeInTheDocument();
    expect(screen.getByText("Не помогло")).toBeInTheDocument();
  });

  it("does not render the incidents section when the endpoint 404s", async () => {
    server.use(
      http.get("*/api/operator/tickets", () => HttpResponse.json([])),
      http.get("*/api/operator/incidents", () => HttpResponse.json({}, { status: 404 })),
    );
    render(<OperatorPage />);
    await screen.findByText("Нет обращений");
    expect(screen.queryByLabelText("Массовые инциденты")).not.toBeInTheDocument();
  });
});
