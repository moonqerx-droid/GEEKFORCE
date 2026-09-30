import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeConversation } from "../test/fixtures";
import { CasePassport } from "./CasePassport";

describe("«Что я понял»", () => {
  it("names the error code and what was tried, and hides bookkeeping facts", () => {
    render(<CasePassport audience="employee" conversation={makeConversation({
      status: "CLARIFYING",
      summary: "Не подключается VPN — ошибка 809",
      known_facts: {
        error_code: "809",
        tried_steps: "Перезагрузите домашний роутер",
        "handoff.access_rights": "нужен новый доступ",
        "started.printer": "yes",
        "issue_resolved.printer": "yes",
      },
    })} />);

    expect(screen.getByText("Код ошибки")).toBeInTheDocument();
    expect(screen.getByText("Сам уже пробовал")).toBeInTheDocument();
    expect(screen.queryByText(/handoff|started|issue resolved/)).not.toBeInTheDocument();
  });

  it("lists tried steps by their titles, not by the message they came with", () => {
    render(<CasePassport audience="employee" conversation={makeConversation({
      status: "ESCALATED",
      summary: "Не печатает принтер",
      completed_steps: [{
        id: 1, code: "check_printer_ready", outcome: "helped", position: 0, created_at: "2026-10-01T01:18:00Z",
        instruction: "Вижу сразу несколько проблем: доступ; принтер. Проверьте, что принтер включён.",
        title: "Проверьте, что принтер включён и выбран",
      }],
    })} />);

    expect(screen.getByText("Проверьте, что принтер включён и выбран")).toBeInTheDocument();
    expect(screen.queryByText(/Вижу сразу несколько проблем/)).not.toBeInTheDocument();
  });
});
