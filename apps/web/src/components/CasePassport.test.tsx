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
});
