import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { renderAs, makeUser } from "../../test/render";
import { SelfHelpPage } from "./SelfHelpPage";

const VPN_809 = {
  query: "809",
  code: {
    code: "809", title: "Сеть не пропускает VPN", meaning: "Сеть не пропускает VPN-соединение.",
    steps: [{ id: "code.809.hotspot", title: "Подключитесь к интернету с телефона", instruction: "Включите раздачу." }],
  },
  guide: {
    playbook_id: "vpn_connection", title: "Не подключается VPN",
    steps: [{ id: "restart_vpn_client", title: "Перезапустите программу VPN", instruction: "Закройте и откройте." }],
  },
  document: { source_id: "document:vpn:1", title: "Инструкция по VPN — Ошибка 809", text: "Роутер блокирует VPN." },
  specialist_only: false,
  notice: null,
};

function Probe() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname}{location.search}</p>;
}

function renderPage() {
  return renderAs(
    <Routes>
      <Route path="/employee/help" element={<SelfHelpPage />} />
      <Route path="/employee" element={<Probe />} />
    </Routes>,
    makeUser(),
    "/employee/help",
  );
}

describe("«Решить самому»", () => {
  it("explains a code, lists the steps and quotes the company document", async () => {
    server.use(http.get("*/api/self-help", () => HttpResponse.json(VPN_809)));
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByRole("searchbox", { name: /Код ошибки или что не работает/ }), "809");
    await user.click(screen.getByRole("button", { name: "Найти" }));

    expect(await screen.findByRole("heading", { name: /Ошибка 809 — Сеть не пропускает VPN/ })).toBeInTheDocument();
    expect(screen.getByText("Сеть не пропускает VPN-соединение.")).toBeInTheDocument();
    expect(screen.getByText("Подключитесь к интернету с телефона")).toBeInTheDocument();
    expect(screen.getByText("Перезапустите программу VPN")).toBeInTheDocument();
    expect(screen.getByText("Роутер блокирует VPN.")).toBeInTheDocument();
  });

  it("hands over to a request with the words and the tried steps filled in", async () => {
    server.use(http.get("*/api/self-help", () => HttpResponse.json(VPN_809)));
    const user = userEvent.setup();
    renderPage();
    await user.type(await screen.findByRole("searchbox", { name: /Код ошибки или что не работает/ }), "809");
    await user.click(screen.getByRole("button", { name: "Найти" }));
    await user.click(await screen.findByRole("checkbox", { name: /Подключитесь к интернету с телефона/ }));

    await user.click(screen.getByRole("button", { name: /Не помогло — создать обращение/ }));

    const where = decodeURIComponent((await screen.findByTestId("where")).textContent ?? "");
    expect(where).toContain("/employee?new=1&draft=");
    expect(where).toContain("809");
    expect(where).toContain("Уже пробовал: Подключитесь к интернету с телефона");
  });

  it("sends dangerous topics straight to a specialist", async () => {
    server.use(http.get("*/api/self-help", () => HttpResponse.json({
      query: "ввёл пароль на странном сайте", code: null, guide: null, document: null,
      specialist_only: true, notice: "Отключите компьютер от сети. С этим сразу к специалисту.",
    })));
    const user = userEvent.setup();
    renderPage();
    await user.type(await screen.findByRole("searchbox", { name: /Код ошибки или что не работает/ }), "ввёл пароль");
    await user.click(screen.getByRole("button", { name: "Найти" }));

    expect(await screen.findByText(/Отключите компьютер от сети/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Создать обращение/ })).toBeInTheDocument();
  });

  it("offers popular codes and topics as one tap", async () => {
    server.use(
      http.get("*/api/self-help/popular", () => HttpResponse.json({
        codes: [{ code: "691", title: "VPN не принимает логин или пароль" }],
        topics: [{ title: "Не печатает принтер", query: "принтер не печатает" }],
      })),
      http.get("*/api/self-help", ({ request }) => HttpResponse.json({
        ...VPN_809, query: new URL(request.url).searchParams.get("q"),
      })),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /691/ }));

    expect(await screen.findByRole("heading", { name: /Ошибка 809 — Сеть не пропускает VPN/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Не печатает принтер" })).toBeInTheDocument();
  });

  it("shows the status of services with known outages", async () => {
    server.use(http.get("*/api/known-issues", () => HttpResponse.json([
      { id: "i1", service: "VPN", since: "2026-10-01T09:00:00Z", affected: 5, update: "Меняем сертификат" },
    ])));
    renderPage();

    const status = await screen.findByRole("region", { name: "Статус сервисов" });
    expect(await within(status).findByText(/VPN/)).toBeInTheDocument();
    expect(within(status).getByText(/Сбой — уже чиним/)).toBeInTheDocument();
    expect(within(status).getAllByText(/Нет известных сбоев/).length).toBeGreaterThan(3);
  });
});
