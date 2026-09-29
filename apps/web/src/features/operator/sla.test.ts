import { describe, expect, it } from "vitest";
import type { Sla } from "./operatorApi";
import { slaView } from "./sla";

const NOW = Date.parse("2026-09-28T12:00:00Z");

function sla(overrides: Partial<Sla>): Sla {
  return {
    target_minutes: 60,
    started_at: "2026-09-28T11:30:00Z",
    due_at: "2026-09-28T12:30:00Z",
    replied_at: null,
    state: "ok",
    waited_minutes: 30,
    remaining_minutes: 30,
    ...overrides,
  };
}

describe("slaView", () => {
  it("counts down on the client from the due time, not from a stale state", () => {
    expect(slaView(sla({}), NOW)).toEqual({ tone: "ok", text: "Ответить за 30 мин" });
    // 11 of 60 minutes left: less than a fifth, the label turns yellow even if the server said ok.
    expect(slaView(sla({ due_at: "2026-09-28T12:11:00Z" }), NOW)).toEqual({ tone: "warning", text: "Осталось 11 мин" });
  });

  it("says how late a reply is, in words and not only in colour", () => {
    expect(slaView(sla({ due_at: "2026-09-28T10:35:00Z", target_minutes: 15 }), NOW))
      .toEqual({ tone: "breached", text: "Просрочено на 1 ч 25 мин" });
  });

  it("describes an answered ticket", () => {
    expect(slaView(sla({ state: "met", replied_at: "2026-09-28T11:40:00Z", waited_minutes: 10 }), NOW))
      .toEqual({ tone: "met", text: "Ответ за 10 мин, в норме" });
    expect(slaView(sla({ state: "missed", replied_at: "2026-09-28T12:50:00Z", waited_minutes: 80 }), NOW))
      .toEqual({ tone: "missed", text: "Ответ за 1 ч 20 мин, норма 1 ч" });
  });

  it("shows nothing without an SLA", () => {
    expect(slaView(null, NOW)).toBeNull();
  });
});
