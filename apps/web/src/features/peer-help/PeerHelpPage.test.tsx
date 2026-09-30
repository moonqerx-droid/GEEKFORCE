import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server";
import { renderAs } from "../../test/render";
import { PeerHelpPage } from "./PeerHelpPage";
import { ELENA, ME, makePeerHelp } from "./fixtures";

describe("Помощь коллег", () => {
  it("shows colleagues' requests and lets me take one", async () => {
    const open = makePeerHelp();
    server.use(
      http.get("*/api/peer-help", () => HttpResponse.json([open])),
      http.post("*/api/peer-help/peer-1/claim", () =>
        HttpResponse.json(makePeerHelp({ status: "HELPING", helper: ME }))),
    );
    renderAs(<PeerHelpPage />, undefined, "/employee/peers");

    const card = await screen.findByRole("article", { name: /портал не открывается/ });
    expect(within(card).getByText("Елена Соколова")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Помогу" }));

    expect(await screen.findByRole("region", { name: "Чат с коллегой" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Помог совет коллеги" })).not.toBeInTheDocument();
  });

  it("explains why a message with a password was not sent", async () => {
    server.use(
      http.get("*/api/peer-help", () => HttpResponse.json([makePeerHelp({ status: "HELPING", helper: ME })])),
      http.get("*/api/peer-help/peer-1", () => HttpResponse.json(makePeerHelp({ status: "HELPING", helper: ME }))),
      http.post("*/api/peer-help/peer-1/messages", () => HttpResponse.json(
        { detail: { code: "secret_detected", message: "Не отправляйте пароли, коды или токены." } },
        { status: 422 },
      )),
    );
    renderAs(<PeerHelpPage />, undefined, "/employee/peers");

    await userEvent.click(await screen.findByRole("button", { name: "Открыть чат" }));
    await userEvent.type(await screen.findByLabelText("Сообщение коллеге"), "пароль: qwerty123");
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Не отправляйте пароли");
    expect(screen.getByLabelText("Сообщение коллеге")).toHaveValue("пароль: qwerty123");
  });

  it("says so when the feed is empty", async () => {
    server.use(http.get("*/api/peer-help", () => HttpResponse.json([])));
    renderAs(<PeerHelpPage />, undefined, "/employee/peers");

    expect(await screen.findByText(/Сейчас никто не просит помощи/)).toBeInTheDocument();
  });

  it("shows who is already helping", async () => {
    server.use(http.get("*/api/peer-help", () =>
      HttpResponse.json([makePeerHelp({ status: "HELPING", author: ELENA, helper: { ...ELENA, id: "x", name: "Ольга Морозова" } })])));
    renderAs(<PeerHelpPage />, undefined, "/employee/peers");

    expect(await screen.findByText("Помогает: Ольга Морозова")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Помогу" })).not.toBeInTheDocument();
  });
});
