import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ELENA, ME, makePeerHelp } from "../peer-help/fixtures";
import { PeerHelpNote } from "./PeerHelpNote";

describe("Специалист видит помощь коллег", () => {
  it("names the helping colleague and shows their chat on demand", async () => {
    render(<PeerHelpNote item={makePeerHelp({ author: ME, helper: ELENA, status: "HELPING",
      messages: [{ id: 1, sender: ELENA, content: "Перезапустите VPN-клиент.", created_at: "2026-10-01T09:05:00Z" }] })} />);

    expect(screen.getByText("Помогает коллега: Елена Соколова")).toBeInTheDocument();
    await userEvent.click(screen.getByText(/Переписка сотрудников/));
    expect(screen.getByText("Перезапустите VPN-клиент.")).toBeVisible();
  });

  it("says the employee is still waiting for a colleague", () => {
    render(<PeerHelpNote item={makePeerHelp({ author: ME })} />);

    expect(screen.getByText(/Сотрудник спросил коллег/)).toBeInTheDocument();
    expect(screen.queryByText(/Переписка сотрудников/)).not.toBeInTheDocument();
  });
});
