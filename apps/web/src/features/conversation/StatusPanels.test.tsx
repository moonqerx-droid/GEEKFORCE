import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeConversation } from "../../test/fixtures";
import { WaitingPanel } from "./StatusPanels";

describe("WaitingPanel", () => {
  it("tells the employee when to expect a reply, by urgency", () => {
    const { rerender } = render(<WaitingPanel conversation={makeConversation({ status: "ESCALATED", urgency: "high" })} />);
    expect(screen.getByRole("status")).toHaveTextContent("в течение часа");
    rerender(<WaitingPanel conversation={makeConversation({ status: "ESCALATED", urgency: "critical" })} />);
    expect(screen.getByRole("status")).toHaveTextContent("в течение 15 минут");
  });
});
