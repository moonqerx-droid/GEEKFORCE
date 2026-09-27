import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { Metrics } from "../../api/types";
import { server } from "../../test/server";
import { makeIncident } from "../../test/fixtures";
import { makeUser, renderAs } from "../../test/render";
import { AdminDashboard } from "./AdminDashboard";

const admin = makeUser({ id: "admin-1", first_name: "Мария", last_name: "Иванова", role: "admin" });

function makeMetrics(): Metrics {
  return {
    days: 7, total: 40, resolved_by_assistant: 24, resolved_by_operator: 10, open: 6, waiting: 4,
    self_service_rate: 0.7, median_resolution_minutes: 12, median_first_reply_minutes: 4,
    average_rating: 4.6, ratings_count: 20, daily: [], top_problems: [],
    urgency: { low: 5, normal: 20, high: 10, critical: 5 }, operators: [],
  };
}

describe("AdminDashboard", () => {
  it("shows active outages next to the metrics", async () => {
    server.use(
      http.get("*/api/admin/metrics", () => HttpResponse.json(makeMetrics())),
      http.get("*/api/operator/incidents", () => HttpResponse.json([makeIncident({ status: "ACTIVE" })])),
    );
    renderAs(<AdminDashboard />, admin);

    const block = await screen.findByRole("region", { name: "Массовые сбои сейчас" });
    expect(await within(block).findByText("VPN не работает у 4 сотрудников")).toBeInTheDocument();
    expect(within(block).getByText("Подтверждён")).toBeInTheDocument();
    expect(within(block).getByRole("link", { name: /VPN не работает/ })).toHaveAttribute("href", "/operator?incident=inc-1");
  });

  it("says so when there are no outages", async () => {
    server.use(
      http.get("*/api/admin/metrics", () => HttpResponse.json(makeMetrics())),
      http.get("*/api/operator/incidents", () => HttpResponse.json([])),
    );
    renderAs(<AdminDashboard />, admin);

    expect(await screen.findByText("Массовых сбоев сейчас нет")).toBeInTheDocument();
  });
});
