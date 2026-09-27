import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeTicket } from "../../test/fixtures";
import { TicketDetail } from "./TicketDetail";

describe("TicketDetail AI provenance", () => {
  it("shows grounded sources and safe fallback metadata only to the operator", () => {
    const ticket = {
      ...makeTicket(),
      rag_source_ids: ["vpn.authentication", "vpn_connection.question.error_text"],
      ai_fallback_reason: "low_confidence",
      ai_latency_ms: 321,
    };

    render(<TicketDetail ticket={ticket} />);

    expect(screen.getByText("Источники ответа")).toBeInTheDocument();
    expect(screen.getByText("vpn.authentication")).toBeInTheDocument();
    expect(screen.getByText("vpn_connection.question.error_text")).toBeInTheDocument();
    expect(screen.getByText("Использован безопасный fallback")).toBeInTheDocument();
  });
});
